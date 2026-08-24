"""Apply the Android runtime contract before a direct MFW run.

The regular Android runner performs these checks before handing the device to
Maa.  Direct MFW batch runs must use the same contract, but cannot require the
game to be foreground yet because GAME_START is responsible for that.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

# ``python tools/mfw_android_preflight.py`` puts ``tools/`` at sys.path[0].
# Add the project root so the same direct command works outside pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
try:
    sys.path.remove(str(PROJECT_ROOT))
except ValueError:
    pass
sys.path.insert(0, str(PROJECT_ROOT))

from agent.android.adb import AdbDevice
from agent.android.config import DEFAULT_CONFIG_PATH, AndroidConfig
from agent.android.sdk import AndroidSdk
from agent.errors import MJAError
from tools.android_emulator_contract import verify_emulator_contract


def run_preflight(
    config: AndroidConfig,
    *,
    sdk_factory: Callable[[AndroidConfig], Any] = AndroidSdk,
    device_factory: Callable[[AndroidConfig, Any], Any] = AdbDevice,
    emulator_contract: Callable[[AndroidConfig], dict[str, str]] = verify_emulator_contract,
) -> dict[str, Any]:
    """Verify and repair shared emulator state without sending game input."""

    paths = sdk_factory(config).ensure()
    device = device_factory(config, paths)
    info = device.wait_ready()
    phantom_process_monitor = device.ensure_phantom_process_monitor_disabled()
    selinux = device.ensure_selinux_mode(config.selinux_mode)
    memory_health = getattr(device, "require_memory_health", None)
    memory = memory_health() if callable(memory_health) else None
    emulator = emulator_contract(config)
    sdk_version = getattr(info, "sdk", getattr(info, "sdk_version", ""))
    result: dict[str, Any] = {
        "serial": str(getattr(info, "serial", config.serial)),
        "display": f"{getattr(info, 'width', 0)}x{getattr(info, 'height', 0)}",
        "sdk_version": str(sdk_version),
        "phantom_process_monitor": str(phantom_process_monitor),
        "selinux": str(selinux),
        **emulator,
    }
    if memory is not None:
        for field in (
            "total_bytes",
            "available_bytes",
            "swap_total_bytes",
            "swap_free_bytes",
        ):
            if hasattr(memory, field):
                result[f"memory_{field}"] = int(getattr(memory, field))
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply the Android runtime contract before a direct MFW run."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Android JSON config path (default: config/android.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="atomically write the preflight result JSON",
    )
    return parser.parse_args()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = _parse_args()
    try:
        result = run_preflight(AndroidConfig.load(args.config))
    except MJAError as exc:
        payload = {"status": "failed", **exc.as_dict()}
        if args.output is not None:
            _write_json_atomic(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        payload = {
            "status": "failed",
            "code": "MFW_PREFLIGHT_FAILED",
            "message": str(exc),
        }
        if args.output is not None:
            _write_json_atomic(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1

    payload = {"status": "ok", **result}
    if args.output is not None:
        _write_json_atomic(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the shell entrypoint
    raise SystemExit(main())


__all__ = ["main", "run_preflight"]
