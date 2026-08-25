from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES

ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline"


def _load(relative: str) -> dict[str, dict]:
    return json.loads((PIPELINE / relative).read_text(encoding="utf-8"))


def test_collection_entry_reads_the_bottom_left_collection_deployment_label() -> None:
    node = _load("daily/collection_deployment_daily.json")[
        "0243-采集部署-采集-打开"
    ]
    assert node["recognition"] == "OCR"
    assert node["expected"] == "采集部署"
    assert node["roi"] == [0, 500, 500, 160]


def test_collection_deployment_button_reads_the_bottom_left_one_click_button() -> None:
    node = _load("daily/collection_deployment_daily.json")[
        "0246-采集部署-采集-部署-全部"
    ]
    assert node["expected"] == "^(?:一键部署|键部署)$"
    assert node["roi"] == [0, 610, 500, 85]


def test_food_and_equipment_share_the_bottom_right_item_entry() -> None:
    food = _load("daily/eat_stamina_food_daily.json")[
        "0413-吃体力食物-食物-资源-入口"
    ]
    equipment = _load("daily/equipment_decompose_daily.json")[
        "0457-分解装备-装备-资源-入口"
    ]
    expected = {
        "recognition": "OCR",
        "expected": "(?:道)?具",
        "roi": [980, 580, 300, 140],
    }
    assert food == {**expected, "action": "DoNothing"}
    assert equipment == {**expected, "action": "DoNothing"}


def test_dungeon_entry_is_scoped_to_the_top_right_dungeon_label() -> None:
    node = _load("daily/dungeon_sweep_daily.json")["0343-副本扫荡-副本-入口"]
    assert node["recognition"] == "OCR"
    assert node["expected"] == "副本"
    assert node["roi"] == [960, 0, 180, 120]


def test_daily_entry_uses_the_current_bottom_right_trial_marker() -> None:
    node = _load("daily/daily_task_reward_claim_daily.json")[
        "0299-日常任务奖励-日常-主页-试炼"
    ]
    assert node["roi"] == [960, 520, 240, 100]


def test_daily_reward_closes_when_no_unlocked_chest_remains() -> None:
    nodes = _load("daily/daily_task_reward_claim_daily.json")
    close_reward = nodes["0262-日常任务奖励-关闭-奖励"]

    assert close_reward["next"] == [
        "0268-日常任务奖励-领取-宝箱",
        "0280-日常任务奖励-关闭",
    ]
    assert nodes["0268-日常任务奖励-领取-宝箱"]["on_error"] == [
        "0280-日常任务奖励-关闭"
    ]


def test_stamina_purchase_click_targets_the_ten_cost_under_plus_eighty() -> None:
    nodes = _load("daily/jianlin_resource_condensate_stamina_daily.json")
    node = nodes[
        "0780-剑林凝结体体力-购买-体力-一次"
    ]
    assert node["recognition"]["param"]["all_of"][-1] == (
        "0981-剑林凝结体体力-剑林-体力-价格10"
    )
    assert node["recognition"]["param"]["box_index"] == 2
    assert node["custom_action_param"]["evidence"]["target_index"] == 2
    assert node["custom_action_param"]["evidence"]["target_name"] == (
        "0981-剑林凝结体体力-剑林-体力-价格10"
    )
    assert nodes["0981-剑林凝结体体力-剑林-体力-价格10"]["roi"] == [
        300,
        100,
        900,
        500,
    ]


def test_stamina_purchase_failure_does_not_loop_back_to_the_page_behind_dialog() -> None:
    nodes = _load("daily/jianlin_resource_condensate_stamina_daily.json")
    assert "on_error" not in nodes["0778-剑林凝结体体力-打开-体力-购买"]


def test_stamina_price_fifty_is_an_optional_skip_branch() -> None:
    nodes = _load("daily/jianlin_resource_condensate_stamina_daily.json")
    open_purchase = nodes["0778-剑林凝结体体力-打开-体力-购买"]
    optional = nodes["0790-剑林凝结体体力-购买-体力-80可选50"]

    assert open_purchase["next"] == [
        "0780-剑林凝结体体力-购买-体力-一次",
        "0790-剑林凝结体体力-购买-体力-80可选50",
    ]
    assert optional["action"] == "Custom"
    assert optional["custom_action"] == "GuardedInput"
    assert optional["max_hit"] == 1
    assert optional["post_delay"] == 1000
    assert optional["custom_action_param"] == {
        "task_id": "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "action_id": "dismiss_jianlin_stamina_purchase",
        "kind": "click",
        "fixed_click_mode": "jianlin_page_close",
        "evidence": {
            "page_index": 0,
            "target_index": 2,
            "page_name": "0978-剑林凝结体体力-剑林-体力-购买-提示",
            "target_name": "0981-剑林凝结体体力-剑林-体力-价格50-可选",
        },
    }
    assert optional["next"] == ["0787-剑林凝结体体力-重新识别-体力"]
    assert optional["recognition"]["param"]["all_of"][-1] == (
        "0981-剑林凝结体体力-剑林-体力-价格50-可选"
    )


def test_stamina_cleanup_closes_the_next_fifty_cost_offer() -> None:
    nodes = _load("daily/jianlin_resource_condensate_stamina_daily.json")
    cleanup = nodes["0791-剑林凝结体体力-关闭-购买-面板"]

    assert cleanup["recognition"]["param"]["all_of"][-1] == (
        "0981-剑林凝结体体力-剑林-体力-价格50-可选"
    )
    assert cleanup["custom_action_param"]["evidence"]["target_name"] == (
        "0981-剑林凝结体体力-剑林-体力-价格50-可选"
    )


def test_jianlin_cleanup_closes_both_nested_pages_before_home_success() -> None:
    nodes = _load("daily/jianlin_resource_condensate_stamina_daily.json")
    page_close = nodes["0959-剑林凝结体体力-清理-页面-关闭"]
    daily_close = nodes["0960-剑林凝结体体力-清理-日常-关闭"]

    assert page_close["post_delay"] == 1500
    assert page_close["next"] == [
        "0960-剑林凝结体体力-清理-日常-关闭",
        "1371-公共-原生成功-主页边界",
    ]
    assert daily_close["custom_action"] == "GuardedInput"
    assert daily_close["custom_action_param"]["action_id"] == "close_daily_tasks"
    assert daily_close["custom_action_param"]["fixed_click_mode"] == (
        "jianlin_page_close"
    )
    assert daily_close["next"] == ["1371-公共-原生成功-主页边界"]


def test_ring_zero_attempts_are_success_and_page_title_allows_banner_text() -> None:
    nodes = _load("daily/ring_challenge_daily.json")
    entry = nodes["1079-擂台挑战-点击-擂台"]
    completed = nodes["1180-擂台挑战-擂台-次数为0-已完成"]

    assert entry["next"][0] == "1180-擂台挑战-擂台-次数为0-已完成"
    assert completed["recognition"]["param"]["all_of"] == [
        "1138-擂台挑战-擂台-页面",
        "1143-擂台挑战-擂台-次数-耗尽",
    ]
    assert completed["next"] == ["1121-擂台挑战-关闭-页面"]
    assert nodes["1138-擂台挑战-擂台-页面"]["expected"] == [
        "^擂台$",
        "擂台",
        "\\d{1,2}\\s*/\\s*12",
    ]
    assert nodes["1139-擂台挑战-擂台-页面-证据"]["expected"] == [
        "^擂台$",
        "擂台",
        "\\d{1,2}\\s*/\\s*12",
    ]
    assert nodes["1122-擂台挑战-关闭-对弈"]["custom_action"] == "GuardedInput"


def test_hero_claim_recognition_covers_visible_button_variants() -> None:
    node = _load("daily/hero_dispatch_daily.json")[
        "0754-英雄派遣-英雄-领取-按钮"
    ]

    assert node["expected"] == ["领取", "领 取"]
    assert node["roi"] == [900, 450, 380, 220]


def test_dungeon_zero_assignment_is_not_a_success_terminal() -> None:
    nodes = _load("daily/dungeon_sweep_daily.json")
    open_sweep = nodes["0318-副本扫荡-打开-扫荡"]

    assert open_sweep["next"] == ["0324-副本扫荡-选择-面板-燕王"]
    assert "0321-副本扫荡-数量为0-已完成" not in nodes
    assert "0375-副本扫荡-副本-扫荡数量为0" not in nodes


def test_dungeon_close_accepts_the_current_challenge_page_title() -> None:
    node = _load("daily/dungeon_sweep_daily.json")["0344-副本扫荡-副本-页面"]

    assert node["expected"] == ["副本", "^.*前往挑战.*$"]


def test_dungeon_close_uses_the_visible_close_control_before_home_boundary() -> None:
    nodes = _load("daily/dungeon_sweep_daily.json")

    for name in ("0337-副本扫荡-成功-关闭",):
        assert nodes[name]["recognition"]["param"]["all_of"] == [
            "0374-副本扫荡-副本-关闭"
        ]
        assert nodes[name]["action"] == "Click"
        assert nodes[name]["target"] == [1202, 30, 24, 24]
        assert nodes[name]["post_delay"] == 1500
        assert nodes[name]["next"] == ["1371-公共-原生成功-主页边界"]

    assert "0338-副本扫荡-关闭后返回主页" not in nodes


def test_guild_donation_requires_post_click_nine_of_ten() -> None:
    nodes = _load("daily/guild_donation_daily.json")
    donation = nodes["0681-帮派捐献-捐献-免费"]
    donation_entry = nodes["0674-帮派捐献-打开-捐献"]
    reward_close = nodes["0683-帮派捐献-捐献-关闭-奖励"]
    unchanged = nodes["0707-帮派捐献-帮派-捐献-剩余-10-共-10"]
    completed = nodes["0708-帮派捐献-帮派-捐献-剩余-9-共-10"]

    assert donation["next"][0:2] == [
        "0707-帮派捐献-帮派-捐献-剩余-10-共-10",
        "0708-帮派捐献-帮派-捐献-剩余-9-共-10",
    ]
    assert donation["recognition"]["param"]["all_of"] == [
        "0705-帮派捐献-帮派-捐献-免费",
        "0715-帮派捐献-免费按钮-文字",
    ]
    assert donation["recognition"]["param"]["box_index"] == 1
    assert donation_entry["next"][:2] == [
        "0708-帮派捐献-帮派-捐献-剩余-9-共-10",
        "0681-帮派捐献-捐献-免费",
    ]
    assert reward_close["next"] == donation["next"][0:2]
    assert unchanged["custom_action"] == "FailTask"
    assert unchanged["Abort"] is True
    assert "next" not in unchanged
    assert completed["next"] == ["0690-帮派捐献-关闭-捐献"]


def test_shadow_ruins_accepts_direct_exploration_and_continues() -> None:
    nodes = _load("daily/shadow_ruins_daily.json")

    assert nodes["1174-影之遗迹-进入-关卡"]["next"][:2] == [
        "1176-影之遗迹-跨图-确认",
        "1593-MJA-影之遗迹-进入-探索页",
    ]
    assert nodes["1593-MJA-影之遗迹-进入-探索页"]["next"] == [
        "1501-MJA-影之遗迹地图推进-前景三点循环"
    ]
    assert nodes["1511-MJA-影之遗迹地图推进-战斗胜利"]["next"] == [
        "1501-MJA-影之遗迹地图推进-前景三点循环"
    ]


def test_shadow_ruins_starts_battle_from_the_preparation_screen() -> None:
    nodes = _load("daily/shadow_ruins_daily.json")

    start = nodes["1594-MJA-影之遗迹-开始战斗"]
    foreground = nodes["1501-MJA-影之遗迹地图推进-前景三点循环"]

    assert foreground["next"][:2] == [
        "1595-MJA-影之遗迹-确认退出",
        "1594-MJA-影之遗迹-开始战斗",
    ]
    assert start["custom_action"] == "GuardedInput"
    assert start["custom_action_param"]["action_id"] == "challenge_shadow_stage"
    assert start["custom_action_param"]["fixed_click_mode"] == "shadow_battle_start"
    assert start["next"] == [
        "[JumpBack]1509-MJA-影之遗迹地图推进-战斗等待"
    ]


def test_shadow_ruins_confirms_the_exit_dialog() -> None:
    nodes = _load("daily/shadow_ruins_daily.json")

    confirm = nodes["1595-MJA-影之遗迹-确认退出"]
    assert nodes["1501-MJA-影之遗迹地图推进-前景三点循环"]["next"][0] == (
        "1595-MJA-影之遗迹-确认退出"
    )
    assert confirm["custom_action_param"]["action_id"] == "confirm_shadow_completion"
    assert confirm["custom_action_param"]["fixed_click_mode"] == (
        "shadow_completion_confirm"
    )
    assert confirm["recognition"]["param"]["all_of"] == [
        "1596-MJA-影之遗迹-退出确认-文案"
    ]
    assert confirm["next"] == [
        "1597-MJA-影之遗迹-关闭奖励弹窗",
        "[JumpBack]1591-MJA-影之遗迹-关闭-影-页面",
        "1371-公共-原生成功-主页边界",
    ]
    assert nodes["1529-MJA-影之遗迹地图推进-识别-前景就绪"]["expected"] == [
        "^第.+层$",
        "^●-$",
    ]
    reward = nodes["1597-MJA-影之遗迹-关闭奖励弹窗"]
    assert reward["recognition"]["param"]["all_of"] == [
        "1598-MJA-影之遗迹-奖励弹窗文案"
    ]
    assert nodes["1598-MJA-影之遗迹-奖励弹窗文案"]["expected"] == [
        "^恭$",
        "^喜获得$",
        "^[恭泰]喜获得$",
    ]
    assert reward["custom_action_param"]["action_id"] == (
        "dismiss_shadow_reward_popup"
    )
    assert reward["custom_action_param"]["fixed_click_mode"] == (
        "shadow_reward_blank"
    )
    assert reward["next"] == [
        "1597-MJA-影之遗迹-关闭奖励弹窗",
        "[JumpBack]1591-MJA-影之遗迹-关闭-影-页面",
        "1371-公共-原生成功-主页边界",
    ]


def test_completed_task_cleanup_uses_native_home_boundary() -> None:
    cases = {
        "daily/dungeon_sweep_daily.json": [
            "0337-副本扫荡-成功-关闭",
        ],
        "daily/guild_donation_daily.json": [
            "0692-帮派捐献-关闭-面板",
            "0708-帮派捐献-帮派-捐献-剩余-9-共-10",
        ],
        "daily/jianlin_resource_condensate_stamina_daily.json": [
            "0959-剑林凝结体体力-清理-页面-关闭",
        ],
        "daily/battle_pass_reward_daily.json": ["0063-战令奖励-关闭-成功"],
    }

    for relative, node_names in cases.items():
        nodes = _load(relative)
        for node_name in node_names:
            expected_next = (
                ["1371-公共-原生成功-主页边界"]
                if relative == "daily/dungeon_sweep_daily.json"
                else ["0690-帮派捐献-关闭-捐献"]
                if (
                    relative == "daily/guild_donation_daily.json"
                    and node_name == "0708-帮派捐献-帮派-捐献-剩余-9-共-10"
                )
                else [
                    "0960-剑林凝结体体力-清理-日常-关闭",
                    "1371-公共-原生成功-主页边界",
                ]
                if (
                    relative
                    == "daily/jianlin_resource_condensate_stamina_daily.json"
                    and node_name == "0959-剑林凝结体体力-清理-页面-关闭"
                )
                else ["1371-公共-原生成功-主页边界"]
            )
            assert nodes[node_name]["next"] == expected_next, (relative, node_name)


def test_shadow_ruins_keeps_three_fixed_foreground_clicks() -> None:
    node = _load("daily/shadow_ruins_daily.json")[
        "1501-MJA-影之遗迹地图推进-前景三点循环"
    ]
    assert node["custom_action_param"]["fixed_click_boxes"] == [
        [436, 536, 24, 24],
        [629, 536, 24, 24],
        [822, 536, 24, 24],
    ]
    assert node["next"][-1] == "[JumpBack]1501-MJA-影之遗迹地图推进-前景三点循环"


def test_ring_sweep_confirms_the_ticket_conversion_before_result_cleanup() -> None:
    nodes = _load("daily/ring_challenge_daily.json")
    sweep = nodes["1094-擂台挑战-大师-点击扫荡"]
    confirm = nodes["1172-擂台挑战-扫荡-确认"]

    assert sweep["next"] == [
        "1095-擂台挑战-擂台-券-耗尽-探测",
        "1172-擂台挑战-扫荡-确认",
        "1113-擂台挑战-关闭-结果",
    ]
    assert confirm["custom_action"] == "GuardedInput"
    assert confirm["custom_action_param"]["action_id"] == "confirm_ring_sweep"
    assert confirm["custom_action_param"]["evidence"]["target_name"] == (
        "1163-擂台挑战-擂台-扫荡-确认"
    )


def test_condensate_budget_uses_confirmed_large_cap_without_removing_action_guards() -> None:
    policy = TASK_POLICIES["SPEND_CONDENSATE_DAILY"]

    assert policy.resource_caps["凝晶"] == 999_999_999
    assert policy.action_caps["buy_yanwu_currency_max"] == 1
    assert policy.action_caps["buy_yunzhou_currency_max"] == 1


def test_break_array_is_in_the_executable_interface() -> None:
    interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
    assert "tasks/日常/BREAK_ARRAY_MARTIAL_DAILY.json" in interface["import"]
    assert any(
        item.get("name") == "BREAK_ARRAY_MARTIAL_DAILY" and item["enabled"] is True
        for preset in interface["preset"]
        if preset["name"] == "日常-完整版"
        for item in preset["task"]
    )
    assert (ROOT / "assets/tasks/日常/BREAK_ARRAY_MARTIAL_DAILY.json").exists()
