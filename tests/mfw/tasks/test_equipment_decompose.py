from __future__ import annotations

from collections.abc import Mapping

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_abort_code,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_ordered_actions,
    assert_outcome,
    assert_task_contract,
    load_task_nodes,
)


EQUIPMENT = TaskContract(
    "EQUIPMENT_DECOMPOSE_DAILY",
    "daily/equipment_decompose_daily.json",
)


def test_equipment_decompose_task_has_the_explicit_contract() -> None:
    assert_task_contract(EQUIPMENT)
    nodes = load_task_nodes(EQUIPMENT)
    guarded_actions = [
        "close_function_panel",
        "open_resource_page",
        "open_equipment_inventory",
        "open_equipment_decompose",
        "open_quality_filter",
        "select_quality_b_or_below",
        "open_level_filter",
        "select_level_80_or_below",
        "batch_select_equipment",
        "confirm_equipment_decompose",
        "confirm_equipment_decompose_final",
        "close_equipment_page",
    ]
    assert_guarded_actions(nodes, EQUIPMENT.task_id, guarded_actions)
    assert_ordered_actions(nodes, guarded_actions)
    assert_outcome(
        nodes,
        "MJA_EQUIPMENT_DECOMPOSE_SUCCESS",
        "success",
        "equipment.decomposition_confirmed",
    )
    assert_abort_code(
        nodes,
        "MJA_EQUIPMENT_RECORD_FAILURE",
        "EQUIPMENT_DECOMPOSE_POSTCONDITION_MISSING",
    )
    for action_id in guarded_actions:
        assert_no_side_effect_retry(nodes, action_id)


def test_equipment_decompose_uses_the_requested_quality_and_level_filters() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    assert nodes["equipment.decompose.page"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["equipment.page", "equipment.quality.filter"],
            "box_index": 1,
        },
    }
    assert nodes["equipment.quality.filter"]["expected"] == "品质"
    assert nodes["equipment.quality.dialog"]["expected"] == "品质"
    assert nodes["equipment.quality.option_b_or_below"]["expected"] == "乙"
    assert nodes["equipment.level.filter"]["expected"] == "级"
    assert nodes["equipment.level.dialog"]["expected"] == "级及以下"
    assert nodes["equipment.level.option_80_or_below"]["expected"] == "80"
    assert nodes["equipment.batch_select"]["expected"] == "批量选择"
    assert nodes["equipment.confirm_decompose"]["expected"] == "确认分解"
    assert nodes["equipment.confirm.final"]["expected"] == "确认"
    assert nodes["equipment.decompose.success"]["expected"] == [
        "分解成功",
        "分解完成",
    ]


def test_equipment_entry_roi_excludes_the_annotation_book_icon() -> None:
    node = load_task_nodes(EQUIPMENT)["equipment.entry"]
    assert node["roi"] == [25, 315, 80, 80]
    assert node["threshold"] == 0.3


def test_equipment_decompose_button_roi_covers_the_bottom_decompose_button() -> None:
    node = load_task_nodes(EQUIPMENT)["equipment.decompose.button"]
    assert node["expected"] == "分解"
    assert node["roi"] == [620, 620, 240, 100]


def test_equipment_filter_dialog_rois_include_the_full_option_labels() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    for node_name in (
        "equipment.quality.dialog",
        "equipment.quality.option_b_or_below",
        "equipment.level.dialog",
        "equipment.level.option_80_or_below",
    ):
        x, y, width, height = nodes[node_name]["roi"]
        # The live failure showed the first character at approximately x=148,
        # so an ROI starting at x=180 can only OCR the suffix "质及以下".
        assert x <= 145
        assert y <= 473
        assert x + width >= 260
        assert y + height >= 630


def test_equipment_decompose_policy_is_bounded_and_has_no_resource_purchase() -> None:
    policy = TASK_POLICIES[EQUIPMENT.task_id]
    assert policy.risk_levels == frozenset({"consumptive", "stateful"})
    assert policy.max_steps == 32
    assert dict(policy.resource_caps) == {}
    assert dict(policy.action_caps) == {
        "close_function_panel": 1,
        "open_resource_page": 1,
        "open_equipment_inventory": 1,
        "open_equipment_decompose": 1,
        "open_quality_filter": 1,
        "select_quality_b_or_below": 1,
        "open_level_filter": 1,
        "select_level_80_or_below": 1,
        "batch_select_equipment": 1,
        "confirm_equipment_decompose": 1,
        "confirm_equipment_decompose_final": 1,
        "close_equipment_page": 1,
    }


def test_equipment_mutations_are_guarded_by_page_and_target_evidence() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    mutating = {
        "open_equipment_decompose",
        "open_quality_filter",
        "select_quality_b_or_below",
        "open_level_filter",
        "select_level_80_or_below",
        "batch_select_equipment",
        "confirm_equipment_decompose",
        "confirm_equipment_decompose_final",
    }
    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if not isinstance(params, Mapping) or params.get("action_id") not in mutating:
            continue
        evidence = params["evidence"]
        assert evidence["page_name"]
        assert evidence["target_name"]
        assert isinstance(evidence["page_index"], int)
        assert isinstance(evidence["target_index"], int)
        assert node.get("retry_times", 0) == 0
