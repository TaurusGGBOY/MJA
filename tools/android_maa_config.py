"""Android-only MaaPiCli configuration shared by the runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any

CLI_COMMAND = ["./MaaPiCli", "-d"]


def build_android_maa_config(
    adb_path: Path,
    serial: str,
    task_name: str,
) -> dict[str, Any]:
    """Build the canonical Android ADB controller configuration."""

    return {
        "controller": {"name": "android"},
        "adb": {
            "name": serial,
            "adb_path": str(adb_path),
            "address": serial,
        },
        "resource": "mja_android",
        "task": [{"name": task_name}],
    }


__all__ = ["CLI_COMMAND", "build_android_maa_config"]
