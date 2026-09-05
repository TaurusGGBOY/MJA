from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_reachable,
    load_task_nodes,
)

JIANLIN = TaskContract(
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "daily/jianlin_resource_condensate_stamina_daily.json",
)
TASK_PREFIX = "剑林凝结体体力-"
ROOT = Path(__file__).parents[3]
START = "0014-剑林凝结体体力-任务入口"
BATTLE_RESULT = "0953-剑林凝结体体力-战斗-结果-探测"
BATTLE_WAIT = "0952-剑林凝结体体力-战斗-中-等待"
BATTLE_PAGE = "0935-剑林凝结体体力-战斗-页面-探测"


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


def test_jianlin_entry_is_home_visible_and_delegates_residual_recovery_to_startup() -> None:
    nodes = load_task_nodes(JIANLIN)
    entry = nodes[START]

    assert entry["recognition"] == {
        "type": "And",
        "param": {"all_of": ["0026-公共-游戏主页-页面"], "box_index": 0},
    }
    assert entry["next"] == ["0763-剑林凝结体体力-打开-资源-入口"]
    assert entry["on_error"] == [
        "MJA-任务入口失败-JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]

    task_nodes = {name: node for name, node in nodes.items() if name.startswith(TASK_PREFIX)}
    assert all(node.get("action") not in {"StartApp", "StopApp"} for node in task_nodes.values())
    scoped = json.loads(
        (ROOT / "assets/resource/base/pipeline" / JIANLIN.pipeline_file).read_text(encoding="utf-8")
    )
    assert "0963-剑林凝结体体力-记录-失败" not in scoped
    assert_native_failure_node(nodes["0962-剑林凝结体体力-预算-不安全"])
    assert_reachable(nodes, START, "1371-公共-原生成功-主页边界")
    assert_no_custom_outcome_nodes(scoped)
    assert_on_error_contract(
        scoped,
        shared_targets={"1365-公共-主页边界-失败", "1372-公共-原生成功-尝试返回"},
    )


def test_jianlin_battle_wait_is_read_only_bounded_and_result_first() -> None:
    nodes = load_task_nodes(JIANLIN)

    challenge = nodes["0934-剑林凝结体体力-挑战-凝结体"]
    assert challenge["timeout"] == 180_000
    assert challenge["next"] == [BATTLE_RESULT, BATTLE_WAIT, BATTLE_PAGE]

    wait = nodes[BATTLE_WAIT]
    assert wait == {
        "recognition": {
            "type": "And",
            "param": {"all_of": ["1018-剑林凝结体体力-剑林-战斗-中"]},
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
                "page_name": "1018-剑林凝结体体力-剑林-战斗-中",
                "target_name": "1018-剑林凝结体体力-剑林-战斗-中",
            },
        },
        "next": [BATTLE_RESULT],
        "retry_times": 0,
    }

    marker = nodes["1018-剑林凝结体体力-剑林-战斗-中"]
    assert marker["recognition"] == "OCR"
    assert marker["expected"] == [
        "^自动战斗中$",
        "^自动中(?:…|\\.\\.\\.)?$",
        "^战斗中$",
    ]
    assert marker["roi"] == [1030, 620, 240, 100]
    assert marker["action"] == "DoNothing"

    assert nodes[BATTLE_RESULT]["next"] == ["0954-剑林凝结体体力-关闭-凝结体-结果"]
    assert "on_error" not in nodes[BATTLE_RESULT]
    assert all(
        node["timeout"] == 180_000 and node["next"][-2:] == [BATTLE_RESULT, BATTLE_WAIT]
        for name, node in nodes.items()
        if name.startswith("剑林凝结体体力-开始-战斗-")
    )
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["wait_jianlin_battle"] == 12


def test_jianlin_enters_resource_page_directly_from_home() -> None:
    nodes = load_task_nodes(JIANLIN)
    open_menu = nodes["0763-剑林凝结体体力-打开-资源-入口"]
    assert open_menu["recognition"]["param"]["all_of"] == ["0026-公共-游戏主页-页面"]
    assert open_menu["next"] == ["0764-剑林凝结体体力-点击-资源"]
    open_resource = nodes["0764-剑林凝结体体力-点击-资源"]
    assert open_resource["recognition"]["param"]["all_of"] == ["0975-剑林凝结体体力-资源-入口"]
    assert open_resource["next"] == ["0774-剑林凝结体体力-选择-凝结体"]


def test_jianlin_selects_condensate_only_on_proven_resource_page() -> None:
    nodes = load_task_nodes(JIANLIN)
    select = nodes["0774-剑林凝结体体力-选择-凝结体"]
    assert select["recognition"]["param"]["all_of"] == [
        "0973-剑林凝结体体力-剑林-页面",
        "0976-剑林凝结体体力-剑林-凝结体-资源",
    ]
    assert select["recognition"]["param"]["box_index"] == 1
    assert select["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0973-剑林凝结体体力-剑林-页面",
        "target_name": "0976-剑林凝结体体力-剑林-凝结体-资源",
    }


def test_jianlin_page_proof_uses_live_ocr_controls_not_the_blank_template() -> None:
    nodes = load_task_nodes(JIANLIN)

    page = nodes["0973-剑林凝结体体力-剑林-页面"]
    assert page["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0974-剑林凝结体体力-剑林-页面-标题",
                "1011-剑林凝结体体力-剑林-倍率-条",
                "0996-剑林凝结体体力-剑林-次数-条",
                "0998-剑林凝结体体力-剑林-次数-上限",
                "1013-剑林凝结体体力-剑林-倍率-上限",
            ],
            "box_index": 0,
        },
    }
    assert nodes["0974-剑林凝结体体力-剑林-页面-标题"]["expected"] == [
        r"^剑林\s*/\s*养成$",
        r"^养成\s*/\s*资源$",
        r"^剑林\s*/\s*资源$",
    ]
    assert nodes["0974-剑林凝结体体力-剑林-页面-标题"]["roi"] == [40, 0, 280, 100]

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
        assert "on_error" not in node

    assert "on_error" not in nodes[BATTLE_WAIT]
    assert_native_failure_node(nodes["0962-剑林凝结体体力-预算-不安全"])


def test_jianlin_terminal_outcomes_use_bounded_best_effort_home_cleanup() -> None:
    nodes = load_task_nodes(JIANLIN)
    assert nodes["0789-剑林凝结体体力-体力耗尽"]["next"] == ["0959-剑林凝结体体力-清理-页面-关闭"]

    page_close = nodes["0959-剑林凝结体体力-清理-页面-关闭"]
    assert page_close["custom_action_param"]["action_id"] == "close_jianlin_page"
    assert page_close["custom_action_param"]["fixed_click_mode"] == ("jianlin_page_close")
    assert page_close["retry_times"] == 0
    assert page_close["next"] == [
        "0960-剑林凝结体体力-清理-日常-关闭",
        "1371-公共-原生成功-主页边界",
    ]

    daily_close = nodes["0960-剑林凝结体体力-清理-日常-关闭"]
    assert daily_close["custom_action_param"]["action_id"] == "close_daily_tasks"
    assert daily_close["retry_times"] == 0
    assert daily_close["next"] == ["1371-公共-原生成功-主页边界"]
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["close_daily_tasks"] == 1
    assert_reachable(nodes, "0789-剑林凝结体体力-体力耗尽", "1371-公共-原生成功-主页边界")


def test_jianlin_business_guarded_nodes_have_explicit_failure_routes() -> None:
    nodes = load_task_nodes(JIANLIN)

    guarded = [
        (name, node)
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == JIANLIN.task_id
    ]
    assert guarded
    for name, node in guarded:
        assert "on_error" not in node, name
        assert node.get("retry_times", 0) == 0


def test_jianlin_live_multiplier_ocr_accepts_x_variants_with_spaces() -> None:
    nodes = load_task_nodes(JIANLIN)
    expected = nodes["1012-剑林凝结体体力-剑林-倍率-已选择"]["expected"]

    assert all("^" not in pattern and "$" not in pattern for pattern in expected)
    assert any(re.search(pattern, "结算倍率 X3") for pattern in expected)
    assert any(re.search(pattern, "结算倍率 x 3") for pattern in expected)
    assert any(re.search(pattern, "结算倍率 ×3") for pattern in expected)
    assert any(re.search(pattern, "X3") for pattern in expected)
    assert any(re.search(pattern, "x 3") for pattern in expected)
    assert any(re.search(pattern, "结算倍率 Xl") for pattern in expected)
    assert not any(re.search(pattern, "结算倍率") for pattern in expected)

    for node_name in (
        "0998-剑林凝结体体力-剑林-次数-上限",
        "1013-剑林凝结体体力-剑林-倍率-上限",
    ):
        limit_expected = nodes[node_name]["expected"]
        assert re.search(limit_expected, "上限6")
        assert re.search(limit_expected, "上限3")

    assert any(re.search(pattern, "结算倍率 X 3") for pattern in expected)


def test_jianlin_stamina_dialog_uses_the_live_refill_title_only() -> None:
    nodes = load_task_nodes(JIANLIN)

    expected = nodes["0978-剑林凝结体体力-剑林-体力-购买-提示"]["expected"]
    assert expected == "补充体力"
    assert "购买体力" not in expected
    assert "^" not in expected and "$" not in expected
