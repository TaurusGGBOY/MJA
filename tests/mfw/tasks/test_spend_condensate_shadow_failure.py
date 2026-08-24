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
    assert_reachable,
    load_task_nodes,
)


CONDENSATE = TaskContract(
    "SPEND_CONDENSATE_DAILY",
    "daily/spend_condensate_daily.json",
)
PIPELINE_PATH = (
    Path(__file__).parents[3]
    / "assets/resource/base/pipeline"
    / CONDENSATE.pipeline_file
)
FAILURE = "1279-消耗凝结体-预算-不安全"


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


def test_silver_entry_is_scoped_to_the_upper_right_currency_region() -> None:
    nodes = load_task_nodes(CONDENSATE)

    for name in (
        "1294-消耗凝结体-凝结体-偃武-货币-入口",
        "1304-消耗凝结体-凝结体-云州-货币-入口",
    ):
        target = nodes[name]
        assert target["recognition"] == "OCR"
        assert target["expected"] == r"^\d+两\d+文$"
        assert target["roi"] == [990, 0, 210, 90]


def test_first_region_purchase_failure_continues_to_the_second_region() -> None:
    nodes = _scoped_nodes()

    assert nodes["1256-消耗凝结体-打开-偃武"]["on_error"] == [
        "1264-消耗凝结体-选择-云州-之后-购买"
    ]
    assert nodes["1260-消耗凝结体-设置-偃武-最大"]["on_error"] == [
        "1315-消耗凝结体-关闭-偃武购买页面"
    ]
    assert nodes["1261-消耗凝结体-购买-偃武"]["on_error"] == [
        "1315-消耗凝结体-关闭-偃武购买页面"
    ]
    assert nodes["1315-消耗凝结体-关闭-偃武购买页面"]["next"] == [
        "1264-消耗凝结体-选择-云州-之后-购买"
    ]


def test_final_region_purchase_failure_is_the_only_condensate_business_failure() -> None:
    nodes = _scoped_nodes()
    assert_native_failure_node(nodes[FAILURE])

    assert nodes["1266-消耗凝结体-打开-云州-恢复"]["on_error"] == [FAILURE]
    assert nodes["1270-消耗凝结体-设置-云州-最大-恢复"]["on_error"] == [FAILURE]
    assert nodes["1271-消耗凝结体-购买-云州-恢复"]["on_error"] == [FAILURE]
    assert_reachable(nodes, "1271-消耗凝结体-购买-云州-恢复", FAILURE)


def test_condensate_has_no_legacy_outcome_recorder_and_native_success_cleanup() -> None:
    nodes = _scoped_nodes()
    assert_no_custom_outcome_nodes(nodes)
    assert_on_error_contract(
        nodes,
        shared_targets={
            "1369-公共-通用停止",
            "1372-公共-原生成功-尝试返回",
        },
    )
    assert nodes["1276-消耗凝结体-完成-收尾"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]


def test_consumptive_inputs_keep_policy_caps_and_no_replay() -> None:
    nodes = load_task_nodes(CONDENSATE)
    policy = TASK_POLICIES[CONDENSATE.task_id]

    guarded = [
        (name, node)
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == CONDENSATE.task_id
    ]
    assert guarded

    for name, node in guarded:
        params = node["custom_action_param"]
        action_id = params["action_id"]
        assert action_id in policy.action_caps, name
        assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
        assert node.get("retry_times", 0) == 0
        assert_no_side_effect_retry(nodes, action_id)

    assert all(
        FAILURE not in target
        for node in nodes.values()
        for target in _targets(node)
        if target != FAILURE
    )
