"""Native MFW task identity and safety-budget session bindings."""

from __future__ import annotations

from threading import RLock

from .state import SAFETY_BUDGETS, SafetyBudgetStore


def _native_task_key(native_task_id: int) -> int:
    if isinstance(native_task_id, bool) or not isinstance(native_task_id, int):
        raise TypeError("native_task_id must be an integer")
    if native_task_id < 0:
        raise ValueError("native_task_id must be non-negative")
    return native_task_id


class TaskSessionRegistry:
    """Bind one MFW native task ID to one safety-only business session."""

    def __init__(self, budgets: SafetyBudgetStore = SAFETY_BUDGETS) -> None:
        self._budgets = budgets
        self._sessions: dict[int, str] = {}
        self._lock = RLock()

    def begin(self, native_task_id: int, business_task_id: str) -> None:
        native_key = _native_task_key(native_task_id)
        if not isinstance(business_task_id, str) or not business_task_id.strip():
            raise ValueError("business_task_id must be non-empty")
        business_key = business_task_id.strip().upper()
        with self._lock:
            if native_key in self._sessions:
                raise PermissionError(
                    f"native task {native_key} already has an active session"
                )
            self._budgets.begin(business_key, managed=True)
            self._sessions[native_key] = business_key

    def business_task_id(self, native_task_id: int) -> str | None:
        native_key = _native_task_key(native_task_id)
        with self._lock:
            return self._sessions.get(native_key)

    def end(self, native_task_id: int) -> str | None:
        native_key = _native_task_key(native_task_id)
        with self._lock:
            business_key = self._sessions.get(native_key)
            if business_key is None:
                return None
            self._budgets.end(business_key)
            del self._sessions[native_key]
            return business_key


TASK_SESSIONS = TaskSessionRegistry()

__all__ = ["TASK_SESSIONS", "TaskSessionRegistry"]
