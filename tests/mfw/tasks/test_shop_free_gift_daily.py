from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_outcome,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

SHOP = TaskContract("SHOP_FREE_GIFT_DAILY", "daily/shop_free_gift_daily.json")
RECOVERY_ATTEMPTS = [
    "商店免费礼包-运行时-恢复-尝试-1",
    "商店免费礼包-运行时-恢复-尝试-2",
]
RECOVERY_EXHAUSTED = "商店免费礼包-运行时-恢复-耗尽"
RECOVERY_ROUTE = [*RECOVERY_ATTEMPTS, RECOVERY_EXHAUSTED]
POST_CLAIM_RECOVERY_ATTEMPTS = [
    "商店免费礼包-领取后-恢复-尝试-1",
    "商店免费礼包-领取后-恢复-尝试-2",
]
POST_CLAIM_RECOVERY_EXHAUSTED = "商店免费礼包-领取后-恢复-耗尽"
POST_CLAIM_RECOVERY_ROUTE = [
    *POST_CLAIM_RECOVERY_ATTEMPTS,
    POST_CLAIM_RECOVERY_EXHAUSTED,
]
ALLOWED_TERMINAL_STATUSES = {
    "success",
    "already_complete",
    "not_eligible",
    "failed",
}
POST_TERMINAL_CLEANUP = {
    "商店免费礼包-关闭",
    "商店免费礼包-面板关闭后",
    "商店免费礼包-关闭-面板",
    "商店免费礼包-主页-返回-探测",
    "商店免费礼包-关闭-已完成",
    "商店免费礼包-面板关闭后-已完成",
    "商店免费礼包-关闭-面板-已完成",
    "商店免费礼包-主页-返回-探测-已完成",
}


def _task_nodes(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {name: node for name, node in nodes.items() if name.startswith("商店免费礼包-")}


def _targets(node: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list):
            continue
        for target in values:
            if not isinstance(target, str):
                continue
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            result.append(target)
    return result


def _reachable_names(nodes: Mapping[str, Mapping[str, Any]], source: str) -> set[str]:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(_targets(nodes.get(current, {})))
    return visited


def test_shop_process_exit_recovery_is_bounded_and_truthful() -> None:
    assert_task_contract(SHOP)
    nodes = load_task_nodes(SHOP)

    assert nodes["商店免费礼包-任务入口"]["next"] == [
        "商店免费礼包-直接-状态-探测",
        "商店免费礼包-直接-领取-门禁",
        "商店免费礼包-打开-周期",
        "商店免费礼包-权益-页面-探测",
        "商店免费礼包-面板-探测",
        "商店免费礼包-页面-探测",
        "商店免费礼包-主页-探测",
    ]
    assert nodes["商店免费礼包-任务入口"]["on_error"] == RECOVERY_ROUTE
    for attempt in RECOVERY_ATTEMPTS:
        assert nodes[attempt]["next"] == [
            "商店免费礼包-直接-状态-探测",
            "商店免费礼包-直接-领取-门禁",
            "商店免费礼包-打开-周期",
            "商店免费礼包-权益-页面-探测",
            "商店免费礼包-面板-探测",
            "商店免费礼包-页面-探测",
            "商店免费礼包-主页-探测",
            "[JumpBack]启动-游戏启动",
        ]
        assert nodes[attempt]["timeout"] == 30000
        assert nodes[attempt]["max_hit"] == 2
    assert nodes[RECOVERY_ATTEMPTS[0]]["on_error"] == [
        RECOVERY_ATTEMPTS[1],
        RECOVERY_EXHAUSTED,
    ]
    assert nodes[RECOVERY_ATTEMPTS[1]]["on_error"] == [RECOVERY_EXHAUSTED]
    assert nodes[RECOVERY_EXHAUSTED]["custom_action_param"]["status"] == "failed"
    assert nodes[RECOVERY_EXHAUSTED]["custom_action_param"]["error_code"] == (
        "SHOP_RUNTIME_RECOVERY_EXHAUSTED"
    )
    assert nodes[RECOVERY_EXHAUSTED]["Abort"] is True
    assert_reachable(nodes, RECOVERY_EXHAUSTED, "公共-通用中止")


def test_shop_pre_claim_navigation_failures_converge_on_bounded_recovery() -> None:
    nodes = load_task_nodes(SHOP)

    for node_name in (
        "商店免费礼包-页面-探测",
        "商店免费礼包-权益-页面-探测",
        "商店免费礼包-领取-门禁",
        "商店免费礼包-主页-探测",
        "商店免费礼包-打开-面板",
        "商店免费礼包-面板-探测",
        "商店免费礼包-打开-商店",
        "商店免费礼包-打开-周期",
    ):
        assert nodes[node_name]["on_error"] == RECOVERY_ROUTE

    assert nodes["商店免费礼包-状态-探测"]["on_error"] == [
        "商店免费礼包-领取-门禁",
        *RECOVERY_ROUTE,
    ]
    assert nodes["商店免费礼包-页面-探测"]["next"] == [
        "商店免费礼包-直接-状态-探测",
        "商店免费礼包-直接-领取-门禁",
        "商店免费礼包-打开-周期",
        "商店免费礼包-权益-页面-探测",
    ]
    assert nodes["商店免费礼包-打开-周期"]["next"] == ["商店免费礼包-权益-页面-探测"]


def test_shop_post_claim_recovery_verifies_without_replaying_claim() -> None:
    nodes = load_task_nodes(SHOP)

    assert nodes["商店免费礼包-领取"]["retry_times"] == 0
    assert nodes["商店免费礼包-领取"]["on_error"] == ["商店免费礼包-记录-失败"]
    assert nodes["商店免费礼包-直接-领取"]["retry_times"] == 0
    assert nodes["商店免费礼包-直接-领取"]["on_error"] == ["商店免费礼包-记录-失败"]
    assert_no_side_effect_retry(nodes, "claim_free_gift")
    assert nodes["商店免费礼包-奖励-探测"]["on_error"] == POST_CLAIM_RECOVERY_ROUTE
    assert nodes["商店免费礼包-关闭-奖励"]["on_error"] == POST_CLAIM_RECOVERY_ROUTE
    assert nodes["商店免费礼包-关闭-奖励"]["next"] == [
        "商店免费礼包-领取-校验",
        "商店免费礼包-直接-领取-校验",
    ]
    assert nodes["商店免费礼包-领取-校验"]["on_error"] == POST_CLAIM_RECOVERY_ROUTE
    assert nodes["商店免费礼包-直接-领取-校验"]["on_error"] == (POST_CLAIM_RECOVERY_ROUTE)
    for attempt in POST_CLAIM_RECOVERY_ATTEMPTS:
        assert nodes[attempt]["timeout"] == 30000
        assert nodes[attempt]["max_hit"] == 2
        assert "商店免费礼包-领取" not in _reachable_names(nodes, attempt)
    assert nodes[POST_CLAIM_RECOVERY_ATTEMPTS[0]]["on_error"] == [
        POST_CLAIM_RECOVERY_ATTEMPTS[1],
        POST_CLAIM_RECOVERY_EXHAUSTED,
    ]
    assert nodes[POST_CLAIM_RECOVERY_ATTEMPTS[1]]["on_error"] == [POST_CLAIM_RECOVERY_EXHAUSTED]
    assert (
        nodes[POST_CLAIM_RECOVERY_EXHAUSTED]["custom_action_param"]["error_code"]
        == "SHOP_POST_CLAIM_STATE_UNKNOWN"
    )
    assert nodes[POST_CLAIM_RECOVERY_EXHAUSTED]["Abort"] is True
    assert_reachable(nodes, POST_CLAIM_RECOVERY_EXHAUSTED, "公共-通用中止")


def test_shop_live_daily_deals_page_can_claim_without_period_benefits() -> None:
    nodes = load_task_nodes(SHOP)

    direct_status = nodes["商店免费礼包-直接-状态-探测"]
    assert direct_status["recognition"]["param"] == {
        "all_of": ["商店免费礼包-商店-页面", "商店免费礼包-商店-日常-免费-礼包-已领取"],
        "box_index": 1,
    }
    assert direct_status["next"] == ["商店免费礼包-已完成"]

    direct_gate = nodes["商店免费礼包-直接-领取-门禁"]
    assert direct_gate["recognition"]["param"] == {
        "all_of": ["商店免费礼包-商店-页面", "商店免费礼包-商店-日常-免费-礼包"],
        "box_index": 1,
    }
    assert direct_gate["next"] == ["商店免费礼包-直接-领取"]

    direct_claim = nodes["商店免费礼包-直接-领取"]
    assert direct_claim["recognition"]["param"] == {
        "all_of": ["商店免费礼包-商店-页面", "商店免费礼包-商店-日常-免费-礼包"],
        "box_index": 1,
    }
    assert direct_claim["custom_action"] == "GuardedInput"
    assert direct_claim["custom_action_param"]["action_id"] == "claim_free_gift"
    assert direct_claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "商店免费礼包-商店-页面",
        "target_name": "商店免费礼包-商店-日常-免费-礼包",
    }

    direct_verify = nodes["商店免费礼包-直接-领取-校验"]
    assert direct_verify["recognition"]["param"] == {
        "all_of": ["商店免费礼包-商店-页面", "商店免费礼包-商店-日常-免费-礼包-已领取"],
        "box_index": 1,
    }
    assert direct_verify["next"] == ["商店免费礼包-成功"]
    assert nodes["商店免费礼包-领取后-页面-探测"]["next"] == [
        "商店免费礼包-直接-领取-校验",
        "商店免费礼包-领取后-打开-周期",
    ]


def test_shop_recovery_policy_replays_only_idempotent_navigation() -> None:
    policy = TASK_POLICIES[SHOP.task_id]

    assert policy.action_caps["open_function_panel"] == 3
    assert policy.action_caps["open_shop"] == 3
    assert policy.action_caps["open_period_benefits"] == 3
    assert policy.action_caps["claim_free_gift"] == 1
    assert policy.action_caps["dismiss_free_gift_reward"] == 1
    assert policy.action_caps["close_function_panel"] == 1


def test_shop_all_task_branches_write_an_allowed_terminal_outcome() -> None:
    nodes = load_task_nodes(SHOP)
    scoped = _task_nodes(nodes)
    outcomes = {
        name for name, node in scoped.items() if node.get("custom_action") == "RecordTaskOutcome"
    }

    assert outcomes
    for outcome in outcomes:
        status = scoped[outcome]["custom_action_param"]["status"]
        assert status in ALLOWED_TERMINAL_STATUSES

    for name, node in scoped.items():
        if name in outcomes or name in POST_TERMINAL_CLEANUP:
            continue
        assert node.get("on_error"), f"{name} can fail without recording a terminal result"
        reachable = _reachable_names(nodes, name)
        assert outcomes & reachable, f"{name} cannot reach a task outcome"

    for outcome in outcomes:
        params = scoped[outcome]["custom_action_param"]
        if params["status"] == "failed":
            assert scoped[outcome]["Abort"] is True
            assert_reachable(nodes, outcome, "公共-通用中止")

    assert_outcome(
        nodes,
        "商店免费礼包-记录-已完成",
        "already_complete",
        "shop.daily_free_gift_claimed",
    )
    assert_outcome(
        nodes,
        "商店免费礼包-记录-成功",
        "success",
        "shop.daily_free_gift_claimed",
    )
    assert nodes["商店免费礼包-已完成"]["action"] == "DoNothing"
    assert nodes["商店免费礼包-已完成"]["next"] == [
        "商店免费礼包-关闭-已完成"
    ]
    assert nodes["商店免费礼包-成功"]["action"] == "DoNothing"
    assert nodes["商店免费礼包-成功"]["next"] == ["商店免费礼包-关闭"]
    assert nodes["商店免费礼包-关闭"]["next"] == ["商店免费礼包-面板关闭后"]
    assert nodes["商店免费礼包-面板关闭后"]["next"] == ["商店免费礼包-关闭-面板"]
    assert nodes["商店免费礼包-关闭-面板"]["next"] == ["商店免费礼包-主页-返回-探测"]
    assert nodes["商店免费礼包-主页-返回-探测"]["next"] == [
        "商店免费礼包-记录-成功"
    ]
    assert nodes["商店免费礼包-关闭-已完成"]["next"] == [
        "商店免费礼包-面板关闭后-已完成"
    ]
    assert nodes["商店免费礼包-面板关闭后-已完成"]["next"] == [
        "商店免费礼包-关闭-面板-已完成"
    ]
    assert nodes["商店免费礼包-关闭-面板-已完成"]["next"] == [
        "商店免费礼包-主页-返回-探测-已完成"
    ]
    assert nodes["商店免费礼包-主页-返回-探测-已完成"]["next"] == [
        "商店免费礼包-记录-已完成"
    ]
    assert nodes["商店免费礼包-关闭"]["on_error"] == ["商店免费礼包-记录-失败"]
    assert nodes["商店免费礼包-面板关闭后"]["on_error"] == [
        "商店免费礼包-记录-失败"
    ]
    assert nodes["商店免费礼包-关闭-面板"]["on_error"] == ["商店免费礼包-记录-失败"]
    assert nodes["商店免费礼包-主页-返回-探测"]["on_error"] == [
        "商店免费礼包-记录-失败"
    ]


def test_shop_terminal_outcome_is_written_only_after_panel_and_home_cleanup() -> None:
    nodes = load_task_nodes(SHOP)

    for branch, cleanup, outcome in (
        (
            "商店免费礼包-成功",
            [
                "商店免费礼包-关闭",
                "商店免费礼包-面板关闭后",
                "商店免费礼包-关闭-面板",
                "商店免费礼包-主页-返回-探测",
            ],
            "商店免费礼包-记录-成功",
        ),
        (
            "商店免费礼包-已完成",
            [
                "商店免费礼包-关闭-已完成",
                "商店免费礼包-面板关闭后-已完成",
                "商店免费礼包-关闭-面板-已完成",
                "商店免费礼包-主页-返回-探测-已完成",
            ],
            "商店免费礼包-记录-已完成",
        ),
    ):
        assert nodes[branch].get("custom_action") is None
        assert _reachable_names(nodes, branch) >= {*cleanup, outcome}
        assert not any(
            nodes[name].get("custom_action") == "RecordTaskOutcome"
            for name in cleanup
        )
        assert nodes[outcome]["custom_action"] == "RecordTaskOutcome"
