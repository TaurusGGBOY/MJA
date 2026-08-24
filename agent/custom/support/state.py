"""Thread-safe, run-local counters for MFW task safety budgets."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from typing import Any

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


class SafetyBudgetStore:
    """Keep only bounded action, resource, and marker state for one task run."""

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

    def begin(self, task_id: str, *, managed: bool = False) -> None:
        key, policy = self._policy(task_id)
        with self._lock:
            if (
                managed
                and key in self._runs
                and self._runs[key].get("managed") is True
            ):
                raise PermissionError(f"task {key} already has an active safety run")
            self._runs[key] = {
                "actions": {},
                "resources": {},
                "markers": {},
                "steps": 0,
                "max_steps": policy.max_steps,
                "managed": bool(managed),
            }

    def end(self, task_id: str) -> None:
        key = _task_key(task_id)
        with self._lock:
            self._runs.pop(key, None)

    def increment(self, task_id: str, action_id: str, amount: int = 1) -> int:
        action = _counter_key(action_id, "action_id")
        amount = _positive_amount(amount)
        with self._lock:
            key, policy, run = self._run(task_id)
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
        resource = resource_id.strip() if isinstance(resource_id, str) else resource_id
        if not isinstance(resource, str) or not resource:
            raise ValueError("resource_id must be non-empty")
        amount = _positive_amount(amount)
        with self._lock:
            key, policy, run = self._run(task_id)
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

    def set_marker(self, task_id: str, marker: str, value: Any) -> None:
        key_name = _counter_key(marker, "marker")
        with self._lock:
            _, _, run = self._run(task_id)
            run["markers"][key_name] = value

    def get_marker(self, task_id: str, marker: str, default: Any = None) -> Any:
        key_name = _counter_key(marker, "marker")
        with self._lock:
            _, _, run = self._run(task_id)
            return run["markers"].get(key_name, default)

    def increment_marker(self, task_id: str, marker: str, amount: int = 1) -> int:
        key_name = _counter_key(marker, "marker")
        amount = _positive_amount(amount)
        with self._lock:
            _, _, run = self._run(task_id)
            current = run["markers"].get(key_name, 0)
            if isinstance(current, bool) or not isinstance(current, int) or current < 0:
                raise ValueError(f"marker {key_name} is not a non-negative integer")
            new_value = current + amount
            run["markers"][key_name] = new_value
            return new_value

    def snapshot(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            _, _, run = self._run(task_id)
            return {
                "actions": dict(run["actions"]),
                "resources": dict(run["resources"]),
                "markers": dict(run["markers"]),
                "steps": run["steps"],
                "max_steps": run["max_steps"],
            }


class TaskRunStore(SafetyBudgetStore):
    """Compatibility name for tests and callers that still use RUN_STORE."""


SAFETY_BUDGETS = SafetyBudgetStore()
RUN_STORE = SAFETY_BUDGETS

__all__ = ["RUN_STORE", "SAFETY_BUDGETS", "SafetyBudgetStore", "TaskRunStore"]
