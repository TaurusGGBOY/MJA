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
            assert_reachable(nodes, contract.entry, "公共-通用停止")
            assert_reachable(nodes, contract.entry, "公共-通用中止")
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
    assert_outcome(nodes, "买茶-售罄", "already_complete", "tea.sold_out")
    assert_abort_code(
        nodes,
        "买茶-价格-不安全",
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
        "消耗凝结体-已完成",
        "already_complete",
        "condensate.both_regions_sold_out",
    )
    assert_abort_code(
        nodes,
        "消耗凝结体-预算-不安全",
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
    assert_loop_bound(nodes, "吃体力食物-候选-循环", maximum=6)
    assert_loop_bound(nodes, "吃体力食物-替换-确认-循环", maximum=6)
    assert_loop_bound(nodes, "MJA_FOOD_CONTINUE_AFTER_VERIFIED_USE", maximum=5)
    assert_no_side_effect_retry(nodes, "eat_longjing_shrimp")
    assert_outcome(
        nodes,
        "吃体力食物-体力-已满",
        "already_complete",
        "food.overfull",
    )
    assert_outcome(
        nodes,
        "吃体力食物-成功",
        "success",
        "food.buff_after_verified_use",
    )
    assert_outcome(
        nodes,
        "吃体力食物-无安全卡",
        "not_eligible",
        "food.longjing_shrimp_unavailable",
    )


def test_food_r20_start_uses_specific_same_level_siblings_and_home_resource_entry() -> None:
    nodes = load_task_nodes(FOOD)

    start = nodes[FOOD.entry]
    assert start["next"] == [
        "吃体力食物-剑林-页面-探测",
        "吃体力食物-面板-探测",
        "吃体力食物-副本-页面-探测",
        "吃体力食物-恢复继续-替换-探测",
        "吃体力食物-页面-探测",
        "吃体力食物-背包-页面-探测",
        "吃体力食物-打开-资源",
        "吃体力食物-游戏启动恢复",
    ]
    assert start["on_error"] == ["吃体力食物-游戏启动恢复失败"]
    assert start["retry_times"] == 0
    assert "MJA_FOOD_HOME_PROBE" not in nodes
    assert "MJA_FOOD_OPEN_PANEL" not in nodes
    assert "MJA_FOOD_OPEN_BAG" not in nodes

    food_page = nodes["吃体力食物-页面-探测"]
    bag_page = nodes["吃体力食物-食物-背包-页面"]
    assert bag_page == {
        "recognition": "TemplateMatch",
        "template": "daily/EAT_STAMINA_FOOD_DAILY/food_bag_title_live.png",
        "roi": [0, 0, 150, 120],
        "threshold": 0.4,
        "action": "DoNothing",
    }
    category = nodes["吃体力食物-食物-分类"]
    assert category == {
        "recognition": "TemplateMatch",
        "template": "daily/EAT_STAMINA_FOOD_DAILY/food_category_icon_live.png",
        "roi": [0, 130, 150, 180],
        "threshold": 0.4,
        "action": "DoNothing",
    }
    food_tab = nodes["吃体力食物-食物-食物-标签"]
    assert food_tab == {
        "recognition": "OCR",
        "expected": "食物",
        "roi": [300, 30, 180, 75],
        "action": "DoNothing",
    }
    assert food_page["recognition"]["param"] == {
        "all_of": ["吃体力食物-食物-分类-页面", "吃体力食物-食物-食物-标签"],
        "box_index": 1,
    }
    assert nodes["吃体力食物-食物-食物-页面"]["recognition"]["param"] == food_page[
        "recognition"
    ]["param"]

    target = nodes["吃体力食物-食物-资源-入口"]
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
    assert archived_home_ncc > nodes["吃体力食物-食物-主页-页面"]["threshold"]
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

    home_entry = nodes["吃体力食物-打开-资源"]
    assert home_entry["recognition"]["param"] == {
        "all_of": ["吃体力食物-食物-主页-页面", "吃体力食物-食物-资源-入口"],
        "box_index": 1,
    }
    assert home_entry["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "吃体力食物-食物-主页-页面",
        "target_name": "吃体力食物-食物-资源-入口",
    }
    assert home_entry["custom_action_param"]["action_id"] == "open_resource_page"
    assert home_entry["retry_times"] == 0
    assert TASK_POLICIES[FOOD.task_id].action_caps["open_resource_page"] == 1
    assert_reachable(nodes, FOOD.entry, "吃体力食物-背包-页面-探测")


def test_food_recovers_once_when_startup_leaves_a_non_food_surface() -> None:
    nodes = load_task_nodes(FOOD)
    start = nodes[FOOD.entry]
    recovery = nodes["吃体力食物-游戏启动恢复"]
    state_probe = nodes["吃体力食物-恢复-状态-探测"]

    assert start["next"] == [
        "吃体力食物-剑林-页面-探测",
        "吃体力食物-面板-探测",
        "吃体力食物-副本-页面-探测",
        "吃体力食物-恢复继续-替换-探测",
        "吃体力食物-页面-探测",
        "吃体力食物-背包-页面-探测",
        "吃体力食物-打开-资源",
        "吃体力食物-游戏启动恢复",
    ]
    assert start["on_error"] == ["吃体力食物-游戏启动恢复失败"]

    assert recovery == {
        "recognition": "DirectHit",
        "max_hit": 1,
        "action": "StartApp",
        "package": "com.hanjiasongshu.dr22/.MainActivity",
        "post_delay": 5000,
        "retry_times": 0,
        "next": ["吃体力食物-恢复-状态-探测"],
        "on_error": ["吃体力食物-游戏启动恢复失败"],
    }
    assert state_probe == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "timeout": 30000,
        "next": [
            "吃体力食物-剑林-页面-探测",
            "吃体力食物-面板-探测",
            "吃体力食物-副本-页面-探测",
            "吃体力食物-恢复继续-替换-探测",
            "吃体力食物-页面-探测",
            "吃体力食物-背包-页面-探测",
            "吃体力食物-打开-资源",
        ],
        "on_error": ["吃体力食物-游戏启动恢复失败"],
    }

    failed = nodes["吃体力食物-游戏启动恢复失败"]
    assert failed["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "status": "failed",
        "postcondition": "food.game_foreground_or_recoverable_state",
        "error_code": "FOOD_GAME_START_RECOVERY_EXHAUSTED",
        "native_fail_after_record": True,
    }
    assert failed["Abort"] is True
    assert failed["next"] == ["公共-通用中止"]
    assert "on_error" not in failed
    assert [
        name
        for name, node in nodes.items()
        if name.startswith("吃体力食物-") and node.get("action") == "StartApp"
    ] == ["吃体力食物-游戏启动恢复"]
    assert_reachable(nodes, FOOD.entry, "吃体力食物-游戏启动恢复失败")


def test_food_alternatives_follow_real_maa_next_list_semantics() -> None:
    nodes = load_task_nodes(FOOD)
    action_caps = TASK_POLICIES[FOOD.task_id].action_caps
    assert action_caps["open_resource_page"] == 1
    assert action_caps["inspect_food_candidate"] == 6
    assert action_caps["eat_longjing_shrimp"] == 6
    assert action_caps["confirm_food_buff_replace"] == 6

    assert nodes["吃体力食物-恢复继续-替换-探测"]["on_error"] == [
        "吃体力食物-记录-失败"
    ]
    assert nodes["吃体力食物-页面-探测"]["next"] == [
        "吃体力食物-重新检查-已满",
        "吃体力食物-候选-循环",
    ]
    assert nodes["吃体力食物-详情-探测"]["next"] == [
        f"吃体力食物-次数-{count}-探测" for count in range(6, 0, -1)
    ]

    after_eat = [
        "吃体力食物-已超上限-之后-食用-探测",
        "吃体力食物-替换-探测",
        "吃体力食物-使用-结果-探测",
    ]
    for count in range(6, 0, -1):
        count_probe = nodes[f"吃体力食物-次数-{count}-探测"]
        assert count_probe["on_error"] == ["吃体力食物-记录-失败"]
        eat = nodes[f"吃体力食物-食用-次数-{count}"]
        assert eat["max_hit"] == 6
        assert eat["next"] == after_eat
        assert eat["on_error"] == ["吃体力食物-记录-失败"]
        assert eat["retry_times"] == 0

    strict_pair = [
        "吃体力食物-食物-替换-提示",
        "吃体力食物-食物-替换-确认",
        "吃体力食物-食物-龙井虾仁-名称",
    ]
    for name in (
        "吃体力食物-恢复继续-替换-探测",
        "吃体力食物-替换-探测",
        "吃体力食物-替换-确认-循环",
    ):
        assert nodes[name]["recognition"]["param"]["all_of"] == strict_pair
    confirm = nodes["吃体力食物-替换-确认-循环"]
    assert confirm["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "吃体力食物-食物-替换-提示",
        "target_name": "吃体力食物-食物-替换-确认",
    }
    assert confirm["next"] == [
        "吃体力食物-已超上限-之后-食用-探测",
        "吃体力食物-使用-结果-探测",
    ]
    assert confirm.get("retry_times", 0) == 0

    buff = nodes["吃体力食物-使用-结果-探测"]
    assert buff["recognition"] == {
        "type": "Or",
        "param": {"any_of": ["吃体力食物-食物-使用-结果", "吃体力食物-食物-之后-使用-状态"]},
    }
    assert buff["next"] == ["吃体力食物-之后-使用-进度-探测"]
    progress = nodes["吃体力食物-之后-使用-进度-探测"]
    assert progress["custom_action"] == "VerifyFoodQuantityDecrease"
    assert progress["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "resource_id": "龙井虾仁",
        "amount_index": 2,
        "amount_result_name": "吃体力食物-食物-可用-正向",
    }
    assert progress["next"] == [
        "吃体力食物-成功",
        "MJA_FOOD_CONTINUE_AFTER_VERIFIED_USE",
    ]
    assert nodes["MJA_FOOD_CONTINUE_AFTER_VERIFIED_USE"]["next"] == [
        "吃体力食物-页面-探测"
    ]


def test_food_failures_record_failed_before_native_abort_and_cannot_remain_running() -> None:
    nodes = load_task_nodes(FOOD)

    failure = nodes["吃体力食物-记录-失败"]
    assert failure["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "status": "failed",
        "postcondition": "FOOD_POSTCONDITION_MISSING",
        "error_code": "FOOD_POSTCONDITION_MISSING",
        "native_fail_after_record": True,
    }
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
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
        if name != "吃体力食物-关闭-背包":
            assert node["on_error"] == ["吃体力食物-记录-失败"]

    direct_native_abort = {
        name
        for name, node in nodes.items()
        if name.startswith("吃体力食物-")
        and name
        not in {
            "吃体力食物-记录-失败",
            "吃体力食物-游戏启动恢复失败",
        }
        and (
            "公共-通用中止" in node.get("next", [])
            or "公共-通用中止" in node.get("on_error", [])
        )
    }
    assert direct_native_abort == set()
    assert_reachable(nodes, FOOD.entry, "吃体力食物-记录-失败")


def test_jianlin_has_one_verified_refill_and_bounded_challenges() -> None:
    nodes = load_task_nodes(JIANLIN)
    assert_guarded_actions(
        nodes,
        JIANLIN.task_id,
        [
            "open_function_panel",
            "open_daily_tasks",
            "open_dueling_menu",
            "scroll_daily_jianlin",
            "open_jianlin",
            "open_jianlin_resource",
            "select_jianlin_condensate",
            "open_jianlin_stamina_purchase",
            "buy_stamina_once",
            "confirm_jianlin_stamina_purchase",
            "close_postpurchase_stamina_prompt",
            "dismiss_jianlin_stamina_result",
            "set_safe_count",
            "set_safe_multiplier",
            "challenge_condensate",
            "enable_jianlin_skip_prepare",
            "start_jianlin_battle",
            "wait_jianlin_battle",
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
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["wait_jianlin_battle"] == 12
    assert_loop_bound(nodes, "剑林凝结体体力-挑战-循环", maximum=12)
    assert_no_side_effect_retry(nodes, "buy_stamina_once")
    assert_no_side_effect_retry(nodes, "start_jianlin_battle")
    assert_abort_code(
        nodes,
        "剑林凝结体体力-第二次-优惠",
        "JIANLIN_ESCALATED_STAMINA_OFFER",
    )
