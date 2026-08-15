from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from agent.android.adb import AdbDevice
from agent.android.config import DEFAULT_CONFIG_PATH, ROOT, AndroidConfig
from agent.errors import ErrorCode, MJAError

ALLOWED_APK_ROOTS = ((ROOT / "artifacts").resolve(), (ROOT / "install").resolve())


class GameInstaller:
    def __init__(
        self,
        config: AndroidConfig,
        device: AdbDevice,
        *,
        config_path: Path = DEFAULT_CONFIG_PATH,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        notify: Callable[[str], None] = print,
    ) -> None:
        self.config = config
        self.device = device
        self.config_path = config_path
        self.sleeper = sleeper
        self.clock = clock
        self.notify = notify

    def ensure_installed(self) -> str:
        if self.config.package_name and self.device.package_installed(self.config.package_name):
            return self.config.package_name
        if self.config.apk_path is not None:
            return self.install_apk(self.config.apk_path)
        raise MJAError(
            ErrorCode.ANDROID_INSTALL_FAILED,
            "Android game APK is required; set apk_path in config/android.json. "
            "Google Play installation is disabled.",
        )

    def install_apk(self, path: Path) -> str:
        path = path.resolve()
        if not path.is_file() or path.suffix.lower() != ".apk":
            raise MJAError(ErrorCode.ANDROID_INSTALL_FAILED, f"APK does not exist: {path}")
        if not any(root == path or root in path.parents for root in ALLOWED_APK_ROOTS):
            raise MJAError(
                ErrorCode.ANDROID_INSTALL_FAILED,
                f"APK path is outside allowed roots: {path}",
            )
        before = self.device.list_packages()
        self.device.install(path)
        if self.config.package_name and self.device.package_installed(self.config.package_name):
            return self.config.package_name
        installed = self.device.list_packages() - before
        if len(installed) != 1:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                "APK installed but package_name is not configured and exactly one "
                "new package was not found",
            )
        package_name = installed.pop()
        self._persist_package_name(package_name)
        return package_name

    def _persist_package_name(self, package_name: str) -> None:
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        payload["package_name"] = package_name
        temporary = self.config_path.with_name(f".{self.config_path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.config_path)


__all__ = ["GameInstaller"]
