from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.mfw.task_contract import load_task_declaration
from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes

ROOT = Path(__file__).parents[3]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"
DAILY_ROOT = PIPELINE_ROOT / "daily"

TASK_PIPELINES = {
    "SHADOW_RUINS_DAILY": "shadow_ruins_daily.json",
    "DUNGEON_SWEEP_DAILY": "dungeon_sweep_daily.json",
    "RING_CHALLENGE_DAILY": "ring_challenge_daily.json",
    "GUILD_ACTIVITY_CHALLENGE_DAILY": "guild_activity_challenge_daily.json",
    "BREAK_ARRAY_MARTIAL_DAILY": "break_array_martial_daily.json",
}

BOUNDED_LOOPS = {
    "MJA_SHADOW_TRANSFER_LOOP": 8,
    "影之遗迹-前台-循环": 40,
    "影之遗迹-战斗-循环": 12,
    "MJA_DUNGEON_SCROLL_LOOP": 4,
    "副本扫荡-分配-券-循环": 100,
    "擂台挑战-战斗-循环": 12,
    "擂台挑战-开始-匹配中": 12,
    "帮派活动挑战-帮派-挑战-循环": 2,
    "破阵武学-启动-循环": 12,
    "破阵武学-挑战-循环": 3,
    "破阵武学-战斗-循环": 12,
    "破阵武学-结果-循环": 3,
}

UNKNOWN_OR_FAILURE_TERMINALS = {
    "影之遗迹-战斗未知结果-结果",
    "副本扫荡-记录-失败",
    "擂台挑战-战斗未知结果-结果",
    "帮派活动挑战-帮派-未知结果",
    "破阵武学-战斗-未知-结果",
}

SUCCESS_TERMINALS = {
    "影之遗迹-记录-成功": "shadow.no_active_or_done_and_home",
    "副本扫荡-成功": "dungeon.ticket_count_zero",
    "擂台挑战-成功": "ring.challenge_done",
    "帮派活动挑战-成功": "guild.remaining_conquest_0_of_2",
    "破阵武学-成功": "break_array.remaining_zero_of_nine",
}


def _read_task_pipeline(task_id: str) -> dict[str, dict[str, Any]]:
    path = DAILY_ROOT / TASK_PIPELINES[task_id]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _reachable(nodes: dict[str, dict[str, Any]], start: str, target: str) -> bool:
    pending = [start]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited or current not in nodes:
            continue
        visited.add(current)
        for field in ("next", "on_error"):
            values = nodes[current].get(field, [])
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                pending.extend(
                    value.removeprefix("[JumpBack]")
                    for value in values
                    if isinstance(value, str)
                )
    return False


def test_batch_c_declarations_and_entries_are_native_task_local() -> None:
    for task_id, filename in TASK_PIPELINES.items():
        declaration = load_task_declaration(task_id)
        assert declaration["entry"].endswith("任务入口")
        payload = _read_task_pipeline(task_id)
        assert declaration["entry"] in payload
        prefix = declaration["entry"].removesuffix("任务入口")
        assert any(name.startswith(prefix) for name in payload)
        assert filename.endswith(".json")


def test_batch_c_does_not_delegate_business_flow_to_the_legacy_engine() -> None:
    forbidden = ("run_workflow", "MaaAndroidWorkflowDriver", "DailyWorkflowAction")
    for task_id in TASK_PIPELINES:
        serialized = json.dumps(_read_task_pipeline(task_id), ensure_ascii=False)
        assert not any(marker in serialized for marker in forbidden), task_id

    break_array = json.dumps(
        _read_task_pipeline("BREAK_ARRAY_MARTIAL_DAILY"), ensure_ascii=False
    )
    assert "BreakArrayMartialDailyAction" not in break_array

    action_source = (
        ROOT / "agent/custom/action/break_array_martial_daily.py"
    ).read_text(encoding="utf-8")
    assert not any(marker in action_source for marker in forbidden), action_source


def test_break_array_native_pipeline_has_task_local_phase_boundaries() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    start = nodes["破阵武学-任务入口"]
    assert start["custom_action"] == "BeginTask"
    assert start["next"] == [
        "破阵武学-启动-探测",
        "破阵武学-页面-探测",
        "破阵武学-活动-探测",
        "破阵武学-主页-探测",
    ]
    assert "MJA_BREAK_ARRAY_MARTIAL_DAILY_EXECUTE" not in nodes
    guarded = {
        node.get("custom_action_param", {}).get("action_id")
        for node in nodes.values()
        if node.get("custom_action") == "GuardedInput"
        and isinstance(node.get("custom_action_param"), dict)
        and node["custom_action_param"].get("task_id")
        == "BREAK_ARRAY_MARTIAL_DAILY"
    }
    assert {
        "open_break_array_activity",
        "open_break_array",
        "start_break_array_challenge",
        "confirm_break_array_challenge",
        "start_break_array_battle",
        "wait_break_array_battle",
        "wait_break_array_result",
        "dismiss_break_array_result",
    } <= guarded


def test_break_array_resource_and_battle_terminals_are_explicit() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    expected = {
        "破阵武学-已完成": "already_complete",
        "破阵武学-不符合条件": "not_eligible",
        "破阵武学-战斗-失败": "failed",
        "破阵武学-战斗-循环-耗尽": "failed",
        "破阵武学-结果-循环-耗尽": "failed",
        "破阵武学-记录-失败": "failed",
    }
    for name, status in expected.items():
        params = nodes[name]["custom_action_param"]
        assert nodes[name]["custom_action"] == "RecordTaskOutcome"
        assert params["status"] == status
        assert params["postcondition"]
        if status == "failed":
            assert params["native_fail_after_record"] is True
            assert nodes[name]["Abort"] is True
            assert nodes[name]["next"] == ["公共-通用中止"]
            assert "on_error" not in nodes[name]


def test_batch_c_pipeline_graph_has_targets_and_only_bounded_cycles() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    assert not validate_nodes(nodes)
    for name, maximum in BOUNDED_LOOPS.items():
        assert nodes[name]["max_hit"] == maximum
        assert nodes[name].get("retry_times", 0) == 0


def test_batch_c_unknown_or_failure_terminals_abort_natively() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    for name in UNKNOWN_OR_FAILURE_TERMINALS:
        node = nodes[name]
        params = node["custom_action_param"]
        assert node["custom_action"] == "RecordTaskOutcome"
        assert params["status"] == "failed"
        assert params["error_code"]
        assert params["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["公共-通用中止"]
        assert "on_error" not in node


def test_batch_c_success_terminals_record_business_postconditions() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    for name, postcondition in SUCCESS_TERMINALS.items():
        node = nodes[name]
        params = node["custom_action_param"]
        assert node["custom_action"] == "RecordTaskOutcome"
        assert params["status"] == "success"
        assert params["postcondition"] == postcondition
        assert node.get("Abort") is not True
        assert _reachable(nodes, name, "公共-通用停止")
