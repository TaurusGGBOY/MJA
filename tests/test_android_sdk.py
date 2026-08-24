from __future__ import annotations

from pathlib import Path

import pytest

from agent.android.config import AndroidConfig
from agent.android.sdk import REQUIRED_PACKAGES, AndroidSdk


def _tool(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_discover_prefers_project_sdk(tmp_path: Path) -> None:
    root = tmp_path / "sdk"
    for relative in (
        "cmdline-tools/latest/bin/sdkmanager",
        "cmdline-tools/latest/bin/avdmanager",
        "platform-tools/adb",
        "emulator/emulator",
    ):
        _tool(root / relative)
    config = AndroidConfig(sdk_root=root)

    paths = AndroidSdk(config).discover()

    assert paths is not None
    assert paths.root == root


def test_ensure_without_tools_raises_stable_error(tmp_path: Path) -> None:
    config = AndroidConfig(sdk_root=tmp_path / "missing")

    with pytest.raises(RuntimeError, match="Android SDK") as error:
        AndroidSdk(config).ensure()

    assert error.value.code.value == "ANDROID_SDK_UNAVAILABLE"


def test_install_components_uses_pinned_packages(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    root = tmp_path / "sdk"
    for relative in (
        "cmdline-tools/latest/bin/sdkmanager",
        "cmdline-tools/latest/bin/avdmanager",
        "platform-tools/adb",
        "emulator/emulator",
    ):
        _tool(root / relative)

    def runner(argv: list[str], **_: object) -> object:
        calls.append(argv)
        return object()

    AndroidSdk(AndroidConfig(sdk_root=root), runner=runner).ensure(install_missing=True)

    assert any(all(package in call for package in REQUIRED_PACKAGES) for call in calls)
    assert any("--licenses" in call for call in calls)


def test_install_components_uses_configured_system_image(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    root = tmp_path / "sdk"
    for relative in (
        "cmdline-tools/latest/bin/sdkmanager",
        "cmdline-tools/latest/bin/avdmanager",
        "platform-tools/adb",
        "emulator/emulator",
    ):
        _tool(root / relative)

    def runner(argv: list[str], **_: object) -> object:
        calls.append(argv)
        return object()

    package = "system-images;android-35;google_apis;arm64-v8a"
    config = AndroidConfig(sdk_root=root, system_image_package=package)
    AndroidSdk(config, runner=runner).ensure(install_missing=True)

    assert any(package in call for call in calls)
    assert not any("google_apis_playstore" in call for call in calls)
