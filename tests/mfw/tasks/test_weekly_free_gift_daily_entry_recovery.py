from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    load_task_nodes,
)
from tools.mfw_task_selection import select_tasks


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline/daily/weekly_free_gift_daily.json"
WEEKLY = TaskContract("WEEKLY_FREE_GIFT_DAILY", "daily/weekly_free_gift_daily.json")


def _pipeline() -> dict[str, dict[str, Any]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_weekly_gift_is_selectable_every_day() -> None:
    for operation_date in (date(2026, 8, 17), date(2026, 8, 23)):
        selection = select_tasks(
            ROOT,
            operation_date=operation_date,
            explicit_tasks=("WEEKLY_FREE_GIFT_DAILY",),
        )
        assert selection["selected_tasks"] == ["WEEKLY_FREE_GIFT_DAILY"]


def test_weekly_entry_preserves_bounded_navigation_recovery() -> None:
    nodes = _pipeline()

    assert nodes["0022-每周免费礼包-任务入口"]["next"] == [
        "1336-每周免费礼包-打开-面板"
    ]
    assert nodes["0022-每周免费礼包-任务入口"]["timeout"] == 5000
    assert nodes["0022-每周免费礼包-任务入口"]["on_error"] == [
        "MJA-任务入口失败-WEEKLY_FREE_GIFT_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    for name in (
        "1336-每周免费礼包-打开-面板",
        "1337-每周免费礼包-打开-商店",
        "1338-每周免费礼包-打开-礼包-标签",
    ):
        assert nodes[name]["max_hit"] == 1
        assert nodes[name].get("retry_times", 0) == 0
        assert "on_error" not in nodes[name]
    assert nodes["1339-每周免费礼包-打开-每周"]["on_error"] == [
        "1345-每周免费礼包-关闭"
    ]


def test_weekly_page_has_explicit_available_and_already_claimed_candidates() -> None:
    nodes = _pipeline()

    assert nodes["1339-每周免费礼包-打开-每周"]["next"] == [
        "1340-每周免费礼包-免费-领取",
        "1343-每周免费礼包-已完成",
    ]
    available = nodes["1340-每周免费礼包-免费-领取"]
    assert available["recognition"]["param"]["all_of"] == [
        "1350-每周免费礼包-商店-每周-页面",
        "1351-每周免费礼包-商店-每周-幸运-背包-免费",
    ]
    assert available["next"] == ["1341-每周免费礼包-奖励-成功"]

    claimed = nodes["1343-每周免费礼包-已完成"]
    assert claimed["recognition"]["param"]["all_of"] == [
        "1350-每周免费礼包-商店-每周-页面",
        "1353-每周免费礼包-商店-每周-幸运-背包-已领取",
    ]
    assert claimed["next"] == ["1345-每周免费礼包-关闭"]


def test_weekly_success_candidates_use_native_cleanup() -> None:
    nodes = load_task_nodes(WEEKLY)

    assert nodes["1341-每周免费礼包-奖励-成功"]["action"] == "DoNothing"
    assert nodes["1341-每周免费礼包-奖励-成功"]["next"] == [
        "1342-每周免费礼包-关闭-奖励"
    ]
    assert nodes["1342-每周免费礼包-关闭-奖励"]["on_error"] == [
        "1345-每周免费礼包-关闭"
    ]
    assert nodes["1345-每周免费礼包-关闭"]["next"] == [
        "1346-每周免费礼包-完成-关闭-面板"
    ]
    assert nodes["1346-每周免费礼包-完成-关闭-面板"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_weekly_has_no_recorder_or_error_as_state_route() -> None:
    nodes = _pipeline()

    assert_no_custom_outcome_nodes(nodes)
    assert "1344-每周免费礼包-记录-失败" not in nodes
    assert_on_error_contract(
        nodes,
        local_nodes=set(nodes),
        shared_targets={"1369-公共-通用停止"},
    )
    for name in (
        "1340-每周免费礼包-免费-领取",
        "1341-每周免费礼包-奖励-成功",
        "1343-每周免费礼包-已完成",
        "1336-每周免费礼包-打开-面板",
        "1337-每周免费礼包-打开-商店",
        "1338-每周免费礼包-打开-礼包-标签",
    ):
        assert "on_error" not in nodes[name]
    assert nodes["1339-每周免费礼包-打开-每周"]["on_error"] == [
        "1345-每周免费礼包-关闭"
    ]


def test_weekly_cleanup_failure_stops_without_downgrading_success() -> None:
    nodes = _pipeline()

    assert nodes["1345-每周免费礼包-关闭"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert nodes["1346-每周免费礼包-完成-关闭-面板"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert_no_side_effect_retry(load_task_nodes(WEEKLY), "claim_weekly_lucky_bag")


def test_weekly_cleanup_closes_function_panel_at_fixed_close_button() -> None:
    nodes = _pipeline()
    close_panel = nodes["1346-每周免费礼包-完成-关闭-面板"]["custom_action_param"]

    assert close_panel["action_id"] == "close_function_panel"
    assert close_panel["fixed_click_mode"] == "function_panel_close"


def test_weekly_preserves_guarded_actions_and_caps() -> None:
    nodes = load_task_nodes(WEEKLY)
    policy = TASK_POLICIES[WEEKLY.task_id]

    assert_guarded_actions(
        nodes,
        WEEKLY.task_id,
        [
            "open_function_panel",
            "open_shop",
            "open_gift_tab",
            "open_weekly_must_buy",
            "claim_weekly_lucky_bag",
            "dismiss_weekly_reward",
            "close_shop",
            "close_function_panel",
        ],
    )
    assert policy.action_caps == {
        "open_function_panel": 1,
        "open_shop": 1,
        "open_gift_tab": 1,
        "open_weekly_must_buy": 1,
        "claim_weekly_lucky_bag": 1,
        "dismiss_weekly_reward": 1,
        "close_shop": 1,
        "close_function_panel": 1,
    }
    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if params.get("task_id") != WEEKLY.task_id:
            continue
        action_id = params.get("action_id")
        if action_id not in policy.action_caps:
            continue
        assert node.get("retry_times", 0) == 0
        assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
