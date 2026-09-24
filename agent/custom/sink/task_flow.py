"""Keep native MFW task sessions bounded without making business failures fatal.

Maa_bbb lets an ordinary failed task return control to the checked-task queue.
MJA follows that default.  The only queue-level exception is the startup task:
without ``GAME_START`` later business tasks cannot operate on a valid surface,
so later GUI submissions must fail before executing any business action.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from agent.custom.support.crash_evidence import emit
from agent.custom.support.task_session import TASK_SESSIONS

try:  # MaaFw is installed in the assembled runtime, not during source tests.
    from maa.agent.agent_server import AgentServer
    from maa.tasker import NotificationType, TaskerEventSink
except ImportError:  # pragma: no cover - exercised only without MaaFw.

    class _FallbackAgentServer:
        @staticmethod
        def tasker_sink():
            def decorate(sink):
                return sink

            return decorate

    class TaskerEventSink:  # type: ignore[no-redef]
        pass

    class NotificationType:  # type: ignore[no-redef]
        Starting = "Starting"
        Succeeded = "Succeeded"
        Failed = "Failed"

    AgentServer = _FallbackAgentServer  # type: ignore[assignment,misc]

_LOGGER = logging.getLogger(__name__)
_SUCCEEDED_MESSAGE = "Tasker.Task.Succeeded"
_FAILED_MESSAGE = "Tasker.Task.Failed"
_GAME_START_ENTRY = "0023-启动-游戏入口"


@AgentServer.tasker_sink()
class GlobalPrerequisiteStopSink(TaskerEventSink):
    """Release native task sessions and stop only after GAME_START fails."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._startup_failed = False
        self._blocked_entries: dict[str, dict[str, Any]] = {}

    def on_tasker_task(self, tasker: Any, noti_type: Any, detail: Any) -> None:
        """Handle Maa's typed Tasker notification callback."""

        status = self._status_from_notification(noti_type)
        value = getattr(noti_type, "value", noti_type)
        if value in (getattr(NotificationType.Starting, "value", "Starting"), "Starting"):
            self._handle_starting(tasker, getattr(detail, "entry", None))
            return
        if status is None:
            return
        task_id = getattr(detail, "task_id", None)
        entry = getattr(detail, "entry", None)
        self._handle_terminal(tasker, status, task_id, entry)

    def on_raw_notification(
        self,
        tasker: Any,
        msg: str,
        details: dict[str, Any],
    ) -> None:
        """Handle the raw form as well as the typed callback."""

        if msg == "Tasker.Task.Starting":
            self._handle_starting(
                tasker, details.get("entry") if isinstance(details, dict) else None
            )
            return
        if msg == _SUCCEEDED_MESSAGE:
            status = "Succeeded"
        elif msg == _FAILED_MESSAGE:
            status = "Failed"
        else:
            return
        task_id = details.get("task_id") if isinstance(details, dict) else None
        entry = details.get("entry") if isinstance(details, dict) else None
        emit("native_task_terminal", task_id=task_id, entry=entry, native_terminal=status)
        self._handle_terminal(tasker, status, task_id, entry)

    @staticmethod
    def _status_from_notification(noti_type: Any) -> str | None:
        value = getattr(noti_type, "value", noti_type)
        succeeded_value = getattr(NotificationType.Succeeded, "value", "Succeeded")
        failed_value = getattr(NotificationType.Failed, "value", "Failed")
        if value == succeeded_value or value == "Succeeded":
            return "Succeeded"
        if value == failed_value or value == "Failed":
            return "Failed"
        return None

    def _handle_terminal(
        self,
        tasker: Any,
        status: str,
        native_task_id: Any,
        entry: Any,
    ) -> None:
        normalized_task_id = self._normalize_task_id(native_task_id)
        if normalized_task_id is not None:
            TASK_SESSIONS.end(normalized_task_id)

        self._restore_entry(tasker, entry)
        if status == "Failed" and entry == _GAME_START_ENTRY:
            with self._lock:
                self._startup_failed = True

    def _restore_entry(self, tasker: Any, entry: Any) -> None:
        with self._lock:
            original = self._blocked_entries.pop(entry, None)
        if original is not None:
            if not tasker.resource.override_pipeline({entry: original}):
                raise RuntimeError(f"Could not restore blocked native entry: {entry}")

    def _handle_starting(self, tasker: Any, entry: Any) -> None:
        if not isinstance(entry, str) or entry == "MaaTaskerPostStop":
            return
        with self._lock:
            if entry == _GAME_START_ENTRY:
                self._startup_failed = False
            blocked = self._startup_failed
            already_overridden = entry in self._blocked_entries
        if not blocked or already_overridden:
            return

        # Maa 5.12.3 emits Succeeded when post_stop interrupts a task before
        # its first node. That produced 21 false successes in a real GUI run.
        # Execute an explicit native failure instead, then restore the entry
        # at its terminal event so an explicit new run uses the real pipeline.
        resource = tasker.resource
        original = resource.get_node_data(entry)
        if not original:
            raise RuntimeError(f"Could not inspect blocked native entry: {entry}")
        override = {
            "recognition": "DirectHit",
            "action": "Custom",
            "custom_action": "FailTask",
            "custom_action_param": {},
            "next": [],
            "on_error": [],
            "max_hit": 1,
            "enabled": True,
        }
        with self._lock:
            self._blocked_entries[entry] = original
        if not resource.override_pipeline({entry: override}):
            raise RuntimeError(f"Could not fail blocked native entry: {entry}")
        _LOGGER.error(
            "GAME_START failed; refusing business entry %s through native FailTask", entry
        )

    @staticmethod
    def _normalize_task_id(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = ["GlobalPrerequisiteStopSink"]
