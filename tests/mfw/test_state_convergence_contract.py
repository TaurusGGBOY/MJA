from __future__ import annotations

import pytest

from agent.custom.support.convergence import (
    ConvergenceOutcome,
    ConvergenceSession,
    ConvergenceState,
    RecoveryAction,
    classify_state,
    recommended_actions,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_classifier_uses_the_safety_first_priority_order() -> None:
    assert classify_state(
        [
            ConvergenceState.RUNTIME_TRANSIENT,
            ConvergenceState.HOME,
            ConvergenceState.TASK_RESUMABLE,
            ConvergenceState.DANGEROUS,
        ]
    ) is ConvergenceState.DANGEROUS
    assert classify_state(
        [ConvergenceState.STALE_PAGE, ConvergenceState.RESULT_PENDING]
    ) is ConvergenceState.RESULT_PENDING
    assert classify_state([]) is ConvergenceState.UNKNOWN


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (ConvergenceState.DANGEROUS, RecoveryAction.FAIL_CLOSED),
        (ConvergenceState.RESULT_PENDING, RecoveryAction.RETURN_HOME),
        (ConvergenceState.TASK_RESUMABLE, RecoveryAction.RESUME_TASK),
        (ConvergenceState.SAFE_MODAL, RecoveryAction.DISMISS_MODAL),
        (ConvergenceState.HOME, RecoveryAction.ENTER_TASK),
        (ConvergenceState.STALE_PAGE, RecoveryAction.RETURN_HOME),
        (ConvergenceState.STARTUP_TRANSIENT, RecoveryAction.WAIT),
        (ConvergenceState.APP_UNAVAILABLE, RecoveryAction.RELAUNCH),
        (ConvergenceState.RUNTIME_TRANSIENT, RecoveryAction.WAIT),
        (ConvergenceState.UNKNOWN, RecoveryAction.FAIL_CLOSED),
    ],
)
def test_each_state_has_one_safe_first_action(
    state: ConvergenceState,
    action: RecoveryAction,
) -> None:
    assert recommended_actions(state) == (action,)


def test_state_names_are_normalized_but_unknown_names_are_rejected() -> None:
    assert classify_state(["home", "runtime_transient"]) is ConvergenceState.HOME
    assert recommended_actions("SAFE_MODAL") == (RecoveryAction.DISMISS_MODAL,)
    with pytest.raises(ValueError, match="invalid state"):
        classify_state(["not-a-state"])


def test_session_records_resumable_observations_and_safe_actions() -> None:
    clock = FakeClock()
    session = ConvergenceSession(
        " mail_reward_daily ",
        clock=clock,
        session_id="convergence-1",
    )

    home = session.observe(ConvergenceState.HOME, evidence="home marker", frame_id="frame-1")
    assert home.task_id == "MAIL_REWARD_DAILY"
    assert home.previous_state is None

    clock.advance(1.5)
    action = session.record_action(
        RecoveryAction.ENTER_TASK,
        evidence="task entry is allowed from home",
        frame_id="frame-2",
    )
    task_page = session.observe(
        ConvergenceState.TASK_RESUMABLE,
        evidence="mail page marker",
        frame_id="frame-3",
    )
    snapshot = session.finish(ConvergenceOutcome.CONVERGED)

    assert action.state is ConvergenceState.HOME
    assert task_page.previous_state is ConvergenceState.HOME
    assert snapshot.session_id == "convergence-1"
    assert snapshot.task_id == "MAIL_REWARD_DAILY"
    assert snapshot.outcome is ConvergenceOutcome.CONVERGED
    assert snapshot.last_state is ConvergenceState.TASK_RESUMABLE
    assert len(snapshot.observations) == 2
    assert len(snapshot.actions) == 1
    assert snapshot.budget.closed is True


def test_closed_session_cannot_be_reused() -> None:
    session = ConvergenceSession("MAIL_REWARD_DAILY")
    session.finish(ConvergenceOutcome.FAILED)

    with pytest.raises(RuntimeError, match="closed"):
        session.observe(ConvergenceState.HOME)
    with pytest.raises(RuntimeError, match="closed"):
        session.record_action(RecoveryAction.ENTER_TASK)
