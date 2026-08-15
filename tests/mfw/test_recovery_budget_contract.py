from __future__ import annotations

import pytest

from agent.custom.support.convergence import (
    BudgetExceeded,
    BudgetKind,
    ConvergenceLimits,
    ConvergenceOutcome,
    ConvergenceSession,
    ConvergenceState,
    RecoveryAction,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_default_limits_match_the_shared_convergence_contract() -> None:
    limits = ConvergenceLimits()

    assert limits.max_duration_seconds == 120.0
    assert limits.max_modal_actions == 2
    assert limits.max_return_home_actions == 3
    assert limits.max_surface_restarts == 1
    assert limits.max_launches == 2
    assert limits.max_wait_seconds == 30.0
    assert limits.max_unknown_seconds == 10.0


def test_modal_budget_is_atomic_and_closes_the_session_when_exhausted() -> None:
    session = ConvergenceSession("MAIL_REWARD_DAILY")
    session.spend(RecoveryAction.DISMISS_MODAL)
    session.spend(RecoveryAction.DISMISS_MODAL)

    with pytest.raises(BudgetExceeded) as caught:
        session.spend(RecoveryAction.DISMISS_MODAL)

    assert caught.value.kind is BudgetKind.MODAL_ACTIONS
    assert caught.value.consumed == 2
    assert caught.value.requested == 1
    assert session.budget_snapshot().modal_actions == 2
    assert session.outcome is ConvergenceOutcome.FAILED


def test_recovery_budgets_are_isolated_per_convergence_session() -> None:
    first = ConvergenceSession("MAIL_REWARD_DAILY")
    second = ConvergenceSession("MAIL_REWARD_DAILY")

    first.spend(RecoveryAction.RESTART_SURFACE)
    second.spend(RecoveryAction.RESTART_SURFACE)

    with pytest.raises(BudgetExceeded, match="surface_restarts"):
        first.spend(RecoveryAction.RESTART_SURFACE)
    with pytest.raises(BudgetExceeded, match="surface_restarts"):
        second.spend(RecoveryAction.RESTART_SURFACE)


def test_wait_budget_accepts_fractional_seconds_but_never_overcommits() -> None:
    session = ConvergenceSession("MAIL_REWARD_DAILY")
    session.spend(BudgetKind.WAIT_SECONDS, 29.5)

    with pytest.raises(BudgetExceeded) as caught:
        session.spend(RecoveryAction.WAIT, 0.6)

    assert caught.value.kind is BudgetKind.WAIT_SECONDS
    assert session.budget_snapshot().wait_seconds == 0.0 + 29.5


def test_unknown_state_budget_is_contiguous_and_resets_after_known_state() -> None:
    clock = FakeClock()
    session = ConvergenceSession("MAIL_REWARD_DAILY", clock=clock)

    session.observe(ConvergenceState.UNKNOWN, evidence="no recognizer")
    clock.advance(9.0)
    session.observe(ConvergenceState.UNKNOWN, evidence="still no recognizer")
    assert session.budget_snapshot().unknown_seconds == 9.0

    session.observe(ConvergenceState.HOME, evidence="home recovered")
    assert session.budget_snapshot().unknown_seconds == 0.0

    session.observe(ConvergenceState.UNKNOWN, evidence="new unknown interval")
    clock.advance(10.0)
    with pytest.raises(BudgetExceeded) as caught:
        session.observe(ConvergenceState.UNKNOWN, evidence="unknown interval expired")

    assert caught.value.kind is BudgetKind.UNKNOWN_SECONDS
    assert session.outcome is ConvergenceOutcome.FAILED


def test_total_session_time_is_also_bounded() -> None:
    clock = FakeClock()
    session = ConvergenceSession(
        "MAIL_REWARD_DAILY",
        clock=clock,
        limits=ConvergenceLimits(max_duration_seconds=5.0),
    )
    clock.advance(5.0)

    with pytest.raises(BudgetExceeded) as caught:
        session.observe(ConvergenceState.HOME)

    assert caught.value.kind is BudgetKind.TOTAL_SECONDS
    assert session.outcome is ConvergenceOutcome.FAILED


def test_budget_snapshot_remaining_is_detached_from_future_spend() -> None:
    session = ConvergenceSession("MAIL_REWARD_DAILY")
    before = session.budget_snapshot()
    session.spend(RecoveryAction.RETURN_HOME)
    after = session.budget_snapshot()

    assert before.return_home_actions == 0
    assert before.remaining(BudgetKind.RETURN_HOME_ACTIONS, session.limits) == 3
    assert after.return_home_actions == 1
    assert after.remaining(BudgetKind.RETURN_HOME_ACTIONS, session.limits) == 2


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"max_modal_actions": -1}, "max_modal_actions"),
        ({"max_return_home_actions": -1}, "max_return_home_actions"),
        ({"max_surface_restarts": -1}, "max_surface_restarts"),
        ({"max_launches": -1}, "max_launches"),
    ],
)
def test_negative_action_limits_are_rejected(kwargs: dict[str, int], field: str) -> None:
    with pytest.raises(ValueError, match=field):
        ConvergenceLimits(**kwargs)
