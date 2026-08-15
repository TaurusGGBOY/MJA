from agent.workflows.definitions.daily_task_reward_claim_daily import (
    DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
)
from tests.workflows.support import evaluate_decision


def test_daily_reward_prefers_completed_row():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "main",
        ("日常任务奖励-日常-页面", "日常任务奖励-日常-已完成-行-领取"),
    )
    assert decision.transition.intent.action_id == "claim_completed_daily_row"
    assert safety.allowed


def test_daily_reward_claims_activity_chest_before_scrolling_rows():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "main",
        ("日常任务奖励-日常-页面", "日常任务奖励-日常-已解锁-活动-宝箱"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "claim_unlocked_activity_chest"
    assert decision.transition.postcondition == "daily.reward_popup"
    assert safety is not None and safety.allowed


def test_daily_reward_scrolls_when_current_view_has_no_claimable_target():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "main",
        ("日常任务奖励-日常-页面",),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "scroll_daily_reward_rows"
    assert decision.transition.intent.input_kind.value == "swipe"
    assert safety is not None and safety.allowed


def test_daily_reward_reuses_an_already_open_daily_page():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "home",
        ("日常任务奖励-日常-页面", "日常任务奖励-日常-已完成-行-领取"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "claim_completed_daily_row"
    assert safety is not None and safety.allowed


def test_daily_reward_finishes_after_one_auto_claim():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "main",
        ("日常任务奖励-日常-页面",),
        counters={"claim_completed_daily_row": 1, "close_reward_popup": 1},
    )
    assert decision.status.value == "completed"
    assert safety is None


def test_daily_reward_claims_each_unlocked_chest_after_auto_claiming_rows():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "main",
        ("日常任务奖励-日常-页面", "日常任务奖励-日常-已解锁-活动-宝箱"),
        counters={"claim_completed_daily_row": 1, "close_reward_popup": 1},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "claim_unlocked_activity_chest"
    assert safety is not None and safety.allowed


def test_daily_reward_resumes_at_reward_popup_from_initial_state():
    decision, safety = evaluate_decision(
        DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
        "home",
        ("日常任务奖励-日常-奖励-弹窗", "日常任务奖励-日常-奖励-弹窗-关闭"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_reward_popup"
    assert safety is not None and safety.allowed
