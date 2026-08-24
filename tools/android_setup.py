from __future__ import annotations

import argparse
import json
import sys

from agent.android.avd import AndroidAvd
from agent.android.config import AndroidConfig
from agent.android.sdk import AndroidSdk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install and verify the MJA Android runtime")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify tools without installing")
    mode.add_argument("--install", action="store_true", help="install missing tools and AVD")
    parser.add_argument("--wipe-data", action="store_true")
    parser.add_argument("--print-env", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = AndroidConfig.load()
        install = args.install
        sdk = AndroidSdk(config)
        paths = sdk.ensure(install_missing=install)
        avd = AndroidAvd(config, paths)
        avd.ensure()
        if args.print_env:
            payload = {
                "sdk_root": str(paths.root),
                "adb": str(paths.adb),
                "emulator": str(paths.emulator),
                "avd": config.avd_name,
            }
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"Android runtime {'installed' if install else 'verified'}: {config.avd_name}")
        return 0
    except Exception as exc:
        code = getattr(getattr(exc, "code", None), "value", "ANDROID_SETUP_FAILED")
        print(f"ERROR: {code}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
