from __future__ import annotations

import time
from enum import StrEnum
from typing import Callable

from agent.android.adb import AdbDevice
from agent.android.config import AndroidConfig
from agent.errors import ErrorCode, MJAError


class LoginState(StrEnum):
    READY = "LOGIN_READY"
    REQUIRED = "LOGIN_REQUIRED"


LOGIN_MARKERS = (
    "验证码",
    "手机号",
    "微信登录",
    "Google sign-in",
    "Sign in",
    "Verify",
)
MAX_START_APP_ATTEMPTS = 3
DEFAULT_FOREGROUND_TIMEOUT_SECONDS = 120.0


class LoginGate:
    def __init__(
        self,
        config: AndroidConfig,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        notify: Callable[[str], None] = print,
        foreground_timeout_seconds: float = DEFAULT_FOREGROUND_TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self.sleeper = sleeper
        self.clock = clock
        self.notify = notify
        if foreground_timeout_seconds <= 0:
            raise ValueError("foreground_timeout_seconds must be positive")
        self.foreground_timeout_seconds = foreground_timeout_seconds

    def wait_until_ready(
        self,
        device: AdbDevice,
        *,
        require_interactive: bool = False,
    ) -> LoginState:
        if not self.config.package_name:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                "package_name is required before login gate",
            )
        started = self.clock()
        deadline = started + self.config.login_timeout_seconds
        foreground_deadline = started + min(
            self.config.login_timeout_seconds,
            self.foreground_timeout_seconds,
        )
        required_announced = False
        login_required_seen = False
        ready_streak = 0
        start_attempts = 0
        while True:
            now = self.clock()
            if now >= deadline:
                break
            foreground = device.foreground_package()
            # Do not ask uiautomator to dump Launcher before attempting the
            # bounded app foreground recovery.  On the live emulator that
            # dump can fail while Launcher is still settling, which used to
            # abort recovery and surface the original
            # ANDROID_GAME_NOT_FOREGROUND error to the first Maa task.
            if foreground is None or "launcher" in foreground.casefold():
                ready_streak = 0
                starter = getattr(device, "start_app", None)
                if callable(starter) and start_attempts < MAX_START_APP_ATTEMPTS:
                    starter(self.config.package_name)
                    start_attempts += 1
                elif not login_required_seen and now >= foreground_deadline:
                    raise MJAError(
                        ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                        "game did not return to the foreground after bounded start attempts",
                    )
                self.sleeper(2.0)
                continue
            try:
                ui = device.ui_xml()
            except MJAError:
                # A non-game activity may disappear while its accessibility
                # tree is being dumped.  Treat that as an unavailable login
                # hint and continue the existing bounded start recovery.  A
                # dump failure while the game is foreground remains fatal so
                # a real ADB/UI service failure is not hidden.
                if foreground == self.config.package_name:
                    raise
                ui = ""
            login_required = any(marker.casefold() in ui.casefold() for marker in LOGIN_MARKERS)
            if login_required:
                login_required_seen = True
                ready_streak = 0
                if not required_announced:
                    self.notify("请完成游戏账号登录，完成后无需点击继续")
                    required_announced = True
            elif foreground == self.config.package_name:
                readiness_probe = getattr(
                    device,
                    "interactive_ready" if require_interactive else "renderer_ready",
                    None,
                )
                if callable(readiness_probe) and not readiness_probe():
                    # The package may be foreground while Unity is still
                    # presenting a loading surface. Maa must not start until
                    # the required usable frame is visible.
                    ready_streak = 0
                else:
                    ready_streak += 1
                if ready_streak >= 3:
                    return LoginState.READY
            else:
                ready_streak = 0
                starter = getattr(device, "start_app", None)
                if callable(starter) and start_attempts < MAX_START_APP_ATTEMPTS:
                    starter(self.config.package_name)
                    start_attempts += 1
                elif not login_required_seen and now >= foreground_deadline:
                    raise MJAError(
                        ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                        "game did not return to the foreground after bounded start attempts",
                    )
            self.sleeper(2.0)
        if not login_required_seen:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                "game did not return to the foreground before the startup deadline",
            )
        raise MJAError(
            ErrorCode.ANDROID_LOGIN_REQUIRED,
            "login was not completed before the configured timeout",
        )


__all__ = [
    "DEFAULT_FOREGROUND_TIMEOUT_SECONDS",
    "LOGIN_MARKERS",
    "MAX_START_APP_ATTEMPTS",
    "LoginGate",
    "LoginState",
]
