from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "android.json"
DISPLAY_SIZE = (1280, 720)
DEFAULT_AVD_NAME = "mja-api35-apis"
DEFAULT_SERIAL = "emulator-5556"
DEFAULT_GAME_LABEL = "对决！剑之川"
DEFAULT_SYSTEM_IMAGE_PACKAGE = "system-images;android-35;google_apis;arm64-v8a"
DEFAULT_SELINUX_MODE = "permissive"
MIN_DATA_PARTITION_SIZE_GB = 12
MIN_AVD_RAM_SIZE_MB = 2_048
DEFAULT_AVD_RAM_SIZE_MB = 6_144
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_SERIAL = re.compile(r"^[A-Za-z0-9._:-]+$")
_SELINUX_MODES = frozenset({"enforcing", "permissive"})


@dataclass(frozen=True)
class AndroidConfig:
    avd_name: str = DEFAULT_AVD_NAME
    serial: str = DEFAULT_SERIAL
    package_name: str | None = None
    game_label: str = DEFAULT_GAME_LABEL
    display_size: tuple[int, int] = DISPLAY_SIZE
    apk_path: Path | None = None
    keep_running: bool = True
    login_timeout_seconds: int = 900
    sdk_root: Path = ROOT / "install" / "android-sdk"
    avd_home: Path | None = None
    avd_ram_size_mb: int = DEFAULT_AVD_RAM_SIZE_MB
    system_image_package: str = DEFAULT_SYSTEM_IMAGE_PACKAGE
    selinux_mode: str = DEFAULT_SELINUX_MODE
    data_partition_size_gb: int = MIN_DATA_PARTITION_SIZE_GB

    def validate(self) -> None:
        if not self.avd_name or not _SAFE_NAME.fullmatch(self.avd_name):
            raise ValueError(
                "avd_name must contain only ASCII letters, digits, dots, dashes, or underscores"
            )
        if not self.serial or not _SAFE_SERIAL.fullmatch(self.serial):
            raise ValueError("serial contains unsupported characters")
        if self.package_name is not None and (
            not self.package_name or not _SAFE_SERIAL.fullmatch(self.package_name)
        ):
            raise ValueError("package_name contains unsupported characters")
        if not self.game_label.strip():
            raise ValueError("game_label must not be empty")
        if tuple(self.display_size) != DISPLAY_SIZE:
            raise ValueError("Android display_size must be exactly 1280x720")
        if self.login_timeout_seconds <= 0:
            raise ValueError("login_timeout_seconds must be positive")
        if not self.sdk_root.is_absolute():
            raise ValueError("sdk_root must be resolved to an absolute path")
        if self.avd_home is not None:
            if not self.avd_home.is_absolute():
                raise ValueError("avd_home must be resolved to an absolute path")
            if self.avd_home.exists() and not self.avd_home.is_dir():
                raise ValueError("avd_home must point to a directory")
        if (
            isinstance(self.avd_ram_size_mb, bool)
            or self.avd_ram_size_mb < MIN_AVD_RAM_SIZE_MB
            or self.avd_ram_size_mb % 256 != 0
        ):
            raise ValueError(
                f"avd_ram_size_mb must be a multiple of 256 and at least {MIN_AVD_RAM_SIZE_MB}"
            )
        if self.apk_path is not None and self.apk_path.suffix.lower() != ".apk":
            raise ValueError("apk_path must point to an .apk file")
        if not self.system_image_package.startswith("system-images;android-35;"):
            raise ValueError("system_image_package must be an Android 35 system image")
        if "playstore" in self.system_image_package.lower():
            raise ValueError("Google Play system images are not supported")
        if self.selinux_mode not in _SELINUX_MODES:
            raise ValueError("selinux_mode must be enforcing or permissive")
        if self.data_partition_size_gb < MIN_DATA_PARTITION_SIZE_GB:
            raise ValueError(
                f"data_partition_size_gb must be at least {MIN_DATA_PARTITION_SIZE_GB}"
            )

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH, *, root: Path = ROOT) -> AndroidConfig:
        payload: Mapping[str, Any] = {}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("android config must be a JSON object")
            payload = loaded

        def resolve_path(value: Any, default: Path | None) -> Path | None:
            if value is None:
                return default
            candidate = Path(str(value))
            return candidate if candidate.is_absolute() else (root / candidate).resolve()

        display = payload.get("display_size", list(DISPLAY_SIZE))
        if not isinstance(display, list) or len(display) != 2:
            raise ValueError("display_size must be a two-element JSON array")
        config = cls(
            avd_name=str(payload.get("avd_name", DEFAULT_AVD_NAME)),
            serial=str(payload.get("serial", DEFAULT_SERIAL)),
            package_name=(str(payload["package_name"]) if payload.get("package_name") else None),
            game_label=str(payload.get("game_label", DEFAULT_GAME_LABEL)),
            display_size=(int(display[0]), int(display[1])),
            apk_path=resolve_path(payload.get("apk_path"), None),
            keep_running=bool(payload.get("keep_running", True)),
            login_timeout_seconds=int(payload.get("login_timeout_seconds", 900)),
            sdk_root=resolve_path(
                payload.get("sdk_root"), root / "install" / "android-sdk"
            )
            or (root / "install" / "android-sdk").resolve(),
            avd_home=resolve_path(payload.get("avd_home"), None),
            avd_ram_size_mb=int(
                payload.get("avd_ram_size_mb", DEFAULT_AVD_RAM_SIZE_MB)
            ),
            system_image_package=str(
                payload.get("system_image_package", DEFAULT_SYSTEM_IMAGE_PACKAGE)
            ),
            selinux_mode=str(payload.get("selinux_mode", DEFAULT_SELINUX_MODE)).lower(),
            data_partition_size_gb=int(
                payload.get("data_partition_size_gb", MIN_DATA_PARTITION_SIZE_GB)
            ),
        )
        config.validate()
        return config


__all__ = [
    "AndroidConfig",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_AVD_RAM_SIZE_MB",
    "DEFAULT_SELINUX_MODE",
    "DEFAULT_SYSTEM_IMAGE_PACKAGE",
    "DISPLAY_SIZE",
    "MIN_AVD_RAM_SIZE_MB",
    "MIN_DATA_PARTITION_SIZE_GB",
]
