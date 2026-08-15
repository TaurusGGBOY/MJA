from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.android.adb import AdbDevice
from agent.android.config import AndroidConfig
from agent.android.sdk import AndroidSdk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check and capture the MJA Android device")
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args(argv)
    config = AndroidConfig.load()
    paths = AndroidSdk(config).ensure()
    device = AdbDevice(config, paths)
    info = device.wait_ready()
    device.require_runtime_health()
    payload = {"serial": info.serial, "width": info.width, "height": info.height, "sdk": info.sdk}
    if args.capture:
        device.screencap(args.capture)
        payload["capture"] = str(args.capture)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
