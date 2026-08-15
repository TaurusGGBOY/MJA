from agent.workflows.definitions.battle_pass_reward_daily import BATTLE_PASS_REWARD_DAILY_DEFINITION
from tests.workflows.support import evaluate_decision


def test_battle_pass_targets_basic_track_reward():
    decision, safety = evaluate_decision(
        BATTLE_PASS_REWARD_DAILY_DEFINITION,
        "main",
        ("战令奖励-战斗-战令-任务", "战令奖励-战斗-战令-任务-奖励-领取"),
    )
    assert decision.transition.intent.action_id == "claim_task_reward"
    assert safety.allowed


def test_battle_pass_closes_after_basic_track_is_exhausted():
    decision, safety = evaluate_decision(
        BATTLE_PASS_REWARD_DAILY_DEFINITION,
        "rewards",
        (
            "战令奖励-战斗-战令-页面",
            "战令奖励-战斗-战令-奖励",
            "战令奖励-战斗-战令-基础-全部已领取",
            "战令奖励-战斗-战令-关闭",
        ),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_battle_pass"
    assert safety.allowed


def test_battle_pass_does_not_finish_rewards_navigation_without_claim_or_all_claimed_proof():
    decision, _ = evaluate_decision(
        BATTLE_PASS_REWARD_DAILY_DEFINITION,
        "rewards",
        ("战令奖励-战斗-战令-页面", "战令奖励-战斗-战令-奖励", "战令奖励-战斗-战令-关闭"),
    )

    assert decision.status is not None


def test_battle_pass_closes_an_already_open_reward_popup_before_continuing():
    decision, safety = evaluate_decision(
        BATTLE_PASS_REWARD_DAILY_DEFINITION,
        "tasks",
        ("战令奖励-战斗-战令-奖励-弹窗", "战令奖励-战斗-战令-奖励-弹窗-关闭"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_reward_popup"
    assert decision.transition.postcondition == "battle_pass.tasks"
    assert safety.allowed
