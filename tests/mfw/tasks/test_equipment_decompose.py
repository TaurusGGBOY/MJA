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
    assert_reachable,
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
        "分解装备-分解-成功",
        "success",
        "equipment.decomposition_confirmed",
    )
    assert_abort_code(
        nodes,
        "分解装备-记录-失败",
        "EQUIPMENT_DECOMPOSE_POSTCONDITION_MISSING",
    )
    for action_id in guarded_actions:
        assert_no_side_effect_retry(nodes, action_id)


def test_equipment_success_closes_before_deferred_home_boundary() -> None:
    nodes = load_task_nodes(EQUIPMENT)

    outcome = nodes["分解装备-分解-成功"]
    assert outcome["custom_action_param"]["defer_home_boundary"] is True
    assert outcome["next"] == ["公共-主页边界"]

    # The reward evidence is detected first, then the reward popup and
    # equipment page are closed, and only then is the deferred success
    # outcome recorded.
    assert nodes["分解装备-之后-确认-探测"]["next"] == ["分解装备-关闭-奖励"]
    assert nodes["分解装备-之后-确认-探测"]["on_error"] == [
        "分解装备-无可分解-已完成"
    ]
    reward_close = nodes["分解装备-关闭-奖励"]
    assert reward_close["action"] == "Click"
    assert reward_close["recognition"]["param"] == {
        "all_of": ["分解装备-装备-分解-成功", "公共-已知-点击空白关闭"],
        "box_index": 1,
    }
    assert reward_close["next"] == ["分解装备-关闭"]
    assert nodes["分解装备-关闭"]["next"] == ["分解装备-主页-之后-关闭"]
    assert nodes["分解装备-主页-之后-关闭"]["next"] == ["分解装备-分解-成功"]
    assert nodes["分解装备-关闭"]["on_error"] == ["分解装备-记录-失败"]
    assert nodes["分解装备-关闭"]["custom_action_param"]["fixed_click_mode"] == (
        "equipment_page_close"
    )
    assert_reachable(nodes, "分解装备-分解-成功", "公共-通用停止")


def test_equipment_decompose_uses_the_requested_quality_and_level_filters() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    assert nodes["分解装备-装备-分解-页面"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["分解装备-装备-页面", "分解装备-装备-品质-筛选"],
            "box_index": 1,
        },
    }
    assert nodes["分解装备-装备-品质-筛选"]["expected"] == "品质"
    assert nodes["分解装备-装备-品质-对话框"]["expected"] == "品质"
    assert nodes["分解装备-装备-品质-乙级或以下"]["expected"] == "乙品质及以下"
    assert nodes["分解装备-装备-等级-筛选"]["expected"] == "级"
    assert nodes["分解装备-装备-等级-对话框"]["expected"] == "级及以下"
    assert nodes["分解装备-装备-等级-选项-80-或-以下"]["expected"] == "80"
    assert nodes["分解装备-装备-批量-选择"]["expected"] == "批量选择"
    assert nodes["分解装备-装备-确认-分解"]["expected"] == "确认分解"
    assert nodes["分解装备-装备-确认-最终"]["expected"] == "确认"
    assert nodes["分解装备-装备-分解-成功"]["expected"] == "恭喜获得"

    level_selection = nodes["分解装备-选择-等级"]
    assert level_selection["recognition"]["param"]["box_index"] == 2
    assert level_selection["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 2,
        "page_name": "分解装备-装备-分解-页面",
        "target_name": "分解装备-装备-等级-选项-80-或-以下",
    }

    assert nodes["分解装备-装备-批量-选择"]["roi"] == [620, 620, 240, 100]


def test_equipment_second_confirmation_matches_the_live_reward_dialog() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    expected = nodes["分解装备-装备-确认-对话框"]["expected"]

    assert "分解后将获得" in expected


def test_equipment_success_uses_only_the_reward_title_as_business_evidence() -> None:
    node = load_task_nodes(EQUIPMENT)["分解装备-装备-分解-成功"]

    # The live popup visibly says 恭喜获得.  The close hint is cleanup
    # evidence, not a success signal.
    assert node["expected"] == "恭喜获得"
    assert "恭喜获得" in node["expected"]
    assert "悉喜获得" not in node["expected"]
    assert "点击空白处关闭" not in node["expected"]
    assert load_task_nodes(EQUIPMENT)["分解装备-关闭-奖励"]["next"] == [
        "分解装备-关闭"
    ]


def test_equipment_without_eligible_items_is_already_complete_and_returns_home() -> None:
    nodes = load_task_nodes(EQUIPMENT)

    # After the first successful run the live page remained on the filtered
    # equipment screen, with no second confirmation popup.  That is the
    # bounded evidence for “nothing matching the requested filters remains”.
    assert nodes["分解装备-确认-分解"]["on_error"] == ["分解装备-无可分解-探测"]
    probe = nodes["分解装备-无可分解-探测"]
    assert probe["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "分解装备-装备-分解-页面",
                "分解装备-装备-批量-选择",
            ],
            "box_index": 1,
        },
    }
    assert probe["next"] == ["分解装备-无可分解-已完成"]
    assert probe["on_error"] == ["分解装备-记录-失败"]

    completed = nodes["分解装备-无可分解-已完成"]
    assert completed["custom_action_param"] == {
        "task_id": EQUIPMENT.task_id,
        "status": "already_complete",
        "postcondition": "equipment.no_reward_popup",
        "defer_home_boundary": True,
    }
    assert completed["next"] == ["分解装备-无可分解-关闭"]
    close = nodes["分解装备-无可分解-关闭"]
    assert close["action"] == "Click"
    assert close["post_delay"] == 500
    assert close["next"] == ["分解装备-无可分解-主页-探测"]
    probe_after_close = nodes["分解装备-无可分解-主页-探测"]
    assert probe_after_close["on_error"] == ["分解装备-无可分解-重启"]
    restart = nodes["分解装备-无可分解-重启"]
    assert restart["custom_action"] == "RestartGameSurface"
    assert restart["custom_action_param"] == {
        "package": "com.hanjiasongshu.dr22",
        "activity": "com.hanjiasongshu.dr22/.MainActivity",
        "force_stop": True,
        "cooldown_ms": 2000,
        "start_repeat": 1,
    }
    assert nodes["分解装备-无可分解-重启后-主页-探测"]["next"] == [
        "公共-主页边界"
    ]
    assert_reachable(nodes, "分解装备-无可分解-已完成", "公共-通用停止")


def test_equipment_entry_roi_excludes_the_annotation_book_icon() -> None:
    node = load_task_nodes(EQUIPMENT)["分解装备-装备-入口"]
    assert node["roi"] == [25, 315, 80, 80]
    assert node["threshold"] == 0.3


def test_equipment_decompose_button_roi_covers_the_bottom_decompose_button() -> None:
    node = load_task_nodes(EQUIPMENT)["分解装备-装备-分解-按钮"]
    assert node["expected"] == "分解"
    assert node["roi"] == [620, 620, 240, 100]


def test_equipment_filter_dialog_rois_include_the_full_option_labels() -> None:
    nodes = load_task_nodes(EQUIPMENT)
    for node_name in (
        "分解装备-装备-品质-对话框",
        "分解装备-装备-品质-乙级或以下",
        "分解装备-装备-等级-对话框",
        "分解装备-装备-等级-选项-80-或-以下",
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
