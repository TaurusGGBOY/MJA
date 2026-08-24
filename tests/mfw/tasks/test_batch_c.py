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
    "SHADOW_RUINS_DAILY": "shadow_ruins_daily.json",
    "DUNGEON_SWEEP_DAILY": "dungeon_sweep_daily.json",
    "RING_CHALLENGE_DAILY": "ring_challenge_daily.json",
    "GUILD_ACTIVITY_CHALLENGE_DAILY": "guild_activity_challenge_daily.json",

}


def _local(name: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / "daily" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_batch_c_entries_are_task_local_and_native() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    for task_id, filename in TASKS.items():
        declaration = load_task_declaration(task_id)
        local = _local(filename)
        assert declaration["entry"] in local
        assert local[declaration["entry"]].get("custom_action") == "BeginTask"
        assert any(node.get("action") == "StopTask" for node in local.values()) or (
            "1369-公共-通用停止" in nodes
        )


def test_dungeon_entry_begins_task_before_opening_dungeon() -> None:
    local = _local("dungeon_sweep_daily.json")
    entry = local["0006-副本扫荡-任务入口"]
    open_dungeon = local["0316-副本扫荡-打开-副本"]

    assert entry["custom_action"] == "BeginTask"
    assert entry["custom_action_param"] == {"task_id": "DUNGEON_SWEEP_DAILY"}
    assert entry["recognition"]["param"] == {
        "all_of": ["0026-公共-游戏主页-页面"],
        "box_index": 0,
    }
    assert entry["next"] == ["0316-副本扫荡-打开-副本"]
    assert open_dungeon["custom_action"] == "GuardedInput"
    assert open_dungeon["custom_action_param"]["action_id"] == "open_dungeon"
    assert open_dungeon["post_delay"] == 1500
    assert open_dungeon["next"] == [
        "0317-副本扫荡-选择-燕王",
        "0315-副本扫荡-滚动-寻找-燕王",
    ]


def test_batch_c_has_no_recorders_and_all_explicit_failures_are_terminal() -> None:
    for filename in TASKS.values():
        local = _local(filename)
        assert_no_custom_outcome_nodes(local)
        for node in local.values():
            if node.get("custom_action") == "FailTask":
                assert_native_failure_node(node)


def test_batch_c_keeps_bounded_battle_and_resource_loops() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    assert_all_cycles_bounded(nodes)
    for name in (
        "0326-副本扫荡-分配-券-循环",
        "1107-擂台挑战-战斗-循环",
    ):
        assert name in nodes
        assert any(
            isinstance(nodes[name].get(field), int) and nodes[name][field] > 0
            for field in ("max_hit", "max_times", "retry_times", "limit")
        )
