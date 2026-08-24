from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_ordered_actions,
    assert_reachable,
    load_task_nodes,
)


EQUIPMENT = TaskContract(
    "EQUIPMENT_DECOMPOSE_DAILY",
    "daily/equipment_decompose_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / EQUIPMENT.pipeline_file
FIXTURE_PATH = (
    ROOT
    / "tests/fixtures/EQUIPMENT_DECOMPOSE_DAILY/20260824_reward_popup.json"
)


def _local_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_equipment_decompose_task_has_the_native_terminal_contract() -> None:
    local = _local_nodes()
    nodes = load_task_nodes(EQUIPMENT)
    guarded_actions = [
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
    assert_no_custom_outcome_nodes(local)
    assert_on_error_contract(
        local,
        local_nodes=set(local),
        shared_targets={"1365-公共-主页边界-失败", "1371-公共-原生成功-主页边界"},
    )
    assert_native_failure_node(local["0479-分解装备-记录-失败"])
    assert_native_success_node(nodes["1369-公共-通用停止"])
    assert "1363-公共-主页边界" not in json.dumps(local, ensure_ascii=False)
    assert "1366-公共-通用中止" not in json.dumps(local, ensure_ascii=False)
    for action_id in guarded_actions:
        assert_no_side_effect_retry(nodes, action_id)


def test_equipment_entry_begins_task_before_opening_resource_page() -> None:
    local = _local_nodes()
    entry = local["0008-分解装备-任务入口"]
    open_resource = local["0439-分解装备-打开-资源"]

    assert entry["custom_action"] == "BeginTask"
    assert entry["custom_action_param"] == {"task_id": EQUIPMENT.task_id}
    assert entry["recognition"]["param"] == {
        "all_of": ["0456-分解装备-装备-主页"],
        "box_index": 0,
    }
    assert entry["next"] == ["0439-分解装备-打开-资源"]
    assert open_resource["custom_action"] == "GuardedInput"
    assert open_resource["custom_action_param"]["action_id"] == "open_resource_page"
    assert open_resource["next"] == ["0440-分解装备-打开-库存"]


def test_equipment_success_closes_before_deferred_home_boundary() -> None:
    nodes = load_task_nodes(EQUIPMENT)

    outcome = nodes["0478-分解装备-分解-成功"]
    assert outcome["action"] == "DoNothing"
    assert outcome["next"] == ["1371-公共-原生成功-主页边界"]

    # The reward evidence is detected first, then the reward popup and
    # equipment page are closed, and only then is the deferred success
    # native success boundary.
    reward_probe = nodes["0450-分解装备-之后-确认-探测"]
    assert reward_probe["recognition"]["param"] == {
        "all_of": [
            "0473-分解装备-装备-分解-成功",
            "0038-公共-已知-点击空白关闭",
        ],
        "box_index": 1,
    }
    assert reward_probe["next"] == ["0475-分解装备-关闭-奖励"]
    assert reward_probe["on_error"] == [
        "0451-分解装备-无可分解-已完成"
    ]
    reward_close = nodes["0475-分解装备-关闭-奖励"]
    assert reward_close["action"] == "Click"
    assert reward_close["recognition"]["param"] == {
        "all_of": ["0473-分解装备-装备-分解-成功", "0038-公共-已知-点击空白关闭"],
        "box_index": 1,
    }
    assert reward_close["next"] == ["0476-分解装备-关闭"]
    assert nodes["0476-分解装备-关闭"]["next"] == ["0482-分解装备-成功-关闭装备页"]
    close_inventory = nodes["0482-分解装备-成功-关闭装备页"]
    assert close_inventory["recognition"]["param"] == {
        "all_of": [
            "0460-分解装备-装备-页面",
            "0474-分解装备-装备-关闭",
        ],
        "box_index": 1,
    }
    assert close_inventory["custom_action_param"]["action_id"] == "close_equipment_page"
    assert close_inventory["next"] == ["0477-分解装备-主页-之后-关闭"]
    assert nodes["0477-分解装备-主页-之后-关闭"]["next"] == ["0478-分解装备-分解-成功"]
    assert "on_error" not in nodes["0476-分解装备-关闭"]
    assert nodes["0476-分解装备-关闭"]["custom_action_param"]["fixed_click_mode"] == (
        "equipment_page_close"
    )
    assert_reachable(nodes, "0478-分解装备-分解-成功", "1369-公共-通用停止")


def test_equipment_decompose_uses_the_requested_quality_and_level_filters() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    assert nodes["0462-分解装备-装备-分解-页面"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["0460-分解装备-装备-页面", "0463-分解装备-装备-品质-筛选"],
            "box_index": 1,
        },
    }
    assert nodes["0463-分解装备-装备-品质-筛选"]["expected"] == "品质"
    assert nodes["0464-分解装备-装备-品质-对话框"]["expected"] == "品质"
    assert nodes["0465-分解装备-装备-品质-乙级或以下"]["expected"] == "乙品质及以下"
    assert nodes["0466-分解装备-装备-等级-筛选"]["expected"] == "级"
    assert nodes["0467-分解装备-装备-等级-对话框"]["expected"] == "级及以下"
    assert nodes["0468-分解装备-装备-等级-选项-80-或-以下"]["expected"] == "80"
    assert nodes["0469-分解装备-装备-批量-选择"]["expected"] == "批量选择"
    assert nodes["0470-分解装备-装备-确认-分解"]["expected"] == "确认分解"
    assert nodes["0472-分解装备-装备-确认-最终"]["expected"] == "确认"
    assert nodes["0473-分解装备-装备-分解-成功"]["expected"] == [
        "恭喜获得",
        "悉喜获得",
    ]

    level_selection = nodes["0445-分解装备-选择-等级"]
    assert level_selection["recognition"]["param"]["box_index"] == 2
    assert level_selection["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 2,
        "page_name": "0462-分解装备-装备-分解-页面",
        "target_name": "0468-分解装备-装备-等级-选项-80-或-以下",
    }

    assert nodes["0469-分解装备-装备-批量-选择"]["roi"] == [620, 620, 240, 100]


def test_equipment_second_confirmation_matches_the_live_reward_dialog() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    expected = nodes["0471-分解装备-装备-确认-对话框"]["expected"]

    assert "分解后将获得" in expected


def test_equipment_success_requires_reward_title_and_close_hint_in_one_frame() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    reward_title = nodes["0473-分解装备-装备-分解-成功"]

    # The live popup visibly says 恭喜获得, while the 2026-08-24 OCR snapshot
    # repeatedly read the stylized first glyph as 悉. Keep that one bounded
    # variant and require the stable popup close hint in the same frame.
    assert reward_title["expected"] == ["恭喜获得", "悉喜获得"]
    assert nodes["0450-分解装备-之后-确认-探测"]["recognition"]["param"] == {
        "all_of": [
            "0473-分解装备-装备-分解-成功",
            "0038-公共-已知-点击空白关闭",
        ],
        "box_index": 1,
    }
    assert "点击空白处关闭" not in reward_title["expected"]
    assert nodes["0475-分解装备-关闭-奖励"]["next"] == [
        "0476-分解装备-关闭"
    ]


def test_equipment_20260824_reward_popup_matches_the_same_frame_contract() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    title = fixture["recognitions"]["0473-分解装备-装备-分解-成功"]
    close_hint = fixture["recognitions"]["0038-公共-已知-点击空白关闭"]

    assert fixture["frame_size"] == [1280, 720]
    assert fixture["native_terminal"] == "Failed"
    assert fixture["reward_quantity"] == 180
    assert title["text"] in nodes["0473-分解装备-装备-分解-成功"]["expected"]
    assert close_hint["text"] in nodes["0038-公共-已知-点击空白关闭"]["expected"]
    assert close_hint["score"] > 0.999

    for node_name, observed in fixture["recognitions"].items():
        rx, ry, rw, rh = nodes[node_name]["roi"]
        bx, by, bw, bh = observed["box"]
        assert rx <= bx and ry <= by
        assert bx + bw <= rx + rw and by + bh <= ry + rh

    expected_anchors = [
        "0473-分解装备-装备-分解-成功",
        "0038-公共-已知-点击空白关闭",
    ]
    assert nodes["0450-分解装备-之后-确认-探测"]["recognition"]["param"][
        "all_of"
    ] == expected_anchors
    assert nodes["0475-分解装备-关闭-奖励"]["recognition"]["param"][
        "all_of"
    ] == expected_anchors


def test_equipment_without_eligible_items_is_already_complete_and_returns_home() -> None:
    nodes = load_task_nodes(EQUIPMENT)

    # After the first successful run the live page remained on the filtered
    # equipment screen, with no second confirmation popup.  That is the
    # bounded evidence for “nothing matching the requested filters remains”.
    assert nodes["0447-分解装备-确认-分解"]["on_error"] == ["0448-分解装备-无可分解-探测"]
    probe = nodes["0448-分解装备-无可分解-探测"]
    assert probe["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0462-分解装备-装备-分解-页面",
                "0469-分解装备-装备-批量-选择",
            ],
            "box_index": 1,
        },
    }
    assert probe["next"] == ["0451-分解装备-无可分解-已完成"]
    assert "on_error" not in probe

    completed = nodes["0451-分解装备-无可分解-已完成"]
    assert completed["action"] == "DoNothing"
    assert "custom_action" not in completed
    assert completed["next"] == ["0452-分解装备-无可分解-关闭"]
    close = nodes["0452-分解装备-无可分解-关闭"]
    assert close["action"] == "Custom"
    assert close["custom_action"] == "GuardedInput"
    assert close["custom_action_param"]["fixed_click_mode"] == "equipment_page_close"
    assert close["post_delay"] == 500
    assert close["next"] == ["0480-分解装备-无可分解-关闭装备页"]
    close_inventory = nodes["0480-分解装备-无可分解-关闭装备页"]
    assert close_inventory["recognition"]["param"] == {
        "all_of": [
            "0460-分解装备-装备-页面",
            "0474-分解装备-装备-关闭",
        ],
        "box_index": 1,
    }
    assert close_inventory["custom_action_param"]["action_id"] == "close_equipment_page"
    assert close_inventory["custom_action_param"]["fixed_click_mode"] == "equipment_page_close"
    assert close_inventory["next"] == ["0453-分解装备-无可分解-主页-探测"]
    probe_after_close = nodes["0453-分解装备-无可分解-主页-探测"]
    assert probe_after_close["next"] == ["1371-公共-原生成功-主页边界"]
    assert "on_error" not in probe_after_close
    assert_reachable(nodes, "0451-分解装备-无可分解-已完成", "1369-公共-通用停止")


def test_equipment_entry_roi_excludes_the_annotation_book_icon() -> None:
    node = load_task_nodes(EQUIPMENT)["0459-分解装备-装备-入口"]
    assert node["roi"] == [25, 315, 80, 80]
    assert node["threshold"] == 0.3


def test_equipment_decompose_button_roi_covers_the_bottom_decompose_button() -> None:
    node = load_task_nodes(EQUIPMENT)["0461-分解装备-装备-分解-按钮"]
    assert node["expected"] == "分解"
    assert node["roi"] == [620, 620, 240, 100]


def test_equipment_filter_dialog_rois_include_the_full_option_labels() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    for node_name in (
        "0464-分解装备-装备-品质-对话框",
        "0465-分解装备-装备-品质-乙级或以下",
        "0467-分解装备-装备-等级-对话框",
        "0468-分解装备-装备-等级-选项-80-或-以下",
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
    assert policy.cleanup_action_ids == frozenset({"close_equipment_page"})
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
        "close_equipment_page": 2,
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
