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
        nodes, "MJA_SHADOW_FOREGROUND_LOOP", 40, "SHADOW_FOREGROUND_LIMIT"
    )
    assert_terminal_after_loop(nodes, "MJA_SHADOW_BATTLE_LOOP", 12, "SHADOW_BATTLE_LIMIT")
    assert nodes["MJA_SHADOW_BATTLE_LOOP"]["timeout"] == 240000
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
        "MJA_SHADOW_RECORD_SUCCESS",
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
        "MJA_SHADOW_HOME_BOUNDARY_PROBE",
        "[JumpBack]MJA_GAME_START",
    ]
    boundary_failure = nodes["MJA_SHADOW_BOUNDARY_FAILURE"]
    assert boundary_failure["custom_action_param"]["error_code"] == "SHADOW_HOME_BOUNDARY_MISSING"
    assert boundary_failure["custom_action_param"]["native_fail_after_record"] is True
    assert boundary_failure["Abort"] is True


def test_shadow_r19_adjacent_dungeon_page_fails_without_clicking_it() -> None:
    nodes = load_task_nodes(SHADOW)
    start = nodes["MJA_SHADOW_RUINS_DAILY_START"]
    assert start["next"] == [
        "[JumpBack]MJA_KNOWN_TEA_DETAIL_CLOSE",
        "[JumpBack]MJA_KNOWN_TEA_SHOP_CLOSE",
        "MJA_SHADOW_PAGE_PROBE",
        "MJA_SHADOW_PAINTING_PAGE",
        "MJA_SHADOW_DUNGEON_PAGE_PROBE",
        "MJA_SHADOW_HOME_PROBE",
    ]
    assert start["on_error"] == ["MJA_SHADOW_ENTRY_UNKNOWN"]
    open_painting = nodes["MJA_SHADOW_OPEN_PAINTING"]
    recognition = open_painting["recognition"]["param"]

    # r19 matched the broad home template and the combined OCR text
    # “副本（画卷”, but Maa returned the page box [1040, 0, 240, 110] to
    # GuardedInput.  The replacement must return only the exact 画卷 box.
    assert recognition["all_of"] == ["shadow.home.page", "shadow.painting.entry"]
    assert recognition["box_index"] == 1
    assert open_painting["retry_times"] == 0
    assert open_painting["max_hit"] == 1
    assert open_painting["next"] == [
        "MJA_SHADOW_PAINTING_PAGE",
        "MJA_SHADOW_DUNGEON_PAGE_PROBE",
        "MJA_SHADOW_HOME_RECOVERY_PROBE",
    ]
    assert nodes["shadow.home.page"] == {
        "recognition": "TemplateMatch",
        "template": "home/home_marker.png",
        "roi": [1040, 0, 240, 110],
        "threshold": 0.375,
        "action": "DoNothing",
    }
    assert nodes["shadow.home.dungeon"]["expected"] == r"^副本$"
    assert nodes["shadow.home.trial"]["expected"] == r"^试剑$"
    assert nodes["shadow.painting.entry"]["expected"] == r"^画卷$"

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
    assert failure["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failure

    # The ordinary page can still show the 画卷 navigation sibling at
    # [1116, 58, 32, 14].  It must not satisfy the true page-title ROI.
    title = nodes["shadow.painting.page.title"]
    assert not _box_is_inside(title["roi"], (1116, 58, 32, 14))


def test_shadow_r21_painting_page_uses_exact_tight_shadow_entry() -> None:
    nodes = load_task_nodes(SHADOW)

    # The same r21 frame proves a real home boundary before the input.
    _assert_archived_ocr_hit(nodes["shadow.home.dungeon"], "副本", (1058, 57, 32, 18))
    _assert_archived_ocr_hit(nodes["shadow.home.trial"], "试剑", (992, 644, 39, 18))
    _assert_archived_ocr_hit(nodes["shadow.painting.entry"], "画卷", (1115, 55, 34, 20))

    # These are the four stable r21 HERO OCR hits from the real painting page.
    _assert_archived_ocr_hit(nodes["shadow.painting.page.title"], "画卷", (92, 29, 44, 25))
    _assert_archived_ocr_hit(
        nodes["shadow.painting.page.world"], "·偃武世界", (118, 144, 115, 28)
    )
    _assert_archived_ocr_hit(nodes["shadow.painting.page.region"], "云州", (133, 244, 53, 31))
    entry = nodes["shadow.entry"]
    assert entry["expected"] == r"^蜃影武墟$"
    _assert_archived_ocr_hit(entry, "蜃影武墟", (1116, 651, 84, 22))

    # The adjacent 侠客派遣 label must be outside the tight Shadow ROI.
    assert not _box_is_inside(entry["roi"], (1006, 648, 86, 28))
    open_shadow = nodes["MJA_SHADOW_OPEN_SHADOW"]
    recognition = open_shadow["recognition"]["param"]
    assert recognition["all_of"] == ["shadow.painting.page", "shadow.entry"]
    assert recognition["box_index"] == 1
    assert open_shadow["retry_times"] == 0
    assert open_shadow["max_hit"] == 1


def test_shadow_entry_recovery_is_finite_and_unknown_is_native_failure() -> None:
    nodes = load_task_nodes(SHADOW)
    policy = TASK_POLICIES[SHADOW.task_id]

    assert nodes["MJA_SHADOW_RUINS_DAILY_START"]["custom_action"] == "BeginTask"
    assert nodes["MJA_SHADOW_PAINTING_PAGE"]["on_error"] == [
        "MJA_SHADOW_ENTRY_UNKNOWN"
    ]
    recovery = nodes["MJA_SHADOW_OPEN_PAINTING_RECOVERY"]
    assert recovery["custom_action_param"]["action_id"] == "open_painting_scroll"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["next"] == [
        "MJA_SHADOW_PAINTING_PAGE",
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
    unknown = nodes["MJA_SHADOW_ENTRY_UNKNOWN"]
    assert unknown["custom_action"] == "RecordTaskOutcome"
    assert unknown["custom_action_param"] == {
        "task_id": "SHADOW_RUINS_DAILY",
        "status": "failed",
        "error_code": "SHADOW_PAINTING_ENTRY_UNKNOWN",
        "postcondition": "shadow.painting_entry_state_known",
        "native_fail_after_record": True,
    }
    assert unknown["Abort"] is True
    assert unknown["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in unknown


def test_shadow_runtime_alternatives_are_parent_siblings_and_fail_natively() -> None:
    nodes = load_task_nodes(SHADOW)

    assert nodes["MJA_SHADOW_PAGE_PROBE"]["next"] == [
        "MJA_SHADOW_SELECT_ACTIVE",
        "MJA_SHADOW_STATUS_PROBE",
    ]
    assert nodes["MJA_SHADOW_ENTER_STAGE"]["next"] == [
        "MJA_SHADOW_AUTO_ROUTE_PROBE",
        "MJA_SHADOW_BATTLE_GATE",
        "MJA_SHADOW_RECOMMENDED_PROBE",
        "MJA_SHADOW_STAGE_PROBE",
        "MJA_SHADOW_EXPLORATION_PAGE",
    ]
    assert nodes["MJA_SHADOW_STAGE_PROBE"]["next"] == [
        "MJA_SHADOW_AUTO_ROUTE_PROBE",
        "MJA_SHADOW_RECOMMENDED_PROBE",
        "MJA_SHADOW_BATTLE_GATE",
        "MJA_SHADOW_FOREGROUND_LEFT",
        "MJA_SHADOW_EXPLORATION_PAGE",
    ]


def test_shadow_active_card_selection_uses_live_card_status_not_stale_challenge_roi() -> None:
    nodes = load_task_nodes(SHADOW)
    select = nodes["MJA_SHADOW_SELECT_ACTIVE"]
    assert select["recognition"] == {
        "type": "And",
        "param": {"all_of": ["shadow.page", "shadow.active"], "box_index": 1},
    }
    assert select["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "shadow.page",
        "target_name": "shadow.active",
    }
    assert nodes["MJA_SHADOW_EXPLORATION_PAGE"]["next"] == [
        "MJA_SHADOW_BATTLE_RESULT_PROBE",
        "MJA_SHADOW_BATTLE_IN_PROGRESS_WAIT",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_FOREGROUND_GATE",
        "MJA_SHADOW_BATTLE_GATE",
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_BLACK_FREEZE_RECOVERY",
    ]
    assert nodes["MJA_SHADOW_BATTLE_RESULT_PROBE"]["next"] == [
        "MJA_SHADOW_BATTLE_RESULT_VICTORY",
        "MJA_SHADOW_BATTLE_RESULT_DEFEAT",
    ]
    assert nodes["MJA_SHADOW_BATTLE_GATE"]["recognition"]["param"]["all_of"] == [
        "shadow.battle.page",
        "shadow.battle.target",
    ]
    assert nodes["MJA_SHADOW_BATTLE_LOOP"]["custom_action_param"]["evidence"][
        "page_name"
    ] == "shadow.battle.page"
    assert nodes["MJA_SHADOW_BATTLE_RESULT_PROBE"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.battle.result.page"]
    assert nodes["MJA_SHADOW_BATTLE_RESULT_VICTORY"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.battle.result.page", "shadow.battle.victory"]
    assert nodes["MJA_SHADOW_BATTLE_RESULT_VICTORY"]["custom_action_param"][
        "fixed_click_mode"
    ] == "shadow_result_blank"
    assert nodes["MJA_SHADOW_BATTLE_RESULT_VICTORY"]["next"] == [
        "MJA_SHADOW_CLAIM_VICTORY_CHEST_FIRST"
    ]
    assert nodes["MJA_SHADOW_BATTLE_RESULT_VICTORY"]["timeout"] == 50000
    first_claim = nodes["MJA_SHADOW_CLAIM_VICTORY_CHEST_FIRST"]
    retry_claim = nodes["MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY"]
    for claim in (first_claim, retry_claim):
        assert claim["recognition"]["param"]["all_of"] == [
            "shadow.exploration.page",
            "shadow.foreground.ready",
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
            "page_name": "shadow.exploration.page",
            "target_name": "shadow.foreground.ready",
        }
        assert claim["max_hit"] == nodes["MJA_SHADOW_BATTLE_LOOP"]["max_hit"]
        assert claim["retry_times"] == 0
        assert claim["timeout"] == 50000
    assert first_claim["next"] == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY",
    ]
    assert first_claim["on_error"] == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_RECORD_FAILURE",
    ]
    assert retry_claim["next"] == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_POST_RETRY_WAIT",
    ]
    assert retry_claim["on_error"] == retry_claim["next"]
    post_retry_wait = nodes["MJA_SHADOW_VICTORY_CHEST_POST_RETRY_WAIT"]
    assert post_retry_wait["recognition"] == "DirectHit"
    assert post_retry_wait["action"] == "DoNothing"
    assert post_retry_wait["post_delay"] == 1000
    assert post_retry_wait["max_hit"] == nodes["MJA_SHADOW_BATTLE_LOOP"]["max_hit"]
    assert post_retry_wait["next"] == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_RECORD_FAILURE",
    ]
    assert post_retry_wait["on_error"] == ["MJA_SHADOW_RECORD_FAILURE"]
    assert nodes["MJA_SHADOW_REWARD_PROBE"]["recognition"]["param"]["all_of"] == [
        "shadow.reward.close"
    ]
    assert nodes["MJA_SHADOW_REWARD_PROBE"]["on_error"] == [
        "MJA_SHADOW_REWARD_WAIT"
    ]
    wait = nodes["MJA_SHADOW_REWARD_WAIT"]
    assert wait["recognition"] == "DirectHit"
    assert wait["post_delay"] == 1000
    assert wait["max_hit"] == 35
    assert wait["next"] == ["MJA_SHADOW_REWARD_PROBE"]
    assert wait["on_error"] == ["MJA_SHADOW_RECORD_FAILURE"]
    assert nodes["MJA_SHADOW_DISMISS_REWARD"]["recognition"]["param"]["all_of"] == [
        "shadow.reward",
        "shadow.reward.close",
    ]
    assert nodes["MJA_SHADOW_DISMISS_REWARD"]["custom_action_param"][
        "fixed_click_mode"
    ] == "shadow_reward_blank"
    assert nodes["MJA_SHADOW_DISMISS_REWARD"]["post_delay"] == 750
    assert nodes["MJA_SHADOW_CONFIRM_COMPLETION"]["next"] == [
        "MJA_SHADOW_FINAL_REWARD_PROBE"
    ]
    assert nodes["MJA_SHADOW_CONFIRM_COMPLETION"]["timeout"] == 50000
    final_reward_probe = nodes["MJA_SHADOW_FINAL_REWARD_PROBE"]
    assert final_reward_probe["recognition"]["param"]["all_of"] == [
        "shadow.reward.close"
    ]
    assert final_reward_probe["next"] == ["MJA_SHADOW_FINAL_DISMISS_REWARD"]
    assert final_reward_probe["on_error"] == ["MJA_SHADOW_DONE_PROBE"]
    assert final_reward_probe["timeout"] == 50000
    final_reward_dismiss = nodes["MJA_SHADOW_FINAL_DISMISS_REWARD"]
    assert final_reward_dismiss["recognition"]["param"]["all_of"] == [
        "shadow.reward",
        "shadow.reward.close",
    ]
    assert final_reward_dismiss["custom_action_param"]["fixed_click_mode"] == (
        "shadow_reward_blank"
    )
    assert final_reward_dismiss["next"] == ["MJA_SHADOW_DONE_PROBE"]
    assert final_reward_dismiss["post_delay"] == 750
    assert nodes["MJA_SHADOW_DONE_PROBE"]["on_error"] == [
        "MJA_SHADOW_HOME_BOUNDARY_PROBE"
    ]
    assert nodes["MJA_SHADOW_BATTLE_RESULT_DEFEAT"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.battle.result.page", "shadow.battle.defeat"]

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
        assert node["next"] == ["MJA_COMMON_ABORT"]
        assert "on_error" not in node


def test_shadow_transfer_gate_uses_live_exploration_button_not_confirm_roi() -> None:
    nodes = load_task_nodes(SHADOW)
    transfer_gate = nodes["MJA_SHADOW_TRANSFER_GATE"]
    transfer_loop = nodes["MJA_SHADOW_TRANSFER_LOOP"]
    assert transfer_gate["recognition"] == {
        "type": "And",
        "param": {"all_of": ["shadow.exploration.page", "shadow.transfer.entry"]},
    }
    assert transfer_loop["recognition"] == {
        "type": "And",
        "param": {"all_of": ["shadow.exploration.page", "shadow.transfer.entry"]},
    }
    assert transfer_loop["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "shadow.exploration.page",
        "target_name": "shadow.transfer.entry",
    }
    assert nodes["shadow.transfer.entry"] == {
        "recognition": "OCR",
        "expected": "^传送$",
        "roi": [900, 570, 260, 150],
        "action": "DoNothing",
    }
    assert nodes["MJA_SHADOW_FOREGROUND_GATE"]["recognition"]["param"]["all_of"] == [
        "shadow.exploration.page",
        "shadow.foreground.ready",
    ]
    assert nodes["MJA_SHADOW_FOREGROUND_LOOP"]["recognition"]["param"]["all_of"] == [
        "shadow.exploration.page",
        "shadow.foreground.ready",
    ]
    assert nodes["MJA_SHADOW_FOREGROUND_LOOP"]["custom_action_param"][
        "fixed_click_boxes"
    ] == [[436, 536, 24, 24], [629, 536, 24, 24], [822, 536, 24, 24]]
    assert nodes["MJA_SHADOW_FOREGROUND_LOOP"]["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "shadow.exploration.page",
        "target_name": "shadow.foreground.ready",
    }
    assert nodes["shadow.foreground.ready"] == {
        "recognition": "OCR",
        "expected": "^第.+层$",
        "roi": [1000, 40, 220, 120],
        "action": "DoNothing",
    }
    assert nodes["MJA_SHADOW_FOREGROUND_LOOP"]["on_error"] == [
        "MJA_SHADOW_TRANSFER_GATE",
        "MJA_SHADOW_FOREGROUND_LOOP_EXHAUSTED",
    ]
    assert nodes["shadow.transfer"]["roi"] == [300, 540, 320, 180]


def test_shadow_stage_entry_clicks_the_entry_target_box() -> None:
    nodes = load_task_nodes(SHADOW)
    assert nodes["MJA_SHADOW_ENTER_STAGE"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["shadow.page", "shadow.stage_entry"],
            "box_index": 1,
        },
    }
    assert nodes["MJA_SHADOW_ENTER_STAGE"]["custom_action_param"][
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
    assert_terminal_after_loop(nodes, "MJA_MARTIAL_CLAIM_LOOP", 3, "MARTIAL_CLAIM_LIMIT")
    assert_outcome(
        nodes,
        "MJA_MARTIAL_SUCCESS_NO_CLAIM",
        "success",
        "martial.successful_breakthroughs_claimed_or_none",
    )
    assert nodes["MJA_MARTIAL_PAGE_PROBE"]["next"] == [
        "MJA_MARTIAL_CLAIM_GATE",
        "MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH",
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
        "MJA_DUNGEON_NO_TICKET",
        "not_eligible",
        "dungeon.ticket_unavailable",
    )


def test_dungeon_sweep_has_explicit_failure_and_business_success_postconditions() -> None:
    nodes = load_task_nodes(DUNGEON)

    assert nodes["MJA_DUNGEON_OPEN_SWEEP"]["next"][0] == "MJA_DUNGEON_BAG_FULL_PROBE"
    assert nodes["MJA_DUNGEON_OPEN_SWEEP"]["on_error"][0] == (
        "MJA_DUNGEON_SWEEP_UNAVAILABLE_PROBE"
    )
    assert nodes["dungeon.sweep.target"]["expected"] == ["扫荡", "未解锁扫荡"]
    assert nodes["dungeon.sweep.unavailable_hint"]["expected"] == [
        "已完成极境模式",
        "未解锁扫荡",
        "累计通关6次可解锁该难度扫荡功能",
        "前往开通",
    ]
    assert_outcome(
        nodes,
        "MJA_DUNGEON_SWEEP_UNAVAILABLE",
        "not_eligible",
        "dungeon.sweep_unavailable",
    )
    assert_outcome(nodes, "MJA_DUNGEON_BAG_FULL", "failed", "dungeon.inventory_full")
    assert nodes["MJA_DUNGEON_BAG_FULL"]["custom_action_param"]["error_code"] == "DUNGEON_BAG_FULL"
    assert nodes["MJA_DUNGEON_BAG_FULL"]["Abort"] is True

    bag_full = nodes["dungeon.bag.full"]
    assert bag_full["recognition"] == "OCR"
    assert "背包已满" in bag_full["expected"]

    result = nodes["dungeon.result"]
    assert result["recognition"]["param"]["all_of"] == [
        "dungeon.result.panel.surface",
        "dungeon.result.panel.badge",
    ]
    assert "expected" not in result
    assert nodes["MJA_DUNGEON_RESULT_PROBE"]["recognition"]["param"]["all_of"] == [
        "dungeon.result",
        "dungeon.result.close",
    ]

    post = nodes["MJA_DUNGEON_POST_PROBE"]
    assert post["recognition"]["param"]["all_of"] == [
        "dungeon.page",
        "dungeon.ticket.depleted",
    ]
    assert post["next"] == ["MJA_DUNGEON_SUCCESS"]
    assert_outcome(
        nodes,
        "MJA_DUNGEON_SUCCESS",
        "success",
        "dungeon.reward_popup_seen_and_ticket_count_zero",
    )
    assert nodes["MJA_DUNGEON_SUCCESS"]["next"] == ["MJA_DUNGEON_CLOSE"]
    assert nodes["MJA_DUNGEON_SUCCESS"]["timeout"] == 8000
    assert nodes["MJA_DUNGEON_SUCCESS"]["on_error"] == ["MJA_COMMON_STOP"]
    assert nodes["MJA_DUNGEON_NO_TICKET"]["next"] == ["MJA_DUNGEON_CLOSE"]
    assert nodes["MJA_DUNGEON_NO_TICKET"]["timeout"] == 8000
    assert nodes["MJA_DUNGEON_NO_TICKET"]["on_error"] == ["MJA_COMMON_STOP"]
    assert nodes["MJA_DUNGEON_CLOSE"]["timeout"] == 8000
    assert nodes["MJA_DUNGEON_CLOSE"]["next"] == ["MJA_DUNGEON_EXIT_HOME_PROBE"]
    assert nodes["MJA_DUNGEON_CLOSE"]["on_error"] == ["MJA_COMMON_STOP"]
    assert nodes["MJA_DUNGEON_EXIT_HOME_PROBE"]["recognition"]["param"]["all_of"] == [
        "dungeon.home"
    ]
    assert nodes["MJA_DUNGEON_EXIT_HOME_PROBE"]["next"] == ["MJA_COMMON_STOP"]


def test_dungeon_result_page_uses_exact_visual_panel_and_close_text_same_frame() -> None:
    nodes = load_task_nodes(DUNGEON)

    surface = nodes["dungeon.result.panel.surface"]
    assert surface == {
        "recognition": "ColorMatch",
        "lower": [205, 180, 135],
        "upper": [255, 255, 245],
        "roi": [235, 245, 1000, 220],
        "connected": True,
        "count": 90000,
        "action": "DoNothing",
    }
    badge = nodes["dungeon.result.panel.badge"]
    assert badge == {
        "recognition": "ColorMatch",
        "lower": [210, 75, 15],
        "upper": [255, 165, 90],
        "roi": [165, 205, 65, 300],
        "connected": True,
        "count": 8000,
        "action": "DoNothing",
    }
    close = nodes["dungeon.result.close"]
    assert close == {
        "recognition": "OCR",
        "expected": "点击空白处关闭",
        "roi": [350, 580, 600, 140],
        "action": "DoNothing",
    }

    same_frame = ["dungeon.result", "dungeon.result.close"]
    assert nodes["MJA_DUNGEON_RESULT_PROBE"]["recognition"]["param"]["all_of"] == same_frame
    dismiss = nodes["MJA_DUNGEON_DISMISS_RESULT"]
    assert dismiss["recognition"]["param"]["all_of"] == same_frame
    assert dismiss["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "dungeon.result",
        "target_name": "dungeon.result.close",
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
    panel = nodes["dungeon.sweep.panel"]
    assert panel["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "dungeon.sweep.button",
                "dungeon.sweep.yanwangling.card",
            ]
        },
    }
    assert nodes["dungeon.sweep.button"]["expected"] == expected_button_text
    assert nodes["dungeon.start"]["expected"] == expected_button_text
    assert "开始" not in expected_button_text

    card = nodes["dungeon.sweep.yanwangling.card"]
    assert card["expected"] == ["燕王秘陵", "燕王"]
    assert card["roi"] == [880, 240, 400, 100]

    select = nodes["MJA_DUNGEON_SELECT_PANEL_YANWANG"]
    assert select["recognition"]["param"]["all_of"] == [
        "dungeon.sweep.panel",
        "dungeon.sweep.yanwangling.card",
    ]
    assert select["custom_action_param"]["evidence"]["target_name"] == (
        "dungeon.sweep.yanwangling.card"
    )


def test_dungeon_direct_plus_is_scoped_to_live_yanwangling_master_controls() -> None:
    nodes = load_task_nodes(DUNGEON)

    master = nodes["dungeon.master.80"]
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
    ready = nodes["MJA_DUNGEON_MASTER_ASSIGNMENT_READY"]
    assert ready["recognition"]["param"]["all_of"] == [
        "dungeon.sweep.panel",
        "dungeon.sweep.yanwangling.card",
        "dungeon.master.80",
        "dungeon.ticket.plus",
        "dungeon.ticket.icon",
        "dungeon.ticket.balance",
    ]
    assert ready["action"] == "DoNothing"
    assert ready["next"] == ["MJA_DUNGEON_ASSIGN_TICKET_LOOP"]

    plus = nodes["dungeon.ticket.plus"]
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

    icon = nodes["dungeon.ticket.icon"]
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
    balance = nodes["dungeon.ticket.balance"]
    assert balance["expected"] == r"^(?:[1-9]|1[0-9]|20)$"
    assert balance["roi"] == [840, 520, 90, 70]
    assert 840 <= 862 < 840 + 90
    assert 520 <= 550 < 520 + 70
    assert android_nodes["ticket_balance"] == balance

    assign = nodes["MJA_DUNGEON_ASSIGN_TICKET_LOOP"]
    assert assign["recognition"]["param"]["all_of"] == [
        "dungeon.sweep.panel",
        "dungeon.sweep.yanwangling.card",
        "dungeon.master.80",
        "dungeon.ticket.plus",
        "dungeon.ticket.icon",
        "dungeon.ticket.balance",
    ]
    assert assign["recognition"]["param"]["box_index"] == 3
    assert assign["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 3,
        "page_name": "dungeon.sweep.panel",
        "target_name": "dungeon.ticket.plus",
    }
    assert assign["custom_action_param"]["resource_index"] == 4
    assert assign["custom_action_param"]["resource_evidence_name"] == (
        "dungeon.ticket.icon"
    )
    assert assign["custom_action_param"]["amount_index"] == 5
    assert assign["max_hit"] == 100
    assert assign["retry_times"] == 0
    assert TASK_POLICIES[DUNGEON.task_id].action_caps["assign_sweep_ticket"] == 100


def test_dungeon_sweep_recovers_once_from_launcher_then_requires_home() -> None:
    nodes = load_task_nodes(DUNGEON)

    start = nodes["MJA_DUNGEON_SWEEP_DAILY_START"]
    assert start["timeout"] == 8000
    assert start["next"] == [
        "MJA_DUNGEON_PANEL_PROBE",
        "MJA_DUNGEON_REWARD_PREVIEW_RECOVERY_PROBE",
        "MJA_DUNGEON_SHADOW_PAGE_PROBE",
        "MJA_DUNGEON_HOME_PROBE",
    ]
    assert start["on_error"] == [
        "MJA_DUNGEON_GAME_START_RECOVERY",
        "MJA_DUNGEON_GAME_START_RECOVERY_FAILED",
    ]
    recovery_probe = nodes["MJA_DUNGEON_REWARD_PREVIEW_RECOVERY_PROBE"]
    assert recovery_probe["recognition"] == {
        "type": "Or",
        "param": {
            "any_of": ["dungeon.reward.preview.page", "food.food.page"]
        },
    }

    recovery = nodes["MJA_DUNGEON_GAME_START_RECOVERY"]
    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "DoNothing"
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 30000
    assert recovery["next"] == [
        "MJA_DUNGEON_PANEL_PROBE",
        "MJA_DUNGEON_REWARD_PREVIEW_RECOVERY_PROBE",
        "MJA_DUNGEON_SHADOW_PAGE_PROBE",
        "MJA_DUNGEON_HOME_PROBE",
    ]
    assert recovery["on_error"] == ["MJA_DUNGEON_GAME_START_RECOVERY_FAILED"]

    assert_outcome(
        nodes,
        "MJA_DUNGEON_GAME_START_RECOVERY_FAILED",
        "failed",
        "dungeon.game_foreground_and_home",
    )
    failed = nodes["MJA_DUNGEON_GAME_START_RECOVERY_FAILED"]
    assert failed["custom_action_param"]["error_code"] == (
        "DUNGEON_GAME_START_RECOVERY_EXHAUSTED"
    )
    assert failed["custom_action_param"]["native_fail_after_record"] is True
    assert failed["Abort"] is True
    assert failed["next"] == ["MJA_COMMON_ABORT"]
    assert nodes["MJA_DUNGEON_HOME_PROBE"]["on_error"] == [
        "MJA_DUNGEON_GAME_START_RECOVERY",
        "MJA_DUNGEON_RECORD_FAILURE",
    ]


def test_dungeon_shadow_page_is_known_fail_closed_start_state() -> None:
    nodes = load_task_nodes(DUNGEON)

    marker = nodes["dungeon.shadow.page"]
    assert marker == {
        "recognition": "OCR",
        "expected": "蜃影武墟",
        "roi": [0, 0, 1280, 720],
        "action": "DoNothing",
    }
    _assert_archived_ocr_hit(marker, "蜃影武墟", (326, 389, 282, 83))

    probe = nodes["MJA_DUNGEON_SHADOW_PAGE_PROBE"]
    assert probe["recognition"] == {
        "type": "And",
        "param": {"all_of": ["dungeon.shadow.page"]},
    }
    assert probe["action"] == "DoNothing"
    assert probe["next"] == ["MJA_DUNGEON_UNEXPECTED_SHADOW_PAGE"]
    assert probe["on_error"] == ["MJA_DUNGEON_RECORD_FAILURE"]

    failure = nodes["MJA_DUNGEON_UNEXPECTED_SHADOW_PAGE"]
    assert_outcome(
        nodes,
        "MJA_DUNGEON_UNEXPECTED_SHADOW_PAGE",
        "failed",
        "dungeon.state_known",
    )
    assert failure["custom_action_param"]["error_code"] == (
        "DUNGEON_UNEXPECTED_SHADOW_PAGE"
    )
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failure


def test_dungeon_reward_preview_recovery_is_exact_bounded_and_fail_closed() -> None:
    nodes = load_task_nodes(DUNGEON)

    page = nodes["dungeon.reward.preview.page"]
    assert page["recognition"]["param"]["all_of"] == [
        "dungeon.reward.preview.title",
        "dungeon.reward.preview.body",
    ]
    assert nodes["dungeon.reward.preview.title"]["roi"] == [400, 250, 500, 75]
    assert nodes["dungeon.reward.preview.body"]["expected"] == "概率获得以下奖励"
    assert nodes["dungeon.reward.preview.close"]["roi"] == [840, 255, 55, 55]

    close = nodes["MJA_DUNGEON_CLOSE_REWARD_PREVIEW"]
    assert close["max_hit"] == 1
    assert close["retry_times"] == 0
    assert close["custom_action_param"]["action_id"] == (
        "close_dungeon_reward_preview"
    )
    assert close["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "dungeon.reward.preview.page",
        "target_name": "dungeon.reward.preview.close",
    }
    assert close["on_error"] == ["MJA_DUNGEON_RECORD_FAILURE"]
    recovered = nodes["MJA_DUNGEON_REWARD_PREVIEW_RECOVERED_PANEL"]
    assert recovered["next"] == ["MJA_DUNGEON_ASSIGN_TICKET_LOOP"]
    assert recovered["on_error"] == ["MJA_DUNGEON_RECORD_FAILURE"]
    assert_action_limit(DUNGEON.task_id, "close_dungeon_reward_preview", 1)


def test_dungeon_recovery_never_replays_consumptive_actions() -> None:
    nodes = load_task_nodes(DUNGEON)
    recovery_nodes = {
        "MJA_DUNGEON_GAME_START_RECOVERY",
        "MJA_DUNGEON_GAME_START_RECOVERY_FAILED",
        "MJA_DUNGEON_PANEL_PROBE",
        "MJA_DUNGEON_PANEL_CLOSE",
        "MJA_DUNGEON_SHADOW_PAGE_PROBE",
        "MJA_DUNGEON_UNEXPECTED_SHADOW_PAGE",
        "MJA_DUNGEON_REWARD_PREVIEW_RECOVERY_PROBE",
        "MJA_DUNGEON_CLOSE_REWARD_PREVIEW",
        "MJA_DUNGEON_REWARD_PREVIEW_RECOVERED_PANEL",
    }
    dangerous_action_nodes = {
        "MJA_DUNGEON_ASSIGN_TICKET_LOOP",
        "MJA_DUNGEON_START_SWEEP",
        "MJA_DUNGEON_CONFIRM_SWEEP",
    }

    for node_name in dangerous_action_nodes:
        routes = set(nodes[node_name].get("next", [])) | set(
            nodes[node_name].get("on_error", [])
        )
        assert routes.isdisjoint(recovery_nodes)

    assert nodes["MJA_DUNGEON_GAME_START_RECOVERY"]["next"] == [
        "MJA_DUNGEON_PANEL_PROBE",
        "MJA_DUNGEON_REWARD_PREVIEW_RECOVERY_PROBE",
        "MJA_DUNGEON_SHADOW_PAGE_PROBE",
        "MJA_DUNGEON_HOME_PROBE",
    ]


def test_dungeon_ticket_guard_is_dynamic_but_positive_and_budgeted() -> None:
    params = load_task_nodes(DUNGEON)["MJA_DUNGEON_ASSIGN_TICKET_LOOP"][
        "custom_action_param"
    ]
    assert "observed_amount" not in params
    assert params["resource_id"] == "副本票"
    assert params["budget_amount"] == 1
    assert "[1-9]" in load_task_nodes(DUNGEON)["dungeon.ticket.balance"]["expected"]


def test_ring_challenge_partitions_sweep_fight_and_not_open() -> None:
    nodes = load_task_nodes(RING)
    assert nodes["ring.daily.page"]["roi"] == [0, 0, 520, 180]
    assert nodes["MJA_RING_DAILY_PAGE"]["next"] == [
        "MJA_RING_DAILY_REWARD_PROBE",
        "MJA_RING_OPEN",
    ]
    assert nodes["ring.entry"] == {
        "recognition": "OCR",
        "expected": "^前往$",
        "roi": [1000, 510, 180, 100],
        "action": "DoNothing",
    }
    assert nodes["MJA_RING_PAGE_PROBE"]["next"] == [
        "MJA_RING_NOT_OPEN_PROBE",
        "MJA_RING_ATTEMPTS_PROBE",
        "MJA_RING_OPEN_MODE",
    ]
    assert nodes["MJA_RING_OPEN_MODE"]["next"] == [
        "MJA_RING_SWEEP_ELIGIBLE",
        "MJA_RING_SWEEP_SCORE_ELIGIBLE",
        "MJA_RING_FIGHT_EXHAUSTED_PROBE",
        "MJA_RING_FIGHT_GATE",
        "MJA_RING_MATCH_GATE",
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
    assert_condition(nodes, "MJA_RING_SWEEP_ELIGIBLE", "master_mode_or_score_gte_5000")
    assert "论剑阵容模式" not in nodes["ring.master.mode"]["expected"]
    assert "大师赛模式" in nodes["ring.master.mode"]["expected"]
    assert nodes["MJA_RING_SWEEP_ELIGIBLE"]["on_error"] == [
        "MJA_RING_SWEEP_SCORE_ELIGIBLE"
    ]
    assert nodes["MJA_RING_SWEEP_SCORE_ELIGIBLE"]["on_error"] == [
        "MJA_RING_FIGHT_EXHAUSTED_PROBE"
    ]
    assert nodes["擂台券"]["expected"] == [
        "擂台券",
        "^[1-9][0-9]?/12$",
    ]
    assert nodes["擂台券"]["roi"] == [1000, 0, 280, 100]
    assert nodes["ring.ticket.amount"]["expected"] == [
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
        "MJA_RING_MATCHING_LOADING_PROBE",
        "MJA_RING_BATTLE_PREPARE",
        "MJA_RING_FIGHT_PAGE",
        "MJA_RING_BATTLE_LOADING_PROBE",
    ]
    assert nodes["MJA_RING_FIGHT_LOOP"]["next"] == expected_battle_entry
    assert nodes["MJA_RING_START_MATCHING"]["next"] == expected_battle_entry
    assert nodes["MJA_RING_FIGHT_PAGE"]["on_error"] == [
        "MJA_RING_BATTLE_RESULT_PROBE",
        "MJA_RING_BATTLE_RESULT_DEFEAT",
        "MJA_RING_BATTLE_LOADING_PROBE",
    ]
    assert nodes["MJA_RING_POST_RESULT"]["next"] == [
        "MJA_RING_FIGHT_EXHAUSTED_PROBE",
        "MJA_RING_FIGHT_GATE",
        "MJA_RING_MATCH_GATE",
    ]
    assert nodes["MJA_RING_BATTLE_RESULT_PROBE"]["recognition"]["param"]["all_of"] == [
        "ring.battle.result",
        "ring.battle.victory",
    ]
    assert nodes["ring.battle.result"]["expected"] == [
        "战斗胜利",
        "战斗胜",
        "战斗失败",
        "战斗败",
        "胜利",
        "失败",
    ]
    assert nodes["ring.battle.victory"]["expected"] == [
        "战斗胜利",
        "战斗胜",
        "胜利",
    ]
    assert nodes["ring.result.close"]["expected"] == [
        "点击(?:空白处|任意位置)关闭",
        "擂台积分\\d+",
    ]
    assert (
        nodes["MJA_RING_BATTLE_PREPARE"]["custom_action_param"]["action_id"]
        == "start_ring_battle"
    )
    assert (
        nodes["MJA_RING_BATTLE_LOADING_WAIT"]["custom_action_param"]["action_id"]
        == "wait_ring_battle"
    )
    assert nodes["MJA_RING_BATTLE_LOADING_WAIT"]["custom_action_param"]["kind"] == "none"
    assert nodes["MJA_RING_MATCH_GATE"]["next"] == ["MJA_RING_START_MATCHING"]
    assert (
        nodes["MJA_RING_START_MATCHING"]["custom_action_param"]["action_id"]
        == "start_ring_matching"
    )
    assert nodes["MJA_RING_SWEEP_GATE"]["on_error"] == ["MJA_RING_RECORD_FAILURE"]
    assert_action_limit(RING.task_id, "sweep_ring", 1)
    assert_action_limit(RING.task_id, "skip_ring_battle", 12)
    assert nodes["MJA_RING_FIGHT_LOOP"]["max_hit"] == 12
    assert nodes["MJA_RING_FIGHT_LOOP_EXHAUSTED"]["custom_action_param"]["status"] == "success"
    assert nodes["MJA_RING_FIGHT_LOOP_EXHAUSTED"]["recognition"]["type"] == "And"
    assert "ring.attempts.exhausted" in nodes["MJA_RING_FIGHT_LOOP_EXHAUSTED"][
        "recognition"
    ]["param"]["all_of"]
    assert nodes["MJA_RING_FIGHT_LOOP_EXHAUSTED"]["next"] == ["MJA_RING_CLOSE_OPPONENTS"]
    assert nodes["MJA_RING_POST_RESULT"]["on_error"] == [
        "MJA_RING_POST_RESULT_RING_PAGE_EXHAUSTED_PROBE"
    ]
    assert nodes["MJA_RING_POST_RESULT_RING_PAGE_EXHAUSTED_PROBE"]["recognition"][
        "param"
    ]["all_of"] == ["ring.page", "ring.attempts.exhausted"]
    assert nodes["MJA_RING_POST_RESULT_RING_PAGE_EXHAUSTED_PROBE"]["on_error"] == [
        "MJA_RING_POST_RESULT_RING_PAGE_CONTINUE"
    ]
    assert nodes["MJA_RING_POST_RESULT_RING_PAGE_CONTINUE"]["next"] == [
        "MJA_RING_OPEN_MODE"
    ]
    assert_outcome(
        nodes,
        "MJA_RING_POST_RESULT_RING_PAGE_EXHAUSTED",
        "success",
        "ring.manual_attempts_complete",
    )
    assert_outcome(
        nodes,
        "MJA_RING_FIGHT_LOOP_EXHAUSTED",
        "success",
        "ring.manual_attempts_complete",
    )
    assert_outcome(
        nodes,
        "MJA_RING_ATTEMPTS_EXHAUSTED",
        "success",
        "ring.attempts_exhausted",
    )
    assert_outcome(nodes, "MJA_RING_NOT_OPEN", "not_eligible", "ring.not_open")
    assert_battle_result_partition(nodes, "MJA_RING_BATTLE_RESULT")
    assert_no_side_effect_retry(nodes, "sweep_ring")
    assert_no_side_effect_retry(nodes, "fight_ring_opponent")
    assert_no_side_effect_retry(nodes, "start_ring_matching")
