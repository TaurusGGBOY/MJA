"""Supervise diagnostic children, or retain a child exit signal locally."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.custom.support.crash_evidence import capture, emit, preserve_host_reports


class RotatingStream:
    """Keep exact logcat bytes, including lines split across pipe reads."""

    def __init__(self, path: Path, limit: int = 8 * 1024 * 1024):
        self.path = path
        self.limit = limit
        self.stream = path.open("ab")

    def write(self, block: bytes) -> None:
        if self.stream.tell() + len(block) > self.limit:
            self.stream.close()
            self.path.with_name(self.path.name + ".4").unlink(missing_ok=True)
            for index in range(3, 0, -1):
                source = self.path.with_name(self.path.name + f".{index}")
                if source.exists():
                    source.rename(self.path.with_name(self.path.name + f".{index + 1}"))
            self.path.rename(self.path.with_name(self.path.name + ".1"))
            self.stream = self.path.open("ab")
        self.stream.write(block)
        self.stream.flush()

    def close(self) -> None:
        self.stream.close()


def process_presence(probe: subprocess.CompletedProcess) -> bool | None:
    if probe.returncode == 0:
        pids = probe.stdout.split()
        return True if pids and all(pid.isdigit() for pid in pids) else None
    if probe.returncode == 1 and not probe.stdout.strip() and not probe.stderr.strip():
        return False
    return None


def prepare(candidate: Path) -> Path:
    candidate = candidate.resolve()
    supplied = os.environ.get("MJA_ACCEPTANCE_TICKET")
    tickets = (
        [Path(supplied)]
        if supplied
        else sorted(
            (candidate / "debug/acceptance").glob("*/*/ticket.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    )
    base = candidate / "debug/observability"
    for ticket in tickets:
        try:
            value = json.loads(ticket.read_text())
            if Path(value["candidate"]).resolve() != candidate:
                continue
            if not supplied and (
                time.time() - ticket.stat().st_mtime > 3600
                or (ticket.parent / "acceptance.json").exists()
            ):
                continue
            base = ticket.parent / "observability"
            break
        except (OSError, ValueError, KeyError):
            continue
    # Separate launches under one ticket so retries cannot overwrite evidence.
    root = base / f"launch-{time.time_ns()}"
    root.mkdir(parents=True, mode=0o700)
    return root


def supervise(command: list[str]) -> int:
    started = time.time()
    child = subprocess.Popen(command)
    emit("host_process_started", child_pid=child.pid, command=command)

    def forward(signum, _frame):
        emit("host_stop_requested", child_pid=child.pid, signal=signum)
        child.send_signal(signum)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, forward)
    code = child.wait()
    emit(
        "host_process_exited",
        child_pid=child.pid,
        returncode=code,
        signal=-code if code < 0 else None,
    )
    if code != 0 and os.environ.get("MJA_CRASH_EVIDENCE_DIR"):
        try:
            preserve_host_reports(Path(os.environ["MJA_CRASH_EVIDENCE_DIR"]), started)
        except Exception as exc:
            emit("host_reports_error", error=str(exc))
    return code if code >= 0 else 128 - code


def observe(parent: int) -> None:
    root = Path(os.environ["MJA_CRASH_EVIDENCE_DIR"])
    root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    stop = False

    def stopping(_signum, _frame):
        nonlocal stop
        stop = True

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, stopping)
    adb = [os.environ["MJA_ANDROID_ADB"], "-s", os.environ["MJA_ANDROID_SERIAL"]]
    stream = RotatingStream(root / "android.log")
    emit(
        "observer_started",
        launcher_pid=parent,
        candidate=os.environ.get("MJA_MFW_CANDIDATE"),
        serial=os.environ["MJA_ANDROID_SERIAL"],
    )
    pending_capture = None
    try:
        # Version output stays local; failures and missing tools stay explicit.
        candidate = Path(os.environ["MJA_MFW_CANDIDATE"])
        metadata = [
            ("game-version.txt", adb + ["shell", "dumpsys", "package", "com.hanjiasongshu.dr22"]),
            ("device-properties.txt", adb + ["shell", "getprop"]),
            ("guest-clock.txt", adb + ["shell", "date", "+%s"]),
            ("launcher-process.txt", ["ps", "-p", str(parent), "-o", "pid,ppid,command"]),
        ]
        libraries = list((candidate / "maafw").glob("*.dylib"))
        sdk = Path(os.environ["MJA_ANDROID_ADB"]).parent.parent
        libraries += [sdk / "emulator/lib64/libgfxstream_backend.dylib"]
        libraries += [candidate / "MFW", sdk / "emulator/qemu/darwin-aarch64/qemu-system-aarch64"]
        for index, library in enumerate(libraries):
            metadata.append((f"binary-{index}-uuid.txt", ["dwarfdump", "--uuid", str(library)]))
        for name, command in metadata:
            if stop:
                break
            try:
                with (root / name).open("wb") as output:
                    result = subprocess.run(
                        command, stdout=output, stderr=subprocess.STDOUT, timeout=2, check=False
                    )
                emit("runtime_metadata", artifact=name, returncode=result.returncode)
            except (OSError, subprocess.TimeoutExpired) as exc:
                emit("runtime_metadata_missing", artifact=name, error=str(exc))
        last_process = None
        probe_at = 0.0
        reports_at = 0.0
        while not stop:
            try:
                os.kill(parent, 0)
            except ProcessLookupError:
                break
            child = subprocess.Popen(
                adb
                + ["logcat", "-b", "crash", "-b", "main", "-b", "system", "-v", "epoch", "-T", "1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            emit("logcat_connected", child_pid=child.pid)
            selector = selectors.DefaultSelector()
            selector.register(child.stdout, selectors.EVENT_READ)
            previous_tail = b""
            try:
                while not stop:
                    try:
                        os.kill(parent, 0)
                    except ProcessLookupError:
                        stop = True
                        break
                    if time.monotonic() >= probe_at:
                        probe_at = time.monotonic() + 5
                        try:
                            probe = subprocess.run(
                                adb + ["shell", "pidof", "com.hanjiasongshu.dr22"],
                                capture_output=True,
                                timeout=0.5,
                            )
                            # A transport failure is unknown, not a process exit.
                            present = process_presence(probe)
                            if present is None:
                                emit(
                                    "process_probe_unavailable",
                                    returncode=probe.returncode,
                                    error=probe.stderr.decode(errors="replace")[:1000],
                                )
                            if present is not None and present != last_process:
                                emit(
                                    "game_process_observed",
                                    present=present,
                                    previous=last_process,
                                    game_pid=probe.stdout.decode(errors="replace").strip(),
                                )
                                if (
                                    last_process is True
                                    and present is False
                                    and (
                                        pending_capture is None
                                        or pending_capture.poll() is not None
                                    )
                                ):
                                    pending_capture = subprocess.Popen(
                                        [
                                            sys.executable,
                                            __file__,
                                            "--capture",
                                            "game_process_disappeared",
                                        ],
                                        stdin=subprocess.DEVNULL,
                                    )
                                last_process = present
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            emit("process_probe_unavailable", error=str(exc))
                    if time.monotonic() >= reports_at:
                        reports_at = time.monotonic() + 15
                        try:
                            preserve_host_reports(root, started, budget=0.25)
                        except Exception as exc:
                            emit("host_reports_error", error=str(exc))
                    stream_closed = False
                    for key, _ in selector.select(timeout=0.5):
                        block = os.read(key.fd, 8192)
                        if block:
                            stream.write(block)
                            detection = previous_tail + block
                            previous_tail = block[-128:]
                            if b"Fatal signal" in detection or b"FATAL EXCEPTION" in detection:
                                if pending_capture is None or pending_capture.poll() is not None:
                                    pending_capture = subprocess.Popen(
                                        [
                                            sys.executable,
                                            __file__,
                                            "--capture",
                                            "android_fatal_log",
                                        ],
                                        stdin=subprocess.DEVNULL,
                                    )
                        else:
                            stream_closed = True
                    if stream_closed:
                        break
            finally:
                selector.close()
                if child.poll() is None:
                    child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                child.stdout.close()
            if not stop:
                emit("logcat_disconnected", returncode=child.returncode)
                time.sleep(1)
    finally:
        if pending_capture is not None:
            try:
                pending_capture.wait(timeout=7)
            except subprocess.TimeoutExpired:
                pending_capture.terminate()
                pending_capture.wait(timeout=2)
        try:
            preserve_host_reports(root, started)
        except Exception as exc:
            emit("host_reports_error", error=str(exc))
        stream.close()
        emit("observer_stopped")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=int)
    parser.add_argument("--capture")
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--record-mfw-exit", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.record_mfw_exit:
        emit("mfw_process_exited", shell_wait_status=int(os.environ["MJA_OBSERVED_EXIT"]))
        return 0
    if args.prepare:
        print(prepare(args.prepare))
        return 0
    if args.capture:
        capture(args.capture)
        return 0
    if args.parent:
        observe(args.parent)
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return supervise(command)


if __name__ == "__main__":
    raise SystemExit(main())
