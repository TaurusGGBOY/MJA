"""Small, bounded state-convergence primitives for the embedded MFW Agent.

This module deliberately does not know about Maa resources, business tasks, or
controllers.  It gives a future convergence router a stable vocabulary for
what it observed, which safe action it chose, and how much recovery budget is
left for this one invocation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from time import monotonic
from types import MappingProxyType
from typing import Any
from uuid import uuid4


class ConvergenceState(StrEnum):
    """Mutually ordered classes of surfaces seen by the shared router."""

    DANGEROUS = "dangerous"
    RESULT_PENDING = "result_pending"
    TASK_RESUMABLE = "task_resumable"
    SAFE_MODAL = "safe_modal"
    HOME = "home"
    STALE_PAGE = "stale_page"
    STARTUP_TRANSIENT = "startup_transient"
    APP_UNAVAILABLE = "app_unavailable"
    RUNTIME_TRANSIENT = "runtime_transient"
    UNKNOWN = "unknown"


class RecoveryAction(StrEnum):
    """Actions a convergence router may request from its caller."""

    RESUME_TASK = "resume_task"
    ENTER_TASK = "enter_task"
    DISMISS_MODAL = "dismiss_modal"
    RETURN_HOME = "return_home"
    WAIT = "wait"
    RESTART_SURFACE = "restart_surface"
    RELAUNCH = "relaunch"
    FAIL_CLOSED = "fail_closed"


class BudgetKind(StrEnum):
    """Finite resources owned by one convergence invocation."""

    MODAL_ACTIONS = "modal_actions"
    RETURN_HOME_ACTIONS = "return_home_actions"
    SURFACE_RESTARTS = "surface_restarts"
    LAUNCHES = "launches"
    WAIT_SECONDS = "wait_seconds"
    UNKNOWN_SECONDS = "unknown_seconds"
    TOTAL_SECONDS = "total_seconds"


class ConvergenceOutcome(StrEnum):
    """Terminal state of a convergence session."""

    CONVERGED = "converged"
    FAILED = "failed"


_STATE_ORDER: tuple[ConvergenceState, ...] = (
    ConvergenceState.DANGEROUS,
    ConvergenceState.RESULT_PENDING,
    ConvergenceState.TASK_RESUMABLE,
    ConvergenceState.SAFE_MODAL,
    ConvergenceState.HOME,
    ConvergenceState.STALE_PAGE,
    ConvergenceState.STARTUP_TRANSIENT,
    ConvergenceState.APP_UNAVAILABLE,
    ConvergenceState.RUNTIME_TRANSIENT,
    ConvergenceState.UNKNOWN,
)
STATE_PRIORITY: Mapping[ConvergenceState, int] = MappingProxyType(
    {state: priority for priority, state in enumerate(_STATE_ORDER)}
)

_STATE_ACTIONS: Mapping[ConvergenceState, tuple[RecoveryAction, ...]] = MappingProxyType(
    {
        ConvergenceState.DANGEROUS: (RecoveryAction.FAIL_CLOSED,),
        ConvergenceState.RESULT_PENDING: (RecoveryAction.RETURN_HOME,),
        ConvergenceState.TASK_RESUMABLE: (RecoveryAction.RESUME_TASK,),
        ConvergenceState.SAFE_MODAL: (RecoveryAction.DISMISS_MODAL,),
        ConvergenceState.HOME: (RecoveryAction.ENTER_TASK,),
        ConvergenceState.STALE_PAGE: (RecoveryAction.RETURN_HOME,),
        ConvergenceState.STARTUP_TRANSIENT: (RecoveryAction.WAIT,),
        ConvergenceState.APP_UNAVAILABLE: (RecoveryAction.RELAUNCH,),
        ConvergenceState.RUNTIME_TRANSIENT: (RecoveryAction.WAIT,),
        ConvergenceState.UNKNOWN: (RecoveryAction.FAIL_CLOSED,),
    }
)

_ACTION_BUDGETS: Mapping[RecoveryAction, BudgetKind] = MappingProxyType(
    {
        RecoveryAction.DISMISS_MODAL: BudgetKind.MODAL_ACTIONS,
        RecoveryAction.RETURN_HOME: BudgetKind.RETURN_HOME_ACTIONS,
        RecoveryAction.RESTART_SURFACE: BudgetKind.SURFACE_RESTARTS,
        RecoveryAction.RELAUNCH: BudgetKind.LAUNCHES,
        RecoveryAction.WAIT: BudgetKind.WAIT_SECONDS,
    }
)


def _enum_value(value: Any, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str) and value.strip():
        candidate = value.strip().lower()
        try:
            return enum_type(candidate)
        except ValueError:
            try:
                return enum_type[candidate.upper()]
            except KeyError as exc:
                raise ValueError(f"invalid {field_name}: {value}") from exc
    raise ValueError(f"{field_name} must be a supported string")


def _task_key(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be non-empty")
    return task_id.strip().upper()


def _positive_number(value: Any, field_name: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    result = float(value)
    if not isfinite(result) or (result < 0 if allow_zero else result <= 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field_name} must be {qualifier}")
    return result


def _non_negative_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def classify_state(
    candidates: Iterable[ConvergenceState | str] | ConvergenceState | str,
) -> ConvergenceState:
    """Choose the highest-priority state from recognizer candidates.

    No candidate is treated as ``UNKNOWN``.  Invalid candidate names raise so
    a recognizer configuration error cannot silently become a safe action.
    """

    if isinstance(candidates, (ConvergenceState, str)):
        values: Iterable[ConvergenceState | str] = (candidates,)
    else:
        values = candidates

    normalized = {
        _enum_value(candidate, ConvergenceState, "state") for candidate in values
    }
    if not normalized:
        return ConvergenceState.UNKNOWN
    return min(normalized, key=STATE_PRIORITY.__getitem__)


def recommended_actions(state: ConvergenceState | str) -> tuple[RecoveryAction, ...]:
    """Return the only safe first action(s) for a classified state."""

    normalized = _enum_value(state, ConvergenceState, "state")
    return _STATE_ACTIONS[normalized]  # type: ignore[index]


@dataclass(frozen=True, slots=True)
class ConvergenceLimits:
    """Default per-invocation limits from the shared convergence contract."""

    max_duration_seconds: float = 120.0
    max_modal_actions: int = 2
    max_return_home_actions: int = 3
    max_surface_restarts: int = 1
    max_launches: int = 2
    max_wait_seconds: float = 30.0
    max_unknown_seconds: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_duration_seconds",
            _positive_number(self.max_duration_seconds, "max_duration_seconds"),
        )
        object.__setattr__(
            self,
            "max_wait_seconds",
            _positive_number(self.max_wait_seconds, "max_wait_seconds", allow_zero=True),
        )
        object.__setattr__(
            self,
            "max_unknown_seconds",
            _positive_number(self.max_unknown_seconds, "max_unknown_seconds", allow_zero=True),
        )
        for field_name in (
            "max_modal_actions",
            "max_return_home_actions",
            "max_surface_restarts",
            "max_launches",
        ):
            _non_negative_integer(getattr(self, field_name), field_name)


DEFAULT_CONVERGENCE_LIMITS = ConvergenceLimits()


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Detached budget state suitable for diagnostics and assertions."""

    elapsed_seconds: float
    modal_actions: int
    return_home_actions: int
    surface_restarts: int
    launches: int
    wait_seconds: float
    unknown_seconds: float
    closed: bool

    def remaining(self, kind: BudgetKind | str, limits: ConvergenceLimits) -> float:
        """Return remaining capacity for one budget kind."""

        normalized = _enum_value(kind, BudgetKind, "budget kind")
        limits_by_kind: Mapping[BudgetKind, float] = {
            BudgetKind.MODAL_ACTIONS: float(limits.max_modal_actions),
            BudgetKind.RETURN_HOME_ACTIONS: float(limits.max_return_home_actions),
            BudgetKind.SURFACE_RESTARTS: float(limits.max_surface_restarts),
            BudgetKind.LAUNCHES: float(limits.max_launches),
            BudgetKind.WAIT_SECONDS: limits.max_wait_seconds,
            BudgetKind.UNKNOWN_SECONDS: limits.max_unknown_seconds,
            BudgetKind.TOTAL_SECONDS: limits.max_duration_seconds,
        }
        consumed: Mapping[BudgetKind, float] = {
            BudgetKind.MODAL_ACTIONS: float(self.modal_actions),
            BudgetKind.RETURN_HOME_ACTIONS: float(self.return_home_actions),
            BudgetKind.SURFACE_RESTARTS: float(self.surface_restarts),
            BudgetKind.LAUNCHES: float(self.launches),
            BudgetKind.WAIT_SECONDS: self.wait_seconds,
            BudgetKind.UNKNOWN_SECONDS: self.unknown_seconds,
            BudgetKind.TOTAL_SECONDS: self.elapsed_seconds,
        }
        return max(0.0, limits_by_kind[normalized] - consumed[normalized])  # type: ignore[index]


@dataclass(frozen=True, slots=True)
class StateObservation:
    """One classified frame observation in a convergence session."""

    task_id: str
    state: ConvergenceState
    previous_state: ConvergenceState | None
    evidence: str
    frame_id: str | None
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """One requested recovery action and its post-request result."""

    task_id: str
    action: RecoveryAction
    state: ConvergenceState | None
    evidence: str
    frame_id: str | None
    succeeded: bool
    elapsed_seconds: float
    budget: BudgetSnapshot


@dataclass(frozen=True, slots=True)
class ConvergenceSnapshot:
    """Immutable, detached view of a convergence session."""

    session_id: str
    task_id: str
    outcome: ConvergenceOutcome | None
    last_state: ConvergenceState | None
    budget: BudgetSnapshot
    observations: tuple[StateObservation, ...]
    actions: tuple[ActionRecord, ...]


class BudgetExceeded(RuntimeError):
    """Raised when an action or state observation exceeds its local budget."""

    def __init__(
        self,
        kind: BudgetKind,
        *,
        limit: float,
        consumed: float,
        requested: float,
    ) -> None:
        self.kind = kind
        self.limit = limit
        self.consumed = consumed
        self.requested = requested
        super().__init__(
            f"convergence budget exceeded: {kind.value} "
            f"{consumed:g}+{requested:g}>{limit:g}"
        )


class ConvergenceSession:
    """Own one isolated, finite convergence attempt.

    The session is intentionally independent of ``TaskRunStore``.  A caller
    may create several sessions while one business task remains active, but a
    session can never spend another session's budget or mutate task counters.
    """

    def __init__(
        self,
        task_id: str,
        *,
        limits: ConvergenceLimits = DEFAULT_CONVERGENCE_LIMITS,
        clock: Callable[[], float] = monotonic,
        session_id: str | None = None,
    ) -> None:
        if not isinstance(limits, ConvergenceLimits):
            raise TypeError("limits must be ConvergenceLimits")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.task_id = _task_key(task_id)
        self.limits = limits
        self.session_id = session_id.strip() if isinstance(session_id, str) else uuid4().hex
        if not self.session_id:
            raise ValueError("session_id must be non-empty")
        self._clock = clock
        self._started_at = self._read_clock()
        self._last_clock = self._started_at
        self._last_state: ConvergenceState | None = None
        self._unknown_started_at: float | None = None
        self._unknown_seconds = 0.0
        self._spent: dict[BudgetKind, float] = {
            BudgetKind.MODAL_ACTIONS: 0.0,
            BudgetKind.RETURN_HOME_ACTIONS: 0.0,
            BudgetKind.SURFACE_RESTARTS: 0.0,
            BudgetKind.LAUNCHES: 0.0,
            BudgetKind.WAIT_SECONDS: 0.0,
        }
        self._observations: list[StateObservation] = []
        self._actions: list[ActionRecord] = []
        self._outcome: ConvergenceOutcome | None = None

    @property
    def closed(self) -> bool:
        return self._outcome is not None

    @property
    def outcome(self) -> ConvergenceOutcome | None:
        return self._outcome

    @property
    def last_state(self) -> ConvergenceState | None:
        return self._last_state

    def observe(
        self,
        state: ConvergenceState | str,
        *,
        evidence: str = "",
        frame_id: str | None = None,
    ) -> StateObservation:
        """Record a classified observation and enforce unknown-state time."""

        self._ensure_open()
        now = self._check_wall_clock()
        normalized = _enum_value(state, ConvergenceState, "state")
        previous = self._last_state
        observation = StateObservation(
            task_id=self.task_id,
            state=normalized,
            previous_state=previous,
            evidence=_text(evidence, "evidence", allow_empty=True),
            frame_id=_optional_text(frame_id, "frame_id"),
            elapsed_seconds=now - self._started_at,
        )
        self._observations.append(observation)
        self._last_state = normalized

        if normalized is ConvergenceState.UNKNOWN:
            if self._unknown_started_at is None:
                self._unknown_started_at = now
            self._unknown_seconds = now - self._unknown_started_at
            if self._unknown_seconds >= self.limits.max_unknown_seconds:
                self._fail_budget(
                    BudgetKind.UNKNOWN_SECONDS,
                    limit=self.limits.max_unknown_seconds,
                    consumed=self._unknown_seconds,
                    requested=0.0,
                )
        else:
            self._unknown_started_at = None
            self._unknown_seconds = 0.0
        return observation

    def record_action(
        self,
        action: RecoveryAction | str,
        *,
        state: ConvergenceState | str | None = None,
        evidence: str = "",
        frame_id: str | None = None,
        succeeded: bool = True,
    ) -> ActionRecord:
        """Record an action, consuming its budget before it is attempted."""

        self._ensure_open()
        now = self._check_wall_clock()
        normalized_action = _enum_value(action, RecoveryAction, "action")
        normalized_state = (
            _enum_value(state, ConvergenceState, "state") if state is not None else self._last_state
        )
        if not isinstance(succeeded, bool):
            raise ValueError("succeeded must be a boolean")
        budget_kind = _ACTION_BUDGETS.get(normalized_action)
        if budget_kind is not None:
            self._spend(budget_kind, 1.0)
        record = ActionRecord(
            task_id=self.task_id,
            action=normalized_action,
            state=normalized_state,
            evidence=_text(evidence, "evidence", allow_empty=True),
            frame_id=_optional_text(frame_id, "frame_id"),
            succeeded=bool(succeeded),
            elapsed_seconds=now - self._started_at,
            budget=self.budget_snapshot(),
        )
        self._actions.append(record)
        return record

    def spend(
        self,
        kind: BudgetKind | RecoveryAction | str,
        amount: int | float = 1,
    ) -> BudgetSnapshot:
        """Consume a finite action or time budget and return the new snapshot."""

        self._ensure_open()
        self._check_wall_clock()
        budget_kind = _budget_kind(kind)
        self._spend(budget_kind, amount)
        return self.budget_snapshot()

    def finish(self, outcome: ConvergenceOutcome | str) -> ConvergenceSnapshot:
        """Close the session exactly once and return its detached snapshot."""

        self._ensure_open()
        self._outcome = ConvergenceOutcome(
            _enum_value(outcome, ConvergenceOutcome, "outcome")
        )
        return self.snapshot()

    def budget_snapshot(self) -> BudgetSnapshot:
        """Return current finite-budget usage without closing the session."""

        elapsed = max(0.0, self._last_clock - self._started_at)
        return BudgetSnapshot(
            elapsed_seconds=elapsed,
            modal_actions=int(self._spent[BudgetKind.MODAL_ACTIONS]),
            return_home_actions=int(self._spent[BudgetKind.RETURN_HOME_ACTIONS]),
            surface_restarts=int(self._spent[BudgetKind.SURFACE_RESTARTS]),
            launches=int(self._spent[BudgetKind.LAUNCHES]),
            wait_seconds=self._spent[BudgetKind.WAIT_SECONDS],
            unknown_seconds=self._unknown_seconds,
            closed=self.closed,
        )

    def snapshot(self) -> ConvergenceSnapshot:
        """Return a detached, immutable view of all recorded evidence."""

        return ConvergenceSnapshot(
            session_id=self.session_id,
            task_id=self.task_id,
            outcome=self._outcome,
            last_state=self._last_state,
            budget=self.budget_snapshot(),
            observations=tuple(self._observations),
            actions=tuple(self._actions),
        )

    def _spend(self, kind: BudgetKind, amount: int | float) -> None:
        value = _positive_number(amount, "amount")
        if kind in {
            BudgetKind.MODAL_ACTIONS,
            BudgetKind.RETURN_HOME_ACTIONS,
            BudgetKind.SURFACE_RESTARTS,
            BudgetKind.LAUNCHES,
        } and value != int(value):
            raise ValueError(f"amount for {kind.value} must be an integer")

        limits: Mapping[BudgetKind, float] = {
            BudgetKind.MODAL_ACTIONS: float(self.limits.max_modal_actions),
            BudgetKind.RETURN_HOME_ACTIONS: float(self.limits.max_return_home_actions),
            BudgetKind.SURFACE_RESTARTS: float(self.limits.max_surface_restarts),
            BudgetKind.LAUNCHES: float(self.limits.max_launches),
            BudgetKind.WAIT_SECONDS: self.limits.max_wait_seconds,
        }
        if kind not in limits:
            if kind is BudgetKind.UNKNOWN_SECONDS:
                raise ValueError("unknown_seconds is charged by observe")
            raise ValueError("total_seconds is charged by the session clock")
        current = self._spent[kind]
        limit = limits[kind]
        if current + value > limit:
            self._fail_budget(kind, limit=limit, consumed=current, requested=value)
        self._spent[kind] = current + value

    def _fail_budget(
        self,
        kind: BudgetKind,
        *,
        limit: float,
        consumed: float,
        requested: float,
    ) -> None:
        self._outcome = ConvergenceOutcome.FAILED
        raise BudgetExceeded(kind, limit=limit, consumed=consumed, requested=requested)

    def _check_wall_clock(self) -> float:
        now = self._read_clock()
        elapsed = now - self._started_at
        if elapsed >= self.limits.max_duration_seconds:
            self._fail_budget(
                BudgetKind.TOTAL_SECONDS,
                limit=self.limits.max_duration_seconds,
                consumed=elapsed,
                requested=0.0,
            )
        return now

    def _read_clock(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("clock must return a number")
        result = float(value)
        if not isfinite(result):
            raise ValueError("clock must return a finite number")
        if hasattr(self, "_last_clock") and result < self._last_clock:
            raise ValueError("clock must be monotonic")
        self._last_clock = result
        return result

    def _ensure_open(self) -> None:
        if self.closed:
            raise RuntimeError("convergence session is closed")


def _budget_kind(value: BudgetKind | RecoveryAction | str) -> BudgetKind:
    if isinstance(value, RecoveryAction):
        try:
            return _ACTION_BUDGETS[value]
        except KeyError as exc:
            raise ValueError(f"action has no finite budget: {value.value}") from exc
    if isinstance(value, BudgetKind):
        return value
    if isinstance(value, str):
        try:
            return _enum_value(value, BudgetKind, "budget kind")  # type: ignore[return-value]
        except ValueError:
            action = _enum_value(value, RecoveryAction, "action")
            try:
                return _ACTION_BUDGETS[action]  # type: ignore[index]
            except KeyError as exc:
                raise ValueError(f"action has no finite budget: {action.value}") from exc
    raise ValueError("kind must be a budget kind or budgeted recovery action")


def _text(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    result = value.strip()
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must be non-empty")
    return result


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


__all__ = [
    "ACTION_BUDGETS",
    "ActionRecord",
    "BudgetExceeded",
    "BudgetKind",
    "BudgetSnapshot",
    "ConvergenceLimits",
    "ConvergenceOutcome",
    "ConvergenceSession",
    "ConvergenceSnapshot",
    "ConvergenceState",
    "DEFAULT_CONVERGENCE_LIMITS",
    "RecoveryAction",
    "STATE_PRIORITY",
    "StateObservation",
    "classify_state",
    "recommended_actions",
]


# Public read-only view for callers that need to know which actions consume a
# session budget without reaching into the session implementation.
ACTION_BUDGETS = _ACTION_BUDGETS
