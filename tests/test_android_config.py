from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.android.config import (
    DEFAULT_AVD_RAM_SIZE_MB,
    DEFAULT_SYSTEM_IMAGE_PACKAGE,
    DISPLAY_SIZE,
    MIN_AVD_RAM_SIZE_MB,
    MIN_DATA_PARTITION_SIZE_GB,
    AndroidConfig,
)


def test_defaults_load_with_project_relative_sdk_root(tmp_path: Path) -> None:
    config_path = tmp_path / "android.json"
    config_path.write_text("{}", encoding="utf-8")

    config = AndroidConfig.load(config_path, root=tmp_path)

    assert config.avd_name == "mja-api35-apis"
    assert config.serial == "emulator-5556"
    assert config.display_size == DISPLAY_SIZE
    assert config.system_image_package == DEFAULT_SYSTEM_IMAGE_PACKAGE
    assert config.selinux_mode == "permissive"
    assert config.data_partition_size_gb == MIN_DATA_PARTITION_SIZE_GB
    assert config.sdk_root == (tmp_path / "install/android-sdk").resolve()
    assert config.avd_home is None
    assert config.avd_ram_size_mb == DEFAULT_AVD_RAM_SIZE_MB


def test_load_resolves_apk_and_sdk_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "android.json"
    config_path.write_text(
        json.dumps({"apk_path": "artifacts/game.apk", "sdk_root": "sdk"}),
        encoding="utf-8",
    )

    config = AndroidConfig.load(config_path, root=tmp_path)

    assert config.apk_path == (tmp_path / "artifacts/game.apk").resolve()
    assert config.sdk_root == (tmp_path / "sdk").resolve()


def test_load_resolves_avd_home_and_allows_unmounted_external_path(tmp_path: Path) -> None:
    config_path = tmp_path / "android.json"
    external_avd_home = tmp_path / "external" / ".android" / "avd"
    config_path.write_text(
        json.dumps({"avd_home": str(external_avd_home)}),
        encoding="utf-8",
    )

    config = AndroidConfig.load(config_path, root=tmp_path)

    assert config.avd_home == external_avd_home


def test_loads_and_validates_avd_ram_size(tmp_path: Path) -> None:
    config_path = tmp_path / "android.json"
    config_path.write_text(json.dumps({"avd_ram_size_mb": 3072}), encoding="utf-8")

    config = AndroidConfig.load(config_path, root=tmp_path)

    assert config.avd_ram_size_mb == 3072


@pytest.mark.parametrize("ram_size", [MIN_AVD_RAM_SIZE_MB - 256, 2305])
def test_rejects_unsafe_avd_ram_size(ram_size: int) -> None:
    with pytest.raises(ValueError, match="avd_ram_size_mb"):
        AndroidConfig(avd_ram_size_mb=ram_size).validate()


def test_rejects_relative_avd_home() -> None:
    with pytest.raises(ValueError, match="avd_home must be resolved"):
        AndroidConfig(avd_home=Path("relative/avd")).validate()


@pytest.mark.parametrize("display_size", [[720, 1280], [1920, 1080], [1280, 721]])
def test_rejects_noncanonical_display(display_size: list[int]) -> None:
    with pytest.raises(ValueError, match="1280x720"):
        AndroidConfig(display_size=tuple(display_size)).validate()


def test_rejects_unsafe_serial() -> None:
    with pytest.raises(ValueError, match="unsupported characters"):
        AndroidConfig(serial="emulator 5554").validate()


def test_rejects_non_apk_path() -> None:
    with pytest.raises(ValueError, match=r"\.apk"):
        AndroidConfig(apk_path=Path("game.xapk")).validate()


def test_rejects_google_play_system_image() -> None:
    with pytest.raises(ValueError, match="Google Play"):
        AndroidConfig(
            system_image_package="system-images;android-35;google_apis_playstore;arm64-v8a"
        ).validate()


def test_requires_large_data_partition() -> None:
    with pytest.raises(ValueError, match="at least 12"):
        AndroidConfig(data_partition_size_gb=8).validate()


def test_rejects_unknown_selinux_mode() -> None:
    with pytest.raises(ValueError, match="selinux_mode"):
        AndroidConfig(selinux_mode="disabled").validate()
