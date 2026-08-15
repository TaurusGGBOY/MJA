from datetime import date

from agent.workflows.catalog import (
    TASK_POLICIES,
    WORKFLOW_DEFINITION_ORDER,
    workflow_sequence_for_date,
)
from agent.workflows.registry import WORKFLOW_DEFINITIONS

EXPECTED_TASK_IDS = (
    "MAIL_REWARD_DAILY",
    "SHOP_FREE_GIFT_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "TRIAL_SWORD_DAILY",
    "FREE_APPRAISAL_DAILY",
    "BUY_TEA_DAILY",
    "COLLECTION_DEPLOYMENT_DAILY",
    "HERO_DISPATCH_DAILY",
    "SHADOW_RUINS_DAILY",
    "SPEND_CONDENSATE_DAILY",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "EAT_STAMINA_FOOD_DAILY",
    "DUNGEON_SWEEP_DAILY",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "RING_CHALLENGE_DAILY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
)


def test_catalog_contains_exactly_the_canonical_workflow_ids() -> None:
    assert WORKFLOW_DEFINITION_ORDER == EXPECTED_TASK_IDS
    assert tuple(TASK_POLICIES) == EXPECTED_TASK_IDS
    assert tuple(WORKFLOW_DEFINITIONS) == EXPECTED_TASK_IDS


def test_catalog_entries_have_unique_interface_names_and_finite_caps() -> None:
    entries = [TASK_POLICIES[task_id] for task_id in EXPECTED_TASK_IDS]
    assert len({entry.interface_name for entry in entries}) == len(entries)
    for entry in entries:
        assert entry.entry == f"MJA_Daily_{entry.task_id}"
        assert entry.max_steps > 0
        assert entry.action_caps
        assert all(isinstance(cap, int) and cap > 0 for cap in entry.action_caps.values())


def test_weekly_free_gift_is_monday_only() -> None:
    assert TASK_POLICIES["WEEKLY_FREE_GIFT_MONDAY"].eligible_weekdays == frozenset({0})
    assert "WEEKLY_FREE_GIFT_MONDAY" in workflow_sequence_for_date(date(2026, 7, 27))
    assert "WEEKLY_FREE_GIFT_MONDAY" not in workflow_sequence_for_date(date(2026, 7, 28))


def test_sequence_preserves_business_phase_order() -> None:
    sequence = workflow_sequence_for_date(date(2026, 7, 27))
    positions = {task_id: sequence.index(task_id) for task_id in sequence}
    assert positions["MAIL_REWARD_DAILY"] < positions["TRIAL_SWORD_DAILY"]
    assert positions["HERO_DISPATCH_DAILY"] < positions["SHADOW_RUINS_DAILY"]
    assert positions["RING_CHALLENGE_DAILY"] < positions["DAILY_TASK_REWARD_CLAIM_DAILY"]
    assert positions["DAILY_TASK_REWARD_CLAIM_DAILY"] < positions["BATTLE_PASS_REWARD_DAILY"]


def test_consumptive_tasks_have_explicit_approved_resource_policies() -> None:
    expected_resources = {
        "BUY_TEA_DAILY": {"文"},
        "EAT_STAMINA_FOOD_DAILY": {"龙井虾仁"},
        "SPEND_CONDENSATE_DAILY": {"凝晶"},
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": {"紫色魂玉", "体力"},
        "RING_CHALLENGE_DAILY": {"擂台券"},
        "DUNGEON_SWEEP_DAILY": {"副本票"},
    }
    for task_id, resources in expected_resources.items():
        policy = TASK_POLICIES[task_id]
        assert resources <= policy.approved_resources
        assert policy.resource_caps
        assert all(cap > 0 for cap in policy.resource_caps.values())


def test_catalog_never_approves_real_money_or_premium_resources() -> None:
    forbidden = {"¥", "￥", "人民币", "充值", "Apple Pay", "付费礼包", "月卡"}
    for policy in TASK_POLICIES.values():
        assert not forbidden.intersection(policy.approved_resources)
