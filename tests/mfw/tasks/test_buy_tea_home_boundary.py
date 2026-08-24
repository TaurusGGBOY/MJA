from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_resource_guard,
    load_task_nodes,
)

TEA = TaskContract("BUY_TEA_DAILY", "daily/buy_tea_daily.json")
NORMAL_OUTCOMES = ("0195-买茶-售罄", "0203-买茶-结果-成功", "0204-买茶-已完成")
EXPLICIT_FAILURES = ("0184-买茶-游戏启动恢复失败", "0200-买茶-价格-不安全")
RECORDER = "0209-买茶-记录-失败"
PIPELINE_PATH = Path(__file__).parents[3] / "assets/resource/base/pipeline" / TEA.pipeline_file


def _scoped_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def _targets(node: Mapping[str, object]) -> list[str]:
    targets: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list):
            continue
        targets.extend(target for target in values if isinstance(target, str))
    return targets


def _reachable(nodes: Mapping[str, Mapping[str, object]], source: str, target: str) -> bool:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target:
            return True
        pending.extend(_targets(nodes.get(current, {})))
    return False


def test_normal_buy_tea_outcomes_cleanup_to_home_boundary() -> None:
    nodes = _scoped_nodes()

    for outcome_name in NORMAL_OUTCOMES:
        outcome = nodes[outcome_name]
        assert outcome["action"] == "DoNothing"
        assert "custom_action" not in outcome
        assert "custom_action_param" not in outcome
        assert outcome["next"] == ["0205-买茶-完成-收尾"]
        assert "on_error" not in outcome
        assert _reachable(nodes, outcome_name, "1371-公共-原生成功-主页边界")
        assert _reachable(nodes, outcome_name, "1369-公共-通用停止")

    cleanup = nodes["0205-买茶-完成-收尾"]
    assert cleanup["max_hit"] == 4
    assert cleanup["next"] == [
        "[JumpBack]0206-公共-已知-茶-详情-关闭",
        "[JumpBack]0207-公共-已知-茶-商店-关闭",
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "0208-买茶-完成-主页-探测",
    ]
    assert cleanup["on_error"] == ["0229-MJA-买茶-玉盟商会-关闭"]
    fallback = nodes["0229-MJA-买茶-玉盟商会-关闭"]
    assert fallback["custom_action"] == "GuardedInput"
    assert fallback["custom_action_param"] == {
        "task_id": TEA.task_id,
        "action_id": "close_shop",
        "kind": "click",
        "fixed_click_mode": "function_panel_close",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0216-买茶-茶-万用-商店-页面",
            "target_name": "0037-公共-已知-画卷-关闭-图标",
        },
    }
    assert fallback["next"] == [
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "0208-买茶-完成-主页-探测",
    ]
    assert nodes["0208-买茶-完成-主页-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert nodes["0208-买茶-完成-主页-探测"]["on_error"] == [
        "1372-公共-原生成功-尝试返回"
    ]


def test_buy_tea_has_only_native_failure_endpoints_and_local_recovery() -> None:
    nodes = _scoped_nodes()
    assert_no_custom_outcome_nodes(nodes)
    for failure_name in EXPLICIT_FAILURES:
        assert_native_failure_node(nodes[failure_name])
    assert RECORDER not in nodes
    assert_on_error_contract(
        nodes,
        shared_targets={"1369-公共-通用停止", "1372-公共-原生成功-尝试返回"},
    )
    assert all(
        RECORDER not in target
        for node in nodes.values()
        for field in ("next", "on_error")
        for target in (
            node.get(field, [])
            if isinstance(node.get(field, []), list)
            else [node.get(field)]
        )
        if isinstance(target, str)
    )


def test_buy_tea_preserves_non_repeating_resource_safe_inputs() -> None:
    nodes = _scoped_nodes()
    policy = TASK_POLICIES[TEA.task_id]

    assert nodes["0179-买茶-游戏启动恢复"]["retry_times"] == 0
    assert_resource_guard(nodes, "buy_tea", "文", 500, task_id=TEA.task_id)
    for action_id in policy.action_caps:
        assert_no_side_effect_retry(nodes, action_id)
    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if params.get("task_id") != TEA.task_id or not params.get("action_id"):
            continue
        assert node.get("retry_times", 0) == 0
        assert 1 <= node["max_hit"] <= policy.action_caps[params["action_id"]]


def test_buy_tea_painting_entry_uses_current_world_label_and_action_anchor() -> None:
    nodes = load_task_nodes(TEA)
    entry = nodes["0185-买茶-打开-画卷"]
    target = nodes["0211-买茶-茶-画卷-滚动-入口"]

    assert target["recognition"] == "OCR"
    assert target["expected"] == "^画卷$"
    assert target["roi"] == [1090, 25, 80, 70]
    assert entry["custom_action_param"]["fixed_click_mode"] == (
        "painting_scroll_button"
    )
