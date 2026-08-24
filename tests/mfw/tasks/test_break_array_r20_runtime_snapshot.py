from __future__ import annotations

import json
import re
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract

ROOT = Path(__file__).resolve().parents[3]
TASK = TaskContract("BREAK_ARRAY_MARTIAL_DAILY", "daily/break_array_martial_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / TASK.pipeline_file
FIXTURE_ROOT = ROOT / "tests/fixtures/BREAK_ARRAY_MARTIAL_DAILY"


def _load_pipeline() -> dict[str, dict]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_r20_prepare_snapshot_uses_native_page_and_target_boundaries() -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "r20_prepare_page.json").read_text(encoding="utf-8")
    )
    nodes = _load_pipeline()

    assert nodes["0165-破阵武学-突破-阵法-准备-页面"]["recognition"]["param"][
        "all_of"
    ] == [
        "0160-破阵武学-突破-阵法-准备-阵容",
        "0161-破阵武学-突破-阵法-准备-首领",
        "0162-破阵武学-突破-阵法-准备-时长",
        "0163-破阵武学-突破-阵法-准备-战术",
    ]
    assert fixture["recognitions"]["0164-破阵武学-突破-阵法-准备-开始"]["hit"] is True
    assert nodes["0167-破阵武学-突破-阵法-战斗"]["expected"] == [
        "^跳过$",
        "^自动战斗$",
        "^战斗中$",
        "^自动中(?:…|\\.\\.\\.)?$",
    ]
    assert re.fullmatch(
        nodes["0167-破阵武学-突破-阵法-战斗"]["expected"][-1], "自动中…"
    )


def test_r21_transition_diagnostic_has_no_prepare_or_battle_proof() -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "r21_confirm_transition.json").read_text(encoding="utf-8")
    )
    assert fixture["observations"]["prepare_page"] is False
    assert fixture["observations"]["battle"] is False
    assert fixture["observations"]["prepare_start"] is False
    assert fixture["action_trace"][-1] == "confirm_break_array_challenge"


def test_r22_victory_snapshot_requires_tight_same_frame_anchors() -> None:
    fixture = json.loads((FIXTURE_ROOT / "r22_victory.json").read_text(encoding="utf-8"))
    nodes = _load_pipeline()
    for name in (
        "0171-破阵武学-突破-阵法-结果-胜利-标题",
        "0172-破阵武学-突破-阵法-结果-标识",
    ):
        observed = fixture["recognitions"][name]
        assert re.fullmatch(nodes[name]["expected"], observed["text"])
    assert fixture["recognitions"]["0173-破阵武学-突破-阵法-失败"]["hit"] is False
    assert fixture["recognitions"]["0174-破阵武学-突破-阵法-结果-关闭"]["hit"] is False


def test_r20_snapshot_contract_is_native_and_keeps_failure_caps() -> None:
    nodes = _load_pipeline()
    assert_no_custom_outcome_nodes(nodes)
    assert_on_error_contract(
        nodes,
        local_nodes=set(nodes),
        shared_targets={"1365-公共-主页边界-失败"},
    )
    for name in (
        "0131-破阵武学-战斗-失败",
        "0132-破阵武学-战斗-未知-结果",
        "0133-破阵武学-战斗-循环-耗尽",
        "0134-破阵武学-结果-循环-耗尽",
    ):
        assert_native_failure_node(nodes[name])
    assert nodes["0108-破阵武学-挑战-循环"]["max_hit"] == 9
    assert nodes["0114-破阵武学-战斗-加载-循环"]["max_hit"] == 360
    assert nodes["0115-破阵武学-战斗-循环"]["max_hit"] == 360
    assert nodes["0119-破阵武学-结果-循环"]["max_hit"] == 9
