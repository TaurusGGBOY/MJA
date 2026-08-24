from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
)
from tests.mfw.task_contract import load_task_declaration
from tools.check_mfw_resources import load_pipeline_nodes

ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"
TASKS = {
    "BUY_TEA_DAILY": "buy_tea_daily.json",
    "SPEND_CONDENSATE_DAILY": "spend_condensate_daily.json",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY": "martial_study_breakthrough_daily.json",
    "EAT_STAMINA_FOOD_DAILY": "eat_stamina_food_daily.json",
    "EQUIPMENT_DECOMPOSE_DAILY": "equipment_decompose_daily.json",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": "jianlin_resource_condensate_stamina_daily.json",
}


def _local(name: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / "daily" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_batch_b_entries_are_native_and_safety_policies_remain_present() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    for task_id, filename in TASKS.items():
        declaration = load_task_declaration(task_id)
        local = _local(filename)
        assert declaration["entry"] in local
        assert local[declaration["entry"]]["custom_action"] == "BeginTask"
        assert any(node.get("action") == "StopTask" for node in local.values()) or (
            "1369-公共-通用停止" in nodes
        )
        assert task_id in TASK_POLICIES
        assert TASK_POLICIES[task_id].action_caps


def test_batch_b_guarded_inputs_keep_task_identity_and_no_legacy_outcomes() -> None:
    for filename in TASKS.values():
        local = _local(filename)
        assert_no_custom_outcome_nodes(local)
        for name, node in local.items():
            if node.get("custom_action") != "GuardedInput":
                continue
            params = node.get("custom_action_param", {})
            assert isinstance(params.get("task_id"), str), name
            assert params.get("action_id"), name
            assert node.get("retry_times", 0) >= 0
        for node in local.values():
            if node.get("custom_action") == "FailTask":
                assert_native_failure_node(node)


def test_batch_b_graph_has_only_bounded_cycles() -> None:
    assert_all_cycles_bounded(load_pipeline_nodes(PIPELINE_ROOT))
