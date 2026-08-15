"""Stop the native MFW task queue at its first failed task notification.

This sink is deliberately a narrow Tasker boundary.  It does not infer task
outcomes, inspect result files, poll processes, or launch a replacement
runner.  The task pipeline records its business result first and returns a
native failure; this sink then asks that same Tasker to stop the queue.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

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
        Failed = "Failed"

    AgentServer = _FallbackAgentServer  # type: ignore[assignment,misc]


_LOGGER = logging.getLogger(__name__)
_FAILED_MESSAGE = "Tasker.Task.Failed"


@AgentServer.tasker_sink()
class TaskFlowStopSink(TaskerEventSink):
    """Post one native stop request after the first failed Tasker event."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._stop_posted = False
        self._first_failed_task_id: int | None = None

    def on_tasker_task(self, tasker: Any, noti_type: Any, detail: Any) -> None:
        """Handle Maa's typed Tasker notification callback."""

        if not self._is_failed_notification(noti_type):
            return
        self._post_stop_once(tasker, getattr(detail, "task_id", None))

    def on_raw_notification(
        self,
        tasker: Any,
        msg: str,
        details: dict[str, Any],
    ) -> None:
        """Handle the raw form as well as the typed callback.

        Maa's internal sink adapter dispatches both callbacks for a
        ``Tasker.Task.*`` message.  The shared latch makes that harmless and
        also keeps the sink straightforward to exercise with a fake Tasker.
        """

        if msg != _FAILED_MESSAGE:
            return
        task_id = details.get("task_id") if isinstance(details, dict) else None
        self._post_stop_once(tasker, task_id)

    @staticmethod
    def _is_failed_notification(noti_type: Any) -> bool:
        if noti_type is NotificationType.Failed:
            return True
        value = getattr(noti_type, "value", noti_type)
        failed_value = getattr(NotificationType.Failed, "value", NotificationType.Failed)
        return value == failed_value or value == "Failed"

    def _post_stop_once(self, tasker: Any, task_id: Any) -> bool:
        with self._lock:
            if self._stop_posted:
                return False
            self._stop_posted = True
            self._first_failed_task_id = self._normalize_task_id(task_id)

        try:
            tasker.post_stop()
        except Exception:  # native stop is best-effort, but never retried.
            _LOGGER.exception(
                "native Tasker stop failed after first task failure (task_id=%s)",
                self._first_failed_task_id,
            )
        return True

    @staticmethod
    def _normalize_task_id(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = ["TaskFlowStopSink"]
