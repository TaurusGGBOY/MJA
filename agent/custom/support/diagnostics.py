"""Task-scoped, best-effort diagnostics for the embedded MFW Agent."""

from __future__ import annotations

import json
import logging
import re
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, overload

from .models import TaskOutcomeStatus
from .policy import TASK_POLICIES

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    }
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|token|secret|api[-_]?key|authorization|cookie)"
    r"(\s*=\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    parts = set(normalized.split("_"))
    return bool(parts & _SENSITIVE_KEY_PARTS) or any(
        part in normalized for part in _SENSITIVE_KEY_PARTS
    )


def _redact(value: Any) -> Any:
    """Return JSON-safe diagnostic data without credentials or tokens."""

    if isinstance(value, Mapping):
        return {
            str(key): _redact(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER.sub("Bearer [REDACTED]", _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _task_key(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be non-empty")
    key = task_id.strip().upper()
    if key not in TASK_POLICIES:
        raise KeyError(f"unknown task: {key}")
    return key


def _run_key(run_id: str) -> str:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be non-empty")
    key = run_id.strip()
    if key in {".", ".."} or Path(key).name != key:
        raise ValueError("run_id must be a single path component")
    return key


class TaskDiagnostics:
    """Persist task evidence without changing the verified business result.

    Diagnostics are deliberately best-effort. A disk failure is logged and
    swallowed so a result already verified by the task runner cannot be turned
    into a different business outcome merely because evidence persistence failed.
    """

    def __init__(self, root: Path, *, run_id: str) -> None:
        self.root = Path(root)
        self.run_id = _run_key(run_id)
        self._run_dir = self.root / self.run_id
        self._statuses: dict[str, TaskOutcomeStatus | None] = {}
        self._started_at: dict[str, str] = {}
        self._business_results: dict[str, dict[str, Any] | None] = {}
        self._lock = RLock()
        self._logger = logging.getLogger(__name__)

    def begin(self, task_id: str) -> None:
        key = _task_key(task_id)
        with self._lock:
            task_dir = self._task_dir(key)
            task_dir.mkdir(parents=True, exist_ok=True)
            started_at = _timestamp()
            self._started_at[key] = started_at
            self._statuses[key] = None
            self._business_results[key] = None
            payload = {
                "schema_version": 1,
                "task_id": key,
                "status": "running",
                "started_at": started_at,
                "finished_at": None,
                "postcondition": None,
                "error_code": None,
                "business_result_sealed": False,
                "home_boundary_pending": False,
                "home_boundary_status": None,
                "final_status": None,
                "final_boundary_failure_reason": None,
                "business_result": None,
                "events": [],
            }
            self._try_io("begin result", self._atomic_write_json, task_dir / "result.json", payload)
            self._try_io(
                "begin action trace",
                (task_dir / "action-trace.jsonl").touch,
                exist_ok=True,
            )

    @overload
    def record_action(
        self,
        action_id: str,
        details: Mapping[str, Any] | None = None,
    ) -> None: ...

    @overload
    def record_action(self, intent: Any, decision: Any, frame_id: str) -> None: ...

    def record_action(
        self,
        action_id: Any,
        details: Any = None,
        frame_id: str | None = None,
    ) -> None:
        """Append a local MFW or workflow-engine action to the task trace."""

        if frame_id is None:
            if details is not None and not isinstance(details, Mapping):
                raise TypeError("details must be a mapping or None")
            trace_details = details or {}
        else:
            action_id = getattr(action_id, "action_id", None)
            if not isinstance(frame_id, str) or not frame_id.strip():
                raise ValueError("frame_id must be non-empty")
            reason = getattr(details, "reason", None)
            reason_value = getattr(
                reason,
                "value",
                reason if isinstance(reason, str) else None,
            )
            trace_details = {
                "frame_id": frame_id.strip(),
                "allowed": bool(getattr(details, "allowed", False)),
                "reason": reason_value,
            }

        if not isinstance(action_id, str) or not action_id.strip():
            raise ValueError("action_id must be non-empty")
        key = self._require_started_task(trace_details)
        record = {
            "timestamp": _timestamp(),
            "action_id": action_id.strip().lower(),
            "details": _redact(trace_details),
        }
        task_dir = self._task_dir(key)
        self._try_io("action trace", self._append_jsonl, task_dir / "action-trace.jsonl", record)

    def finish(
        self,
        task_id: str,
        status: TaskOutcomeStatus,
        postcondition: str,
        error_code: str | None,
    ) -> None:
        key = _task_key(task_id)
        outcome = TaskOutcomeStatus(status)
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("postcondition must be non-empty")
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("error_code must be a string or None")

        with self._lock:
            if key not in self._started_at:
                raise RuntimeError(f"task {key} has not begun")
            # The in-memory outcome is the business truth. File persistence is
            # diagnostic only and is allowed to lag if the filesystem fails.
            self._statuses[key] = outcome
            self._business_results[key] = None
            payload = {
                "schema_version": 1,
                "task_id": key,
                "status": outcome.value,
                "started_at": self._started_at[key],
                "finished_at": _timestamp(),
                "postcondition": postcondition.strip(),
                "error_code": error_code,
                "business_result_sealed": False,
                "home_boundary_pending": False,
                "home_boundary_status": (
                    "failed" if outcome is TaskOutcomeStatus.FAILED else "completed"
                ),
                "final_status": outcome.value,
                "final_boundary_failure_reason": None,
                "business_result": None,
                "events": [{"name": "task_finished", "timestamp": _timestamp()}],
            }
            self._try_io(
                "finish result",
                self._atomic_write_json,
                self._task_dir(key) / "result.json",
                payload,
            )

    def seal_business_result(
        self,
        task_id: str,
        status: TaskOutcomeStatus,
        postcondition: str,
        error_code: str | None,
    ) -> None:
        """Persist any business evidence while keeping the home boundary open."""

        key = _task_key(task_id)
        outcome = TaskOutcomeStatus(status)
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("postcondition must be non-empty")
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("error_code must be a string or None")
        with self._lock:
            if key not in self._started_at:
                raise RuntimeError(f"task {key} has not begun")
            if self._business_results[key] is not None:
                raise PermissionError(f"task {key} business result is already sealed")
            business_result = {
                "status": outcome.value,
                "postcondition": postcondition.strip(),
                "error_code": error_code,
            }
            self._statuses[key] = outcome
            self._business_results[key] = dict(business_result)
            payload = {
                "schema_version": 1,
                "task_id": key,
                "status": outcome.value,
                "started_at": self._started_at[key],
                "finished_at": None,
                "postcondition": postcondition.strip(),
                "error_code": error_code,
                "business_result_sealed": True,
                "home_boundary_pending": True,
                "home_boundary_status": "pending",
                "final_status": None,
                "final_boundary_failure_reason": None,
                "business_result": business_result,
                "events": [{"name": "business_result_sealed", "timestamp": _timestamp()}],
            }
            self._try_io(
                "seal business result",
                self._atomic_write_json,
                self._task_dir(key) / "result.json",
                payload,
            )

    def complete_home_boundary(self, task_id: str, boundary: str = "home") -> None:
        """Persist final success after the named boundary has been observed."""

        key = _task_key(task_id)
        if not isinstance(boundary, str) or boundary.strip().casefold() != "home":
            raise ValueError("boundary must be home")
        with self._lock:
            business_result = self._business_results.get(key)
            if business_result is None:
                raise PermissionError(f"task {key} has no sealed business result")
            payload = {
                "schema_version": 1,
                "task_id": key,
                "status": business_result["status"],
                "started_at": self._started_at[key],
                "finished_at": _timestamp(),
                "postcondition": business_result["postcondition"],
                "error_code": business_result["error_code"],
                "business_result_sealed": True,
                "home_boundary_pending": False,
                "home_boundary_status": "completed",
                "final_status": business_result["status"],
                "final_boundary_failure_reason": None,
                "business_result": dict(business_result),
                "events": [
                    {"name": "business_result_sealed", "timestamp": None},
                    {"name": "home_boundary_completed", "timestamp": _timestamp()},
                ],
            }
            self._try_io(
                "complete home boundary",
                self._atomic_write_json,
                self._task_dir(key) / "result.json",
                payload,
            )

    def fail_home_boundary(
        self,
        task_id: str,
        postcondition: str,
        error_code: str | None,
    ) -> None:
        """Persist boundary failure while retaining any sealed business proof."""

        key = _task_key(task_id)
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("postcondition must be non-empty")
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("error_code must be a string or None")
        with self._lock:
            if key not in self._started_at:
                raise RuntimeError(f"task {key} has not begun")
            business_result = self._business_results.get(key)
            sealed = business_result is not None
            effective_postcondition = (
                business_result["postcondition"] if sealed else postcondition.strip()
            )
            payload = {
                "schema_version": 1,
                "task_id": key,
                "status": TaskOutcomeStatus.FAILED.value,
                "started_at": self._started_at[key],
                "finished_at": _timestamp(),
                "postcondition": effective_postcondition,
                "error_code": error_code,
                "business_result_sealed": sealed,
                "home_boundary_pending": False,
                "home_boundary_status": "failed",
                "final_status": TaskOutcomeStatus.FAILED.value,
                "final_boundary_failure_reason": (
                    "HOME_BOUNDARY_FAILED" if sealed else "BUSINESS_RESULT_NOT_SEALED"
                ),
                "business_result": dict(business_result) if sealed else None,
                "events": [
                    {"name": "business_result_sealed", "timestamp": None}
                ]
                if sealed
                else [],
            }
            payload["events"].append(
                {"name": "home_boundary_failed", "timestamp": _timestamp()}
            )
            self._statuses[key] = TaskOutcomeStatus.FAILED
            self._try_io(
                "fail home boundary",
                self._atomic_write_json,
                self._task_dir(key) / "result.json",
                payload,
            )

    def status(self, task_id: str) -> TaskOutcomeStatus | None:
        key = _task_key(task_id)
        with self._lock:
            if key not in self._started_at:
                raise RuntimeError(f"task {key} has not begun")
            return self._statuses[key]

    def write_before_image(self, image: bytes | bytearray | str | Path) -> None:
        self._write_image("before.png", image)

    def write_after_image(self, image: bytes | bytearray | str | Path) -> None:
        self._write_image("after.png", image)

    def write_failure_image(self, image: bytes | bytearray | str | Path) -> None:
        key = self._current_task()
        if self._statuses.get(key) is not TaskOutcomeStatus.FAILED:
            return
        self._write_image("failure.png", image)

    def _current_task(self) -> str:
        with self._lock:
            if not self._started_at:
                raise RuntimeError("no task has begun")
            return next(reversed(self._started_at))

    def _require_started_task(self, details: Mapping[str, Any] | None) -> str:
        task_id = details.get("task_id") if isinstance(details, Mapping) else None
        if isinstance(task_id, str):
            key = _task_key(task_id)
            if key not in self._started_at:
                raise RuntimeError(f"task {key} has not begun")
            return key
        return self._current_task()

    def _task_dir(self, task_id: str) -> Path:
        return self._run_dir / task_id

    def _write_image(self, filename: str, image: bytes | bytearray | str | Path) -> None:
        target = self._task_dir(self._current_task()) / filename

        def write() -> None:
            if isinstance(image, (str, Path)) and Path(image).is_file():
                shutil.copyfile(image, target)
            elif isinstance(image, (bytes, bytearray)):
                target.write_bytes(bytes(image))
            elif isinstance(image, str):
                target.write_bytes(image.encode("utf-8"))
            else:
                raise TypeError("image must be bytes, text, or a file path")

        self._try_io(f"write {filename}", write)

    @staticmethod
    def _append_jsonl(target: Path, record: Mapping[str, Any]) -> None:
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_redact(record), ensure_ascii=False) + "\n")

    @staticmethod
    def _atomic_write_json(target: Path, payload: Mapping[str, Any]) -> None:
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(
            json.dumps(_redact(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

    def _try_io(self, operation: str, callback: Any, *args: Any, **kwargs: Any) -> None:
        try:
            callback(*args, **kwargs)
        except OSError as exc:
            self._logger.warning("diagnostic %s failed: %s", operation, exc)


__all__ = ["TaskDiagnostics"]
