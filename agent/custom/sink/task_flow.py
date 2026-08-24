"""Keep native MFW task sessions bounded without making business failures fatal.

Maa_bbb lets an ordinary failed task return control to the checked-task queue.
MJA follows that default.  The only queue-level exception is the startup task:
without ``GAME_START`` later business tasks cannot operate on a valid surface,
so its failure requests one native queue stop.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

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
        self._stop_posted = False

    def on_tasker_task(self, tasker: Any, noti_type: Any, detail: Any) -> None:
        """Handle Maa's typed Tasker notification callback."""

        status = self._status_from_notification(noti_type)
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

        if msg == _SUCCEEDED_MESSAGE:
            status = "Succeeded"
        elif msg == _FAILED_MESSAGE:
            status = "Failed"
        else:
            return
        task_id = details.get("task_id") if isinstance(details, dict) else None
        entry = details.get("entry") if isinstance(details, dict) else None
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

        if status != "Failed" or entry != _GAME_START_ENTRY:
            return
        self._post_startup_stop_once(tasker, normalized_task_id)

    def _post_startup_stop_once(self, tasker: Any, task_id: int | None) -> None:
        with self._lock:
            if self._stop_posted:
                return
            self._stop_posted = True

        try:
            tasker.post_stop()
        except Exception:  # native stop is best-effort, but never retried.
            _LOGGER.exception(
                "native Tasker stop failed after GAME_START failure (task_id=%s)",
                task_id,
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
