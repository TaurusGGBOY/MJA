from __future__ import annotations

import json
from pathlib import Path

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


def _load(name: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / "daily" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_batch_b_declarations_and_safety_inputs_are_native() -> None:
    for task_id, filename in TASKS.items():
        declaration = load_task_declaration(task_id)
        nodes = _load(filename)
        assert declaration["entry"] in nodes
        for name, node in nodes.items():
            if node.get("custom_action") == "GuardedInput":
                params = node.get("custom_action_param", {})
                assert params.get("task_id") == task_id, name
                assert params.get("action_id"), name
                assert node.get("retry_times", 0) == 0, name
            if node.get("custom_action") == "FailTask":
                assert_native_failure_node(node)


def test_batch_b_has_no_result_recorders_or_status_fields() -> None:
    for filename in TASKS.values():
        nodes = _load(filename)
        assert_no_custom_outcome_nodes(nodes)
        assert '"status"' not in json.dumps(nodes, ensure_ascii=False)


def test_batch_b_graph_preserves_bounded_cycles() -> None:
    assert_all_cycles_bounded(load_pipeline_nodes(PIPELINE_ROOT))
