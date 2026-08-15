"""Bounded MFW action for restarting the game after a known stuck surface."""

from __future__ import annotations

import json
from collections.abc import Mapping
from numbers import Integral
from time import sleep
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.workflows.input import _wait_job

GAME_PACKAGE = "com.hanjiasongshu.dr22"
GAME_ACTIVITY = "com.hanjiasongshu.dr22/.MainActivity"
DEFAULT_PROCESS_DETACH_COOLDOWN_MS = 2_000
MIN_PROCESS_DETACH_COOLDOWN_MS = 1_000
MAX_PROCESS_DETACH_COOLDOWN_MS = 5_000


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


@AgentServer.custom_action("RestartGameSurface")
class RestartGameSurface(CustomAction):
    """Force-stop and relaunch only the configured game package.

    The action is intentionally narrow: it is used after the live
    ``蜃影武墟`` card-list surface has been recognized and has ignored both
    visual close controls and Android Back.  Maa's controller remains the
    only transport; this does not clear application data or shell out to ADB.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            params = _payload(argv)
            package = params.get("package")
            activity = params.get("activity")
            if package != GAME_PACKAGE or activity != GAME_ACTIVITY:
                return False
            cooldown_seconds = _process_detach_cooldown_seconds(params)

            controller = context.tasker.controller
            stop_app = getattr(controller, "post_stop_app", None)
            start_app = getattr(controller, "post_start_app", None)
            if not callable(stop_app) or not callable(start_app):
                return False

            _wait_job(stop_app(package))
            sleep(cooldown_seconds)
            _wait_job(start_app(activity))
        except Exception:
            return False
        return True


__all__ = ["RestartGameSurface"]
