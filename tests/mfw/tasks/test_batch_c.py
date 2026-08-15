from __future__ import annotations

import json
import re
from collections.abc import Mapping

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    ROOT,
    TaskContract,
    assert_action_limit,
    assert_battle_result_partition,
    assert_condition,
    assert_fixture_matrix,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_outcome,
    assert_resource_guard,
    assert_task_contract,
    assert_terminal_after_loop,
    load_task_nodes,
)

SHADOW = TaskContract("SHADOW_RUINS_DAILY", "daily/shadow_ruins_daily.json")
MARTIAL = TaskContract(
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "daily/martial_study_breakthrough_daily.json",
)
DUNGEON = TaskContract("DUNGEON_SWEEP_DAILY", "daily/dungeon_sweep_daily.json")
RING = TaskContract("RING_CHALLENGE_DAILY", "daily/ring_challenge_daily.json")
BATCH_C = [SHADOW, MARTIAL, DUNGEON, RING]


def _assert_archived_ocr_hit(
    node: Mapping[str, object], text: str, box: tuple[int, int, int, int]
) -> None:
    expected = node["expected"]
    patterns = expected if isinstance(expected, list) else [expected]
    assert any(re.fullmatch(pattern, text) for pattern in patterns)
    roi_x, roi_y, roi_width, roi_height = node["roi"]
    box_x, box_y, box_width, box_height = box
    assert roi_x <= box_x
    assert roi_y <= box_y
    assert box_x + box_width <= roi_x + roi_width
    assert box_y + box_height <= roi_y + roi_height


def _box_is_inside(
    roi: list[int], box: tuple[int, int, int, int]
) -> bool:
    roi_x, roi_y, roi_width, roi_height = roi
    box_x, box_y, box_width, box_height = box
    return (
        roi_x <= box_x
        and roi_y <= box_y
        and box_x + box_width <= roi_x + roi_width
        and box_y + box_height <= roi_y + roi_height
    )


def test_batch_c_contracts_use_existing_fixture_matrix_until_live_capture() -> None:
    for contract in BATCH_C:
        assert_task_contract(
            contract,
            require_game_start_recovery=contract is not DUNGEON,
        )
        assert_fixture_matrix(
            contract.task_id,
            {"entry", "actionable", "completed", "danger"},
        )


def test_shadow_ruins_has_bounded_exploration_and_truthful_battle_partition() -> None:
    nodes = load_task_nodes(SHADOW)
    assert_guarded_actions(
        nodes,
        SHADOW.task_id,
        [
            "open_painting_scroll",
            "open_shadow",
            "select_active_shadow_card",
            "enter_shadow_stage",
            "confirm_shadow_auto_route",
            "dismiss_shadow_battle_result",
            "dismiss_shadow_battle_failure",
            "dismiss_shadow_reward_popup",
            "confirm_shadow_completion",
            "advance_shadow_foreground_triplet",
            "transfer_shadow_stage",
            "confirm_shadow_transfer",
            "apply_shadow_recommended_team",
            "use_shadow_recommended_team",
            "close_shadow_recommended_team",
            "move_shadow_foreground_left",
            "move_shadow_foreground_center",
            "move_shadow_foreground_right",
            "battle",
        ],
    )
    assert_terminal_after_loop(nodes, "MJA_SHADOW_TRANSFER_LOOP", 8, "SHADOW_TRANSFER_LIMIT")
    assert_terminal_after_loop(
        nodes, "影之遗迹-前台-循环", 40, "SHADOW_FOREGROUND_LIMIT"
    )
    assert_terminal_after_loop(nodes, "影之遗迹-战斗-循环", 12, "SHADOW_BATTLE_LIMIT")
    assert nodes["影之遗迹-战斗-循环"]["timeout"] == 240000
    assert_terminal_after_loop(
        nodes,
        "MJA_SHADOW_FAILURE_DISMISS_LOOP",
        3,
        "SHADOW_FAILURE_DISMISS_LIMIT",
    )
    assert_action_limit(SHADOW.task_id, "confirm_shadow_completion", 1)
    assert_battle_result_partition(nodes, "MJA_SHADOW_BATTLE_RESULT")
    assert_outcome(
        nodes,
        "影之遗迹-记录-成功",
        "success",
        "shadow.no_active_or_done_and_home",
    )
    for action_id in (
        "battle",
        "transfer_shadow_stage",
        "confirm_shadow_completion",
    ):
        assert_no_side_effect_retry(nodes, action_id)

    assert nodes["MJA_SHADOW_NO_ACTIVE_CARD"]["next"] == [
        "MJA_SHADOW_RESTART_SURFACE"
    ]
    assert nodes["MJA_SHADOW_SUCCESS"]["next"] == ["MJA_SHADOW_RESTART_SURFACE"]
    restart = nodes["MJA_SHADOW_RESTART_SURFACE"]
    assert restart["custom_action"] == "RestartGameSurface"
    assert restart["custom_action_param"] == {
        "package": "com.hanjiasongshu.dr22",
        "activity": "com.hanjiasongshu.dr22/.MainActivity",
    }
    assert restart["next"] == [
        "影之遗迹-主页边界-探测",
        "[JumpBack]启动-游戏启动",
    ]
    boundary_failure = nodes["影之遗迹-边界-失败"]
    assert boundary_failure["custom_action_param"]["error_code"] == "SHADOW_HOME_BOUNDARY_MISSING"
    assert boundary_failure["custom_action_param"]["native_fail_after_record"] is True
    assert boundary_failure["Abort"] is True


def test_shadow_r19_adjacent_dungeon_page_fails_without_clicking_it() -> None:
    nodes = load_task_nodes(SHADOW)
    start = nodes["影之遗迹-任务入口"]
    assert start["next"] == [
        "[JumpBack]公共-已知-茶-详情-关闭",
        "[JumpBack]公共-已知-茶-商店-关闭",
        "影之遗迹-页面-探测",
        "影之遗迹-画卷-页面",
        "MJA_SHADOW_DUNGEON_PAGE_PROBE",
        "影之遗迹-主页-探测",
    ]
    assert start["on_error"] == ["影之遗迹-入口-未知"]
    open_painting = nodes["影之遗迹-打开-画卷"]
    recognition = open_painting["recognition"]["param"]

    # r19 matched the broad home template and the combined OCR text
    # “副本（画卷”, but Maa returned the page box [1040, 0, 240, 110] to
    # GuardedInput.  The replacement must return only the exact 画卷 box.
    assert recognition["all_of"] == ["影之遗迹-影-主页-页面", "影之遗迹-影-画卷-入口"]
    assert recognition["box_index"] == 1
    assert open_painting["retry_times"] == 0
    assert open_painting["max_hit"] == 1
    assert open_painting["next"] == [
        "影之遗迹-画卷-页面",
        "MJA_SHADOW_DUNGEON_PAGE_PROBE",
        "影之遗迹-主页-恢复-探测",
    ]
    assert nodes["影之遗迹-影-主页-页面"] == {
        "recognition": "TemplateMatch",
        "template": "home/home_marker.png",
        "roi": [1040, 0, 240, 110],
        "threshold": 0.375,
        "action": "DoNothing",
    }
    assert nodes["影之遗迹-影-主页-副本"]["expected"] == r"^副本$"
    assert nodes["影之遗迹-影-主页-试炼"]["expected"] == r"^试剑$"
    assert nodes["影之遗迹-影-画卷-入口"]["expected"] == r"^画卷$"

    # The r19 post-click frame was the ordinary dungeon page.  Its top-left
    # title and list item are an explicit wrong-page boundary, and that branch
    # records failure without exposing any input action.
    _assert_archived_ocr_hit(nodes["shadow.dungeon.page.title"], "副本", (92, 29, 44, 25))
    _assert_archived_ocr_hit(
        nodes["shadow.dungeon.page.list"], "贼寇山洞", (109, 291, 100, 27)
    )
    wrong_page = nodes["MJA_SHADOW_DUNGEON_PAGE_PROBE"]
    assert wrong_page["action"] == "DoNothing"
    assert wrong_page["next"] == ["MJA_SHADOW_WRONG_ENTRY_FAILURE"]
    failure = nodes["MJA_SHADOW_WRONG_ENTRY_FAILURE"]
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["error_code"] == "SHADOW_WRONG_ENTRY_PAGE"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
    assert "on_error" not in failure

    # The ordinary page can still show the 画卷 navigation sibling at
    # [1116, 58, 32, 14].  It must not satisfy the true page-title ROI.
    title = nodes["影之遗迹-影-画卷-页面-标题"]
    assert not _box_is_inside(title["roi"], (1116, 58, 32, 14))


def test_shadow_r21_painting_page_uses_exact_tight_shadow_entry() -> None:
    nodes = load_task_nodes(SHADOW)

    # The same r21 frame proves a real home boundary before the input.
    _assert_archived_ocr_hit(nodes["影之遗迹-影-主页-副本"], "副本", (1058, 57, 32, 18))
    _assert_archived_ocr_hit(nodes["影之遗迹-影-主页-试炼"], "试剑", (992, 644, 39, 18))
    _assert_archived_ocr_hit(nodes["影之遗迹-影-画卷-入口"], "画卷", (1115, 55, 34, 20))

    # These are the four stable r21 HERO OCR hits from the real painting page.
    _assert_archived_ocr_hit(nodes["影之遗迹-影-画卷-页面-标题"], "画卷", (92, 29, 44, 25))
    _assert_archived_ocr_hit(
        nodes["影之遗迹-影-画卷-页面-世界"], "·偃武世界", (118, 144, 115, 28)
    )
    _assert_archived_ocr_hit(nodes["影之遗迹-影-画卷-页面-区域"], "云州", (133, 244, 53, 31))
    entry = nodes["影之遗迹-影-入口"]
    assert entry["expected"] == r"^蜃影武墟$"
    _assert_archived_ocr_hit(entry, "蜃影武墟", (1116, 651, 84, 22))

    # The adjacent 侠客派遣 label must be outside the tight Shadow ROI.
    assert not _box_is_inside(entry["roi"], (1006, 648, 86, 28))
    open_shadow = nodes["影之遗迹-打开-影"]
    recognition = open_shadow["recognition"]["param"]
    assert recognition["all_of"] == ["影之遗迹-影-画卷-页面", "影之遗迹-影-入口"]
    assert recognition["box_index"] == 1
    assert open_shadow["retry_times"] == 0
    assert open_shadow["max_hit"] == 1


def test_shadow_entry_recovery_is_finite_and_unknown_is_native_failure() -> None:
    nodes = load_task_nodes(SHADOW)
    policy = TASK_POLICIES[SHADOW.task_id]

    assert nodes["影之遗迹-任务入口"]["custom_action"] == "BeginTask"
    assert nodes["影之遗迹-画卷-页面"]["on_error"] == [
        "影之遗迹-入口-未知"
    ]
    recovery = nodes["影之遗迹-打开-画卷-恢复"]
    assert recovery["custom_action_param"]["action_id"] == "open_painting_scroll"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["next"] == [
        "影之遗迹-画卷-页面",
        "MJA_SHADOW_DUNGEON_PAGE_PROBE",
    ]
    assert policy.action_caps["open_painting_scroll"] == 2

    guarded_action_ids = {
        node["custom_action_param"]["action_id"]
        for node in nodes.values()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == SHADOW.task_id
    }
    assert guarded_action_ids <= policy.action_caps.keys()
    assert all(policy.action_caps[action_id] > 0 for action_id in guarded_action_ids)

    # BeginTask makes the diagnostic result fresh; RecordTaskOutcome plus
    # Abort makes the same unknown entry a native Maa Failed as well.
    unknown = nodes["影之遗迹-入口-未知"]
    assert unknown["custom_action"] == "RecordTaskOutcome"
    assert unknown["custom_action_param"] == {
        "task_id": "SHADOW_RUINS_DAILY",
        "status": "failed",
        "error_code": "SHADOW_PAINTING_ENTRY_UNKNOWN",
        "postcondition": "shadow.painting_entry_state_known",
        "native_fail_after_record": True,
    }
    assert unknown["Abort"] is True
    assert unknown["next"] == ["公共-通用中止"]
    assert "on_error" not in unknown


def test_shadow_runtime_alternatives_are_parent_siblings_and_fail_natively() -> None:
    nodes = load_task_nodes(SHADOW)

    assert nodes["影之遗迹-页面-探测"]["next"] == [
        "影之遗迹-选择-进行中",
        "MJA_SHADOW_STATUS_PROBE",
    ]
    assert nodes["影之遗迹-进入-关卡"]["next"] == [
        "MJA_SHADOW_AUTO_ROUTE_PROBE",
        "影之遗迹-战斗-门禁",
        "MJA_SHADOW_RECOMMENDED_PROBE",
        "影之遗迹-关卡-探测",
        "影之遗迹-探索-页面",
    ]
    assert nodes["影之遗迹-关卡-探测"]["next"] == [
        "MJA_SHADOW_AUTO_ROUTE_PROBE",
        "MJA_SHADOW_RECOMMENDED_PROBE",
        "影之遗迹-战斗-门禁",
        "影之遗迹-前台-左",
        "影之遗迹-探索-页面",
    ]


def test_shadow_active_card_selection_uses_live_card_status_not_stale_challenge_roi() -> None:
    nodes = load_task_nodes(SHADOW)
    select = nodes["影之遗迹-选择-进行中"]
    assert select["recognition"] == {
        "type": "And",
        "param": {"all_of": ["影之遗迹-影-页面", "影之遗迹-影-进行中"], "box_index": 1},
    }
    assert select["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "影之遗迹-影-页面",
        "target_name": "影之遗迹-影-进行中",
    }
    assert nodes["影之遗迹-探索-页面"]["next"] == [
        "影之遗迹-战斗-结果-探测",
        "影之遗迹-战斗-中-进度-等待",
        "影之遗迹-奖励-探测",
        "影之遗迹-前台-门禁",
        "影之遗迹-战斗-门禁",
        "影之遗迹-最终-探测",
        "影之遗迹-黑屏-冻结-恢复",
    ]
    assert nodes["影之遗迹-战斗-结果-探测"]["next"] == [
        "影之遗迹-战斗-结果-胜利",
        "影之遗迹-战斗-结果-失败",
    ]
    assert nodes["影之遗迹-战斗-门禁"]["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-战斗-页面",
        "shadow.battle.target",
    ]
    assert nodes["影之遗迹-战斗-循环"]["custom_action_param"]["evidence"][
        "page_name"
    ] == "影之遗迹-影-战斗-页面"
    assert nodes["影之遗迹-战斗-结果-探测"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-战斗-结果-页面"]
    assert nodes["影之遗迹-战斗-结果-胜利"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-战斗-结果-页面", "影之遗迹-影-战斗-胜利"]
    assert nodes["影之遗迹-战斗-结果-胜利"]["custom_action_param"][
        "fixed_click_mode"
    ] == "shadow_result_blank"
    assert nodes["影之遗迹-战斗-结果-胜利"]["next"] == [
        "影之遗迹-领取-胜利-宝箱-首个"
    ]
    assert nodes["影之遗迹-战斗-结果-胜利"]["timeout"] == 50000
    first_claim = nodes["影之遗迹-领取-胜利-宝箱-首个"]
    retry_claim = nodes["影之遗迹-领取-胜利-宝箱-重试"]
    for claim in (first_claim, retry_claim):
        assert claim["recognition"]["param"]["all_of"] == [
            "影之遗迹-影-探索-页面",
            "影之遗迹-影-前台-就绪",
        ]
        assert claim["custom_action"] == "GuardedInput"
        assert claim["custom_action_param"]["fixed_click_boxes"] == [
            [436, 536, 24, 24],
            [629, 536, 24, 24],
            [822, 536, 24, 24],
        ]
        assert claim["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": "影之遗迹-影-探索-页面",
            "target_name": "影之遗迹-影-前台-就绪",
        }
        assert claim["max_hit"] == nodes["影之遗迹-战斗-循环"]["max_hit"]
        assert claim["retry_times"] == 0
        assert claim["timeout"] == 50000
    assert first_claim["next"] == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-领取-胜利-宝箱-重试",
    ]
    assert first_claim["on_error"] == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-记录-失败",
    ]
    assert retry_claim["next"] == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-胜利-宝箱-之后-重试-等待",
    ]
    assert retry_claim["on_error"] == retry_claim["next"]
    post_retry_wait = nodes["影之遗迹-胜利-宝箱-之后-重试-等待"]
    assert post_retry_wait["recognition"] == "DirectHit"
    assert post_retry_wait["action"] == "DoNothing"
    assert post_retry_wait["post_delay"] == 1000
    assert post_retry_wait["max_hit"] == nodes["影之遗迹-战斗-循环"]["max_hit"]
    assert post_retry_wait["next"] == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-记录-失败",
    ]
    assert post_retry_wait["on_error"] == ["影之遗迹-记录-失败"]
    assert nodes["影之遗迹-奖励-探测"]["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-奖励-关闭"
    ]
    assert nodes["影之遗迹-奖励-探测"]["on_error"] == [
        "影之遗迹-奖励-等待"
    ]
    wait = nodes["影之遗迹-奖励-等待"]
    assert wait["recognition"] == "DirectHit"
    assert wait["post_delay"] == 1000
    assert wait["max_hit"] == 35
    assert wait["next"] == ["影之遗迹-奖励-探测"]
    assert wait["on_error"] == ["影之遗迹-记录-失败"]
    assert nodes["影之遗迹-关闭-奖励"]["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-奖励",
        "影之遗迹-影-奖励-关闭",
    ]
    assert nodes["影之遗迹-关闭-奖励"]["custom_action_param"][
        "fixed_click_mode"
    ] == "shadow_reward_blank"
    assert nodes["影之遗迹-关闭-奖励"]["post_delay"] == 750
    assert nodes["影之遗迹-确认-完成"]["next"] == [
        "影之遗迹-最终-奖励-探测"
    ]
    assert nodes["影之遗迹-确认-完成"]["timeout"] == 50000
    final_reward_probe = nodes["影之遗迹-最终-奖励-探测"]
    assert final_reward_probe["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-奖励-关闭"
    ]
    assert final_reward_probe["next"] == ["影之遗迹-最终-关闭-奖励"]
    assert final_reward_probe["on_error"] == ["MJA_SHADOW_DONE_PROBE"]
    assert final_reward_probe["timeout"] == 50000
    final_reward_dismiss = nodes["影之遗迹-最终-关闭-奖励"]
    assert final_reward_dismiss["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-奖励",
        "影之遗迹-影-奖励-关闭",
    ]
    assert final_reward_dismiss["custom_action_param"]["fixed_click_mode"] == (
        "shadow_reward_blank"
    )
    assert final_reward_dismiss["next"] == ["MJA_SHADOW_DONE_PROBE"]
    assert final_reward_dismiss["post_delay"] == 750
    assert nodes["MJA_SHADOW_DONE_PROBE"]["on_error"] == [
        "影之遗迹-主页边界-探测"
    ]
    assert nodes["影之遗迹-战斗-结果-失败"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-战斗-结果-页面", "影之遗迹-影-战斗-失败"]

    failed_nodes = [
        node
        for node in nodes.values()
        if node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id") == SHADOW.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    ]
    assert failed_nodes
    for node in failed_nodes:
        assert node["custom_action_param"]["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["公共-通用中止"]
        assert "on_error" not in node


def test_shadow_transfer_gate_uses_live_exploration_button_not_confirm_roi() -> None:
    nodes = load_task_nodes(SHADOW)
    transfer_gate = nodes["MJA_SHADOW_TRANSFER_GATE"]
    transfer_loop = nodes["MJA_SHADOW_TRANSFER_LOOP"]
    assert transfer_gate["recognition"] == {
        "type": "And",
        "param": {"all_of": ["影之遗迹-影-探索-页面", "shadow.transfer.entry"]},
    }
    assert transfer_loop["recognition"] == {
        "type": "And",
        "param": {"all_of": ["影之遗迹-影-探索-页面", "shadow.transfer.entry"]},
    }
    assert transfer_loop["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "影之遗迹-影-探索-页面",
        "target_name": "shadow.transfer.entry",
    }
    assert nodes["shadow.transfer.entry"] == {
        "recognition": "OCR",
        "expected": "^传送$",
        "roi": [900, 570, 260, 150],
        "action": "DoNothing",
    }
    assert nodes["影之遗迹-前台-门禁"]["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-探索-页面",
        "影之遗迹-影-前台-就绪",
    ]
    assert nodes["影之遗迹-前台-循环"]["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-探索-页面",
        "影之遗迹-影-前台-就绪",
    ]
    assert nodes["影之遗迹-前台-循环"]["custom_action_param"][
        "fixed_click_boxes"
    ] == [[436, 536, 24, 24], [629, 536, 24, 24], [822, 536, 24, 24]]
    assert nodes["影之遗迹-前台-循环"]["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "影之遗迹-影-探索-页面",
        "target_name": "影之遗迹-影-前台-就绪",
    }
    assert nodes["影之遗迹-影-前台-就绪"] == {
        "recognition": "OCR",
        "expected": "^第.+层$",
        "roi": [1000, 40, 220, 120],
        "action": "DoNothing",
    }
    assert nodes["影之遗迹-前台-循环"]["on_error"] == [
        "MJA_SHADOW_TRANSFER_GATE",
        "影之遗迹-前台-循环-耗尽",
    ]
    assert nodes["shadow.transfer"]["roi"] == [300, 540, 320, 180]


def test_shadow_stage_entry_clicks_the_entry_target_box() -> None:
    nodes = load_task_nodes(SHADOW)
    assert nodes["影之遗迹-进入-关卡"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["影之遗迹-影-页面", "影之遗迹-影-关卡-入口"],
            "box_index": 1,
        },
    }
    assert nodes["影之遗迹-进入-关卡"]["custom_action_param"][
        "fixed_click_mode"
    ] == "shadow_stage_entry_button"


def test_martial_study_only_claims_successful_breakthroughs() -> None:
    nodes = load_task_nodes(MARTIAL)
    assert_guarded_actions(
        nodes,
        MARTIAL.task_id,
        [
            "open_function_panel",
            "open_martial_study",
            "claim_success_card",
            "close_reward_popup",
            "close_martial_page",
        ],
    )
    assert_terminal_after_loop(nodes, "武学突破-领取-循环", 3, "MARTIAL_CLAIM_LIMIT")
    assert_outcome(
        nodes,
        "武学突破-成功-无-领取",
        "success",
        "martial.successful_breakthroughs_claimed_or_none",
    )
    assert nodes["武学突破-页面-探测"]["next"] == [
        "武学突破-领取-门禁",
        "武学突破-无-成功-突破",
    ]
    forbidden = (
        "open_martial_plus_slot",
        "study_martial_slot",
        "breakthrough_martial_slot",
        "confirm_martial_breakthrough",
    )
    assert not any(
        any(marker in str(node) for marker in forbidden)
        for node in nodes.values()
        if node.get("custom_action_param", {}).get("task_id") == MARTIAL.task_id
    )
    assert dict(TASK_POLICIES[MARTIAL.task_id].action_caps) == {
        "open_function_panel": 1,
        "open_martial_study": 1,
        "claim_success_card": 3,
        "close_reward_popup": 3,
        "close_martial_page": 1,
    }


def test_dungeon_sweep_separates_ticket_resource_and_action_limits() -> None:
    nodes = load_task_nodes(DUNGEON)
    assert_guarded_actions(
        nodes,
        DUNGEON.task_id,
        [
            "close_function_panel",
            "open_dungeon",
            "scroll_dungeon_list",
            "select_yanwangling",
            "open_sweep_panel",
            "select_yanwangling_in_panel",
            "close_dungeon_reward_preview",
            "assign_sweep_ticket",
            "start_yanwangling_master_sweep",
            "confirm_yanwangling_master_sweep",
            "dismiss_sweep_result",
            "close_dungeon",
        ],
    )
    assert_action_limit(DUNGEON.task_id, "scroll_dungeon_list", 4)
    assert_action_limit(DUNGEON.task_id, "assign_sweep_ticket", 100)
    assert_resource_guard(
        nodes,
        "assign_sweep_ticket",
        "副本票",
        20,
        task_id=DUNGEON.task_id,
        require_observed_amount=False,
    )
    assert_action_limit(DUNGEON.task_id, "start_yanwangling_master_sweep", 1)
    assert_no_side_effect_retry(nodes, "assign_sweep_ticket")
    assert_no_side_effect_retry(nodes, "start_yanwangling_master_sweep")
    assert_outcome(
        nodes,
        "副本扫荡-无-券",
        "not_eligible",
        "dungeon.ticket_unavailable",
    )


def test_dungeon_sweep_has_explicit_failure_and_business_success_postconditions() -> None:
    nodes = load_task_nodes(DUNGEON)

    assert nodes["副本扫荡-打开-扫荡"]["next"][0] == "副本扫荡-背包-已满-探测"
    assert nodes["副本扫荡-打开-扫荡"]["on_error"][0] == (
        "副本扫荡-扫荡-不可用-探测"
    )
    assert nodes["副本扫荡-副本-扫荡-目标"]["expected"] == ["扫荡", "未解锁扫荡"]
    assert nodes["副本扫荡-副本-扫荡-不可用-提示"]["expected"] == [
        "已完成极境模式",
        "未解锁扫荡",
        "累计通关6次可解锁该难度扫荡功能",
        "前往开通",
    ]
    assert_outcome(
        nodes,
        "副本扫荡-扫荡-不可用",
        "not_eligible",
        "dungeon.sweep_unavailable",
    )
    assert_outcome(nodes, "副本扫荡-背包-已满", "failed", "dungeon.inventory_full")
    assert nodes["副本扫荡-背包-已满"]["custom_action_param"]["error_code"] == "DUNGEON_BAG_FULL"
    assert nodes["副本扫荡-背包-已满"]["Abort"] is True

    bag_full = nodes["副本扫荡-副本-背包-已满"]
    assert bag_full["recognition"] == "OCR"
    assert "背包已满" in bag_full["expected"]

    result = nodes["副本扫荡-副本-结果"]
    assert result["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-结果-面板-界面",
        "副本扫荡-副本-结果-面板-徽标",
    ]
    assert "expected" not in result
    assert nodes["副本扫荡-结果-探测"]["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-结果",
        "副本扫荡-副本-结果-关闭",
    ]

    post = nodes["MJA_DUNGEON_POST_PROBE"]
    assert post["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-页面",
        "dungeon.ticket.depleted",
    ]
    assert post["next"] == ["副本扫荡-成功"]
    assert_outcome(
        nodes,
        "副本扫荡-成功",
        "success",
        "dungeon.reward_popup_seen_and_ticket_count_zero",
    )
    assert nodes["副本扫荡-成功"]["next"] == ["副本扫荡-关闭"]
    assert nodes["副本扫荡-成功"]["timeout"] == 8000
    assert nodes["副本扫荡-成功"]["on_error"] == ["公共-通用停止"]
    assert nodes["副本扫荡-无-券"]["next"] == ["副本扫荡-关闭"]
    assert nodes["副本扫荡-无-券"]["timeout"] == 8000
    assert nodes["副本扫荡-无-券"]["on_error"] == ["公共-通用停止"]
    assert nodes["副本扫荡-关闭"]["timeout"] == 8000
    assert nodes["副本扫荡-关闭"]["next"] == ["副本扫荡-退出-主页-探测"]
    assert nodes["副本扫荡-关闭"]["on_error"] == ["公共-通用停止"]
    assert nodes["副本扫荡-退出-主页-探测"]["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-主页"
    ]
    assert nodes["副本扫荡-退出-主页-探测"]["next"] == ["公共-通用停止"]


def test_dungeon_result_page_uses_exact_visual_panel_and_close_text_same_frame() -> None:
    nodes = load_task_nodes(DUNGEON)

    surface = nodes["副本扫荡-副本-结果-面板-界面"]
    assert surface == {
        "recognition": "ColorMatch",
        "lower": [205, 180, 135],
        "upper": [255, 255, 245],
        "roi": [235, 245, 1000, 220],
        "connected": True,
        "count": 90000,
        "action": "DoNothing",
    }
    badge = nodes["副本扫荡-副本-结果-面板-徽标"]
    assert badge == {
        "recognition": "ColorMatch",
        "lower": [210, 75, 15],
        "upper": [255, 165, 90],
        "roi": [165, 205, 65, 300],
        "connected": True,
        "count": 8000,
        "action": "DoNothing",
    }
    close = nodes["副本扫荡-副本-结果-关闭"]
    assert close == {
        "recognition": "OCR",
        "expected": "点击空白处关闭",
        "roi": [350, 580, 600, 140],
        "action": "DoNothing",
    }

    same_frame = ["副本扫荡-副本-结果", "副本扫荡-副本-结果-关闭"]
    assert nodes["副本扫荡-结果-探测"]["recognition"]["param"]["all_of"] == same_frame
    dismiss = nodes["副本扫荡-关闭-结果"]
    assert dismiss["recognition"]["param"]["all_of"] == same_frame
    assert dismiss["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "副本扫荡-副本-结果",
        "target_name": "副本扫荡-副本-结果-关闭",
    }
    assert dismiss["retry_times"] == 0

    android_nodes = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily/dungeon_sweep_daily.json").read_text(
            encoding="utf-8"
        )
    )
    assert android_nodes["result_panel_surface"] == surface
    assert android_nodes["result_panel_badge"] == badge
    assert android_nodes["result_close"] == close


def test_dungeon_sweep_panel_requires_exact_sweep_text_and_yanwangling_card() -> None:
    nodes = load_task_nodes(DUNGEON)

    expected_button_text = ["开始扫荡", "开始扫"]
    panel = nodes["副本扫荡-副本-扫荡-面板"]
    assert panel["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "副本扫荡-副本-扫荡-按钮",
                "dungeon.sweep.yanwangling.card",
            ]
        },
    }
    assert nodes["副本扫荡-副本-扫荡-按钮"]["expected"] == expected_button_text
    assert nodes["副本扫荡-副本-开始"]["expected"] == expected_button_text
    assert "开始" not in expected_button_text

    card = nodes["dungeon.sweep.yanwangling.card"]
    assert card["expected"] == ["燕王秘陵", "燕王"]
    assert card["roi"] == [880, 240, 400, 100]

    select = nodes["副本扫荡-选择-面板-阎王"]
    assert select["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-扫荡-面板",
        "dungeon.sweep.yanwangling.card",
    ]
    assert select["custom_action_param"]["evidence"]["target_name"] == (
        "dungeon.sweep.yanwangling.card"
    )


def test_dungeon_direct_plus_is_scoped_to_live_yanwangling_master_controls() -> None:
    nodes = load_task_nodes(DUNGEON)

    master = nodes["副本扫荡-副本-宗师-80"]
    assert master["recognition"] == "OCR"
    assert master["expected"] == r"大师\s*80级?"
    assert master["roi"] == [900, 370, 210, 100]

    # r13 matched the adjacent 黑刹教 row at (529, 403, 133, 27). The live
    # 燕王秘陵 master row starts near x=918, so its ROI must not cross cards.
    x, y, width, height = master["roi"]
    adjacent_right = 529 + 133
    target_center = (984, 416)
    assert x > adjacent_right
    assert x <= target_center[0] < x + width
    assert y <= target_center[1] < y + height
    assert x + width <= 1110

    assert "MJA_DUNGEON_SELECT_MASTER" not in nodes
    assert "select_master_80" not in TASK_POLICIES[DUNGEON.task_id].action_caps
    ready = nodes["副本扫荡-宗师-分配任务-就绪"]
    assert ready["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-扫荡-面板",
        "dungeon.sweep.yanwangling.card",
        "副本扫荡-副本-宗师-80",
        "副本扫荡-副本-券-加号",
        "副本扫荡-副本-券-图标",
        "副本扫荡-副本-券-余额",
    ]
    assert ready["action"] == "DoNothing"
    assert ready["next"] == ["副本扫荡-分配-券-循环"]

    plus = nodes["副本扫荡-副本-券-加号"]
    assert plus == {
        "recognition": "ColorMatch",
        "lower": [85, 80, 60],
        "upper": [255, 255, 230],
        "roi": [1228, 400, 40, 40],
        "connected": True,
        "count": 40,
        "action": "DoNothing",
    }
    assert "expected" not in plus
    android_nodes = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/dungeon_sweep_daily.json"
        ).read_text(encoding="utf-8")
    )
    assert android_nodes["ticket_plus"] == plus

    icon = nodes["副本扫荡-副本-券-图标"]
    # r17 live scores were 0.652958-0.662200 in this exact ROI. Keep enough
    # margin for the observed frame variance without broadening the search area.
    assert icon == {
        "recognition": "TemplateMatch",
        "template": "daily/DUNGEON_SWEEP_DAILY/ticket_icon.png",
        "roi": [770, 510, 95, 75],
        "threshold": 0.32,
        "action": "DoNothing",
    }
    assert android_nodes["ticket_icon"] == icon
    balance = nodes["副本扫荡-副本-券-余额"]
    assert balance["expected"] == r"^(?:[1-9]|1[0-9]|20)$"
    assert balance["roi"] == [840, 520, 90, 70]
    assert 840 <= 862 < 840 + 90
    assert 520 <= 550 < 520 + 70
    assert android_nodes["ticket_balance"] == balance

    assign = nodes["副本扫荡-分配-券-循环"]
    assert assign["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-扫荡-面板",
        "dungeon.sweep.yanwangling.card",
        "副本扫荡-副本-宗师-80",
        "副本扫荡-副本-券-加号",
        "副本扫荡-副本-券-图标",
        "副本扫荡-副本-券-余额",
    ]
    assert assign["recognition"]["param"]["box_index"] == 3
    assert assign["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 3,
        "page_name": "副本扫荡-副本-扫荡-面板",
        "target_name": "副本扫荡-副本-券-加号",
    }
    assert assign["custom_action_param"]["resource_index"] == 4
    assert assign["custom_action_param"]["resource_evidence_name"] == (
        "副本扫荡-副本-券-图标"
    )
    assert assign["custom_action_param"]["amount_index"] == 5
    assert assign["max_hit"] == 100
    assert assign["retry_times"] == 0
    assert TASK_POLICIES[DUNGEON.task_id].action_caps["assign_sweep_ticket"] == 100


def test_dungeon_sweep_recovers_once_from_launcher_then_requires_home() -> None:
    nodes = load_task_nodes(DUNGEON)

    start = nodes["副本扫荡-任务入口"]
    assert start["timeout"] == 8000
    assert start["next"] == [
        "副本扫荡-面板-探测",
        "副本扫荡-奖励-预览-恢复-探测",
        "副本扫荡-影-页面-探测",
        "副本扫荡-主页-探测",
    ]
    assert start["on_error"] == [
        "副本扫荡-游戏启动恢复",
        "副本扫荡-游戏启动恢复失败",
    ]
    recovery_probe = nodes["副本扫荡-奖励-预览-恢复-探测"]
    assert recovery_probe["recognition"] == {
        "type": "Or",
        "param": {
            "any_of": ["副本扫荡-副本-奖励-预览-页面", "吃体力食物-食物-食物-页面"]
        },
    }

    recovery = nodes["副本扫荡-游戏启动恢复"]
    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "DoNothing"
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 30000
    assert recovery["next"] == [
        "副本扫荡-面板-探测",
        "副本扫荡-奖励-预览-恢复-探测",
        "副本扫荡-影-页面-探测",
        "副本扫荡-主页-探测",
    ]
    assert recovery["on_error"] == ["副本扫荡-游戏启动恢复失败"]

    assert_outcome(
        nodes,
        "副本扫荡-游戏启动恢复失败",
        "failed",
        "dungeon.game_foreground_and_home",
    )
    failed = nodes["副本扫荡-游戏启动恢复失败"]
    assert failed["custom_action_param"]["error_code"] == (
        "DUNGEON_GAME_START_RECOVERY_EXHAUSTED"
    )
    assert failed["custom_action_param"]["native_fail_after_record"] is True
    assert failed["Abort"] is True
    assert failed["next"] == ["公共-通用中止"]
    assert nodes["副本扫荡-主页-探测"]["on_error"] == [
        "副本扫荡-游戏启动恢复",
        "副本扫荡-记录-失败",
    ]


def test_dungeon_shadow_page_is_known_fail_closed_start_state() -> None:
    nodes = load_task_nodes(DUNGEON)

    marker = nodes["副本扫荡-副本-影-页面"]
    assert marker == {
        "recognition": "OCR",
        "expected": "蜃影武墟",
        "roi": [0, 0, 1280, 720],
        "action": "DoNothing",
    }
    _assert_archived_ocr_hit(marker, "蜃影武墟", (326, 389, 282, 83))

    probe = nodes["副本扫荡-影-页面-探测"]
    assert probe["recognition"] == {
        "type": "And",
        "param": {"all_of": ["副本扫荡-副本-影-页面"]},
    }
    assert probe["action"] == "DoNothing"
    assert probe["next"] == ["副本扫荡-意外-影-页面"]
    assert probe["on_error"] == ["副本扫荡-记录-失败"]

    failure = nodes["副本扫荡-意外-影-页面"]
    assert_outcome(
        nodes,
        "副本扫荡-意外-影-页面",
        "failed",
        "dungeon.state_known",
    )
    assert failure["custom_action_param"]["error_code"] == (
        "DUNGEON_UNEXPECTED_SHADOW_PAGE"
    )
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
    assert "on_error" not in failure


def test_dungeon_reward_preview_recovery_is_exact_bounded_and_fail_closed() -> None:
    nodes = load_task_nodes(DUNGEON)

    page = nodes["副本扫荡-副本-奖励-预览-页面"]
    assert page["recognition"]["param"]["all_of"] == [
        "副本扫荡-副本-奖励-预览-标题",
        "副本扫荡-副本-奖励-预览-正文",
    ]
    assert nodes["副本扫荡-副本-奖励-预览-标题"]["roi"] == [400, 250, 500, 75]
    assert nodes["副本扫荡-副本-奖励-预览-正文"]["expected"] == "概率获得以下奖励"
    assert nodes["副本扫荡-副本-奖励-预览-关闭"]["roi"] == [840, 255, 55, 55]

    close = nodes["副本扫荡-关闭-奖励-预览"]
    assert close["max_hit"] == 1
    assert close["retry_times"] == 0
    assert close["custom_action_param"]["action_id"] == (
        "close_dungeon_reward_preview"
    )
    assert close["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "副本扫荡-副本-奖励-预览-页面",
        "target_name": "副本扫荡-副本-奖励-预览-关闭",
    }
    assert close["on_error"] == ["副本扫荡-记录-失败"]
    recovered = nodes["副本扫荡-奖励-预览-已恢复-面板"]
    assert recovered["next"] == ["副本扫荡-分配-券-循环"]
    assert recovered["on_error"] == ["副本扫荡-记录-失败"]
    assert_action_limit(DUNGEON.task_id, "close_dungeon_reward_preview", 1)


def test_dungeon_recovery_never_replays_consumptive_actions() -> None:
    nodes = load_task_nodes(DUNGEON)
    recovery_nodes = {
        "副本扫荡-游戏启动恢复",
        "副本扫荡-游戏启动恢复失败",
        "副本扫荡-面板-探测",
        "副本扫荡-面板-关闭",
        "副本扫荡-影-页面-探测",
        "副本扫荡-意外-影-页面",
        "副本扫荡-奖励-预览-恢复-探测",
        "副本扫荡-关闭-奖励-预览",
        "副本扫荡-奖励-预览-已恢复-面板",
    }
    dangerous_action_nodes = {
        "副本扫荡-分配-券-循环",
        "副本扫荡-开始-扫荡",
        "副本扫荡-确认-扫荡",
    }

    for node_name in dangerous_action_nodes:
        routes = set(nodes[node_name].get("next", [])) | set(
            nodes[node_name].get("on_error", [])
        )
        assert routes.isdisjoint(recovery_nodes)

    assert nodes["副本扫荡-游戏启动恢复"]["next"] == [
        "副本扫荡-面板-探测",
        "副本扫荡-奖励-预览-恢复-探测",
        "副本扫荡-影-页面-探测",
        "副本扫荡-主页-探测",
    ]


def test_dungeon_ticket_guard_is_dynamic_but_positive_and_budgeted() -> None:
    params = load_task_nodes(DUNGEON)["副本扫荡-分配-券-循环"][
        "custom_action_param"
    ]
    assert "observed_amount" not in params
    assert params["resource_id"] == "副本票"
    assert params["budget_amount"] == 1
    assert "[1-9]" in load_task_nodes(DUNGEON)["副本扫荡-副本-券-余额"]["expected"]


def test_ring_challenge_partitions_sweep_fight_and_not_open() -> None:
    nodes = load_task_nodes(RING)
    assert nodes["擂台挑战-擂台-日常-页面"]["roi"] == [0, 0, 520, 180]
    assert nodes["擂台挑战-日常-页面"]["next"] == [
        "擂台挑战-日常-奖励-探测",
        "擂台挑战-打开",
    ]
    assert nodes["擂台挑战-擂台-入口"] == {
        "recognition": "OCR",
        "expected": "^前往$",
        "roi": [1000, 510, 180, 100],
        "action": "DoNothing",
    }
    assert nodes["擂台挑战-页面-探测"]["next"] == [
        "MJA_RING_NOT_OPEN_PROBE",
        "擂台挑战-次数-探测",
        "擂台挑战-打开-模式",
    ]
    assert nodes["擂台挑战-打开-模式"]["next"] == [
        "擂台挑战-扫荡-符合条件",
        "擂台挑战-扫荡-分数-符合条件",
        "擂台挑战-战斗-耗尽-探测",
        "擂台挑战-战斗-门禁",
        "擂台挑战-匹配-门禁",
    ]
    assert_guarded_actions(
        nodes,
        RING.task_id,
        [
            "open_function_panel",
            "open_daily_tasks",
            "open_ring_challenge",
            "close_reward_popup",
            "open_ring_attempt_mode",
            "fight_ring_opponent",
            "start_ring_matching",
            "start_ring_battle",
            "wait_ring_battle",
            "skip_ring_battle",
            "sweep_ring",
            "confirm_ring_sweep",
            "dismiss_ring_result",
            "close_ring_opponents",
            "close_ring_page",
        ],
    )
    assert_condition(nodes, "擂台挑战-扫荡-符合条件", "master_mode_or_score_gte_5000")
    assert "论剑阵容模式" not in nodes["擂台挑战-擂台-宗师-模式"]["expected"]
    assert "大师赛模式" in nodes["擂台挑战-擂台-宗师-模式"]["expected"]
    assert nodes["擂台挑战-扫荡-符合条件"]["on_error"] == [
        "擂台挑战-扫荡-分数-符合条件"
    ]
    assert nodes["擂台挑战-扫荡-分数-符合条件"]["on_error"] == [
        "擂台挑战-战斗-耗尽-探测"
    ]
    assert nodes["擂台券"]["expected"] == [
        "擂台券",
        "^[1-9][0-9]?/12$",
    ]
    assert nodes["擂台券"]["roi"] == [1000, 0, 280, 100]
    assert nodes["擂台挑战-擂台-券-数量"]["expected"] == [
        "^[1-9][0-9]?$",
        "^[1-9][0-9]?/12$",
    ]
    assert_resource_guard(
        nodes,
        "sweep_ring",
        "擂台券",
        12,
        task_id=RING.task_id,
        require_observed_amount=False,
    )
    assert_resource_guard(
        nodes,
        "fight_ring_opponent",
        "擂台券",
        12,
        task_id=RING.task_id,
        require_observed_amount=False,
    )
    assert_resource_guard(
        nodes,
        "start_ring_matching",
        "擂台券",
        12,
        task_id=RING.task_id,
        require_observed_amount=False,
    )
    expected_battle_entry = [
        "擂台挑战-匹配中-加载-探测",
        "擂台挑战-战斗-准备",
        "擂台挑战-战斗-页面",
        "擂台挑战-战斗-加载-探测",
    ]
    assert nodes["擂台挑战-战斗-循环"]["next"] == expected_battle_entry
    assert nodes["擂台挑战-开始-匹配中"]["next"] == expected_battle_entry
    assert nodes["擂台挑战-战斗-页面"]["on_error"] == [
        "擂台挑战-战斗-结果-探测",
        "擂台挑战-战斗-结果-失败",
        "擂台挑战-战斗-加载-探测",
    ]
    assert nodes["擂台挑战-结果后"]["next"] == [
        "擂台挑战-战斗-耗尽-探测",
        "擂台挑战-战斗-门禁",
        "擂台挑战-匹配-门禁",
    ]
    assert nodes["擂台挑战-战斗-结果-探测"]["recognition"]["param"]["all_of"] == [
        "擂台挑战-擂台-战斗-结果",
        "擂台挑战-擂台-战斗-胜利",
    ]
    assert nodes["擂台挑战-擂台-战斗-结果"]["expected"] == [
        "战斗胜利",
        "战斗胜",
        "战斗失败",
        "战斗败",
        "胜利",
        "失败",
    ]
    assert nodes["擂台挑战-擂台-战斗-胜利"]["expected"] == [
        "战斗胜利",
        "战斗胜",
        "胜利",
    ]
    assert nodes["擂台挑战-擂台-结果-关闭"]["expected"] == [
        "点击(?:空白处|任意位置)关闭",
        "擂台积分\\d+",
    ]
    assert (
        nodes["擂台挑战-战斗-准备"]["custom_action_param"]["action_id"]
        == "start_ring_battle"
    )
    assert (
        nodes["擂台挑战-战斗-加载-等待"]["custom_action_param"]["action_id"]
        == "wait_ring_battle"
    )
    assert nodes["擂台挑战-战斗-加载-等待"]["custom_action_param"]["kind"] == "none"
    assert nodes["擂台挑战-匹配-门禁"]["next"] == ["擂台挑战-开始-匹配中"]
    assert (
        nodes["擂台挑战-开始-匹配中"]["custom_action_param"]["action_id"]
        == "start_ring_matching"
    )
    assert nodes["擂台挑战-扫荡-门禁"]["on_error"] == ["擂台挑战-记录-失败"]
    assert_action_limit(RING.task_id, "sweep_ring", 1)
    assert_action_limit(RING.task_id, "skip_ring_battle", 12)
    assert nodes["擂台挑战-战斗-循环"]["max_hit"] == 12
    assert nodes["擂台挑战-战斗-循环-耗尽"]["custom_action_param"]["status"] == "success"
    assert nodes["擂台挑战-战斗-循环-耗尽"]["recognition"]["type"] == "And"
    assert "擂台挑战-擂台-次数-耗尽" in nodes["擂台挑战-战斗-循环-耗尽"][
        "recognition"
    ]["param"]["all_of"]
    assert nodes["擂台挑战-战斗-循环-耗尽"]["next"] == ["擂台挑战-关闭-对手"]
    assert nodes["擂台挑战-结果后"]["on_error"] == [
        "擂台挑战-结果后-擂台-页面-耗尽-探测"
    ]
    assert nodes["擂台挑战-结果后-擂台-页面-耗尽-探测"]["recognition"][
        "param"
    ]["all_of"] == ["擂台挑战-擂台-页面", "擂台挑战-擂台-次数-耗尽"]
    assert nodes["擂台挑战-结果后-擂台-页面-耗尽-探测"]["on_error"] == [
        "擂台挑战-结果后-擂台-页面-继续"
    ]
    assert nodes["擂台挑战-结果后-擂台-页面-继续"]["next"] == [
        "擂台挑战-打开-模式"
    ]
    assert_outcome(
        nodes,
        "擂台挑战-结果后-擂台-页面-耗尽",
        "success",
        "ring.manual_attempts_complete",
    )
    assert_outcome(
        nodes,
        "擂台挑战-战斗-循环-耗尽",
        "success",
        "ring.manual_attempts_complete",
    )
    assert_outcome(
        nodes,
        "擂台挑战-次数-耗尽",
        "success",
        "ring.attempts_exhausted",
    )
    assert_outcome(nodes, "MJA_RING_NOT_OPEN", "not_eligible", "ring.not_open")
    assert_battle_result_partition(nodes, "MJA_RING_BATTLE_RESULT")
    assert_no_side_effect_retry(nodes, "sweep_ring")
    assert_no_side_effect_retry(nodes, "fight_ring_opponent")
    assert_no_side_effect_retry(nodes, "start_ring_matching")
