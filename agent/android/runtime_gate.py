"""Read-only Android runtime checks used by the Maa daily aggregate."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from agent.errors import ErrorCode, MJAError

from .adb import AdbDevice
from .config import AndroidConfig
from .sdk import AndroidSdk


@dataclass(frozen=True, slots=True)
class AndroidRuntimeGate:
    """Expose safe runtime preconditions without sending game input.

    The Android launcher is not a recoverable workflow surface.  This gate
    therefore observes the foreground package and fails closed; it never
    calls ``start_app``.  The normal Android runner remains responsible for
    starting the game and completing the login gate before Maa is launched.
    """

    device: AdbDevice
    package_name: str

    @classmethod
    def from_environment(cls) -> "AndroidRuntimeGate":
        config = AndroidConfig.load()
        serial = os.environ.get("MJA_ANDROID_SERIAL")
        if serial:
            config = replace(config, serial=serial)
        sdk_root = os.environ.get("MJA_ANDROID_SDK_ROOT")
        if sdk_root:
            config = replace(config, sdk_root=Path(sdk_root))
        package_name = os.environ.get("MJA_ANDROID_PACKAGE") or config.package_name
        if not package_name:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                "package_name is required for the Android runtime gate",
            )
        if config.package_name != package_name:
            config = replace(config, package_name=package_name)

        paths = AndroidSdk(config).discover()
        if paths is None:
            raise MJAError(
                ErrorCode.ANDROID_SDK_UNAVAILABLE,
                "Android SDK command-line tools are unavailable for the runtime gate",
            )
        adb_override = os.environ.get("MJA_ANDROID_ADB")
        if adb_override:
            paths = replace(paths, adb=Path(adb_override))
        return cls(AdbDevice(config, paths), package_name)

    def require_health(self) -> None:
        """Run the existing fail-closed Android health check."""

        self.device.require_runtime_health()

    def require_foreground(self) -> None:
        """Require the configured game package to own the foreground window."""

        foreground = self.device.foreground_package()
        if foreground != self.package_name:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                f"expected {self.package_name} in the foreground, got {foreground or 'none'}",
            )


__all__ = ["AndroidRuntimeGate"]
