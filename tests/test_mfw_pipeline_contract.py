from pathlib import Path

import pytest

from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes


def test_base_resource_contains_ocr_and_common_terminals() -> None:
    root = Path("assets/resource/base")
    assert (root / "model/ocr/det.onnx").is_file()
    assert (root / "model/ocr/rec.onnx").is_file()
    assert (root / "model/ocr/keys.txt").is_file()
    nodes = load_pipeline_nodes(root / "pipeline")
    assert nodes["MJA_COMMON_STOP"]["action"] == "StopTask"
    assert nodes["MJA_COMMON_ABORT"]["Abort"] is True
    assert nodes["MJA_COMMON_ABORT"]["action"] == "StopTask"


def test_pipeline_validator_rejects_forbidden_control_planes(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.json"
    pipeline.write_text(
        '{"X":{"action":"Custom","custom_action":"DailyWorkflowAction"}}\n',
        encoding="utf-8",
    )
    nodes = load_pipeline_nodes(tmp_path)
    errors = validate_nodes(nodes)
    assert any("DailyWorkflowAction" in error for error in errors)


def test_pipeline_loader_rejects_duplicate_nodes(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"X":{"action":"StopTask"}}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"X":{"action":"StopTask"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_pipeline_nodes(tmp_path)


def test_pipeline_validator_rejects_missing_target_and_unbounded_cycle() -> None:
    nodes = {
        "A": {"action": "Custom", "next": ["MISSING"]},
        "B": {"action": "Click", "next": ["B"]},
    }
    errors = validate_nodes(nodes)
    assert any("MISSING" in error for error in errors)
    assert any("cycle" in error.lower() for error in errors)


def test_pipeline_validator_rejects_node_reference_as_recognition_type() -> None:
    errors = validate_nodes({"PROBE": {"recognition": "page.home", "action": "DoNothing"}})
    assert any("unknown recognition type page.home" in error for error in errors)
