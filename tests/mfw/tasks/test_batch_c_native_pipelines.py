from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
)
from tests.mfw.task_contract import load_task_declaration
from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes

ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"
TASKS = {
    "SHADOW_RUINS_DAILY": "shadow_ruins_daily.json",
    "DUNGEON_SWEEP_DAILY": "dungeon_sweep_daily.json",
    "RING_CHALLENGE_DAILY": "ring_challenge_daily.json",
    "GUILD_ACTIVITY_CHALLENGE_DAILY": "guild_activity_challenge_daily.json",

}


def _load(name: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / "daily" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_batch_c_declarations_and_entries_are_task_local() -> None:
    for task_id, filename in TASKS.items():
        declaration = load_task_declaration(task_id)
        nodes = _load(filename)
        assert declaration["entry"] in nodes
        assert nodes[declaration["entry"]]["custom_action"] == "BeginTask"


def test_batch_c_unknown_and_failure_nodes_are_native_failures() -> None:
    for filename in TASKS.values():
        nodes = _load(filename)
        assert_no_custom_outcome_nodes(nodes)
        for node in nodes.values():
            if node.get("custom_action") == "FailTask":
                assert_native_failure_node(node)


def test_batch_c_graph_has_no_legacy_outcomes_and_only_bounded_cycles() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    assert not validate_nodes(nodes)
    assert_all_cycles_bounded(nodes)
