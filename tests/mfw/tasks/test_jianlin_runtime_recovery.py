from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_outcome,
    assert_reachable,
    load_task_nodes,
)

JIANLIN = TaskContract(
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "daily/jianlin_resource_condensate_stamina_daily.json",
)
TASK_PREFIX = "剑林凝结体体力-"
START = "剑林凝结体体力-任务入口"
RECORD_FAILURE = "剑林凝结体体力-记录-失败"
CLEANUP_ROUTE = "剑林凝结体体力-终止-清理-路线"
BATTLE_RESULT = "剑林凝结体体力-战斗-结果-探测"
BATTLE_WAIT = "剑林凝结体体力-战斗-中-等待"
BATTLE_PAGE = "剑林凝结体体力-战斗-页面-探测"


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


def _reachable_names(
    nodes: Mapping[str, Mapping[str, Any]], source: str
) -> set[str]:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(_targets(nodes.get(current, {})))
    return visited


def test_jianlin_entry_is_home_visible_and_delegates_residual_recovery_to_startup() -> None:
    nodes = load_task_nodes(JIANLIN)
    entry = nodes[START]

    assert entry["recognition"] == {
        "type": "And",
        "param": {"all_of": ["公共-游戏主页-页面"], "box_index": 0},
    }
    assert entry["next"] == [
        "剑林凝结体体力-关闭-奖励-弹窗",
        "剑林凝结体体力-主页-探测",
    ]
    assert entry["on_error"] == [
        "[JumpBack]启动-游戏启动",
        RECORD_FAILURE,
    ]

    task_nodes = {
        name: node for name, node in nodes.items() if name.startswith(TASK_PREFIX)
    }
    assert all(node.get("action") not in {"StartApp", "StopApp"} for node in task_nodes.values())
    assert_outcome(nodes, RECORD_FAILURE, "failed", "JIANLIN_POSTCONDITION_MISSING")
    assert nodes[RECORD_FAILURE]["custom_action_param"]["error_code"] == (
        "JIANLIN_POSTCONDITION_MISSING"
    )
    assert nodes[RECORD_FAILURE]["custom_action_param"]["defer_home_boundary"] is True
    assert nodes[RECORD_FAILURE]["next"] == ["公共-主页边界-尝试返回"]
    assert_reachable(nodes, START, "公共-通用停止")
    assert_reachable(nodes, START, "公共-通用中止")


def test_jianlin_battle_wait_is_read_only_bounded_and_result_first() -> None:
    nodes = load_task_nodes(JIANLIN)

    challenge = nodes["剑林凝结体体力-挑战-凝结体"]
    assert challenge["timeout"] == 180_000
    assert challenge["next"] == [BATTLE_RESULT, BATTLE_WAIT, BATTLE_PAGE]

    wait = nodes[BATTLE_WAIT]
    assert wait == {
        "recognition": {
            "type": "And",
            "param": {"all_of": ["剑林凝结体体力-剑林-战斗-中"]},
        },
        "max_hit": 12,
        "timeout": 180_000,
        "action": "Custom",
        "custom_action": "GuardedInput",
        "custom_action_param": {
            "task_id": JIANLIN.task_id,
            "action_id": "wait_jianlin_battle",
            "kind": "none",
            "evidence": {
                "page_index": 0,
                "target_index": 0,
                "page_name": "剑林凝结体体力-剑林-战斗-中",
                "target_name": "剑林凝结体体力-剑林-战斗-中",
            },
        },
        "next": [BATTLE_RESULT],
        "on_error": [RECORD_FAILURE],
        "retry_times": 0,
    }

    marker = nodes["剑林凝结体体力-剑林-战斗-中"]
    assert marker["recognition"] == "OCR"
    assert marker["expected"] == [
        "^自动战斗中$",
        "^自动中(?:…|\\.\\.\\.)?$",
        "^战斗中$",
    ]
    assert marker["roi"] == [1030, 620, 240, 100]
    assert marker["action"] == "DoNothing"

    assert nodes[BATTLE_RESULT]["next"] == ["剑林凝结体体力-关闭-凝结体-结果"]
    assert nodes[BATTLE_RESULT]["on_error"] == [RECORD_FAILURE]
    assert all(
        node["timeout"] == 180_000 and node["next"][-2:] == [BATTLE_RESULT, BATTLE_WAIT]
        for name, node in nodes.items()
        if name.startswith("剑林凝结体体力-开始-战斗-")
    )
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["wait_jianlin_battle"] == 12


def test_jianlin_daily_page_uses_sibling_candidates_for_done_and_pending_rows() -> None:
    nodes = load_task_nodes(JIANLIN)

    page_probe = nodes["剑林凝结体体力-日常-页面-探测"]
    assert page_probe["next"] == [
        "剑林凝结体体力-日常-行-探测",
        "剑林凝结体体力-滚动-日常-剑林",
    ]
    assert page_probe["on_error"] == [RECORD_FAILURE]

    row_probe = nodes["剑林凝结体体力-日常-行-探测"]
    assert row_probe["next"] == ["剑林凝结体体力-打开-剑林"]
    assert row_probe["on_error"] == ["剑林凝结体体力-滚动-日常-剑林"]

    scroll = nodes["剑林凝结体体力-滚动-日常-剑林"]
    assert scroll["next"] == ["剑林凝结体体力-日常-页面-之后-滚动"]
    assert scroll["on_error"] == [RECORD_FAILURE]
    assert scroll["max_hit"] == 3

    after_scroll = nodes["剑林凝结体体力-日常-页面-之后-滚动"]
    assert after_scroll["next"] == [
        "剑林凝结体体力-日常-行-探测",
        "剑林凝结体体力-滚动-日常-剑林",
    ]
    assert after_scroll["on_error"] == [RECORD_FAILURE]


def test_jianlin_entry_targets_the_live_go_button_after_row_probe() -> None:
    nodes = load_task_nodes(JIANLIN)

    row = nodes["剑林凝结体体力-剑林-日常-行"]
    assert row["recognition"] == "OCR"
    assert row["expected"] == r"^战胜一次剑林的首领[。.]?$"
    assert row["roi"] == [100, 60, 700, 620]
    assert re.fullmatch(row["expected"], "战胜一次剑林的首领。")
    assert not re.fullmatch(row["expected"], "各位大侠可前往剑林·对弈中参与")
    assert not re.fullmatch(row["expected"], "消耗10000凝晶。")

    entry = nodes["剑林凝结体体力-剑林-入口"]
    assert entry["recognition"] == "OCR"
    assert entry["expected"] == r"^前往$"
    assert entry["roi"] == [980, 500, 240, 130]
    assert entry["roi"] != [0, 0, 1280, 720]

    open_node = nodes["剑林凝结体体力-打开-剑林"]
    assert open_node["recognition"]["param"]["all_of"] == [
        "剑林凝结体体力-剑林-日常-页面",
        "剑林凝结体体力-剑林-入口",
    ]
    assert open_node["recognition"]["param"]["box_index"] == 1
    assert open_node["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "剑林凝结体体力-剑林-日常-页面",
        "target_name": "剑林凝结体体力-剑林-入口",
    }


def test_jianlin_page_proof_uses_live_ocr_controls_not_the_blank_template() -> None:
    nodes = load_task_nodes(JIANLIN)

    page = nodes["剑林凝结体体力-剑林-页面"]
    assert page["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "剑林凝结体体力-剑林-页面-标题",
                "剑林凝结体体力-剑林-倍率-条",
                "剑林凝结体体力-剑林-次数-条",
            ],
            "box_index": 0,
        },
    }
    assert nodes["剑林凝结体体力-剑林-页面-标题"]["expected"] == [
        r"^剑林\s*/\s*养成$",
        r"^养成\s*/\s*资源$",
        r"^剑林\s*/\s*资源$",
    ]
    assert nodes["剑林凝结体体力-剑林-页面-标题"]["roi"] == [40, 0, 280, 100]

    probe = nodes["剑林凝结体体力-页面-探测"]
    assert probe["recognition"]["param"]["all_of"] == [
        "剑林凝结体体力-剑林-页面"
    ]
    assert probe["recognition"]["param"]["box_index"] == 0
    assert "template" not in probe

    serialized = json.dumps(nodes, ensure_ascii=False)
    assert "jianlin_page.png" not in serialized


def test_jianlin_recovery_cannot_replay_purchase_or_resource_actions() -> None:
    nodes = load_task_nodes(JIANLIN)
    protected_actions = {
        "buy_stamina_once",
        "confirm_jianlin_stamina_purchase",
        "challenge_condensate",
        "start_jianlin_battle",
    }

    for action_id in protected_actions:
        assert_no_side_effect_retry(nodes, action_id)

    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if not isinstance(params, Mapping) or params.get("task_id") != JIANLIN.task_id:
            continue
        if params.get("action_id") not in protected_actions:
            continue
        assert node.get("retry_times", 0) == 0
        assert node["on_error"] == [RECORD_FAILURE]

    assert nodes[BATTLE_WAIT]["on_error"] == [RECORD_FAILURE]
    assert nodes["剑林凝结体体力-预算-不安全"]["next"] == [
        "公共-主页边界-尝试返回"
    ]


def test_jianlin_terminal_outcomes_use_bounded_best_effort_home_cleanup() -> None:
    nodes = load_task_nodes(JIANLIN)

    for terminal in (
        "剑林凝结体体力-体力-以下-20-成功",
        "剑林凝结体体力-成功-之后-战斗",
    ):
        assert nodes[terminal]["next"] == [CLEANUP_ROUTE]
        assert nodes[terminal]["on_error"] == [RECORD_FAILURE]
        assert_reachable(nodes, terminal, "公共-通用停止")

    cleanup_route = nodes[CLEANUP_ROUTE]
    assert cleanup_route["timeout"] == 10_000
    assert cleanup_route["next"] == [
        "剑林凝结体体力-清理-页面-关闭",
        "剑林凝结体体力-清理-日常-关闭",
        "剑林凝结体体力-清理-主页-探测",
    ]
    assert cleanup_route["on_error"] == ["公共-主页边界-尝试返回"]

    page_close = nodes["剑林凝结体体力-清理-页面-关闭"]
    assert page_close["custom_action_param"]["action_id"] == "close_jianlin_page"
    assert page_close["custom_action_param"]["fixed_click_mode"] == (
        "jianlin_page_close"
    )
    assert page_close["retry_times"] == 0
    assert page_close["next"] == [
        "剑林凝结体体力-清理-日常-关闭",
        "剑林凝结体体力-清理-主页-探测",
    ]

    daily_close = nodes["剑林凝结体体力-清理-日常-关闭"]
    assert daily_close["custom_action_param"]["action_id"] == "close_daily_tasks"
    assert daily_close["retry_times"] == 0
    assert daily_close["next"] == ["剑林凝结体体力-清理-主页-探测"]
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["close_daily_tasks"] == 1

    home_probe = nodes["剑林凝结体体力-清理-主页-探测"]
    assert home_probe["next"] == ["公共-主页边界"]
    assert home_probe["on_error"] == ["公共-主页边界-尝试返回"]


def test_jianlin_business_guarded_nodes_have_explicit_failure_routes() -> None:
    nodes = load_task_nodes(JIANLIN)
    cleanup_actions = {"close_jianlin_page", "close_daily_tasks"}

    guarded = [
        (name, node)
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == JIANLIN.task_id
    ]
    assert guarded
    for name, node in guarded:
        action_id = node["custom_action_param"]["action_id"]
        if action_id in cleanup_actions:
            assert node["on_error"] == ["公共-主页边界-尝试返回"]
        else:
            assert node["on_error"] == [RECORD_FAILURE], name
        assert node.get("retry_times", 0) == 0


def test_jianlin_live_multiplier_ocr_accepts_x_variants_with_spaces() -> None:
    nodes = load_task_nodes(JIANLIN)
    expected = nodes["剑林凝结体体力-剑林-倍率-已选择"]["expected"]

    assert all("^" not in pattern and "$" not in pattern for pattern in expected)
    assert any(re.search(pattern, "结算倍率 X3") for pattern in expected)
    assert any(re.search(pattern, "结算倍率 x 3") for pattern in expected)
    assert any(re.search(pattern, "结算倍率 ×3") for pattern in expected)
    assert any(re.search(pattern, "X3") for pattern in expected)
    assert any(re.search(pattern, "x 3") for pattern in expected)
    assert not any(re.search(pattern, "结算倍率") for pattern in expected)

    for value in (1, 2, 3):
        option = nodes[f"剑林凝结体体力-剑林-倍率-{value}"]["expected"]
        assert any(re.search(pattern, f"结算倍率 X {value}") for pattern in option)


def test_jianlin_stamina_dialog_uses_the_live_refill_title_only() -> None:
    nodes = load_task_nodes(JIANLIN)

    for node_name in (
        "剑林凝结体体力-体力-购买-探测",
        "剑林凝结体体力-剑林-体力-购买-提示",
    ):
        expected = nodes[node_name]["expected"]
        assert expected == "补充体力"
        assert "购买体力" not in expected
        assert "^" not in expected and "$" not in expected
