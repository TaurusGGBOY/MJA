from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.android.config import AndroidConfig
from agent.android.game import GameInstaller


class FakeDevice:
    def __init__(self, *, installed: set[str] | None = None) -> None:
        self.installed = installed or set()
        self.install_calls: list[Path] = []

    def package_installed(self, package_name: str) -> bool:
        return package_name in self.installed

    def list_packages(self) -> set[str]:
        return set(self.installed)

    def install(self, path: Path) -> str:
        self.install_calls.append(path)
        self.installed.add("com.game")
        return "Success"


def test_existing_package_is_reused(tmp_path: Path) -> None:
    config_path = tmp_path / "android.json"
    config_path.write_text(json.dumps({"package_name": "com.game"}), encoding="utf-8")
    config = AndroidConfig(package_name="com.game", sdk_root=tmp_path / "sdk")

    installer = GameInstaller(
        config,
        FakeDevice(installed={"com.game"}),
        config_path=config_path,
    )
    assert installer.ensure_installed() == "com.game"


def test_apk_outside_allowed_root_is_rejected(tmp_path: Path) -> None:
    apk = tmp_path / "game.apk"
    apk.write_bytes(b"apk")
    config = AndroidConfig(apk_path=apk, sdk_root=tmp_path / "sdk")

    with pytest.raises(RuntimeError, match="outside allowed roots"):
        GameInstaller(config, FakeDevice()).ensure_installed()


def test_missing_apk_fails_without_opening_google_play(tmp_path: Path) -> None:
    config_path = tmp_path / "android.json"
    config_path.write_text(json.dumps({"package_name": None}), encoding="utf-8")
    config = AndroidConfig(package_name=None, sdk_root=tmp_path / "sdk")

    with pytest.raises(RuntimeError, match="Google Play installation is disabled"):
        GameInstaller(config, FakeDevice(), config_path=config_path).ensure_installed()
