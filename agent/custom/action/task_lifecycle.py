"""MFW custom actions for starting and truthfully closing one business task."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
import re
from threading import RLock
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.diagnostics import TaskDiagnostics
from agent.custom.support.models import TaskOutcomeStatus
from agent.custom.support.policy import TASK_POLICIES
from agent.custom.support.state import RUN_STORE

_ACTIVE_DIAGNOSTICS: dict[tuple[int, str], TaskDiagnostics] = {}
_LOCK = RLock()
_STARTUP_ERROR_CODE = re.compile(r"^GAME_START_[A-Z0-9_]+$")
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


def _run_id(payload: Mapping[str, Any], context: Any) -> str:
    value = payload.get("run_id") or f"mfw-{_context_key(context)}"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("run_id must be a non-empty string")
    return value.strip()


def _diagnostics_root() -> Path:
    return Path(os.environ.get("MJA_DIAGNOSTICS_ROOT", "debug"))


def diagnostics_for(context: Any, task_id: str) -> TaskDiagnostics | None:
    key = (_context_key(context), task_id.strip().upper())
    with _LOCK:
        return _ACTIVE_DIAGNOSTICS.get(key)


def _active_task_ids(context: Any) -> tuple[str, ...]:
    context_key = _context_key(context)
    with _LOCK:
        return tuple(
            task_id
            for (bound_context, task_id) in _ACTIVE_DIAGNOSTICS
            if bound_context == context_key
        )


def _pop_diagnostics(context: Any, task_id: str) -> TaskDiagnostics | None:
    key = (_context_key(context), task_id.strip().upper())
    with _LOCK:
        return _ACTIVE_DIAGNOSTICS.pop(key, None)


def finish_task(
    context: Any,
    task_id: str,
    status: TaskOutcomeStatus,
    postcondition: str,
    error_code: str | None = None,
) -> bool:
    """Finish one begun task and its active diagnostics as one operation.

    The boolean reports whether this Maa context owned the authoritative active
    ``TaskDiagnostics`` binding. Callers fail closed when no binding exists
    instead of creating a second result writer.
    """

    key = _task_id({"task_id": task_id})
    outcome = TaskOutcomeStatus(status)
    if not isinstance(postcondition, str) or not postcondition.strip():
        raise ValueError("postcondition must be a non-empty string")
    if error_code is not None and not isinstance(error_code, str):
        raise ValueError("error_code must be a string or None")
    normalized_postcondition = postcondition.strip()

    diagnostics = diagnostics_for(context, key)
    if diagnostics is None:
        return False
    if outcome is TaskOutcomeStatus.FAILED:
        snapshot = RUN_STORE.snapshot(key)
        if snapshot.get("business_result_sealed") is True:
            RUN_STORE.fail_home_boundary(key, normalized_postcondition, error_code)
            diagnostics.fail_home_boundary(key, normalized_postcondition, error_code)
            _pop_diagnostics(context, key)
            return True

    RUN_STORE.finish(key, outcome, normalized_postcondition, error_code)
    diagnostics = _pop_diagnostics(context, key)
    if diagnostics is None:
        return False
    diagnostics.finish(key, outcome, normalized_postcondition, error_code)
    return True


def seal_task(
    context: Any,
    task_id: str,
    status: TaskOutcomeStatus,
    postcondition: str,
    error_code: str | None = None,
) -> bool:
    """Seal business evidence while keeping the task active for home return."""

    key = _task_id({"task_id": task_id})
    diagnostics = diagnostics_for(context, key)
    if diagnostics is None:
        return False
    outcome = TaskOutcomeStatus(status)
    normalized_postcondition = postcondition.strip() if isinstance(postcondition, str) else ""
    if not normalized_postcondition:
        raise ValueError("postcondition must be a non-empty string")
    if error_code is not None and not isinstance(error_code, str):
        raise ValueError("error_code must be a string or None")
    RUN_STORE.seal_business_result(key, outcome, normalized_postcondition, error_code)
    diagnostics.seal_business_result(key, outcome, normalized_postcondition, error_code)
    return True


def _active_task_id(context: Any) -> str | None:
    active_task_ids = _active_task_ids(context)
    return active_task_ids[0] if len(active_task_ids) == 1 else None


def complete_task_boundary(context: Any, boundary: str) -> bool:
    """Commit the one active sealed result after its explicit home boundary."""

    task_id = _active_task_id(context)
    if task_id is None:
        return False
    diagnostics = diagnostics_for(context, task_id)
    if diagnostics is None:
        return False
    try:
        RUN_STORE.complete_home_boundary(task_id, boundary)
        diagnostics.complete_home_boundary(task_id, boundary)
    except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
        try:
            RUN_STORE.fail_home_boundary(
                task_id,
                "home.boundary",
                "HOME_BOUNDARY_RECORD_FAILED",
            )
            diagnostics.fail_home_boundary(
                task_id,
                "home.boundary",
                "HOME_BOUNDARY_RECORD_FAILED",
            )
        except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
            return False
        _pop_diagnostics(context, task_id)
        return False
    _pop_diagnostics(context, task_id)
    return True


@AgentServer.custom_action("BeginTask")
class BeginTask(CustomAction):
    """Initialize isolated safety counters and task diagnostics."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _object_payload(argv)
            task_id = _task_id(payload)
            run_id = _run_id(payload, context)
            key = (_context_key(context), task_id)
            with _LOCK:
                if key in _ACTIVE_DIAGNOSTICS:
                    return False
                RUN_STORE.begin(task_id, managed=True)
                diagnostics = TaskDiagnostics(_diagnostics_root(), run_id=run_id)
                diagnostics.begin(task_id)
                _ACTIVE_DIAGNOSTICS[key] = diagnostics
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            return False
        return True


@AgentServer.custom_action("RecordTaskOutcome")
class RecordTaskOutcome(CustomAction):
    """Commit the task outcome; diagnostic persistence remains best-effort."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _object_payload(argv)
            task_id = _task_id(payload)
            raw_status = payload.get("status")
            status = TaskOutcomeStatus(raw_status)
            postcondition = payload.get("postcondition")
            if not isinstance(postcondition, str) or not postcondition.strip():
                raise ValueError("postcondition must be a non-empty string")
            error_code = payload.get("error_code")
            if error_code is not None and not isinstance(error_code, str):
                raise ValueError("error_code must be a string or None")
            native_fail_after_record = payload.get("native_fail_after_record", False)
            if not isinstance(native_fail_after_record, bool):
                raise ValueError("native_fail_after_record must be a boolean")
            defer_home_boundary = payload.get("defer_home_boundary", False)
            if not isinstance(defer_home_boundary, bool):
                raise ValueError("defer_home_boundary must be a boolean")
            if defer_home_boundary:
                if native_fail_after_record or status is TaskOutcomeStatus.FAILED:
                    raise ValueError("deferred business result cannot fail natively")
                if not seal_task(context, task_id, status, postcondition, error_code):
                    return False
            elif not finish_task(context, task_id, status, postcondition, error_code):
                return False
        except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
            return False
        return not native_fail_after_record


@AgentServer.custom_action("CompleteTaskBoundary")
class CompleteTaskBoundary(CustomAction):
    """Commit a sealed business result after the shared home boundary matches."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _object_payload(argv)
            boundary = payload.get("boundary", "home")
            if not isinstance(boundary, str) or boundary.strip().casefold() != "home":
                raise ValueError("boundary must be home")
            return complete_task_boundary(context, boundary)
        except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
            return False


@AgentServer.custom_action("FailStartupRecovery")
class FailStartupRecovery(CustomAction):
    """Record a readable GAME_START failure and stop without a business result.

    This is a control-plane terminal. It writes the stage-specific error to a
    JSONL ledger, emits the same information to the MFW log, and intentionally
    returns ``False`` so Maa emits ``Tasker.Task.Failed``. It does not touch
    RUN_STORE or create a business-task ``failed`` result.
    """

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
            record = {
                "schema_version": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
                "error_code": error_code,
                "postcondition": postcondition,
                "stage": payload.get("stage"),
                "expected": payload.get("expected"),
                "observed": payload.get("observed"),
                "root_cause": payload.get("root_cause"),
            }
            root = _diagnostics_root()
            root.mkdir(parents=True, exist_ok=True)
            with (root / "game_start_failures.jsonl").open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            _LOGGER.error(
                "[GAME_START_FAILURE] %s",
                json.dumps(record, ensure_ascii=False, sort_keys=True),
            )
        except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
            return False
        except OSError:
            _LOGGER.exception("[GAME_START_FAILURE] unable to persist startup failure")
        return False


@AgentServer.custom_action("RecordActiveTaskFailure")
class RecordActiveTaskFailure(CustomAction):
    """Close the one active business task when shared startup recovery fails.

    ``MJA_GAME_START`` is a shared nested pipeline and therefore cannot carry
    the business task id in its static resource node.  The old terminal node
    used ``StopTask`` directly, which made Maa report native success while the
    business result stayed ``running``.  Resolve the single active diagnostic
    binding instead and persist a truthful failure before aborting natively.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _object_payload(argv)
            postcondition = payload.get("postcondition")
            if not isinstance(postcondition, str) or not postcondition.strip():
                raise ValueError("postcondition must be a non-empty string")
            error_code = payload.get("error_code")
            if error_code is not None and not isinstance(error_code, str):
                raise ValueError("error_code must be a string or None")
            native_fail_after_record = payload.get("native_fail_after_record", True)
            if not isinstance(native_fail_after_record, bool):
                raise ValueError("native_fail_after_record must be a boolean")

            active_task_ids = _active_task_ids(context)
            if len(active_task_ids) != 1:
                return False
            task_id = active_task_ids[0]
            snapshot = RUN_STORE.snapshot(task_id)
            if snapshot.get("business_result_sealed") is True:
                diagnostics = diagnostics_for(context, task_id)
                if diagnostics is None:
                    return False
                RUN_STORE.fail_home_boundary(task_id, postcondition, error_code)
                diagnostics.fail_home_boundary(task_id, postcondition, error_code)
                _pop_diagnostics(context, task_id)
            elif not finish_task(
                context, task_id, TaskOutcomeStatus.FAILED, postcondition, error_code
            ):
                return False
        except (KeyError, RuntimeError, TypeError, ValueError, PermissionError):
            return False
        return not native_fail_after_record


__all__ = [
    "BeginTask",
    "CompleteTaskBoundary",
    "FailStartupRecovery",
    "RecordActiveTaskFailure",
    "RecordTaskOutcome",
    "diagnostics_for",
    "finish_task",
    "complete_task_boundary",
    "seal_task",
]
