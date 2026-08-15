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
    "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_1",
    "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_2",
]
RECOVERY_EXHAUSTED = "MJA_SHOP_RUNTIME_RECOVERY_EXHAUSTED"
RECOVERY_ROUTE = [*RECOVERY_ATTEMPTS, RECOVERY_EXHAUSTED]
POST_CLAIM_RECOVERY_ATTEMPTS = [
    "MJA_SHOP_POST_CLAIM_RECOVERY_ATTEMPT_1",
    "MJA_SHOP_POST_CLAIM_RECOVERY_ATTEMPT_2",
]
POST_CLAIM_RECOVERY_EXHAUSTED = "MJA_SHOP_POST_CLAIM_RECOVERY_EXHAUSTED"
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
    "MJA_SHOP_CLOSE",
    "MJA_SHOP_PANEL_AFTER_CLOSE",
    "MJA_SHOP_CLOSE_PANEL",
    "MJA_SHOP_HOME_RETURN_PROBE",
    "MJA_SHOP_CLOSE_ALREADY_COMPLETE",
    "MJA_SHOP_PANEL_AFTER_CLOSE_ALREADY_COMPLETE",
    "MJA_SHOP_CLOSE_PANEL_ALREADY_COMPLETE",
    "MJA_SHOP_HOME_RETURN_PROBE_ALREADY_COMPLETE",
}


def _task_nodes(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {name: node for name, node in nodes.items() if name.startswith("MJA_SHOP_")}


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

    assert nodes["MJA_SHOP_FREE_GIFT_DAILY_START"]["next"] == [
        "MJA_SHOP_DIRECT_STATUS_PROBE",
        "MJA_SHOP_DIRECT_CLAIM_GATE",
        "MJA_SHOP_OPEN_PERIOD",
        "MJA_SHOP_BENEFITS_PAGE_PROBE",
        "MJA_SHOP_PANEL_PROBE",
        "MJA_SHOP_PAGE_PROBE",
        "MJA_SHOP_HOME_PROBE",
    ]
    assert nodes["MJA_SHOP_FREE_GIFT_DAILY_START"]["on_error"] == RECOVERY_ROUTE
    for attempt in RECOVERY_ATTEMPTS:
        assert nodes[attempt]["next"] == [
            "MJA_SHOP_DIRECT_STATUS_PROBE",
            "MJA_SHOP_DIRECT_CLAIM_GATE",
            "MJA_SHOP_OPEN_PERIOD",
            "MJA_SHOP_BENEFITS_PAGE_PROBE",
            "MJA_SHOP_PANEL_PROBE",
            "MJA_SHOP_PAGE_PROBE",
            "MJA_SHOP_HOME_PROBE",
            "[JumpBack]MJA_GAME_START",
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
    assert_reachable(nodes, RECOVERY_EXHAUSTED, "MJA_COMMON_ABORT")


def test_shop_pre_claim_navigation_failures_converge_on_bounded_recovery() -> None:
    nodes = load_task_nodes(SHOP)

    for node_name in (
        "MJA_SHOP_PAGE_PROBE",
        "MJA_SHOP_BENEFITS_PAGE_PROBE",
        "MJA_SHOP_CLAIM_GATE",
        "MJA_SHOP_HOME_PROBE",
        "MJA_SHOP_OPEN_PANEL",
        "MJA_SHOP_PANEL_PROBE",
        "MJA_SHOP_OPEN_SHOP",
        "MJA_SHOP_OPEN_PERIOD",
    ):
        assert nodes[node_name]["on_error"] == RECOVERY_ROUTE

    assert nodes["MJA_SHOP_STATUS_PROBE"]["on_error"] == [
        "MJA_SHOP_CLAIM_GATE",
        *RECOVERY_ROUTE,
    ]
    assert nodes["MJA_SHOP_PAGE_PROBE"]["next"] == [
        "MJA_SHOP_DIRECT_STATUS_PROBE",
        "MJA_SHOP_DIRECT_CLAIM_GATE",
        "MJA_SHOP_OPEN_PERIOD",
        "MJA_SHOP_BENEFITS_PAGE_PROBE",
    ]
    assert nodes["MJA_SHOP_OPEN_PERIOD"]["next"] == ["MJA_SHOP_BENEFITS_PAGE_PROBE"]


def test_shop_post_claim_recovery_verifies_without_replaying_claim() -> None:
    nodes = load_task_nodes(SHOP)

    assert nodes["MJA_SHOP_CLAIM"]["retry_times"] == 0
    assert nodes["MJA_SHOP_CLAIM"]["on_error"] == ["MJA_SHOP_RECORD_FAILURE"]
    assert nodes["MJA_SHOP_DIRECT_CLAIM"]["retry_times"] == 0
    assert nodes["MJA_SHOP_DIRECT_CLAIM"]["on_error"] == ["MJA_SHOP_RECORD_FAILURE"]
    assert_no_side_effect_retry(nodes, "claim_free_gift")
    assert nodes["MJA_SHOP_REWARD_PROBE"]["on_error"] == POST_CLAIM_RECOVERY_ROUTE
    assert nodes["MJA_SHOP_CLOSE_REWARD"]["on_error"] == POST_CLAIM_RECOVERY_ROUTE
    assert nodes["MJA_SHOP_CLOSE_REWARD"]["next"] == [
        "MJA_SHOP_CLAIM_VERIFY",
        "MJA_SHOP_DIRECT_CLAIM_VERIFY",
    ]
    assert nodes["MJA_SHOP_CLAIM_VERIFY"]["on_error"] == POST_CLAIM_RECOVERY_ROUTE
    assert nodes["MJA_SHOP_DIRECT_CLAIM_VERIFY"]["on_error"] == (POST_CLAIM_RECOVERY_ROUTE)
    for attempt in POST_CLAIM_RECOVERY_ATTEMPTS:
        assert nodes[attempt]["timeout"] == 30000
        assert nodes[attempt]["max_hit"] == 2
        assert "MJA_SHOP_CLAIM" not in _reachable_names(nodes, attempt)
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
    assert_reachable(nodes, POST_CLAIM_RECOVERY_EXHAUSTED, "MJA_COMMON_ABORT")


def test_shop_live_daily_deals_page_can_claim_without_period_benefits() -> None:
    nodes = load_task_nodes(SHOP)

    direct_status = nodes["MJA_SHOP_DIRECT_STATUS_PROBE"]
    assert direct_status["recognition"]["param"] == {
        "all_of": ["shop.page", "shop.daily_free_gift_claimed"],
        "box_index": 1,
    }
    assert direct_status["next"] == ["MJA_SHOP_ALREADY_COMPLETE"]

    direct_gate = nodes["MJA_SHOP_DIRECT_CLAIM_GATE"]
    assert direct_gate["recognition"]["param"] == {
        "all_of": ["shop.page", "shop.daily_free_gift"],
        "box_index": 1,
    }
    assert direct_gate["next"] == ["MJA_SHOP_DIRECT_CLAIM"]

    direct_claim = nodes["MJA_SHOP_DIRECT_CLAIM"]
    assert direct_claim["recognition"]["param"] == {
        "all_of": ["shop.page", "shop.daily_free_gift"],
        "box_index": 1,
    }
    assert direct_claim["custom_action"] == "GuardedInput"
    assert direct_claim["custom_action_param"]["action_id"] == "claim_free_gift"
    assert direct_claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "shop.page",
        "target_name": "shop.daily_free_gift",
    }

    direct_verify = nodes["MJA_SHOP_DIRECT_CLAIM_VERIFY"]
    assert direct_verify["recognition"]["param"] == {
        "all_of": ["shop.page", "shop.daily_free_gift_claimed"],
        "box_index": 1,
    }
    assert direct_verify["next"] == ["MJA_SHOP_SUCCESS"]
    assert nodes["MJA_SHOP_POST_CLAIM_PAGE_PROBE"]["next"] == [
        "MJA_SHOP_DIRECT_CLAIM_VERIFY",
        "MJA_SHOP_POST_CLAIM_OPEN_PERIOD",
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
            assert_reachable(nodes, outcome, "MJA_COMMON_ABORT")

    assert_outcome(
        nodes,
        "MJA_SHOP_RECORD_ALREADY_COMPLETE",
        "already_complete",
        "shop.daily_free_gift_claimed",
    )
    assert_outcome(
        nodes,
        "MJA_SHOP_RECORD_SUCCESS",
        "success",
        "shop.daily_free_gift_claimed",
    )
    assert nodes["MJA_SHOP_ALREADY_COMPLETE"]["action"] == "DoNothing"
    assert nodes["MJA_SHOP_ALREADY_COMPLETE"]["next"] == [
        "MJA_SHOP_CLOSE_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_SHOP_SUCCESS"]["action"] == "DoNothing"
    assert nodes["MJA_SHOP_SUCCESS"]["next"] == ["MJA_SHOP_CLOSE"]
    assert nodes["MJA_SHOP_CLOSE"]["next"] == ["MJA_SHOP_PANEL_AFTER_CLOSE"]
    assert nodes["MJA_SHOP_PANEL_AFTER_CLOSE"]["next"] == ["MJA_SHOP_CLOSE_PANEL"]
    assert nodes["MJA_SHOP_CLOSE_PANEL"]["next"] == ["MJA_SHOP_HOME_RETURN_PROBE"]
    assert nodes["MJA_SHOP_HOME_RETURN_PROBE"]["next"] == [
        "MJA_SHOP_RECORD_SUCCESS"
    ]
    assert nodes["MJA_SHOP_CLOSE_ALREADY_COMPLETE"]["next"] == [
        "MJA_SHOP_PANEL_AFTER_CLOSE_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_SHOP_PANEL_AFTER_CLOSE_ALREADY_COMPLETE"]["next"] == [
        "MJA_SHOP_CLOSE_PANEL_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_SHOP_CLOSE_PANEL_ALREADY_COMPLETE"]["next"] == [
        "MJA_SHOP_HOME_RETURN_PROBE_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_SHOP_HOME_RETURN_PROBE_ALREADY_COMPLETE"]["next"] == [
        "MJA_SHOP_RECORD_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_SHOP_CLOSE"]["on_error"] == ["MJA_SHOP_RECORD_FAILURE"]
    assert nodes["MJA_SHOP_PANEL_AFTER_CLOSE"]["on_error"] == [
        "MJA_SHOP_RECORD_FAILURE"
    ]
    assert nodes["MJA_SHOP_CLOSE_PANEL"]["on_error"] == ["MJA_SHOP_RECORD_FAILURE"]
    assert nodes["MJA_SHOP_HOME_RETURN_PROBE"]["on_error"] == [
        "MJA_SHOP_RECORD_FAILURE"
    ]


def test_shop_terminal_outcome_is_written_only_after_panel_and_home_cleanup() -> None:
    nodes = load_task_nodes(SHOP)

    for branch, cleanup, outcome in (
        (
            "MJA_SHOP_SUCCESS",
            [
                "MJA_SHOP_CLOSE",
                "MJA_SHOP_PANEL_AFTER_CLOSE",
                "MJA_SHOP_CLOSE_PANEL",
                "MJA_SHOP_HOME_RETURN_PROBE",
            ],
            "MJA_SHOP_RECORD_SUCCESS",
        ),
        (
            "MJA_SHOP_ALREADY_COMPLETE",
            [
                "MJA_SHOP_CLOSE_ALREADY_COMPLETE",
                "MJA_SHOP_PANEL_AFTER_CLOSE_ALREADY_COMPLETE",
                "MJA_SHOP_CLOSE_PANEL_ALREADY_COMPLETE",
                "MJA_SHOP_HOME_RETURN_PROBE_ALREADY_COMPLETE",
            ],
            "MJA_SHOP_RECORD_ALREADY_COMPLETE",
        ),
    ):
        assert nodes[branch].get("custom_action") is None
        assert _reachable_names(nodes, branch) >= {*cleanup, outcome}
        assert not any(
            nodes[name].get("custom_action") == "RecordTaskOutcome"
            for name in cleanup
        )
        assert nodes[outcome]["custom_action"] == "RecordTaskOutcome"
