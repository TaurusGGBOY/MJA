from __future__ import annotations

from pathlib import Path

import pytest

from agent.android.runtime_gate import AndroidRuntimeGate
from agent.errors import ErrorCode, MJAError


class FakeDevice:
    def __init__(self, foreground: str | None) -> None:
        self.foreground = foreground
        self.health_calls = 0
        self.start_calls = 0

    def foreground_package(self) -> str | None:
        return self.foreground

    def require_runtime_health(self) -> None:
        self.health_calls += 1

    def start_app(self, package_name: str) -> None:
        self.start_calls += 1


def test_require_foreground_accepts_the_configured_game() -> None:
    device = FakeDevice("com.game")
    gate = AndroidRuntimeGate(device=device, package_name="com.game")

    gate.require_foreground()

    assert device.start_calls == 0


@pytest.mark.parametrize("foreground", [None, "com.android.launcher3", "com.other"])
def test_require_foreground_rejects_non_game_screen(foreground: str | None) -> None:
    device = FakeDevice(foreground)
    gate = AndroidRuntimeGate(device=device, package_name="com.game")

    with pytest.raises(MJAError) as error:
        gate.require_foreground()

    assert error.value.code is ErrorCode.ANDROID_GAME_NOT_FOREGROUND
    assert device.start_calls == 0


def test_require_health_delegates_without_starting_app() -> None:
    device = FakeDevice("com.game")
    gate = AndroidRuntimeGate(device=device, package_name="com.game")

    gate.require_health()

    assert device.health_calls == 1
    assert device.start_calls == 0


def test_from_environment_uses_runtime_package_when_install_has_no_project_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Paths:
        adb = "/tmp/adb"

    monkeypatch.setenv("MJA_ANDROID_PACKAGE", "com.runtime.game")
    monkeypatch.setenv("MJA_ANDROID_SDK_ROOT", "/tmp/android-sdk")
    monkeypatch.setenv("MJA_ANDROID_SERIAL", "emulator-5556")
    captured = {}
    monkeypatch.setattr(
        "agent.android.runtime_gate.AndroidConfig.load",
        lambda: type(
            "Config",
            (),
            {"package_name": None, "serial": "emulator-5556", "sdk_root": "/wrong"},
        )(),
    )
    monkeypatch.setattr(
        "agent.android.runtime_gate.replace",
        lambda config, **changes: captured.update(changes) or config,
    )
    monkeypatch.setattr(
        "agent.android.runtime_gate.AndroidSdk.discover",
        lambda self: Paths(),
    )

    gate = AndroidRuntimeGate.from_environment()

    assert gate.package_name == "com.runtime.game"
    assert captured["serial"] == "emulator-5556"
    assert captured["sdk_root"] == Path("/tmp/android-sdk")
