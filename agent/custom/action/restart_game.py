"""Bounded MFW action for restarting the game after a known stuck surface."""

from __future__ import annotations

import json
from collections.abc import Mapping
from numbers import Integral
from time import sleep
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.controller_input import _wait_job

GAME_PACKAGE = "com.hanjiasongshu.dr22"
GAME_ACTIVITY = "com.hanjiasongshu.dr22/.MainActivity"
DEFAULT_PROCESS_DETACH_COOLDOWN_MS = 2_000
MIN_PROCESS_DETACH_COOLDOWN_MS = 1_000
MAX_PROCESS_DETACH_COOLDOWN_MS = 5_000
DEFAULT_FORCE_STOP = True
DEFAULT_START_TIMEOUT_MS = 15_000
MIN_START_TIMEOUT_MS = 1_000
MAX_START_TIMEOUT_MS = 30_000
DEFAULT_START_REPEAT = 1
MIN_START_REPEAT = 1
MAX_START_REPEAT = 5
DEFAULT_START_REPEAT_DELAY_MS = 1_000
MIN_START_REPEAT_DELAY_MS = 0
MAX_START_REPEAT_DELAY_MS = 5_000


def _payload(argv: Any) -> Mapping[str, Any]:
    raw = getattr(argv, "custom_action_param", argv)
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            decoded = raw.decode("utf-8") if not isinstance(raw, str) else raw
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("restart parameters must be valid JSON") from exc
        if isinstance(value, Mapping):
            return value
    raise ValueError("restart parameters must be a JSON object")


def _process_detach_cooldown_seconds(params: Mapping[str, Any]) -> float:
    value = params.get("cooldown_ms", DEFAULT_PROCESS_DETACH_COOLDOWN_MS)
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("cooldown_ms must be an integer")
    cooldown_ms = int(value)
    if not (
        MIN_PROCESS_DETACH_COOLDOWN_MS
        <= cooldown_ms
        <= MAX_PROCESS_DETACH_COOLDOWN_MS
    ):
        raise ValueError(
            f"cooldown_ms must be between {MIN_PROCESS_DETACH_COOLDOWN_MS} and "
            f"{MAX_PROCESS_DETACH_COOLDOWN_MS}"
        )
    return cooldown_ms / 1_000


def _start_repeat(params: Mapping[str, Any]) -> int:
    value = params.get("start_repeat", DEFAULT_START_REPEAT)
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("start_repeat must be an integer")
    repeat = int(value)
    if not MIN_START_REPEAT <= repeat <= MAX_START_REPEAT:
        raise ValueError(
            f"start_repeat must be between {MIN_START_REPEAT} and {MAX_START_REPEAT}"
        )
    return repeat


def _start_repeat_delay_seconds(params: Mapping[str, Any]) -> float:
    value = params.get("start_repeat_delay_ms", DEFAULT_START_REPEAT_DELAY_MS)
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("start_repeat_delay_ms must be an integer")
    delay_ms = int(value)
    if not MIN_START_REPEAT_DELAY_MS <= delay_ms <= MAX_START_REPEAT_DELAY_MS:
        raise ValueError(
            f"start_repeat_delay_ms must be between {MIN_START_REPEAT_DELAY_MS} and "
            f"{MAX_START_REPEAT_DELAY_MS}"
        )
    return delay_ms / 1_000


def _force_stop(params: Mapping[str, Any]) -> bool:
    value = params.get("force_stop", DEFAULT_FORCE_STOP)
    if not isinstance(value, bool):
        raise ValueError("force_stop must be a boolean")
    return value


def _start_timeout_seconds(params: Mapping[str, Any]) -> float:
    value = params.get("start_timeout_ms", DEFAULT_START_TIMEOUT_MS)
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("start_timeout_ms must be an integer")
    timeout_ms = int(value)
    if not MIN_START_TIMEOUT_MS <= timeout_ms <= MAX_START_TIMEOUT_MS:
        raise ValueError(
            f"start_timeout_ms must be between {MIN_START_TIMEOUT_MS} and "
            f"{MAX_START_TIMEOUT_MS}"
        )
    return timeout_ms / 1_000


@AgentServer.custom_action("RestartGameSurface")
class RestartGameSurface(CustomAction):
    """Relaunch only the configured game package.

    Startup invariant: Android/Unity may kill the newly started surface about
    0.7 seconds after ``post_start_app`` returns.  Therefore startup recovery
    must use five starts spaced one second apart.  This is not an optional
    retry optimization: one start can report success while the game process
    has already been killed, so reducing the count can recreate the false
    startup-success failure.

    The action is intentionally narrow: it is used after the live
    ``蜃影武墟`` card-list surface has been recognized and has ignored both
    visual close controls and Android Back.  Maa's controller remains the
    only transport; this does not clear application data or shell out to ADB.
    ``force_stop`` is retained for non-startup recovery, but startup recovery
    can use a soft relaunch.  On the macOS host GPU path, force-stopping Unity
    while the emulator is tearing down its Vulkan surface can crash QEMU and
    take ADB down with it.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            params = _payload(argv)
            package = params.get("package")
            activity = params.get("activity")
            if package != GAME_PACKAGE or activity != GAME_ACTIVITY:
                return False
            force_stop = _force_stop(params)
            cooldown_seconds = _process_detach_cooldown_seconds(params)
            start_timeout_seconds = _start_timeout_seconds(params)
            start_repeat = _start_repeat(params)
            start_repeat_delay_seconds = _start_repeat_delay_seconds(params)

            controller = context.tasker.controller
            stop_app = getattr(controller, "post_stop_app", None)
            start_app = getattr(controller, "post_start_app", None)
            if not callable(start_app) or (force_stop and not callable(stop_app)):
                return False

            if force_stop:
                _wait_job(stop_app(package))
                sleep(cooldown_seconds)
            for index in range(start_repeat):
                if index:
                    sleep(start_repeat_delay_seconds)
                _wait_job(
                    start_app(activity), timeout_seconds=start_timeout_seconds
                )
        except Exception:
            return False
        return True


__all__ = ["RestartGameSurface"]
