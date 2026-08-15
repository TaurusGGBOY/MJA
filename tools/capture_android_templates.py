from __future__ import annotations

import argparse
from pathlib import Path

from agent.android.adb import AdbDevice
from agent.android.config import AndroidConfig
from agent.android.sdk import AndroidSdk
from tools.capture_templates import ANDROID_IMAGE_ROOT, capture_android_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture MJA templates from an Android emulator")
    parser.add_argument("profile", choices=("home", "panel", "mail"))
    parser.add_argument("--output-root", type=Path, default=ANDROID_IMAGE_ROOT)
    args = parser.parse_args(argv)
    config = AndroidConfig.load()
    paths = AndroidSdk(config).ensure()
    outputs = capture_android_profile(
        args.profile,
        AdbDevice(config, paths),
        args.output_root,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
