from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

from agent.custom.support import crash_evidence as evidence
from tools.mfw_crash_report import report
from tools.mfw_observe_runtime import RotatingStream, prepare, process_presence

ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "tools/mfw_observe_runtime.py"


def records(root):
    return [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]


def test_disabled_collection_has_no_side_effects(monkeypatch, tmp_path):
    monkeypatch.delenv("MJA_CRASH_EVIDENCE_DIR", raising=False)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("ADB called"))
    )
    evidence.capture("disabled")
    assert not list(tmp_path.iterdir())


def test_disconnected_adb_is_unknown_not_process_exit():
    assert process_presence(subprocess.CompletedProcess([], 1, b"", b"device offline")) is None
    assert process_presence(subprocess.CompletedProcess([], 0, b"unexpected output", b"")) is None
    assert process_presence(subprocess.CompletedProcess([], 1, b"", b"")) is False
    assert process_presence(subprocess.CompletedProcess([], 0, b"123 456\n", b"")) is True


def test_capture_timeout_is_shared_and_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setenv("MJA_CRASH_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("MJA_ANDROID_ADB", sys.executable)
    monkeypatch.setenv("MJA_ANDROID_SERIAL", "test-device")
    calls = []

    def timeout(command, **kwargs):
        calls.append(command)
        time.sleep(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    start = time.monotonic()
    evidence.capture("test", budget=0.05)
    assert time.monotonic() - start < 0.5
    assert len(calls) == 1
    assert calls[0][1:3] == ["-s", "test-device"]
    assert any(r["event"] == "capture_timeout" for r in records(tmp_path))
    assert any(r["event"] == "capture_skipped" for r in records(tmp_path))


def test_permission_denial_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("MJA_CRASH_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("MJA_ANDROID_ADB", "adb-test")
    monkeypatch.setenv("MJA_ANDROID_SERIAL", "selected-device")

    def denied(command, **kwargs):
        kwargs["stderr"].write(b"Permission denied")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(subprocess, "run", denied)
    evidence.capture("denied")
    commands = [r for r in records(tmp_path) if r["event"] == "capture_command"]
    assert len(commands) == 6
    assert all(r["returncode"] == 1 for r in commands)


def test_ticket_association_and_retry_isolation(tmp_path, monkeypatch):
    monkeypatch.delenv("MJA_ACCEPTANCE_TICKET", raising=False)
    candidate = tmp_path / "candidate"
    ticket = candidate / "debug/acceptance/BATCH/run/ticket.json"
    ticket.parent.mkdir(parents=True)
    ticket.write_text(json.dumps({"candidate": str(candidate)}))
    first, second = prepare(candidate), prepare(candidate)
    assert first != second
    assert first.parent == ticket.parent / "observability"
    (ticket.parent / "acceptance.json").write_text("{}")
    assert prepare(candidate).parent == candidate / "debug/observability"


def test_signal_exit_is_captured_for_isolated_child(tmp_path):
    env = os.environ | {"MJA_CRASH_EVIDENCE_DIR": str(tmp_path)}
    run = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "--",
            sys.executable,
            "-c",
            "import os,signal; os.kill(os.getpid(),signal.SIGTERM)",
        ],
        env=env,
        capture_output=True,
        timeout=10,
    )
    assert run.returncode == 128 + signal.SIGTERM
    exited = next(r for r in records(tmp_path) if r["event"] == "host_process_exited")
    assert exited["returncode"] == -signal.SIGTERM
    assert exited["signal"] == signal.SIGTERM


def test_image_measurement_is_diagnostic_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MJA_CRASH_EVIDENCE_DIR", str(tmp_path))
    path = tmp_path / "frame.png"
    Image.new("RGB", (16, 16), (255, 0, 255)).save(path)
    evidence.inspect_image(path)
    row = records(tmp_path)[-1]
    assert row["magenta_fraction"] == 1.0
    assert "native_terminal" not in row


def test_report_does_not_invent_crash_pc(tmp_path):
    (tmp_path / "events.jsonl").write_text('{"event":"game_process_absent"}\ntruncated')
    text = report(tmp_path).read_text()
    assert "Incomplete diagnostic record" in text
    assert "fault PC, registers and causal instruction remain unverified" in text


def test_rotation_keeps_exact_split_utf8_bytes(tmp_path):
    path = tmp_path / "android.log"
    stream = RotatingStream(path, limit=16)
    content = "崩溃线程\n".encode()
    stream.write(content[:2])
    stream.write(content[2:])
    stream.write(b"next line\n")
    stream.close()
    assert (tmp_path / "android.log.1").read_bytes() + path.read_bytes() == content + b"next line\n"


def test_missing_debugger_is_reported(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("lldb unavailable")

    monkeypatch.setattr(subprocess, "run", missing)
    text = report(tmp_path, tmp_path / "binary", address=0x10).read_text()
    assert "LLDB unavailable/incomplete" in text
    assert "STATIC disassembly only" in text


def test_observer_rotates_stream_and_stops_children(tmp_path):
    adb = tmp_path / "adb"
    adb.write_text(
        f"#!{sys.executable}\n"
        + """
import sys,time,os
if 'logcat' in sys.argv:
    print('stream-pid='+str(os.getpid()), flush=True)
    for _ in range(1200):
        sys.stdout.write('x'*8192+'\\n')
    sys.stdout.flush()
    time.sleep(30)
elif 'pidof' in sys.argv:
    print('12345')
else:
    print('diagnostic metadata')
"""
    )
    adb.chmod(0o755)
    root = tmp_path / "evidence"
    env = os.environ | {
        "MJA_CRASH_EVIDENCE_DIR": str(root),
        "MJA_ANDROID_ADB": str(adb),
        "MJA_ANDROID_SERIAL": "test-device",
        "MJA_MFW_CANDIDATE": str(tmp_path),
    }
    child = subprocess.Popen(
        [sys.executable, str(OBSERVER), "--parent", str(os.getpid())],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (root / "android.log.1").exists():
            time.sleep(0.05)
        assert (root / "android.log.1").exists()
        child.terminate()
        assert child.wait(timeout=12) == 0
        rows = records(root)
        pid = next(r["child_pid"] for r in rows if r["event"] == "logcat_connected")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("observer left its logcat child running")
        assert rows[-1]["event"] == "observer_stopped"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
