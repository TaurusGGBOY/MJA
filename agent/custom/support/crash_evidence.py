"""Local diagnostic evidence; never decides or replaces native task outcomes."""

from __future__ import annotations

import getpass
import io
import json
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)
PACKAGE = "com.hanjiasongshu.dr22"
REQUEST_LOG_HINTS = {
    "dns": re.compile(r"UnknownHostException|EAI_AGAIN|EAI_NONAME", re.I),
    "timeout": re.compile(r"SocketTimeoutException|ETIMEDOUT|connection timed out", re.I),
    "connection": re.compile(r"ECONNREFUSED|ECONNRESET|connection refused|connection reset", re.I),
    "tls": re.compile(r"SSLHandshakeException|certificate verify failed|TLS handshake failed", re.I),
    "http_5xx": re.compile(r"(?:HTTP/[0-9.]+ |HTTP status[ :]+)5[0-9]{2}\b", re.I),
}


def _container_game_tcp_evidence(container: str) -> list[dict]:
    """Read the Redroid namespace's game sockets without saving peer addresses."""
    pid = subprocess.run(
        ["sudo", "-n", "docker", "inspect", "--format={{.State.Pid}}", "--", container],
        capture_output=True, text=True, timeout=1, check=True,
    ).stdout.strip()
    if not pid.isdecimal() or int(pid) <= 1:
        return []
    sockets = subprocess.run(
        ["sudo", "-n", "nsenter", "--target", pid, "--net", "ss", "-HOntiope"],
        capture_output=True, text=True, timeout=1, check=True,
    ).stdout.splitlines()
    summaries = []
    for line in sockets:
        if PACKAGE[-15:] not in line:
            continue
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or not fields[2].isdecimal():
            continue
        retransmits = re.search(r"\bretrans:([\d/]+)", fields[5])
        summaries.append({
            "state": fields[0],
            "send_queue_bytes": int(fields[2]),
            "peer_port": fields[4].rsplit(":", 1)[-1],
            "retransmits": retransmits[1] if retransmits else None,
        })
    return summaries


def capture_request_error(argv) -> None:
    """Preserve the recognized error and app transport hints before recovery."""
    root = os.environ.get("MJA_DEBUG_DIR")
    if not root:
        return
    try:
        from PIL import Image

        now = datetime.now(timezone.utc)
        output = Path(root) / "request-errors" / now.strftime("%Y%m%dT%H%M%S%fZ")
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
        event = {
            "time_utc": now.isoformat(),
            "task_id": getattr(getattr(argv, "task_detail", None), "task_id", None),
            "node": argv.node_name,
            "ocr_box": argv.box,
        }
        adb = os.environ.get("MJA_ANDROID_ADB")
        serial = os.environ.get("MJA_ANDROID_SERIAL")
        try:
            if not adb or not serial:
                raise ValueError("launcher did not supply ADB and serial")
            prefix = [adb, "-s", serial]
            screenshot = subprocess.run(
                prefix + ["exec-out", "screencap", "-p"], capture_output=True, timeout=2, check=True,
            )
            with Image.open(io.BytesIO(screenshot.stdout)) as image:
                # Crop to the centered modal so the account overlay and HUD are omitted.
                width, height = image.size
                image.crop((width * 260 // 1280, height * 165 // 720,
                            width * 1010 // 1280, height * 560 // 720)).save(output / "popup.png")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            event["screenshot_error"] = type(error).__name__

        if adb and serial:
            try:
                pid = subprocess.run(
                    prefix + ["shell", "pidof", PACKAGE], capture_output=True, text=True, timeout=1,
                ).stdout.strip().split()
                if pid and pid[0].isdecimal():
                    log = subprocess.run(
                        prefix + ["logcat", "-d", "--pid", pid[0], "-t", "300", "-v", "epoch"],
                        capture_output=True, text=True, timeout=1.5, check=True,
                    ).stdout.splitlines()
                    event["android_pid"] = int(pid[0])
                    event["app_log_lines"] = len(log)
                    event["transport_hints"] = {
                        name: sum(bool(pattern.search(line)) for line in log)
                        for name, pattern in REQUEST_LOG_HINTS.items()
                    }
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                event["app_log_error"] = type(error).__name__
        if container := os.environ.get("MJA_ANDROID_CONTAINER"):
            try:
                event["game_tcp_sockets"] = _container_game_tcp_evidence(container)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                event["socket_error"] = type(error).__name__
        (output / "request.json").write_text(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        LOG.warning("Could not preserve game request error", exc_info=True)


def emit(event: str, **detail) -> None:
    """Append one correlation record, without raising into the task runner."""
    try:
        root = os.environ.get("MJA_CRASH_EVIDENCE_DIR")
        if not root:
            return
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        record = dict(
            time=datetime.now(timezone.utc).isoformat(),
            monotonic=time.monotonic(),
            pid=os.getpid(),
            event=event,
            **detail,
        )
        # One append/write per event, including across embedded agent processes.
        with (path / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        LOG.warning("Could not save diagnostic event", exc_info=True)


def capture(reason: str, *, budget: float = 6.0, **detail) -> None:
    """Best effort, shared wall-clock budget before any destructive recovery.

    Read-only ADB commands use the exact launcher-selected serial. Missing
    privileges are evidence, never a reason to root/restart adbd.
    """
    root = os.environ.get("MJA_CRASH_EVIDENCE_DIR")
    if not root:
        return
    emit("capture_requested", reason=reason, **detail)
    try:
        deadline = time.monotonic() + budget
        folder = Path(root) / datetime.now(timezone.utc).strftime("capture-%Y%m%dT%H%M%S%fZ")
        folder.mkdir(parents=True, exist_ok=False)
        preserve_host_reports(Path(root), time.time() - 300, budget=0.25)
        adb = os.environ.get("MJA_ANDROID_ADB")
        serial = os.environ.get("MJA_ANDROID_SERIAL")
        if not adb or not serial:
            emit("capture_unavailable", reason="explicit ADB and serial required")
            return
        commands = [
            ("process.txt", ["shell", "pidof", PACKAGE]),
            ("crash-logcat.txt", ["logcat", "-b", "crash", "-d", "-t", "300", "-v", "epoch"]),
            ("exit-info.txt", ["shell", "dumpsys", "activity", "exit-info", PACKAGE]),
            ("screenshot.png", ["exec-out", "screencap", "-p"]),
            ("tombstones.txt", ["shell", "ls", "-lt", "/data/tombstones"]),
            # exec-out can merge remote stderr into stdout. Relative members
            # avoid tar's leading-slash warning corrupting the binary stream.
            ("tombstones.tar", ["exec-out", "tar", "-C", "/data", "-c", "tombstones"]),
        ]
        for name, args in commands:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                emit("capture_skipped", artifact=name, reason="shared budget exhausted")
                continue
            try:
                with (
                    (folder / name).open("wb") as output,
                    (folder / (name + ".stderr")).open("wb") as error,
                ):
                    run = subprocess.run(
                        [adb, "-s", serial, *args],
                        stdout=output,
                        stderr=error,
                        timeout=min(1.0, remaining),
                        check=False,
                    )
                emit("capture_command", artifact=str(folder / name), returncode=run.returncode)
                if name == "screenshot.png" and run.returncode == 0:
                    inspect_image(folder / name)
            except subprocess.TimeoutExpired:
                emit("capture_timeout", artifact=name)
        emit("capture_finished", directory=str(folder), reason=reason, **detail)
    except Exception:
        LOG.warning("Crash evidence collection failed", exc_info=True)
        emit("capture_error", reason=reason)


def inspect_image(path: Path) -> None:
    """Record a color measurement, not a rendering verdict or task gate."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            size = image.size
            image.thumbnail((160, 90))
            pixels = list(image.convert("RGB").get_flattened_data())
        fraction = sum(r > 240 and g < 20 and b > 240 for r, g, b in pixels) / len(pixels)
        emit("image_measurement", artifact=str(path), size=size, magenta_fraction=fraction)
    except Exception as exc:
        emit("image_measurement_unavailable", artifact=str(path), error=str(exc))


def observe_cached_frame(controller, **detail) -> None:
    """Use only the existing controller frame; never issue a device action."""
    root = os.environ.get("MJA_CRASH_EVIDENCE_DIR")
    if not root:
        return
    try:
        from PIL import Image

        frame = controller.cached_image
        if frame is None:
            emit("cached_frame_unavailable", **detail)
            return
        # Maa cached_image is OpenCV BGR, not RGB.
        image = Image.fromarray(frame[:, :, :3][:, :, ::-1])
        path = Path(root) / f"frame-{time.time_ns()}.png"
        image.save(path)
        emit("cached_frame", artifact=str(path), **detail)
        inspect_image(path)
    except Exception as exc:
        emit("cached_frame_unavailable", error=str(exc), **detail)


def preserve_host_reports(root: Path, since: float, budget: float = 2.0) -> None:
    """Copy new local host reports without changing uploader consent settings."""
    sources = [Path.home() / "Library/Logs/DiagnosticReports"]
    extra = os.environ.get("MJA_EMULATOR_CRASH_DIR")
    sources.append(Path(extra) if extra else Path("/tmp") / f"android-{getpass.getuser()}")
    copied = 0
    total = 0
    deadline = time.monotonic() + budget
    for source in sources:
        if not source.exists():
            emit("host_reports_unavailable", directory=str(source))
            continue
        for path in source.rglob("*"):
            if time.monotonic() >= deadline or copied >= 8:
                emit("host_reports_truncated", reason="scan budget")
                return
            if not path.is_file() or path.suffix not in {".ips", ".dmp"}:
                continue
            if path.stat().st_mtime < since:
                continue
            if total + path.stat().st_size > 128 * 1024 * 1024:
                emit("host_report_skipped", artifact=str(path), reason="128 MiB copy budget")
                continue
            if source == sources[0] and not any(
                x in path.name.lower() for x in ("qemu", "emulator", "mfw", "python")
            ):
                continue
            target = root / "host-reports" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_mtime == path.stat().st_mtime:
                continue
            shutil.copy2(path, target)
            copied += 1
            total += path.stat().st_size
            emit("host_report_preserved", artifact=str(target), source_mtime=path.stat().st_mtime)
