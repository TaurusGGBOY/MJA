from __future__ import annotations

from pathlib import Path

import pytest

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_abort_code,
    assert_fixture_matrix,
    assert_guarded_actions,
    assert_loop_bound,
    assert_no_side_effect_retry,
    assert_ordered_actions,
    assert_outcome,
    assert_reachable,
    assert_resource_guard,
    assert_shared_resource_budget,
    assert_task_contract,
    load_task_declaration,
    load_task_nodes,
)

TEA = TaskContract("BUY_TEA_DAILY", "daily/buy_tea_daily.json")
CONDENSATE = TaskContract(
    "SPEND_CONDENSATE_DAILY",
    "daily/spend_condensate_daily.json",
)
FOOD = TaskContract(
    "EAT_STAMINA_FOOD_DAILY",
    "daily/eat_stamina_food_daily.json",
)
JIANLIN = TaskContract(
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "daily/jianlin_resource_condensate_stamina_daily.json",
)
BATCH_B = [TEA, CONDENSATE, FOOD, JIANLIN]
ROOT = Path(__file__).parents[3]


def test_batch_b_contracts_use_only_existing_fixture_cases_until_live_capture() -> None:
    for contract in BATCH_B:
        if contract.task_id in {TEA.task_id, FOOD.task_id, JIANLIN.task_id}:
            declaration = load_task_declaration(contract.task_id)
            nodes = load_task_nodes(contract)
            assert declaration["label"]
            assert declaration["default_check"] is True
            assert declaration["group"] == [contract.group]
            assert declaration["entry"] == contract.entry
            assert_reachable(nodes, contract.entry, "MJA_COMMON_STOP")
            assert_reachable(nodes, contract.entry, "MJA_COMMON_ABORT")
        else:
            assert_task_contract(contract)
        assert_fixture_matrix(
            contract.task_id,
            {"entry", "actionable", "completed", "danger"},
        )


@pytest.mark.parametrize(
    ("task_id", "resource", "maximum"),
    [
        ("BUY_TEA_DAILY", "文", 500),
        ("SPEND_CONDENSATE_DAILY", "凝晶", 100_000),
        ("EAT_STAMINA_FOOD_DAILY", "龙井虾仁", 6),
        ("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", "紫色魂玉", 1),
        ("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", "体力", 360),
    ],
)
def test_batch_b_resource_budgets_match_the_frozen_policy(
    task_id: str, resource: str, maximum: int
) -> None:
    assert TASK_POLICIES[task_id].resource_caps[resource] == maximum


def test_buy_tea_is_one_guarded_purchase_of_wen_at_most_500() -> None:
    nodes = load_task_nodes(TEA)
    assert_guarded_actions(
        nodes,
        TEA.task_id,
        [
            "open_painting_scroll",
            "select_yanwu_world",
            "open_universal_shop",
            "scroll_tea_list",
            "open_tea_tab",
            "open_tea_purchase",
            "set_tea_quantity_max",
            "buy_tea",
            "dismiss_tea_purchase_result",
            "close_function_panel",
        ],
    )
    assert TASK_POLICIES[TEA.task_id].action_caps["buy_tea"] == 1
    assert_resource_guard(nodes, "buy_tea", "文", 500, task_id=TEA.task_id)
    assert_no_side_effect_retry(nodes, "buy_tea")
    assert_ordered_actions(
        nodes,
        ["open_tea_purchase", "set_tea_quantity_max", "buy_tea"],
    )
    assert_outcome(nodes, "MJA_TEA_SOLD_OUT", "already_complete", "tea.sold_out")
    assert_abort_code(
        nodes,
        "MJA_TEA_PRICE_UNSAFE",
        "TEA_PRICE_OR_CURRENCY_UNVERIFIED",
    )


def test_condensate_uses_one_shared_budget_for_both_regions() -> None:
    nodes = load_task_nodes(CONDENSATE)
    assert_guarded_actions(
        nodes,
        CONDENSATE.task_id,
        [
            "open_function_panel",
            "open_daily_tasks_initial",
            "close_daily_tasks",
            "close_function_panel",
            "open_painting_scroll",
            "select_yanwu_world",
            "open_yanwu_currency_purchase",
            "close_yanwu_currency_purchase",
            "set_yanwu_quantity_max",
            "buy_yanwu_currency_max",
            "dismiss_yanwu_reward_popup",
            "select_yunzhou",
            "open_yunzhou_currency_purchase",
            "close_yunzhou_currency_purchase",
            "set_yunzhou_quantity_max",
            "buy_yunzhou_currency_max",
            "dismiss_yunzhou_reward_popup",
        ],
    )
    assert_ordered_actions(
        nodes,
        [
            "buy_yanwu_currency_max",
            "select_yunzhou",
            "buy_yunzhou_currency_max",
        ],
    )
    assert_resource_guard(
        nodes,
        "buy_yanwu_currency_max",
        "凝晶",
        100_000,
        task_id=CONDENSATE.task_id,
    )
    assert_resource_guard(
        nodes,
        "buy_yunzhou_currency_max",
        "凝晶",
        100_000,
        task_id=CONDENSATE.task_id,
    )
    assert_shared_resource_budget(nodes, "凝晶", 100_000)
    assert_no_side_effect_retry(nodes, "buy_yanwu_currency_max")
    assert_no_side_effect_retry(nodes, "buy_yunzhou_currency_max")
    assert_outcome(
        nodes,
        "MJA_CONDENSATE_ALREADY_COMPLETE",
        "already_complete",
        "condensate.both_regions_sold_out",
    )
    assert_abort_code(
        nodes,
        "MJA_CONDENSATE_BUDGET_UNSAFE",
        "CONDENSATE_PRICE_OR_CURRENCY_UNVERIFIED",
    )


def test_food_consumes_only_longjing_shrimp_with_bounded_loops() -> None:
    nodes = load_task_nodes(FOOD)
    assert_guarded_actions(
        nodes,
        FOOD.task_id,
        [
            "open_resource_page",
            "open_food_category",
            "select_food_tab",
            "inspect_food_candidate",
            "eat_longjing_shrimp",
            "confirm_food_buff_replace",
            "close_bag",
            "close_function_panel",
            "close_dungeon_for_food",
            "close_jianlin_for_food",
        ],
    )
    assert_resource_guard(
        nodes,
        "eat_longjing_shrimp",
        "龙井虾仁",
        6,
        task_id=FOOD.task_id,
    )
    assert_loop_bound(nodes, "MJA_FOOD_CANDIDATE_LOOP", maximum=6)
    assert_loop_bound(nodes, "MJA_FOOD_REPLACE_CONFIRM_LOOP", maximum=6)
    assert_loop_bound(nodes, "MJA_FOOD_CONTINUE_AFTER_VERIFIED_USE", maximum=5)
    assert_no_side_effect_retry(nodes, "eat_longjing_shrimp")
    assert_outcome(
        nodes,
        "MJA_FOOD_STAMINA_FULL",
        "already_complete",
        "food.overfull",
    )
    assert_outcome(
        nodes,
        "MJA_FOOD_SUCCESS",
        "success",
        "food.buff_after_verified_use",
    )
    assert_outcome(
        nodes,
        "MJA_FOOD_NO_SAFE_CARD",
        "not_eligible",
        "food.longjing_shrimp_unavailable",
    )


def test_food_r20_start_uses_specific_same_level_siblings_and_home_resource_entry() -> None:
    nodes = load_task_nodes(FOOD)

    start = nodes[FOOD.entry]
    assert start["next"] == [
        "MJA_FOOD_JIANLIN_PAGE_PROBE",
        "MJA_FOOD_PANEL_PROBE",
        "MJA_FOOD_DUNGEON_PAGE_PROBE",
        "MJA_FOOD_RESUME_REPLACE_PROBE",
        "MJA_FOOD_PAGE_PROBE",
        "MJA_FOOD_BAG_PAGE_PROBE",
        "MJA_FOOD_OPEN_RESOURCE",
        "MJA_FOOD_GAME_START_RECOVERY",
    ]
    assert start["on_error"] == ["MJA_FOOD_GAME_START_RECOVERY_FAILED"]
    assert start["retry_times"] == 0
    assert "MJA_FOOD_HOME_PROBE" not in nodes
    assert "MJA_FOOD_OPEN_PANEL" not in nodes
    assert "MJA_FOOD_OPEN_BAG" not in nodes

    food_page = nodes["MJA_FOOD_PAGE_PROBE"]
    bag_page = nodes["food.bag.page"]
    assert bag_page == {
        "recognition": "TemplateMatch",
        "template": "daily/EAT_STAMINA_FOOD_DAILY/food_bag_title_live.png",
        "roi": [0, 0, 150, 120],
        "threshold": 0.4,
        "action": "DoNothing",
    }
    category = nodes["food.category"]
    assert category == {
        "recognition": "TemplateMatch",
        "template": "daily/EAT_STAMINA_FOOD_DAILY/food_category_icon_live.png",
        "roi": [0, 130, 150, 180],
        "threshold": 0.4,
        "action": "DoNothing",
    }
    food_tab = nodes["food.food_tab"]
    assert food_tab == {
        "recognition": "OCR",
        "expected": "食物",
        "roi": [300, 30, 180, 75],
        "action": "DoNothing",
    }
    assert food_page["recognition"]["param"] == {
        "all_of": ["food.category.page", "food.food_tab"],
        "box_index": 1,
    }
    assert nodes["food.food.page"]["recognition"]["param"] == food_page[
        "recognition"
    ]["param"]

    target = nodes["food.resource_entry"]
    assert target == {
        "recognition": "ColorMatch",
        "method": 4,
        "lower": [100, 100, 90],
        "upper": [255, 255, 255],
        "roi": [0, 90, 70, 100],
        "connected": True,
        "count": 450,
        "order_by": "Area",
        "index": 0,
        "action": "DoNothing",
    }

    # Offline calibration from the r20 on-error frame at 18:05:17.773.
    # Its home-marker ROI scores about 0.825 against home_marker.png, above
    # the configured 0.75 threshold.  The left resource glyph is the single
    # dominant connected component inside the deliberately narrow target ROI.
    frame_width, frame_height = 1280, 720
    archived_home_ncc = 0.8253923457503188
    archived_component_box = [19, 114, 34, 28]
    archived_component_pixels = 535
    assert archived_home_ncc > nodes["food.home.page"]["threshold"]
    x, y, width, height = target["roi"]
    component_x, component_y, component_width, component_height = (
        archived_component_box
    )
    assert x <= component_x
    assert y <= component_y
    assert x + width >= component_x + component_width
    assert y + height >= component_y + component_height
    assert x + width <= frame_width
    assert y + height <= frame_height
    assert target["count"] < archived_component_pixels
    assert (component_x + component_width // 2, component_y + component_height // 2) == (
        36,
        128,
    )
    assert width * height < frame_width * frame_height // 100

    home_entry = nodes["MJA_FOOD_OPEN_RESOURCE"]
    assert home_entry["recognition"]["param"] == {
        "all_of": ["food.home.page", "food.resource_entry"],
        "box_index": 1,
    }
    assert home_entry["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "food.home.page",
        "target_name": "food.resource_entry",
    }
    assert home_entry["custom_action_param"]["action_id"] == "open_resource_page"
    assert home_entry["retry_times"] == 0
    assert TASK_POLICIES[FOOD.task_id].action_caps["open_resource_page"] == 1
    assert_reachable(nodes, FOOD.entry, "MJA_FOOD_BAG_PAGE_PROBE")


def test_food_recovers_once_when_startup_leaves_a_non_food_surface() -> None:
    nodes = load_task_nodes(FOOD)
    start = nodes[FOOD.entry]
    recovery = nodes["MJA_FOOD_GAME_START_RECOVERY"]
    state_probe = nodes["MJA_FOOD_RECOVERY_STATE_PROBE"]

    assert start["next"] == [
        "MJA_FOOD_JIANLIN_PAGE_PROBE",
        "MJA_FOOD_PANEL_PROBE",
        "MJA_FOOD_DUNGEON_PAGE_PROBE",
        "MJA_FOOD_RESUME_REPLACE_PROBE",
        "MJA_FOOD_PAGE_PROBE",
        "MJA_FOOD_BAG_PAGE_PROBE",
        "MJA_FOOD_OPEN_RESOURCE",
        "MJA_FOOD_GAME_START_RECOVERY",
    ]
    assert start["on_error"] == ["MJA_FOOD_GAME_START_RECOVERY_FAILED"]

    assert recovery == {
        "recognition": "DirectHit",
        "max_hit": 1,
        "action": "StartApp",
        "package": "com.hanjiasongshu.dr22/.MainActivity",
        "post_delay": 5000,
        "retry_times": 0,
        "next": ["MJA_FOOD_RECOVERY_STATE_PROBE"],
        "on_error": ["MJA_FOOD_GAME_START_RECOVERY_FAILED"],
    }
    assert state_probe == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "timeout": 30000,
        "next": [
            "MJA_FOOD_JIANLIN_PAGE_PROBE",
            "MJA_FOOD_PANEL_PROBE",
            "MJA_FOOD_DUNGEON_PAGE_PROBE",
            "MJA_FOOD_RESUME_REPLACE_PROBE",
            "MJA_FOOD_PAGE_PROBE",
            "MJA_FOOD_BAG_PAGE_PROBE",
            "MJA_FOOD_OPEN_RESOURCE",
        ],
        "on_error": ["MJA_FOOD_GAME_START_RECOVERY_FAILED"],
    }

    failed = nodes["MJA_FOOD_GAME_START_RECOVERY_FAILED"]
    assert failed["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "status": "failed",
        "postcondition": "food.game_foreground_or_recoverable_state",
        "error_code": "FOOD_GAME_START_RECOVERY_EXHAUSTED",
        "native_fail_after_record": True,
    }
    assert failed["Abort"] is True
    assert failed["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failed
    assert [
        name
        for name, node in nodes.items()
        if name.startswith("MJA_FOOD_") and node.get("action") == "StartApp"
    ] == ["MJA_FOOD_GAME_START_RECOVERY"]
    assert_reachable(nodes, FOOD.entry, "MJA_FOOD_GAME_START_RECOVERY_FAILED")


def test_food_alternatives_follow_real_maa_next_list_semantics() -> None:
    nodes = load_task_nodes(FOOD)
    action_caps = TASK_POLICIES[FOOD.task_id].action_caps
    assert action_caps["open_resource_page"] == 1
    assert action_caps["inspect_food_candidate"] == 6
    assert action_caps["eat_longjing_shrimp"] == 6
    assert action_caps["confirm_food_buff_replace"] == 6

    assert nodes["MJA_FOOD_RESUME_REPLACE_PROBE"]["on_error"] == [
        "MJA_FOOD_RECORD_FAILURE"
    ]
    assert nodes["MJA_FOOD_PAGE_PROBE"]["next"] == [
        "MJA_FOOD_RECHECK_FULL",
        "MJA_FOOD_CANDIDATE_LOOP",
    ]
    assert nodes["MJA_FOOD_DETAIL_PROBE"]["next"] == [
        f"MJA_FOOD_COUNT_{count}_PROBE" for count in range(6, 0, -1)
    ]

    after_eat = [
        "MJA_FOOD_OVERFULL_AFTER_EAT_PROBE",
        "MJA_FOOD_REPLACEMENT_PROBE",
        "MJA_FOOD_USE_RESULT_PROBE",
    ]
    for count in range(6, 0, -1):
        count_probe = nodes[f"MJA_FOOD_COUNT_{count}_PROBE"]
        assert count_probe["on_error"] == ["MJA_FOOD_RECORD_FAILURE"]
        eat = nodes[f"MJA_FOOD_EAT_COUNT_{count}"]
        assert eat["next"] == after_eat
        assert eat["on_error"] == ["MJA_FOOD_RECORD_FAILURE"]
        assert eat["retry_times"] == 0

    strict_pair = [
        "food.replace.prompt",
        "food.replace.confirm",
        "food.longjing_name",
    ]
    for name in (
        "MJA_FOOD_RESUME_REPLACE_PROBE",
        "MJA_FOOD_REPLACEMENT_PROBE",
        "MJA_FOOD_REPLACE_CONFIRM_LOOP",
    ):
        assert nodes[name]["recognition"]["param"]["all_of"] == strict_pair
    confirm = nodes["MJA_FOOD_REPLACE_CONFIRM_LOOP"]
    assert confirm["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "food.replace.prompt",
        "target_name": "food.replace.confirm",
    }
    assert confirm["next"] == [
        "MJA_FOOD_OVERFULL_AFTER_EAT_PROBE",
        "MJA_FOOD_USE_RESULT_PROBE",
    ]
    assert confirm.get("retry_times", 0) == 0

    buff = nodes["MJA_FOOD_USE_RESULT_PROBE"]
    assert buff["recognition"] == {
        "type": "Or",
        "param": {"any_of": ["food.use_result", "food.post_use_state"]},
    }
    assert buff["next"] == ["MJA_FOOD_POST_USE_PROGRESS_PROBE"]
    progress = nodes["MJA_FOOD_POST_USE_PROGRESS_PROBE"]
    assert progress["custom_action"] == "VerifyFoodQuantityDecrease"
    assert progress["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "resource_id": "龙井虾仁",
        "amount_index": 2,
        "amount_result_name": "food.available_positive",
    }
    assert progress["next"] == [
        "MJA_FOOD_SUCCESS",
        "MJA_FOOD_CONTINUE_AFTER_VERIFIED_USE",
    ]
    assert nodes["MJA_FOOD_CONTINUE_AFTER_VERIFIED_USE"]["next"] == [
        "MJA_FOOD_PAGE_PROBE"
    ]


def test_food_failures_record_failed_before_native_abort_and_cannot_remain_running() -> None:
    nodes = load_task_nodes(FOOD)

    failure = nodes["MJA_FOOD_RECORD_FAILURE"]
    assert failure["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "status": "failed",
        "postcondition": "FOOD_POSTCONDITION_MISSING",
        "error_code": "FOOD_POSTCONDITION_MISSING",
        "native_fail_after_record": True,
    }
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failure

    guarded = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == FOOD.task_id
    }
    assert guarded
    # close_bag runs only after an outcome has already been persisted; every
    # input that can still leave the task running must close through failure.
    for name, node in guarded.items():
        if name != "MJA_FOOD_CLOSE_BAG":
            assert node["on_error"] == ["MJA_FOOD_RECORD_FAILURE"]

    direct_native_abort = {
        name
        for name, node in nodes.items()
        if name.startswith("MJA_FOOD_")
        and name
        not in {
            "MJA_FOOD_RECORD_FAILURE",
            "MJA_FOOD_GAME_START_RECOVERY_FAILED",
        }
        and (
            "MJA_COMMON_ABORT" in node.get("next", [])
            or "MJA_COMMON_ABORT" in node.get("on_error", [])
        )
    }
    assert direct_native_abort == set()
    assert_reachable(nodes, FOOD.entry, "MJA_FOOD_RECORD_FAILURE")


def test_jianlin_has_one_verified_refill_and_bounded_challenges() -> None:
    nodes = load_task_nodes(JIANLIN)
    assert_guarded_actions(
        nodes,
        JIANLIN.task_id,
        [
            "open_function_panel",
            "open_daily_tasks",
            "scroll_daily_jianlin",
            "open_jianlin",
            "select_jianlin_condensate",
            "open_jianlin_stamina_purchase",
            "buy_stamina_once",
            "confirm_jianlin_stamina_purchase",
            "close_postpurchase_stamina_prompt",
            "dismiss_jianlin_stamina_result",
            "set_safe_count",
            "set_safe_multiplier",
            "challenge_condensate",
            "start_jianlin_battle",
            "close_condensate_result",
            "close_jianlin_page",
            "close_ring_page",
            "close_guild_activity_for_jianlin",
            "close_guild_home_for_jianlin",
            "close_daily_tasks",
            "close_function_panel",
        ],
    )
    assert_resource_guard(
        nodes,
        "buy_stamina_once",
        "紫色魂玉",
        1,
        task_id=JIANLIN.task_id,
    )
    assert_resource_guard(
        nodes,
        "start_jianlin_battle",
        "体力",
        120,
        task_id=JIANLIN.task_id,
    )
    assert all(
        node["custom_action_param"]["observed_amount"] == 10
        for node in nodes.values()
        if node.get("action") == "Custom"
        and node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("action_id") == "buy_stamina_once"
    )
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["buy_stamina_once"] == 1
    assert_loop_bound(nodes, "MJA_JIANLIN_CHALLENGE_LOOP", maximum=12)
    assert_no_side_effect_retry(nodes, "buy_stamina_once")
    assert_no_side_effect_retry(nodes, "start_jianlin_battle")
    assert_abort_code(
        nodes,
        "MJA_JIANLIN_SECOND_OFFER",
        "JIANLIN_ESCALATED_STAMINA_OFFER",
    )
