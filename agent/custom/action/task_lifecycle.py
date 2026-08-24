"""MFW custom actions for starting and truthfully closing one business task."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from time import sleep
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.controller_input import click_box
from agent.custom.support.policy import TASK_POLICIES
from agent.custom.support.task_session import TASK_SESSIONS

_STARTUP_ERROR_CODE = re.compile(r"^GAME_START_[A-Z0-9_]+$")
_GAME_PACKAGE = "com.hanjiasongshu.dr22"
# The world HUD exposes the two-sword shortcut immediately above the
# 310/310 counter.  This is the only fixed coordinate used to move from the
# exploration HUD back to the bottom navigation home; it is deliberately kept
# here, outside business-task action budgets, because it is lifecycle cleanup.
_WORLD_HOME_MENU_BOX = (1090, 585, 85, 80)
# Painting-scroll/world-map pages expose a separate close icon in the upper
# right.  Android BACK is ignored on that surface, so cleanup must dismiss the
# surface first and only then use BACK for any remaining nested page.
_KNOWN_SURFACE_CLOSE_BOX = (1205, 33, 18, 18)
_LOGGER = logging.getLogger(__name__)


def _context_key(context: Any) -> int:
    """Return a key stable across CustomAction wrappers for one Maa context."""

    handle = getattr(context, "_handle", None)
    value = getattr(handle, "value", handle)
    if not isinstance(value, bool):
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            numeric = 0
        if numeric:
            return numeric
    return id(context)


def _object_payload(argv: Any) -> dict[str, Any]:
    raw = getattr(argv, "custom_action_param", argv)
    if isinstance(raw, Mapping):
        payload = dict(raw)
    elif isinstance(raw, (str, bytes, bytearray)):
        try:
            decoded = raw.decode("utf-8") if not isinstance(raw, str) else raw
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("task lifecycle parameters must be valid JSON") from exc
    else:
        raise ValueError("task lifecycle parameters must be a JSON object")
    if not isinstance(payload, dict):
        raise ValueError("task lifecycle parameters must be a JSON object")
    return payload


def _task_id(payload: Mapping[str, Any]) -> str:
    value = payload.get("task_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("task_id must be a non-empty string")
    task_id = value.strip().upper()
    if task_id not in TASK_POLICIES:
        raise ValueError(f"unknown task_id: {task_id}")
    return task_id


def _native_task_id(argv: Any, context: Any) -> int:
    detail = getattr(argv, "task_detail", None)
    value = getattr(detail, "task_id", None)
    if value is None:
        # Older unit fakes and compatibility callers do not expose MFW's
        # TaskDetail. The context handle remains a stable local fallback.
        return _context_key(context)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("argv.task_detail.task_id must be a non-negative integer")
    return value


def _stop_game_surface(context: Any) -> bool:
    """Stop the game through the MFW controller, without shelling out to ADB."""

    controller = context.tasker.controller
    stop_app = getattr(controller, "post_stop_app", None)
    if not callable(stop_app):
        return False
    job = stop_app(_GAME_PACKAGE)
    wait = getattr(job, "wait", None)
    if not callable(wait):
        return False
    return bool(wait())


@AgentServer.custom_action("BeginTask")
class BeginTask(CustomAction):
    """Bind one MFW native task to isolated safety budgets."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _object_payload(argv)
            task_id = _task_id(payload)
            native_task_id = _native_task_id(argv, context)
            active_task_id = TASK_SESSIONS.business_task_id(native_task_id)
            if active_task_id is not None:
                return active_task_id == task_id
            TASK_SESSIONS.begin(native_task_id, task_id)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            if "native_task_id" in locals():
                TASK_SESSIONS.end(native_task_id)
            return False
        return True


@AgentServer.custom_action("ReturnToHome")
class ReturnToHome(CustomAction):
    """Unwind nested game pages before the shared home-boundary check."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            controller = context.tasker.controller
            post_key = getattr(controller, "post_click_key", None)
            if not callable(post_key):
                return False
            # Some map/stage screens consume one BACK only to dismiss their
            # transition layer. Keep unwinding until the common home-boundary
            # detector can observe the actual game home.
            for _ in range(8):
                job = post_key(4)  # Android BACK; controller remains MFW-owned.
                wait = getattr(job, "wait", None)
                if not callable(wait) or not wait():
                    return False
                sleep(0.35)
            # Back unwinds task-specific sheets, but the world HUD is a
            # separate surface from the bottom-navigation home.  Once the
            # nested pages are unwound, use the same fixed two-sword shortcut
            # as startup recovery to open that home surface.
            resolution = getattr(controller, "resolution", None)
            click_box(controller, _WORLD_HOME_MENU_BOX, resolution=resolution)
            sleep(1.5)
            return True
        except Exception:
            return False


@AgentServer.custom_action("ReturnToWorldHome")
class ReturnToWorldHome(CustomAction):
    """Dismiss the world surface and unwind nested pages with Android BACK.

    The world HUD's right-side icons are business entries whose positions vary
    by surface; a fixed tap there can open 蜃影武墟 instead of returning home.
    This cleanup action therefore only dismisses the calibrated close icon and
    unwinds nested pages. The following boundary node owns the final proof.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            controller = context.tasker.controller
            post_key = getattr(controller, "post_click_key", None)
            if not callable(post_key):
                return False
            # The painting-scroll/world-map surface visibly has an upper-right
            # close icon but consumes no Android BACK event.  A best-effort
            # close is safe on pages without that icon (it lands on empty HUD
            # space), while making the known surface dismissible before the
            # bounded BACK unwind below.
            resolution = getattr(controller, "resolution", None)
            try:
                click_box(
                    controller,
                    _KNOWN_SURFACE_CLOSE_BOX,
                    resolution=resolution,
                )
                sleep(0.5)
            except Exception:
                _LOGGER.debug("known surface close icon was not actionable", exc_info=True)
            for _ in range(8):
                job = post_key(4)  # Android BACK; controller remains MFW-owned.
                wait = getattr(job, "wait", None)
                if not callable(wait) or not wait():
                    return False
                sleep(0.35)
            return True
        except Exception:
            return False


@AgentServer.custom_action("CloseKnownPaintingSurface")
class CloseKnownPaintingSurface(CustomAction):
    """Dismiss the painting/world-map surface at its calibrated close icon.

    The shared ``公共-已知-画卷-关闭`` node already proves that the painting
    surface and its upper-right icon are visible.  Maa's generic ``Click``
    action clicked the full 72px template box and landed below the icon on the
    live 1280x720 frame, so this lifecycle-only action uses the small verified
    anchor used by home recovery instead.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        del argv
        try:
            controller = context.tasker.controller
            resolution = getattr(controller, "resolution", None)
            click_box(controller, _KNOWN_SURFACE_CLOSE_BOX, resolution=resolution)
            sleep(1.0)
        except Exception:
            return False
        return True


@AgentServer.custom_action("OpenGameHomeMenu")
class OpenGameHomeMenu(CustomAction):
    """Open the bottom-navigation home from the game lifecycle boundary.

    The two-sword shortcut is a game lifecycle control, not a business task
    action. Its position is fixed on the 1280x720 Android renderer. On the
    bottom-navigation home the same point is intentionally empty, so calling
    this action there is a harmless no-op; on the world HUD it opens the
    bottom-navigation home.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            controller = context.tasker.controller
            resolution = getattr(controller, "resolution", None)
            click_box(controller, _WORLD_HOME_MENU_BOX, resolution=resolution)
            sleep(1.5)
        except Exception:
            return False
        return True


@AgentServer.custom_action("FailStartupRecovery")
class FailStartupRecovery(CustomAction):
    """Log a startup failure and return false for native MFW failure."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _object_payload(argv)
            error_code = payload.get("error_code")
            if not isinstance(error_code, str) or not _STARTUP_ERROR_CODE.fullmatch(
                error_code
            ):
                return False
            postcondition = payload.get("postcondition")
            if not isinstance(postcondition, str) or not postcondition.startswith(
                "startup."
            ):
                return False
            _LOGGER.error(
                "[GAME_START_FAILURE] error_code=%s postcondition=%s stage=%s "
                "expected=%s observed=%s root_cause=%s",
                error_code,
                postcondition,
                payload.get("stage"),
                payload.get("expected"),
                payload.get("observed"),
                payload.get("root_cause"),
            )
            # A startup recovery failure is also a lifecycle boundary.  Stop
            # the game surface so the next continuation cannot inherit the
            # same unknown page or half-started Activity.
            if not _stop_game_surface(context):
                _LOGGER.error("[GAME_START_FAILURE] unable to stop game surface")
        except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
            return False
        return False


__all__ = [
    "BeginTask",
    "CloseKnownPaintingSurface",
    "FailStartupRecovery",
    "OpenGameHomeMenu",
    "ReturnToWorldHome",
]
