from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.check_mfw_resources import (
    TaskEntryDiagnostic,
    check_resource_tree,
    check_task_entry_contracts,
)

PIPELINE_ROOT = Path("assets/resource/base/pipeline")


def _begin(next_target: str, error_target: str = "公共-通用中止") -> dict[str, Any]:
    return {
        "action": "Custom",
        "custom_action": "BeginTask",
        "next": [next_target],
        "on_error": [error_target],
    }


def _terminals() -> dict[str, dict[str, Any]]:
    return {
        "公共-通用停止": {"action": "StopTask"},
        "公共-通用中止": {"action": "StopTask", "Abort": True},
    }


def _shared_startup() -> dict[str, dict[str, Any]]:
    return {
        "启动-游戏启动": {
            "recognition": "TemplateMatch",
            "template": "home/home_marker.png",
            "roi": [1040, 0, 240, 110],
            "threshold": 0.425,
            "timeout": 5000,
            "action": "DoNothing",
            "next": ["启动-游戏就绪"],
            "on_error": ["启动-标题-或-加载"],
        },
        "启动-游戏就绪": {
            "recognition": "TemplateMatch",
            "template": "home/home_marker.png",
            "roi": [1040, 0, 240, 110],
            "threshold": 0.425,
            "timeout": 15000,
            "action": "Custom",
            "custom_action": "RuntimeHealth",
            "next": ["公共-通用停止"],
            "on_error": ["MJA_START_KNOWN_POPUP"],
        },
        "启动-标题-或-加载": {
            "recognition": "OCR",
            "expected": ["点击开始游戏", "进入游戏", "加载中", "穿梭入世"],
            "roi": [350, 500, 580, 220],
            "timeout": 10000,
            "action": "Click",
            "next": ["MJA_START_KNOWN_POPUP"],
            "on_error": ["MJA_START_UNKNOWN_ABORT"],
        },
        "MJA_START_KNOWN_POPUP": {
            "recognition": "TemplateMatch",
            "template": "home/modal_close.png",
            "roi": [1180, 10, 70, 70],
            "threshold": 0.39,
            "timeout": 5000,
            "max_hit": 1,
            "action": "Click",
            "next": ["启动-游戏就绪"],
            "on_error": ["MJA_START_KNOWN_PAGE"],
        },
        "MJA_START_KNOWN_PAGE": {
            "recognition": "TemplateMatch",
            "template": "panel/panel_marker.png",
            "roi": [840, 0, 280, 160],
            "threshold": 0.4,
            "timeout": 5000,
            "action": "DoNothing",
            "next": ["启动-游戏就绪"],
            "on_error": ["MJA_START_UNKNOWN_ABORT"],
        },
        "MJA_START_UNKNOWN_ABORT": {
            "action": "StopTask",
            "Abort": True,
            "next": ["公共-通用中止"],
        },
    }


def _write_pipeline(
    tmp_path: Path,
    task_nodes: dict[str, dict[str, Any]],
    *,
    shared: bool = False,
    terminals: bool = True,
) -> Path:
    pipeline = tmp_path / "pipeline"
    daily = pipeline / "daily"
    daily.mkdir(parents=True)
    (daily / "sample_task.json").write_text(
        json.dumps(task_nodes, ensure_ascii=False), encoding="utf-8"
    )
    if shared:
        startup = pipeline / "startup"
        startup.mkdir()
        (startup / "game_start.json").write_text(
            json.dumps(_shared_startup(), ensure_ascii=False), encoding="utf-8"
        )
    if terminals:
        common = pipeline / "common"
        common.mkdir()
        (common / "terminal.json").write_text(
            json.dumps(_terminals(), ensure_ascii=False), encoding="utf-8"
        )
    return pipeline


def _by_rule(
    diagnostics: list[TaskEntryDiagnostic], rule: str
) -> TaskEntryDiagnostic:
    matches = [diagnostic for diagnostic in diagnostics if diagnostic.rule == rule]
    assert len(matches) == 1
    return matches[0]


def test_shared_convergence_entry_is_accepted_with_structured_evidence(tmp_path: Path) -> None:
    nodes = {
        "TASK_START": _begin("[JumpBack]启动-游戏启动"),
    }
    pipeline = _write_pipeline(tmp_path, nodes, shared=True)

    diagnostics = check_task_entry_contracts(pipeline)

    assert all(diagnostic.ok for diagnostic in diagnostics)
    entry = _by_rule(diagnostics, "entry_convergence")
    assert entry.evidence_nodes == ("启动-游戏启动",)
    assert entry.as_dict()["task_file"] == "daily/sample_task.json"
    assert entry.as_dict()["rule"] == "entry_convergence"


def test_current_task_resume_entry_is_accepted_without_shared_startup(tmp_path: Path) -> None:
    nodes = {
        "TASK_START": _begin("TASK_RESUME_RESULT_PROBE"),
        "TASK_RESUME_RESULT_PROBE": {
            "action": "DoNothing",
            "next": ["TASK_DONE"],
            "on_error": ["TASK_ABORT"],
        },
        "TASK_DONE": {
            "action": "Custom",
            "custom_action": "RecordTaskOutcome",
            "custom_action_param": {"status": "success"},
        },
        "TASK_ABORT": {"action": "StopTask", "Abort": True},
    }
    pipeline = _write_pipeline(tmp_path, nodes, terminals=False)

    diagnostics = check_task_entry_contracts(pipeline)

    assert all(diagnostic.ok for diagnostic in diagnostics)
    assert _by_rule(diagnostics, "entry_convergence").evidence_nodes == (
        "TASK_RESUME_RESULT_PROBE",
    )


def test_home_entry_is_accepted_as_an_equivalent_convergence_route(tmp_path: Path) -> None:
    nodes = {
        "TASK_START": _begin("TASK_HOME_PROBE"),
        "TASK_HOME_PROBE": {
            "recognition": "TemplateMatch",
            "template": "home/home_marker.png",
            "action": "DoNothing",
            "next": ["TASK_DONE"],
            "on_error": ["TASK_ABORT"],
        },
        "TASK_DONE": {
            "action": "Custom",
            "custom_action": "RecordTaskOutcome",
            "custom_action_param": {"status": "success"},
        },
        "TASK_ABORT": {"action": "StopTask", "Abort": True},
    }
    pipeline = _write_pipeline(tmp_path, nodes, terminals=False)

    diagnostics = check_task_entry_contracts(pipeline)

    assert _by_rule(diagnostics, "entry_convergence").ok
    assert _by_rule(diagnostics, "entry_convergence").evidence_nodes == (
        "TASK_HOME_PROBE",
    )


def test_missing_entry_is_reported_as_a_locatable_gap(tmp_path: Path) -> None:
    pipeline = _write_pipeline(
        tmp_path,
        {
            "TASK_PAGE": {"action": "DoNothing"},
            "TASK_DONE": {
                "action": "Custom",
                "custom_action": "RecordTaskOutcome",
                "custom_action_param": {"status": "success"},
            },
        },
        terminals=False,
    )

    diagnostic = _by_rule(check_task_entry_contracts(pipeline), "entry_convergence")

    assert not diagnostic.ok
    assert diagnostic.gap is not None
    assert "BeginTask" in diagnostic.gap
    assert "daily/sample_task.json" in diagnostic.format()


def test_local_stop_and_abort_nodes_satisfy_unified_end_boundary(tmp_path: Path) -> None:
    nodes = {
        "TASK_START": _begin("TASK_HOME_ENTRY", "TASK_LOCAL_ABORT"),
        "TASK_HOME_ENTRY": {
            "recognition": "OCR",
            "expected": "主页",
            "action": "DoNothing",
            "next": ["TASK_SUCCESS"],
        },
        "TASK_SUCCESS": {
            "action": "StopTask",
            "next": ["TASK_LOCAL_STOP"],
        },
        "TASK_LOCAL_STOP": {"action": "StopTask"},
        "TASK_LOCAL_ABORT": {
            "action": "Custom",
            "custom_action": "RecordTaskOutcome",
            "custom_action_param": {"status": "failed"},
            "Abort": True,
        },
    }
    pipeline = _write_pipeline(tmp_path, nodes, terminals=False)

    diagnostic = _by_rule(
        check_task_entry_contracts(pipeline), "unified_end_boundary"
    )

    assert diagnostic.ok
    assert {"TASK_LOCAL_STOP", "TASK_LOCAL_ABORT"} <= set(diagnostic.evidence_nodes)


def test_missing_one_end_boundary_is_reported(tmp_path: Path) -> None:
    nodes = {
        "TASK_START": _begin("TASK_HOME_PROBE"),
        "TASK_HOME_PROBE": {
            "recognition": "TemplateMatch",
            "template": "home/home_marker.png",
            "action": "DoNothing",
            "next": ["TASK_SUCCESS"],
        },
        "TASK_SUCCESS": {"action": "StopTask"},
    }
    pipeline = _write_pipeline(tmp_path, nodes, terminals=False)

    diagnostic = _by_rule(
        check_task_entry_contracts(pipeline), "unified_end_boundary"
    )

    assert not diagnostic.ok
    assert diagnostic.gap is not None
    assert "failure" in diagnostic.gap


def test_complete_copy_of_shared_game_start_recovery_is_rejected(tmp_path: Path) -> None:
    shared = _shared_startup()
    copied_title = deepcopy(shared["启动-标题-或-加载"])
    copied_popup = deepcopy(shared["MJA_START_KNOWN_POPUP"])
    copied_page = deepcopy(shared["MJA_START_KNOWN_PAGE"])
    copied_title["next"] = ["TASK_START_POPUP"]
    copied_title["on_error"] = ["TASK_LOCAL_ABORT"]
    copied_popup["next"] = ["TASK_START_PAGE"]
    copied_popup["on_error"] = ["TASK_START_PAGE"]
    copied_page["next"] = ["TASK_LOCAL_STOP"]
    copied_page["on_error"] = ["TASK_LOCAL_ABORT"]
    nodes = {
        "TASK_START": _begin("TASK_START_TITLE", "TASK_LOCAL_ABORT"),
        "TASK_START_TITLE": copied_title,
        "TASK_START_POPUP": copied_popup,
        "TASK_START_PAGE": copied_page,
        "TASK_LOCAL_STOP": {"action": "StopTask"},
        "TASK_LOCAL_ABORT": {"action": "StopTask", "Abort": True},
    }
    pipeline = _write_pipeline(tmp_path, nodes, shared=True)

    diagnostic = _by_rule(
        check_task_entry_contracts(pipeline), "duplicate_game_start_recovery"
    )

    assert not diagnostic.ok
    assert diagnostic.evidence_nodes == (
        "TASK_START_PAGE",
        "TASK_START_POPUP",
        "TASK_START_TITLE",
    )
    assert diagnostic.gap is not None
    assert "MJA_START" in diagnostic.gap


def test_task_specific_startup_recovery_is_not_reported_as_common_copy(
    tmp_path: Path,
) -> None:
    nodes = {
        "TASK_START": _begin("TASK_GAME_START_RECOVERY"),
        "TASK_GAME_START_RECOVERY": {
            "action": "StartApp",
            "custom_action_param": {"task_id": "SAMPLE_TASK"},
            "next": ["TASK_RECOVERY_STATE"],
            "on_error": ["TASK_LOCAL_ABORT"],
        },
        "TASK_RECOVERY_STATE": {
            "recognition": "OCR",
            "expected": "任务页面",
            "action": "DoNothing",
            "next": ["TASK_HOME_PROBE"],
            "on_error": ["TASK_LOCAL_ABORT"],
        },
        "TASK_HOME_PROBE": {
            "recognition": "TemplateMatch",
            "template": "home/home_marker.png",
            "action": "DoNothing",
            "next": ["TASK_SUCCESS"],
        },
        "TASK_SUCCESS": {
            "action": "Custom",
            "custom_action": "RecordTaskOutcome",
            "custom_action_param": {"status": "success"},
        },
        "TASK_LOCAL_ABORT": {"action": "StopTask", "Abort": True},
    }
    pipeline = _write_pipeline(tmp_path, nodes, shared=True)

    diagnostic = _by_rule(
        check_task_entry_contracts(pipeline), "duplicate_game_start_recovery"
    )

    assert diagnostic.ok
    assert diagnostic.evidence_nodes == ()


def test_real_daily_inventory_reports_readable_gaps_without_forcing_all_passes() -> None:
    diagnostics = check_task_entry_contracts(PIPELINE_ROOT.parent)
    daily_files = sorted(PIPELINE_ROOT.joinpath("daily").glob("*.json"))

    assert len(diagnostics) == len(daily_files) * 3
    assert all(
        diagnostic.task_file.startswith("daily/")
        and diagnostic.rule
        and (diagnostic.ok or diagnostic.evidence_nodes or diagnostic.gap)
        for diagnostic in diagnostics
    )

    break_array = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.task_file == "daily/break_array_martial_daily.json"
        and diagnostic.rule == "entry_convergence"
    ]
    assert len(break_array) == 1
    assert break_array[0].entry_nodes == ("破阵武学-任务入口",)
    assert break_array[0].ok or break_array[0].gap


def test_resource_tree_does_not_gate_task_entry_gaps_by_default() -> None:
    errors = check_resource_tree(Path("assets/resource/base"))

    assert all(not error.startswith("task entry gate:") for error in errors)


def test_resource_tree_surfaces_task_gate_errors_when_explicitly_enabled() -> None:
    errors = check_resource_tree(Path("assets/resource/base"), task_entry_gate=True)

    diagnostics = check_task_entry_contracts(PIPELINE_ROOT.parent)
    expected = [diagnostic.format() for diagnostic in diagnostics if not diagnostic.ok]
    assert [error for error in errors if error.startswith("task entry gate:")] == expected
