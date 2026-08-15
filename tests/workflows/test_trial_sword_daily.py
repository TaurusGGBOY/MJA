from agent.workflows.definitions.trial_sword_daily import TRIAL_SWORD_DAILY_DEFINITION
from agent.workflows.models import TaskStatus
from tests.workflows.support import evaluate_decision


def test_trial_sword_reward_precedes_free_trial():
    decision, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION, "trial", ("试剑-试炼-页面", "试剑-试炼-奖励-领取")
    )
    assert decision.transition.intent.action_id == "claim_trial_sword_reward"


def test_trial_sword_resumes_from_open_free_confirmation_popup():
    decision, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "home",
        ("试剑-试炼-免费-弹窗", "试剑-试炼-免费-确认"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_free_trial"
    assert decision.transition.postcondition == "trial.reward_popup"


def test_trial_sword_closes_free_reward_after_resumed_confirmation():
    decision, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "free_reward",
        ("试剑-试炼-奖励-弹窗", "试剑-试炼-弹窗-关闭"),
        counters={"confirm_free_trial": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_reward_popup"
    assert decision.transition.next_state == "trial_done"
    assert decision.transition.postcondition == "trial.free_used"


def test_trial_sword_finishes_when_reward_claim_returns_home():
    decision, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "reward_popup",
        ("home",),
        counters={"claim_trial_sword_reward": 1},
    )

    assert decision.status is TaskStatus.COMPLETED


def test_trial_sword_closes_page_when_free_duration_is_already_applied():
    decision, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "free_trial",
        ("试剑-试炼-页面", "trial.free_used", "试剑-试炼-关闭"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_trial"
    assert decision.transition.postcondition == "home"


def test_trial_sword_timer_without_trial_page_is_not_completion_evidence():
    decision, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "trial",
        ("trial.free_used",),
        texts=("00:36:00",),
    )

    assert decision.status is TaskStatus.FAILED
