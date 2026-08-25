from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_no_custom_outcome_nodes

ROOT = Path(__file__).resolve().parents[3]
PIPELINE = (
    ROOT
    / "assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json"
)
FIXTURE = (
    ROOT
    / "tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY"
    / "r21_detail_material_insufficient.json"
)


def _nodes() -> dict[str, dict]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_r21_fixture_keeps_the_martial_page_contract() -> None:
    nodes = _nodes()
    fixture = _fixture()
    assert fixture["materials"]
    assert nodes["1057-武学突破-打开-研习"]["next"] == [
        "1058-武学突破-领取-左框",
        "1080-武学突破-领取-中框",
        "1081-武学突破-领取-右框",
        "1061-武学突破-无-成功-突破",
    ]


def test_material_detection_is_configured_fail_closed_for_both_ratio_nodes() -> None:
    nodes = _nodes()
    params = nodes["martial.material.insufficient"]["custom_recognition_param"]
    ratio_nodes = params["ratio_nodes"]
    assert ratio_nodes == [
        "martial.material.ratio.0",
        "martial.material.ratio.1",
    ]
    assert all(nodes[name]["recognition"] == "OCR" for name in ratio_nodes)
    assert nodes[ratio_nodes[0]]["expected"] == r"^[0-9]{1,6}\s*/\s*[0-9]{1,6}$"
    assert nodes[ratio_nodes[1]]["expected"] == r"^[0-9]{1,6}\s*/\s*[0-9]{1,6}$"
    assert params["material_relation"] == "owned<required"


def test_martial_status_migration_has_no_custom_outcome_or_breakthrough_actions() -> None:
    nodes = _nodes()
    serialized = json.dumps(nodes, ensure_ascii=False)
    assert_no_custom_outcome_nodes(nodes)
    for marker in (
        "open_martial_plus_slot",
        "study_martial_slot",
        "breakthrough_martial_slot",
        "confirm_martial_breakthrough",
    ):
        assert marker not in serialized
    assert "道具" not in serialized
    assert "加号" not in serialized
    for name in (
        "1058-武学突破-领取-左框",
        "1080-武学突破-领取-中框",
        "1081-武学突破-领取-右框",
    ):
        assert nodes[name]["max_hit"] == 1
        assert nodes[name].get("on_error") is None
    assert nodes["1061-武学突破-无-成功-突破"]["next"] == [
        "1084-武学突破-打开-馈赠奖励",
        "1062-武学突破-关闭-页面-用于-成功",
    ]
