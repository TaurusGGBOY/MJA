"""Capture a manually prepared, read-only MFW screenshot fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tools.capture_templates import TRUE_1280_CALIBRATION

CASES = frozenset({"not_eligible", "known_drift"})
CONTROLLERS = frozenset({"android"})


def _task_key(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be non-empty")
    key = task_id.strip().upper()
    if key not in TASK_POLICIES:
        raise ValueError(f"unknown task: {key}")
    return key


def fixture_destination(root: Path, task_id: str, case: str) -> Path:
    key = _task_key(task_id)
    if case not in CASES:
        raise ValueError(f"case must be one of {sorted(CASES)}")
    return Path(root) / key / f"{case}.png"


def require_new_fixture_path(path: Path) -> Path:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"fixture already exists: {target}")
    return target


def capture_fixture(
    task_id: str,
    case: str,
    *,
    root: Path = Path("tests/fixtures"),
    config_path: Path | None = None,
    controller: str = "android",
) -> Path:
    destination = require_new_fixture_path(fixture_destination(root, task_id, case))
    backend = controller.strip().lower() if isinstance(controller, str) else ""
    if backend not in CONTROLLERS:
        raise ValueError(f"controller must be one of {sorted(CONTROLLERS)}")

    from agent.android.adb import AdbDevice
    from agent.android.config import AndroidConfig
    from agent.android.sdk import AndroidSdk

    config = AndroidConfig.load(config_path or Path("config/android.json"))
    sdk = AndroidSdk(config).ensure(install_missing=False)
    device = AdbDevice(config, sdk)
    size = device.screencap(destination)
    if size != TRUE_1280_CALIBRATION.maa_capture_size:
        raise ValueError(f"fixture must be 1280x720, got {size[0]}x{size[1]}")
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True, help="canonical task ID")
    parser.add_argument("--case", required=True, choices=sorted(CASES))
    parser.add_argument("--root", type=Path, default=Path("tests/fixtures"))
    parser.add_argument(
        "--controller",
        choices=sorted(CONTROLLERS),
        default="android",
        help="capture backend; only the Android emulator is supported",
    )
    parser.add_argument("--config", type=Path, default=Path("config/android.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    destination = capture_fixture(
        args.task_id,
        args.case,
        root=args.root,
        config_path=args.config,
        controller=args.controller,
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CASES",
    "CONTROLLERS",
    "capture_fixture",
    "fixture_destination",
    "main",
    "require_new_fixture_path",
]
