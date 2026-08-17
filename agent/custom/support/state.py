"""Thread-safe, run-local counters for MFW task safety budgets."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from typing import Any

from .models import TaskOutcomeStatus
from .policy import TASK_POLICIES


def _task_key(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be non-empty")
    return task_id.strip().upper()


def _counter_key(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value.strip().lower()


def _positive_amount(amount: int) -> int:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("amount must be a positive integer")
    return amount


class TaskRunStore:
    """Keep one isolated set of policy counters per task run.

    Every limit check and corresponding mutation occurs under the same reentrant
    lock. A rejected operation therefore cannot consume part of its budget.
    """

    def __init__(self, policies: Mapping[str, Any] = TASK_POLICIES) -> None:
        self._policies = policies
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def _policy(self, task_id: str):
        key = _task_key(task_id)
        try:
            return key, self._policies[key]
        except KeyError as exc:
            raise KeyError(f"unknown task: {key}") from exc

    def _run(self, task_id: str) -> tuple[str, Any, dict[str, Any]]:
        key, policy = self._policy(task_id)
        try:
            run = self._runs[key]
        except KeyError as exc:
            raise RuntimeError(f"task {key} has not begun") from exc
        return key, policy, run

    @staticmethod
    def _require_business_mutable(key: str, run: Mapping[str, Any]) -> None:
        if run.get("business_result_sealed") is True:
            raise PermissionError(f"task {key} business result is sealed")

    @staticmethod
    def _require_action_mutable(
        key: str,
        policy: Any,
        run: Mapping[str, Any],
        action: str,
    ) -> None:
        """Keep business actions closed while allowing explicit boundary cleanup."""

        if run.get("business_result_sealed") is not True:
            return
        if action not in policy.cleanup_action_ids:
            raise PermissionError(f"task {key} business result is sealed")
        if run.get("home_boundary_pending") is not True:
            raise PermissionError(f"task {key} home boundary is already closed")

    def begin(self, task_id: str, *, managed: bool = False) -> None:
        key, policy = self._policy(task_id)
        with self._lock:
            existing = self._runs.get(key)
            if (
                managed
                and existing is not None
                and existing.get("managed") is True
                and existing.get("final_status") is None
            ):
                raise PermissionError(f"task {key} already has an active managed run")
            self._runs[key] = {
                "actions": {},
                "resources": {},
                "markers": {},
                "steps": 0,
                "status": None,
                "postcondition": None,
                "error_code": None,
                "business_result_sealed": False,
                "home_boundary_pending": False,
                "home_boundary_status": None,
                "final_status": None,
                "final_boundary_failure_reason": None,
                "business_result": None,
                "events": [],
                "managed": bool(managed),
                "max_steps": policy.max_steps,
            }

    def increment(self, task_id: str, action_id: str, amount: int = 1) -> int:
        """Atomically consume an action and return its new count."""

        action = _counter_key(action_id, "action_id")
        amount = _positive_amount(amount)
        with self._lock:
            key, policy, run = self._run(task_id)
            self._require_action_mutable(key, policy, run, action)
            try:
                limit = policy.action_caps[action]
            except KeyError as exc:
                raise PermissionError(f"unknown action for {key}: {action}") from exc

            current = run["actions"].get(action, 0)
            if current + amount > limit:
                raise PermissionError(f"action limit exceeded: {key}/{action}")
            if run["steps"] + amount > policy.max_steps:
                raise PermissionError(f"step limit exceeded: {key}")

            new_count = current + amount
            run["actions"][action] = new_count
            run["steps"] += amount
            return new_count

    def consume_resource(self, task_id: str, resource_id: str, amount: int = 1) -> int:
        """Atomically consume a finite resource budget and return its new count."""

        resource = resource_id.strip() if isinstance(resource_id, str) else resource_id
        if not isinstance(resource, str) or not resource:
            raise ValueError("resource_id must be non-empty")
        amount = _positive_amount(amount)
        with self._lock:
            key, policy, run = self._run(task_id)
            self._require_business_mutable(key, run)
            try:
                limit = policy.resource_caps[resource]
            except KeyError as exc:
                raise PermissionError(f"unknown resource for {key}: {resource}") from exc

            current = run["resources"].get(resource, 0)
            if current + amount > limit:
                raise PermissionError(f"resource limit exceeded: {key}/{resource}")

            new_count = current + amount
            run["resources"][resource] = new_count
            return new_count

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
            _, _, run = self._run(key)
            self._require_business_mutable(key, run)
            run["status"] = outcome
            run["postcondition"] = postcondition.strip()
            run["error_code"] = error_code
            run["final_status"] = outcome
            run["home_boundary_pending"] = False
            run["home_boundary_status"] = "failed" if outcome is TaskOutcomeStatus.FAILED else "completed"
            run["final_boundary_failure_reason"] = None
            run["events"].append({"name": "task_finished"})

    def seal_business_result(
        self,
        task_id: str,
        status: TaskOutcomeStatus,
        postcondition: str,
        error_code: str | None,
    ) -> None:
        """Seal business evidence while leaving the home boundary pending.

        Failure is intentionally sealable too: a failed business outcome still
        has to pass through the same home-boundary cleanup as success and
        already-complete outcomes. The boundary decides the final status.
        """

        key = _task_key(task_id)
        outcome = TaskOutcomeStatus(status)
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("postcondition must be non-empty")
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("error_code must be a string or None")
        with self._lock:
            _, _, run = self._run(key)
            if run.get("business_result_sealed") is True:
                raise PermissionError(f"task {key} business result is already sealed")
            normalized_postcondition = postcondition.strip()
            run["status"] = outcome
            run["postcondition"] = normalized_postcondition
            run["error_code"] = error_code
            run["business_result"] = {
                "status": outcome,
                "postcondition": normalized_postcondition,
                "error_code": error_code,
            }
            run["business_result_sealed"] = True
            run["home_boundary_pending"] = True
            run["home_boundary_status"] = "pending"
            run["final_status"] = None
            run["final_boundary_failure_reason"] = None
            run["events"].append({"name": "business_result_sealed"})

    def complete_home_boundary(self, task_id: str, boundary: str = "home") -> None:
        """Commit final success after explicit home evidence is observed."""

        key = _task_key(task_id)
        if not isinstance(boundary, str) or boundary.strip().casefold() != "home":
            raise ValueError("boundary must be home")
        with self._lock:
            _, _, run = self._run(key)
            if run.get("business_result_sealed") is not True:
                raise PermissionError(f"task {key} has no sealed business result")
            if run.get("home_boundary_pending") is not True:
                raise PermissionError(f"task {key} home boundary is already closed")
            outcome = run["status"]
            if not isinstance(outcome, TaskOutcomeStatus):
                raise RuntimeError(f"task {key} has no business outcome")
            run["home_boundary_pending"] = False
            run["home_boundary_status"] = "completed"
            run["final_status"] = outcome
            run["final_boundary_failure_reason"] = None
            run["events"].append({"name": "home_boundary_completed"})

    def fail_home_boundary(
        self,
        task_id: str,
        postcondition: str,
        error_code: str | None,
    ) -> None:
        """Persist a boundary failure without discarding sealed business proof."""

        key = _task_key(task_id)
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("postcondition must be non-empty")
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("error_code must be a string or None")
        with self._lock:
            _, _, run = self._run(key)
            sealed = run.get("business_result_sealed") is True
            if sealed:
                run["postcondition"] = run["business_result"]["postcondition"]
                run["final_boundary_failure_reason"] = "HOME_BOUNDARY_FAILED"
            else:
                run["postcondition"] = postcondition.strip()
                run["final_boundary_failure_reason"] = "BUSINESS_RESULT_NOT_SEALED"
            run["status"] = TaskOutcomeStatus.FAILED
            run["error_code"] = error_code
            run["home_boundary_pending"] = False
            run["home_boundary_status"] = "failed"
            run["final_status"] = TaskOutcomeStatus.FAILED
            run["events"].append({"name": "home_boundary_failed"})

    def set_marker(self, task_id: str, marker: str, value: Any) -> None:
        """Store one run-local observation used by a later guarded probe."""

        key_name = _counter_key(marker, "marker")
        with self._lock:
            key, _, run = self._run(task_id)
            self._require_business_mutable(key, run)
            run["markers"][key_name] = value

    def get_marker(self, task_id: str, marker: str, default: Any = None) -> Any:
        """Read one run-local observation without exposing mutable run state."""

        key_name = _counter_key(marker, "marker")
        with self._lock:
            _, _, run = self._run(task_id)
            return run["markers"].get(key_name, default)

    def increment_marker(self, task_id: str, marker: str, amount: int = 1) -> int:
        """Increment a bounded integer observation under the run lock."""

        key_name = _counter_key(marker, "marker")
        amount = _positive_amount(amount)
        with self._lock:
            key, _, run = self._run(task_id)
            self._require_business_mutable(key, run)
            current = run["markers"].get(key_name, 0)
            if isinstance(current, bool) or not isinstance(current, int) or current < 0:
                raise ValueError(f"marker {key_name} is not a non-negative integer")
            new_value = current + amount
            run["markers"][key_name] = new_value
            return new_value

    def snapshot(self, task_id: str) -> dict[str, Any]:
        """Return a detached snapshot suitable for diagnostics or tests."""

        with self._lock:
            _, _, run = self._run(task_id)
            return {
                "actions": dict(run["actions"]),
                "resources": dict(run["resources"]),
                "markers": dict(run["markers"]),
                "steps": run["steps"],
                "max_steps": run["max_steps"],
                "status": run["status"],
                "postcondition": run["postcondition"],
                "error_code": run["error_code"],
                "business_result_sealed": run["business_result_sealed"],
                "home_boundary_pending": run["home_boundary_pending"],
                "home_boundary_status": run["home_boundary_status"],
                "final_status": run["final_status"],
                "final_boundary_failure_reason": run["final_boundary_failure_reason"],
                "business_result": (
                    dict(run["business_result"]) if run["business_result"] else None
                ),
                "events": [dict(event) for event in run["events"]],
            }


RUN_STORE = TaskRunStore()

__all__ = ["RUN_STORE", "TaskRunStore"]
