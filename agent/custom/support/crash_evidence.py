"""Local diagnostic evidence; never decides or replaces native task outcomes."""

from __future__ import annotations

import getpass
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)
PACKAGE = "com.hanjiasongshu.dr22"


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
