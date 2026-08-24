import json
from pathlib import Path

import pytest

from tools.check_mfw_resources import (
    load_pipeline_nodes,
    validate_guarded_input_evidence,
    validate_nodes,
)
from tests.mfw.pipeline_assertions import assert_native_success_node


FIXTURE_ROOT = Path("tests/fixtures")
MANIFEST_FIXTURES = (
    "BATTLE_PASS_REWARD_DAILY/manifest.json",
    "BUY_TEA_DAILY/manifest.json",
    "COLLECTION_DEPLOYMENT_DAILY/manifest.json",
    "DAILY_TASK_REWARD_CLAIM_DAILY/manifest.json",
    "DUNGEON_SWEEP_DAILY/manifest.json",
    "EAT_STAMINA_FOOD_DAILY/manifest.json",
    "FREE_APPRAISAL_DAILY/manifest.json",
    "HERO_DISPATCH_DAILY/manifest.json",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/manifest.json",
    "MAIL_REWARD_DAILY/manifest.json",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY/manifest.json",
    "RING_CHALLENGE_DAILY/manifest.json",
    "SHADOW_RUINS_DAILY/manifest.json",
    "SHOP_FREE_GIFT_DAILY/manifest.json",
    "SPEND_CONDENSATE_DAILY/manifest.json",
    "TRIAL_SWORD_DAILY/manifest.json",
    "WEEKLY_FREE_GIFT_DAILY/manifest.json",
)
SNAPSHOT_FIXTURES = (
    "BREAK_ARRAY_MARTIAL_DAILY/r11_startup_loading.json",
    "BREAK_ARRAY_MARTIAL_DAILY/r21_confirm_transition.json",
)
FORBIDDEN_FIXTURE_KEYS = {
    "expected_status",
    "success_only_after_action_chain",
    "result_source",
    "result",
}


def _fixture_keys(payload: object) -> set[str]:
    if isinstance(payload, dict):
        return set(payload) | {
            key
            for value in payload.values()
            for key in _fixture_keys(value)
        }
    if isinstance(payload, list):
        return {key for value in payload for key in _fixture_keys(value)}
    return set()


def test_listed_fixtures_are_diagnostic_only() -> None:
    for relative_path in MANIFEST_FIXTURES + SNAPSHOT_FIXTURES:
        path = FIXTURE_ROOT / relative_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not FORBIDDEN_FIXTURE_KEYS & _fixture_keys(payload), path
        assert "result.json" not in path.read_text(encoding="utf-8")

    for relative_path in MANIFEST_FIXTURES:
        payload = json.loads(
            (FIXTURE_ROOT / relative_path).read_text(encoding="utf-8")
        )
        for case in payload["cases"].values():
            assert "expected_page" in case or "page_hits" in case
            assert "expected_targets" in case or "target_hits" in case
            assert "image" in case or "screenshot" in case


def test_base_resource_contains_ocr_and_native_common_terminals() -> None:
    root = Path("assets/resource/base")
    assert (root / "model/ocr/det.onnx").is_file()
    assert (root / "model/ocr/rec.onnx").is_file()
    assert (root / "model/ocr/keys.txt").is_file()
    nodes = load_pipeline_nodes(root / "pipeline")
    assert nodes["1369-公共-通用停止"]["action"] == "StopTask"
    assert nodes["1369-公共-通用停止"]["action"] == "StopTask"
    assert nodes["1371-公共-原生成功-主页边界"]["next"] == [
        "1369-公共-通用停止"
    ]
    assert nodes["1366-公共-通用中止"]["custom_action"] == "FailTask"


def test_base_resource_contains_native_success_cleanup() -> None:
    nodes = load_pipeline_nodes(Path("assets/resource/base/pipeline"))

    home_boundary = nodes["1371-公共-原生成功-主页边界"]
    home_return = nodes["1372-公共-原生成功-尝试返回"]
    assert home_boundary["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["0026-公共-游戏主页-页面"],
            "box_index": 0,
        },
    }
    assert home_boundary["action"] == "DoNothing"
    assert home_boundary["next"] == ["1369-公共-通用停止"]
    assert home_boundary["on_error"] == ["1372-公共-原生成功-尝试返回"]
    assert home_return["custom_action"] == "ReturnToWorldHome"
    assert home_return["next"] == ["1369-公共-通用停止"]
    assert home_return["on_error"] == ["1369-公共-通用停止"]
    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_pipeline_validator_rejects_forbidden_control_planes(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.json"
    pipeline.write_text(
        '{"X":{"action":"Custom","custom_action":"DailyWorkflowAction"}}\n',
        encoding="utf-8",
    )
    nodes = load_pipeline_nodes(tmp_path)
    errors = validate_nodes(nodes)
    assert any("DailyWorkflowAction" in error for error in errors)


def test_pipeline_validator_rejects_legacy_outcomes_status_and_bad_failtask() -> None:
    errors = validate_nodes(
        {
            "LEGACY": {
                "action": "Custom",
                "custom_action": "RecordTaskOutcome",
                "custom_action_param": {"status": "failed"},
            },
            "BAD_FAIL": {
                "action": "Custom",
                "custom_action": "FailTask",
                "Abort": True,
                "next": ["STOP"],
            },
            "STOP": {"action": "StopTask"},
        }
    )
    assert any("legacy outcome" in error for error in errors)
    assert any("business status" in error for error in errors)
    assert any("FailTask must be a terminal leaf" in error for error in errors)


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


def test_all_guarded_input_evidence_matches_its_and_results() -> None:
    nodes = load_pipeline_nodes(Path("assets/resource/base/pipeline"))
    assert validate_guarded_input_evidence(nodes) == []
