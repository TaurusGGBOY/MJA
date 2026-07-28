from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Protocol

from agent.errors import ErrorCode, MJAError

try:  # MaaFw is installed in the assembled runtime, not during source tests.
    from maa.tasker import TaskerEventSink
except ImportError:  # pragma: no cover - exercised only outside the runtime
    class TaskerEventSink:  # type: ignore[no-redef]
        """Small import-time fallback so source-level tests need no MaaFw binary."""

        pass


class Diagnostics(Protocol):
    directory: Path

    def event(self, name: str, details: dict[str, Any] | None = None) -> None: ...

    def fail(self, error: MJAError) -> None: ...

    def succeed(self) -> None: ...


Restore = Callable[[], None]
ScreenWriter = Callable[[Any, Path], None]

TERMINAL_MESSAGES = frozenset({"Tasker.Task.Succeeded", "Tasker.Task.Failed"})
NODE_FAILURE_CODES = {
    "MJA_Start": ErrorCode.HOME_RECOGNITION_TIMEOUT,
    "MJA_ConfirmPanel": ErrorCode.MAIL_OPEN_TIMEOUT,
    "MJA_ConfirmMail": ErrorCode.MAIL_OPEN_TIMEOUT,
    "MJA_ConfirmPanelAfterMail": ErrorCode.HOME_RETURN_TIMEOUT,
    "MJA_ConfirmHome": ErrorCode.HOME_RETURN_TIMEOUT,
}

_LOGGER = logging.getLogger(__name__)


class RestoreWindowSink(TaskerEventSink):
    """Close one MJA task by recording its result and restoring the window.

    MaaFramework can deliver terminal notifications more than once when a
    tasker is shut down. ``_terminal_task_ids`` is therefore updated before
    any side effect, making restoration safe under duplicate and concurrent
    callbacks while allowing a later task ID to run normally.
    """

    def __init__(
        self,
        restore: Restore,
        diagnostics: Diagnostics | None = None,
        *,
        screen_directory: Path | None = None,
        screen_writer: ScreenWriter | None = None,
    ) -> None:
        super().__init__()
        self._restore = restore
        self._diagnostics = diagnostics
        self._screen_directory = Path(screen_directory) if screen_directory else None
        self._screen_writer = screen_writer or self._write_screen
        self._lock = Lock()
        self._terminal_task_ids: set[int] = set()
        self._failure_screen_task_ids: set[int] = set()

    def on_raw_notification(
        self,
        tasker: Any,
        msg: str,
        details: dict[str, Any],
    ) -> None:
        task_id = self._task_id(details)
        if task_id is None:
            return

        if msg == "Node.Recognition.Failed":
            self._record_node_failure(tasker, task_id, details)
            return

        if msg not in TERMINAL_MESSAGES:
            return

        with self._lock:
            if task_id in self._terminal_task_ids:
                return
            # Claim the task ID before invoking user/framework callbacks.
            self._terminal_task_ids.add(task_id)

        succeeded = msg == "Tasker.Task.Succeeded"
        if succeeded:
            self._record_success(tasker, task_id)
        else:
            self._record_event(
                "task_failed",
                {"task_id": task_id, "message": msg},
            )

        try:
            self._restore()
        except Exception as exc:  # terminal result must remain unchanged
            self._record_restore_warning(task_id, exc)

    def _record_node_failure(
        self,
        tasker: Any,
        task_id: int,
        details: dict[str, Any],
    ) -> None:
        node_name = details.get("name")
        code = NODE_FAILURE_CODES.get(node_name)
        if code is None:
            self._record_event(
                "node_recognition_failed",
                {"task_id": task_id, "node": node_name},
            )
            return

        with self._lock:
            if task_id in self._failure_screen_task_ids:
                return
            self._failure_screen_task_ids.add(task_id)

        self._save_screen(tasker, "failure-screen.png", task_id)
        self._record_event(
            "node_recognition_failed",
            {"task_id": task_id, "node": node_name, "code": code.value},
        )
        self._record_failure(
            MJAError(code, f"recognition failed at node {node_name}")
        )

    def _record_success(self, tasker: Any, task_id: int) -> None:
        self._save_screen(tasker, "last-screen.png", task_id)
        self._record_event("task_succeeded", {"task_id": task_id})
        self._safe_diagnostics_call(
            "succeed", self._diagnostics.succeed if self._diagnostics else None
        )

    def _save_screen(self, tasker: Any, filename: str, task_id: int) -> None:
        directory = self._screen_directory
        if directory is None and self._diagnostics is not None:
            directory = Path(self._diagnostics.directory)
        if directory is None:
            return

        path = directory / filename
        try:
            directory.mkdir(parents=True, exist_ok=True)
            image = tasker.controller.cached_image
            self._screen_writer(image, path)
        except Exception as exc:
            self._record_event(
                "screen_capture_failed",
                {"task_id": task_id, "file": filename, "message": str(exc)},
            )

    @staticmethod
    def _write_screen(image: Any, path: Path) -> None:
        if hasattr(image, "save"):
            image.save(path)
            return
        if isinstance(image, bytes):
            path.write_bytes(image)
            return

        from PIL import Image

        Image.fromarray(image).save(path)

    def _record_failure(self, error: MJAError) -> None:
        self._safe_diagnostics_call(
            "fail",
            self._diagnostics.fail if self._diagnostics else None,
            error,
        )

    def _record_event(self, name: str, details: dict[str, Any]) -> None:
        self._safe_diagnostics_call(
            "event",
            self._diagnostics.event if self._diagnostics else None,
            name,
            details,
        )

    def _record_restore_warning(self, task_id: int, error: Exception) -> None:
        details = {
            "task_id": task_id,
            "code": ErrorCode.WINDOW_RESTORE_FAILED.value,
            "severity": "warning",
            "message": str(error),
        }
        _LOGGER.warning("window restoration failed for task %s: %s", task_id, error)
        self._record_event("window_restore_failed", details)

    @staticmethod
    def _safe_diagnostics_call(
        name: str,
        callback: Callable[..., None] | None,
        *args: Any,
    ) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:
            _LOGGER.warning("diagnostics %s failed: %s", name, exc)

    @staticmethod
    def _task_id(details: dict[str, Any]) -> int | None:
        value = details.get("task_id")
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = ["NODE_FAILURE_CODES", "RestoreWindowSink", "TERMINAL_MESSAGES"]
