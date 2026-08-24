from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_action_limit,
    assert_no_side_effect_retry,
    load_task_nodes,
)


DUNGEON = TaskContract("DUNGEON_SWEEP_DAILY", "daily/dungeon_sweep_daily.json")
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / DUNGEON.pipeline_file


def _scoped_nodes() -> dict[str, dict[str, Any]]:
    payload = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_dungeon_scroll_exhaustion_remains_a_native_failure_without_recorder_payload() -> None:
    nodes = _scoped_nodes()
    assert nodes["0314-副本扫荡-滚动-耗尽"] == {
        "recognition": "DirectHit",
        "action": "Custom",
        "custom_action": "FailTask",
        "Abort": True,
    }


def test_dungeon_ticket_exhaustion_returns_home_before_native_success() -> None:
    nodes = _scoped_nodes()
    close = nodes["0319-副本扫荡-扫荡不可用-关闭"]
    home = nodes["0321-副本扫荡-扫荡不可用-主页确认"]

    assert nodes["0317-副本扫荡-选择-燕王"]["next"] == [
        "0318-副本扫荡-打开-扫荡",
        "0319-副本扫荡-扫荡不可用-关闭",
    ]
    assert nodes["0318-副本扫荡-打开-扫荡"]["on_error"] == [
        "0319-副本扫荡-扫荡不可用-关闭"
    ]
    assert close["recognition"]["param"] == {
        "all_of": [
            "0347-副本扫荡-副本-燕王-秘陵-标题",
            "0352-副本扫荡-副本-券-耗尽",
            "0349-副本扫荡-副本-扫荡-目标",
            "0374-副本扫荡-副本-关闭",
        ],
        "box_index": 3,
    }
    assert close["action"] == "Click"
    assert close["target"] == [1202, 30, 24, 24]
    assert close["max_hit"] == 1
    assert close["next"] == ["0321-副本扫荡-扫荡不可用-主页确认"]
    assert home["recognition"]["param"] == {
        "all_of": ["0026-公共-游戏主页-页面"],
        "box_index": 0,
    }
    assert home["next"] == ["1371-公共-原生成功-主页边界"]
    assert "on_error" not in home
    assert "0320-副本扫荡-扫荡-不可用" not in nodes


def test_dungeon_sweep_success_is_only_reachable_after_result_evidence() -> None:
    nodes = _scoped_nodes()
    assert nodes["0332-副本扫荡-关闭-结果"]["next"] == [
        "0337-副本扫荡-成功-关闭"
    ]
    predecessors = {
        name
        for name, node in nodes.items()
        if "0337-副本扫荡-成功-关闭" in node.get("next", [])
    }
    assert predecessors == {"0332-副本扫荡-关闭-结果"}
    assert nodes["0337-副本扫荡-成功-关闭"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert "0338-副本扫荡-关闭后返回主页" not in nodes


def test_dungeon_removes_recorder_routes_but_keeps_bounded_local_recovery() -> None:
    nodes = _scoped_nodes()
    assert_no_custom_outcome_nodes(nodes)
    assert "0339-副本扫荡-记录-失败" not in nodes
    assert "1366-公共-通用中止" not in json.dumps(nodes, ensure_ascii=False)
    assert_on_error_contract(
        nodes,
        local_nodes=set(nodes),
        shared_targets={
            "MJA-任务入口失败-DUNGEON_SWEEP_DAILY",
            "MJA-公共-任务入口-恢复耗尽",
        },
    )
    assert_all_cycles_bounded(nodes)


def test_dungeon_preserves_sweep_resource_and_retry_bounds() -> None:
    nodes = load_task_nodes(DUNGEON)
    assert_action_limit(DUNGEON.task_id, "assign_sweep_ticket", 20)
    assert_action_limit(DUNGEON.task_id, "start_yanwangling_master_sweep", 20)
    action_ids = {
        node.get("custom_action_param", {}).get("action_id")
        for node in _scoped_nodes().values()
        if node.get("custom_action") == "GuardedInput"
    }
    for action_id in action_ids:
        assert isinstance(action_id, str)
        assert_no_side_effect_retry(nodes, action_id)
    assert nodes["0315-副本扫荡-滚动-寻找-燕王"]["max_hit"] == 4
    assert nodes["0326-副本扫荡-分配-券-循环"]["max_hit"] == 20
