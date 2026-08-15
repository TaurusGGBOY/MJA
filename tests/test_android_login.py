from __future__ import annotations

import pytest

from agent.android.config import AndroidConfig
from agent.android.login import LoginGate, LoginState
from agent.errors import ErrorCode, MJAError


class FakeDevice:
    def __init__(
        self,
        foreground: list[str],
        ui: list[str],
        renderer_ready: list[bool] | None = None,
    ) -> None:
        self.foreground_values = iter(foreground)
        self.ui_values = iter(ui)
        self.renderer_values = iter(renderer_ready) if renderer_ready is not None else None
        self.started_packages: list[str] = []

    def foreground_package(self) -> str | None:
        return next(self.foreground_values)

    def ui_xml(self) -> str:
        return next(self.ui_values)

    def start_app(self, package_name: str) -> None:
        self.started_packages.append(package_name)

    def renderer_ready(self) -> bool:
        if self.renderer_values is None:
            return True
        return next(self.renderer_values)


def test_login_gate_notifies_once_then_returns_when_login_is_complete() -> None:
    messages: list[str] = []
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    device = FakeDevice(
        ["com.game", "com.game", "com.game", "com.game"],
        ["手机号 验证码", "主界面", "主界面", "主界面"],
    )
    config = AndroidConfig(package_name="com.game", login_timeout_seconds=10)
    gate = LoginGate(
        config,
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
        notify=messages.append,
    )

    assert gate.wait_until_ready(device) == LoginState.READY
    assert messages == ["请完成游戏账号登录，完成后无需点击继续"]


def test_login_gate_ignores_daily_login_task_text() -> None:
    messages: list[str] = []
    ticks = iter([0.0, 1.0, 2.0, 3.0])
    device = FakeDevice(
        ["com.game", "com.game", "com.game"],
        ["每日登录游戏", "每日登录游戏", "每日登录游戏"],
    )
    config = AndroidConfig(package_name="com.game", login_timeout_seconds=10)
    gate = LoginGate(
        config,
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
        notify=messages.append,
    )

    assert gate.wait_until_ready(device) == LoginState.READY
    assert messages == []


def test_login_gate_retries_maa_start_app_when_game_is_not_foreground() -> None:
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    device = FakeDevice(
        ["com.android.launcher", "com.game", "com.game", "com.game"],
        ["", "主界面", "主界面", "主界面"],
    )
    config = AndroidConfig(package_name="com.game", login_timeout_seconds=10)
    gate = LoginGate(
        config,
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
    )

    assert gate.wait_until_ready(device) == LoginState.READY
    assert device.started_packages == ["com.game"]


def test_login_gate_starts_game_before_dumping_launcher_ui() -> None:
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])

    class LauncherDevice(FakeDevice):
        def ui_xml(self) -> str:
            if not self.started_packages:
                raise MJAError(
                    ErrorCode.ADB_DEVICE_FAILED,
                    "launcher UI dump is temporarily unavailable",
                )
            return super().ui_xml()

    device = LauncherDevice(
        ["com.google.android.apps.nexuslauncher", "com.game", "com.game", "com.game"],
        ["主界面", "主界面", "主界面"],
    )
    gate = LoginGate(
        AndroidConfig(package_name="com.game", login_timeout_seconds=10),
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
    )

    assert gate.wait_until_ready(device) == LoginState.READY
    assert device.started_packages == ["com.game"]


def test_login_gate_waits_for_a_visible_renderer_frame() -> None:
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    device = FakeDevice(
        ["com.game"] * 6,
        ["主界面"] * 6,
        [False, False, True, True, True, True],
    )
    config = AndroidConfig(package_name="com.game", login_timeout_seconds=10)
    gate = LoginGate(
        config,
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
    )

    assert gate.wait_until_ready(device) == LoginState.READY


def test_login_gate_can_require_an_interactive_surface() -> None:
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    device = FakeDevice(
        ["com.game"] * 5,
        ["主界面"] * 5,
    )
    interactive_values = iter([False, False, True, True, True])
    device.interactive_ready = lambda: next(interactive_values)  # type: ignore[attr-defined]
    gate = LoginGate(
        AndroidConfig(package_name="com.game", login_timeout_seconds=10),
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
    )

    assert gate.wait_until_ready(device, require_interactive=True) == LoginState.READY


def test_login_gate_requires_explicit_package() -> None:
    config = AndroidConfig(package_name=None)
    gate = LoginGate(config, sleeper=lambda _: None)

    try:
        gate.wait_until_ready(FakeDevice([], []))
    except RuntimeError as error:
        assert error.args
    else:  # pragma: no cover
        raise AssertionError("expected missing package failure")


def test_login_gate_fails_bounded_when_launcher_never_returns_to_game() -> None:
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    device = FakeDevice(
        [
            "com.android.launcher",
            "com.android.launcher",
            "com.android.launcher",
            "com.android.launcher",
        ],
        ["", "", "", ""],
    )
    gate = LoginGate(
        AndroidConfig(package_name="com.game", login_timeout_seconds=10),
        sleeper=lambda _: None,
        clock=lambda: next(ticks),
        foreground_timeout_seconds=2.0,
    )

    with pytest.raises(MJAError) as exc_info:
        gate.wait_until_ready(device)

    assert exc_info.value.code is ErrorCode.ANDROID_GAME_NOT_FOREGROUND
    assert device.started_packages == ["com.game", "com.game", "com.game"]
