from __future__ import annotations

import json
import re
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_abort_code,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_outcome,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

GUILD_ACTIVITY = TaskContract(
    "GUILD_ACTIVITY_CHALLENGE_DAILY",
    "daily/guild_activity_challenge_daily.json",
)
ROOT = Path(__file__).parents[3]


def test_guild_activity_task_contract_is_registered_as_a_standalone_mfw_task() -> None:
    assert_task_contract(GUILD_ACTIVITY, require_game_start_recovery=False)


def test_guild_activity_start_has_one_bounded_task_local_recovery() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    start = nodes[GUILD_ACTIVITY.entry]
    recovery = nodes["MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_GAME_START_RECOVERY"]
    probes = [
        "MJA_GUILD_START_SAFETY_PROBE",
        "MJA_GUILD_START_PAID_PROBE",
        "MJA_GUILD_RESUME_RESULT_PROBE",
        "MJA_GUILD_RECOVERY_DUNGEON_PAGE_PROBE",
        "MJA_GUILD_RECOVERY_JIANLIN_PAGE_PROBE",
        "MJA_GUILD_RECOVERY_DAILY_PAGE_PROBE",
        "MJA_START_SHADOW_PAGE_BACK",
        "MJA_GUILD_ACTIVITY_PAGE_PROBE",
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_PAGE_PROBE",
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_PANEL_PROBE",
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_HOME_PROBE",
    ]

    assert start["timeout"] == 8000
    assert start["retry_times"] == 0
    assert start["next"] == probes
    assert start["on_error"] == [
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_GAME_START_RECOVERY",
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_RECORD_FAILURE",
    ]
    assert "JumpBack" not in str(start)

    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "StartApp"
    assert recovery["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert recovery["post_delay"] == 5000
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 30000
    assert recovery["retry_times"] == 0
    assert recovery["next"] == probes
    assert recovery["on_error"] == [
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_RECORD_FAILURE"
    ]

    resume = nodes["MJA_GUILD_RESUME_RESULT_PROBE"]
    assert resume["next"] == [
        "MJA_GUILD_RESULT_VICTORY_PROBE",
        "MJA_GUILD_RESULT_DEFEAT_PROBE",
    ]

    # A known home frame that fails to open the panel is a task failure; only
    # the root start boundary may request the one shared startup recovery.
    assert nodes["MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_HOME_PROBE"]["on_error"] == [
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_RECORD_FAILURE"
    ]


def test_guild_activity_challenge_is_bounded_and_requires_exact_zero_of_two() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    assert_guarded_actions(
        nodes,
        GUILD_ACTIVITY.task_id,
        [
            "close_dungeon_for_guild",
            "close_jianlin_for_guild",
            "close_daily_tasks_for_guild",
            "open_function_panel",
            "open_guild",
            "open_guild_activity",
            "challenge_guild_activity",
            "confirm_guild_challenge",
            "start_guild_challenge",
            "dismiss_guild_result",
            "dismiss_guild_defeat_result",
            "exit_guild_activity",
            "exit_guild_home",
            "close_function_panel",
        ],
    )
    assert TASK_POLICIES[GUILD_ACTIVITY.task_id].action_caps[
        "close_function_panel"
    ] == 1
    assert TASK_POLICIES[GUILD_ACTIVITY.task_id].action_caps[
        "close_daily_tasks_for_guild"
    ] == 1
    assert TASK_POLICIES[GUILD_ACTIVITY.task_id].action_caps[
        "close_jianlin_for_guild"
    ] == 1

    loop = nodes["MJA_GUILD_CHALLENGE_LOOP"]
    assert loop["max_hit"] == 2
    assert loop["retry_times"] == 0
    assert loop["on_error"] == ["MJA_GUILD_CHALLENGE_TRANSITION_UNKNOWN"]
    assert_reachable(nodes, "MJA_GUILD_CHALLENGE_LOOP", "MJA_GUILD_CHALLENGE_CONFIRM")
    assert_reachable(nodes, "MJA_GUILD_CHALLENGE_LOOP", "MJA_GUILD_CHALLENGE_START")
    assert_reachable(nodes, "MJA_GUILD_CHALLENGE_LOOP", "MJA_GUILD_RESULT_DISMISS_PROBE")

    available = nodes["guild.remaining.available"]["expected"]
    exhausted = nodes["guild.remaining.exhausted"]["expected"]
    assert all("0" not in pattern for pattern in available)
    assert any("0\\s*/\\s*2" in pattern for pattern in exhausted)
    final_zero_evidence = nodes["MJA_GUILD_FINAL_ZERO_PROBE"]["recognition"]["param"]["all_of"]
    assert "guild.remaining.exhausted" in final_zero_evidence
    assert_outcome(
        nodes,
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_SUCCESS",
        "success",
        "guild.remaining_conquest_0_of_2",
    )
    assert_outcome(
        nodes,
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_ALREADY_COMPLETE",
        "already_complete",
        "guild.remaining_conquest_0_of_2",
    )


def test_guild_activity_handles_both_result_types_without_replaying_side_effects() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    for action_id in (
        "challenge_guild_activity",
        "confirm_guild_challenge",
        "start_guild_challenge",
        "dismiss_guild_result",
        "dismiss_guild_defeat_result",
    ):
        assert_no_side_effect_retry(nodes, action_id)

    assert_reachable(nodes, "MJA_GUILD_RESULT_VICTORY_PROBE", "MJA_GUILD_RESULT_DISMISS_PROBE")
    assert_reachable(
        nodes,
        "MJA_GUILD_RESULT_DEFEAT_PROBE",
        "MJA_GUILD_RESULT_DEFEAT_DISMISS_PROBE",
    )
    assert_reachable(
        nodes,
        "MJA_GUILD_RESULT_DEFEAT_DISMISS_PROBE",
        "MJA_GUILD_RESULT_DEFEAT",
    )
    assert_outcome(
        nodes,
        "MJA_GUILD_RESULT_DEFEAT",
        "failed",
        "guild.challenge_result_known",
    )
    assert_abort_code(nodes, "MJA_GUILD_RESULT_DEFEAT", "GUILD_RESULT_DEFEAT")
    assert_reachable(nodes, "MJA_GUILD_RESULT_UNKNOWN", "MJA_COMMON_ABORT")
    assert_abort_code(nodes, "MJA_GUILD_RESULT_UNKNOWN", "GUILD_RESULT_UNKNOWN")
    assert_abort_code(
        nodes,
        "MJA_GUILD_CHALLENGE_TRANSITION_UNKNOWN",
        "GUILD_CHALLENGE_TRANSITION_UNKNOWN",
    )
    assert_abort_code(nodes, "MJA_GUILD_DANGER_STOP", "GUILD_DANGEROUS_PAGE")
    assert_abort_code(
        nodes,
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_RECORD_FAILURE",
        "GUILD_POSTCONDITION_MISSING",
    )
    assert_abort_code(
        nodes,
        "MJA_GUILD_EXIT_RECORD_FAILURE",
        "GUILD_HOME_RETURN_FAILED",
    )

    failure_nodes = (
        "MJA_GUILD_CHALLENGE_TRANSITION_UNKNOWN",
        "MJA_GUILD_RESULT_DEFEAT",
        "MJA_GUILD_RESULT_UNKNOWN",
        "MJA_GUILD_DANGER_STOP",
        "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_RECORD_FAILURE",
        "MJA_GUILD_EXIT_RECORD_FAILURE",
        "MJA_GUILD_UNKNOWN_PAGE",
    )
    for node_name in failure_nodes:
        assert nodes[node_name]["custom_action_param"]["native_fail_after_record"] is True


def test_guild_activity_result_partition_is_exact_mutually_exclusive_and_fail_closed() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    page = nodes["guild.result.page"]
    known = nodes["guild.result.known"]
    victory = nodes["guild.result.victory"]
    defeat = nodes["guild.result.defeat"]

    assert page["expected"] == [r"^战斗胜利$", r"^战斗失败$"]
    assert known["expected"] == page["expected"]
    assert victory["expected"] == r"^战斗胜利$"
    assert defeat["expected"] == r"^战斗失败$"

    samples = {
        "战斗胜利": (True, False),
        "战斗失败": (False, True),
        "战斗失": (False, False),
        "战斗": (False, False),
        "可以通过以下途径提升": (False, False),
    }
    for text, expected in samples.items():
        observed = (
            re.fullmatch(victory["expected"], text) is not None,
            re.fullmatch(defeat["expected"], text) is not None,
        )
        assert observed == expected

    victory_probe = nodes["MJA_GUILD_RESULT_VICTORY_PROBE"]
    defeat_probe = nodes["MJA_GUILD_RESULT_DEFEAT_PROBE"]
    dismiss_probe = nodes["MJA_GUILD_RESULT_DISMISS_PROBE"]
    assert victory_probe["recognition"]["param"] == {
        "all_of": ["guild.result.page", "guild.result.victory"],
        "box_index": 1,
    }
    assert victory_probe["on_error"] == ["MJA_GUILD_RESULT_DEFEAT_PROBE"]
    assert dismiss_probe["recognition"]["param"] == {
        "all_of": ["guild.result.page", "guild.result.victory"],
        "box_index": 1,
    }
    assert dismiss_probe["custom_action"] == "GuardedInput"
    assert dismiss_probe["custom_action_param"]["fixed_click_mode"] == "guild_result_blank"
    assert dismiss_probe["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "guild.result.page",
        "target_name": "guild.result.victory",
    }
    assert defeat_probe["recognition"]["param"] == {
        "all_of": ["guild.result.defeat.page"],
        "box_index": 0,
    }
    assert defeat_probe["next"] == ["MJA_GUILD_RESULT_DEFEAT_DISMISS_PROBE"]
    assert defeat_probe["on_error"] == ["MJA_GUILD_RESULT_UNKNOWN"]

    defeat_dismiss_probe = nodes["MJA_GUILD_RESULT_DEFEAT_DISMISS_PROBE"]
    assert defeat_dismiss_probe["recognition"]["param"] == {
        "all_of": ["guild.result.defeat", "guild.result.defeat.improve"],
        "box_index": 0,
    }
    assert defeat_dismiss_probe["custom_action"] == "GuardedInput"
    assert defeat_dismiss_probe["custom_action_param"] == {
        "task_id": GUILD_ACTIVITY.task_id,
        "action_id": "dismiss_guild_defeat_result",
        "kind": "click",
        "fixed_click_mode": "guild_result_defeat_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "guild.result.defeat",
            "target_name": "guild.result.defeat.improve",
        },
    }
    assert defeat_dismiss_probe["next"] == ["MJA_GUILD_RESULT_DEFEAT"]
    assert defeat_dismiss_probe["on_error"] == ["MJA_GUILD_RESULT_DEFEAT"]

    defeat_page = nodes["guild.result.defeat.page"]
    assert defeat_page["recognition"]["param"] == {
        "all_of": ["guild.result.defeat", "guild.result.defeat.improve"],
        "box_index": 0,
    }
    improve = nodes["guild.result.defeat.improve"]
    assert improve == {
        "recognition": "OCR",
        "expected": r"^可以通过以下途径提升$",
        "roi": [840, 390, 340, 90],
        "action": "DoNothing",
    }


def test_guild_activity_result_title_roi_contains_r19_archived_batch_ocr_box() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    # Offline calibration from the fresh r19 archive at 17:28:18.214.  The
    # full-frame batch OCR saw all four glyphs, while the old x=150,w=980 ROI
    # ended at x=1130 and re-recognized only “战斗失”.
    frame_width, frame_height = 1280, 720
    batch_box = [742, 97, 504, 149]
    clipped_box = [744, 100, 386, 143]
    old_roi = [150, 100, 980, 520]

    assert old_roi[0] + old_roi[2] == clipped_box[0] + clipped_box[2]
    assert old_roi[0] + old_roi[2] < batch_box[0] + batch_box[2]

    result_names = (
        "guild.result.page",
        "guild.result.known",
        "guild.result.victory",
        "guild.result.defeat",
    )
    rois = {tuple(nodes[name]["roi"]) for name in result_names}
    assert len(rois) == 1
    x, y, width, height = rois.pop()
    assert x >= 700
    assert y <= batch_box[1]
    assert x + width == frame_width
    assert y + height >= batch_box[1] + batch_box[3]
    assert width <= 580
    assert height <= 220
    assert y + height <= frame_height

    # The independent result-page context was OCR'd at [888, 420, 217, 23].
    improve_box = [888, 420, 217, 23]
    improve_roi = nodes["guild.result.defeat.improve"]["roi"]
    improve_x, improve_y, improve_width, improve_height = improve_roi
    assert improve_x <= improve_box[0]
    assert improve_y <= improve_box[1]
    assert improve_x + improve_width >= improve_box[0] + improve_box[2]
    assert improve_y + improve_height >= improve_box[1] + improve_box[3]
    assert improve_width <= 340
    assert improve_height <= 90


def test_guild_activity_world_boss_prepare_page_uses_live_same_frame_boundary() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    prepare = nodes["guild.challenge.prepare.page"]
    assert prepare["recognition"]["param"] == {
        "all_of": [
            "guild.challenge.prepare.world_boss_title",
            "guild.challenge.prepare.battle_title",
        ],
        "box_index": 1,
    }

    world_boss = nodes["guild.challenge.prepare.world_boss_title"]
    assert world_boss["expected"] == "世界首领"
    assert world_boss["roi"] == [60, 0, 180, 80]

    battle_title = nodes["guild.challenge.prepare.battle_title"]
    assert battle_title["expected"] == "首领战斗"
    assert battle_title["roi"] == [1020, 60, 220, 100]

    start = nodes["guild.challenge.start"]
    assert start == {
        "recognition": "ColorMatch",
        "method": 4,
        "lower": [200, 80, 20],
        "upper": [255, 170, 90],
        "roi": [1110, 555, 130, 130],
        "connected": True,
        "count": 5000,
        "order_by": "Area",
        "index": 0,
        "action": "DoNothing",
    }

    for node_name in ("MJA_GUILD_CHALLENGE_PREPARE_PROBE", "MJA_GUILD_CHALLENGE_START"):
        assert nodes[node_name]["recognition"]["param"] == {
            "all_of": ["guild.challenge.prepare.page", "guild.challenge.start"],
            "box_index": 1,
        }

    start_action = nodes["MJA_GUILD_CHALLENGE_START"]
    assert start_action["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "guild.challenge.prepare.page",
        "target_name": "guild.challenge.start",
    }


def test_guild_activity_post_result_checks_zero_before_reentering_bounded_loop() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    assert nodes["MJA_GUILD_POST_RESULT_PROBE"]["next"] == [
        "MJA_GUILD_FINAL_ZERO_PROBE",
        "MJA_GUILD_CHALLENGE_LOOP",
    ]
    assert "MJA_GUILD_CHALLENGE_PREPARE_PROBE" in nodes[
        "MJA_GUILD_CHALLENGE_CONFIRM"
    ]["next"]


def test_guild_activity_accepts_live_battle_then_waits_without_input() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    start_next = nodes["MJA_GUILD_CHALLENGE_START"]["next"]
    assert start_next == [
        "MJA_GUILD_RESULT_DANGER_PROBE",
        "MJA_GUILD_RESULT_VERIFICATION_PROBE",
        "MJA_GUILD_BATTLE_ACTIVE_PROBE",
        "MJA_GUILD_RESULT_VICTORY_PROBE",
        "MJA_GUILD_RESULT_DEFEAT_PROBE",
    ]

    battle = nodes["MJA_GUILD_BATTLE_ACTIVE_PROBE"]
    assert battle["recognition"]["param"] == {
        "all_of": [
            "guild.challenge.battle.timer",
            "guild.challenge.battle.boss",
            "guild.challenge.battle.auto.top",
            "guild.challenge.battle.pause",
            "guild.challenge.battle.auto.bottom",
        ],
        "box_index": 0,
    }
    assert battle["action"] == "DoNothing"
    assert "custom_action" not in battle
    assert battle["timeout"] == 180000
    assert battle["retry_times"] == 0
    assert battle["next"] == [
        "MJA_GUILD_RESULT_DANGER_PROBE",
        "MJA_GUILD_RESULT_VERIFICATION_PROBE",
        "MJA_GUILD_RESULT_VICTORY_PROBE",
        "MJA_GUILD_RESULT_DEFEAT_PROBE",
    ]
    assert battle["on_error"] == ["MJA_GUILD_RESULT_UNKNOWN"]

    expected_controls = {
        "guild.challenge.battle.timer": ("^\\d{2}:\\d{2}$", [170, 5, 120, 65]),
        "guild.challenge.battle.boss": ("^\\d+级.+", [390, 0, 240, 60]),
        "guild.challenge.battle.auto.top": ("自动中", [1090, 25, 100, 65]),
        "guild.challenge.battle.pause": ("暂停", [1175, 25, 80, 65]),
        "guild.challenge.battle.auto.bottom": ("自动中", [1130, 590, 130, 70]),
    }
    for node_name, (expected, roi) in expected_controls.items():
        control = nodes[node_name]
        assert control["recognition"] == "OCR"
        assert control["expected"] == expected
        assert control["roi"] == roi
        assert control["action"] == "DoNothing"
        assert roi[2] <= 240
        assert roi[3] <= 70


def test_guild_activity_home_probe_uses_the_live_guild_home_regions() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    page_probe = nodes["MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_PAGE_PROBE"]
    assert page_probe["recognition"]["param"] == {
        "all_of": ["guild.activity_challenge.page", "guild.activity.entry"],
        "box_index": 1,
    }
    assert page_probe["next"] == ["MJA_GUILD_OPEN_ACTIVITY"]

    guild_home = nodes["guild.activity_challenge.page"]
    assert guild_home["expected"] == "浮生城"
    assert guild_home["roi"] == [0, 0, 380, 100]

    activity_entry = nodes["guild.activity.entry"]
    assert activity_entry["expected"] == "帮会活动"
    assert activity_entry["roi"] == [600, 250, 360, 230]

    open_activity = nodes["MJA_GUILD_OPEN_ACTIVITY"]
    assert open_activity["recognition"]["param"] == {
        "all_of": ["guild.activity_challenge.page", "guild.activity.entry"],
        "box_index": 1,
    }
    assert open_activity["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "guild.activity_challenge.page",
        "target_name": "guild.activity.entry",
    }


def test_guild_activity_terminal_outcomes_restore_home_before_recording() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    branches = (
        (
            "MJA_GUILD_INITIAL_ZERO_PROBE",
            "MJA_GUILD_ALREADY_COMPLETE_EXIT_ACTIVITY",
            "MJA_GUILD_ALREADY_COMPLETE_EXIT_GUILD_HOME",
            "MJA_GUILD_ALREADY_COMPLETE_EXIT_FUNCTION_PANEL_PROBE",
            "MJA_GUILD_ALREADY_COMPLETE_EXIT_FUNCTION_PANEL",
            "MJA_GUILD_ALREADY_COMPLETE_EXIT_HOME_PROBE",
            "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_ALREADY_COMPLETE",
        ),
        (
            "MJA_GUILD_FINAL_ZERO_PROBE",
            "MJA_GUILD_SUCCESS_EXIT_ACTIVITY",
            "MJA_GUILD_SUCCESS_EXIT_GUILD_HOME",
            "MJA_GUILD_SUCCESS_EXIT_FUNCTION_PANEL_PROBE",
            "MJA_GUILD_SUCCESS_EXIT_FUNCTION_PANEL",
            "MJA_GUILD_SUCCESS_EXIT_HOME_PROBE",
            "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_SUCCESS",
        ),
    )

    for (
        source,
        exit_activity,
        exit_guild,
        panel_probe,
        panel_close,
        home_probe,
        outcome,
    ) in branches:
        assert nodes[source]["next"] == [
            exit_activity,
            "MJA_GUILD_EXIT_RECORD_FAILURE",
        ]
        assert_reachable(nodes, source, home_probe)
        assert_reachable(nodes, source, outcome)

        first_close = nodes[exit_activity]
        assert first_close["recognition"]["param"] == {
            "all_of": [
                "guild.activity.page",
                "guild.activity.context",
                "guild.page.close",
            ],
            "box_index": 2,
        }
        assert first_close["custom_action"] == "GuardedInput"
        assert first_close["custom_action_param"]["action_id"] == ("exit_guild_activity")
        assert first_close["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 2,
            "page_name": "guild.activity.page",
            "target_name": "guild.page.close",
        }
        assert first_close["max_hit"] == 1
        assert first_close["retry_times"] == 0
        assert first_close["next"] == [exit_guild]
        assert first_close["on_error"] == ["MJA_GUILD_EXIT_RECORD_FAILURE"]

        second_close = nodes[exit_guild]
        assert second_close["recognition"]["param"] == {
            "all_of": ["guild.home.page", "guild.page.close"],
            "box_index": 1,
        }
        assert second_close["custom_action"] == "GuardedInput"
        assert second_close["custom_action_param"]["action_id"] == "exit_guild_home"
        assert second_close["max_hit"] == 1
        assert second_close["retry_times"] == 0
        assert second_close["next"] == [panel_probe]
        assert second_close["on_error"] == ["MJA_GUILD_EXIT_RECORD_FAILURE"]

        outer_panel = nodes[panel_probe]
        assert outer_panel == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                    "box_index": 0,
                },
            },
            "timeout": 8000,
            "max_hit": 1,
            "action": "DoNothing",
            "next": [panel_close],
            "on_error": ["MJA_GUILD_EXIT_RECORD_FAILURE"],
            "retry_times": 0,
        }

        third_close = nodes[panel_close]
        assert third_close["recognition"]["param"] == {
            "all_of": ["guild.function.panel.page", "guild.function.panel.close"],
            "box_index": 1,
        }
        assert third_close["custom_action"] == "GuardedInput"
        assert third_close["custom_action_param"] == {
            "task_id": GUILD_ACTIVITY.task_id,
            "action_id": "close_function_panel",
            "kind": "click",
            "fixed_click_mode": "function_panel_close",
            "evidence": {
                "page_index": 0,
                "target_index": 1,
                "page_name": "guild.function.panel.page",
                "target_name": "guild.function.panel.close",
            },
        }
        assert third_close["max_hit"] == 1
        assert third_close["retry_times"] == 0
        assert third_close["next"] == [home_probe]
        assert third_close["on_error"] == ["MJA_GUILD_EXIT_RECORD_FAILURE"]

        home = nodes[home_probe]
        assert home["template"] == "home/home_marker.png"
        assert home["roi"] == [1040, 0, 240, 110]
        assert home["threshold"] == 0.75
        assert home["timeout"] == 8000
        assert home["max_hit"] == 1
        assert home["next"] == [outcome]
        assert home["on_error"] == ["MJA_GUILD_EXIT_RECORD_FAILURE"]

    close = nodes["guild.page.close"]
    assert close == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [125, 125, 125],
        "roi": [1180, 0, 100, 100],
        "connected": True,
        "count": 180,
        "action": "DoNothing",
    }

    assert nodes["guild.home.page"]["expected"] == "浮生城"
    assert nodes["guild.home.page"]["roi"] == [0, 0, 380, 100]

    assert nodes["guild.function.panel.page"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }
    assert nodes["guild.function.panel.close"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }


def test_r20_already_complete_screenshot_requires_outer_panel_cleanup() -> None:
    evidence_path = (
        ROOT
        / "tests/fixtures/GUILD_ACTIVITY_CHALLENGE_DAILY"
        / "r20_already_complete_outer_panel.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    nodes = load_task_nodes(GUILD_ACTIVITY)

    assert evidence["candidate"] == "install/mfw-android-all-20260809-r20"
    assert evidence["screenshot_sha256"] == (
        "82cbe596d9adaa01940932bb04699af34ba07c1459318dc43b6ed2cb79a8b000"
    )
    assert evidence["visible_state"] == "outer_function_panel"
    assert evidence["template_scores"]["panel_marker"] >= nodes[
        "guild.function.panel.page"
    ]["threshold"]
    assert evidence["template_scores"]["panel_close"] >= nodes[
        "guild.function.panel.close"
    ]["threshold"]
    assert evidence["template_scores"]["home_marker"] < 0.75
    assert evidence["action_trace"] == [
        "open_function_panel",
        "open_guild",
        "open_guild_activity",
        "exit_guild_activity",
        "exit_guild_home",
    ]

    already_complete_close = nodes[
        "MJA_GUILD_ALREADY_COMPLETE_EXIT_FUNCTION_PANEL"
    ]
    assert already_complete_close["custom_action_param"]["action_id"] == (
        "close_function_panel"
    )
    assert already_complete_close["next"] == [
        "MJA_GUILD_ALREADY_COMPLETE_EXIT_HOME_PROBE"
    ]


def test_all_guild_activity_failures_persist_then_fail_native() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    failures = {
        name: node
        for name, node in nodes.items()
        if name.startswith("MJA_GUILD_")
        and node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id")
        == GUILD_ACTIVITY.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert failures
    for name, node in failures.items():
        assert node["custom_action_param"]["native_fail_after_record"] is True, name
        assert node["Abort"] is True, name
        assert node["next"] == ["MJA_COMMON_ABORT"], name
        assert "on_error" not in node, name


def test_guild_activity_uses_live_huanjing_title_with_context() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    activity_page = nodes["guild.activity.page"]
    assert activity_page["recognition"] == "OCR"
    assert activity_page["expected"] == "幻境征讨"
    assert activity_page["roi"] == [0, 0, 620, 190]

    activity_context = nodes["guild.activity.context"]
    assert activity_context["expected"] == ["讨伐中", "今日剩余征讨次数"]
    context_x, context_y, context_width, _ = activity_context["roi"]
    assert context_x > 0
    assert context_y >= 120
    assert context_x + context_width == 1280
    assert activity_context["roi"] != [200, 120, 900, 500]

    context_bound_nodes = (
        "MJA_GUILD_ACTIVITY_PAGE_PROBE",
        "MJA_GUILD_INITIAL_ZERO_PROBE",
        "MJA_GUILD_CHALLENGE_LOOP",
        "MJA_GUILD_POST_RESULT_PROBE",
        "MJA_GUILD_FINAL_ZERO_PROBE",
        "MJA_GUILD_ALREADY_COMPLETE_EXIT_ACTIVITY",
        "MJA_GUILD_SUCCESS_EXIT_ACTIVITY",
    )
    for node_name in context_bound_nodes:
        all_of = nodes[node_name]["recognition"]["param"]["all_of"]
        assert "guild.activity.page" in all_of
        assert "guild.activity.context" in all_of


def test_guild_activity_live_controls_cover_the_right_edge_without_full_screen_ocr() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    for remaining_name in (
        "guild.remaining.available",
        "guild.remaining.any",
        "guild.remaining.exhausted",
    ):
        remaining = nodes[remaining_name]
        x, y, width, height = remaining["roi"]
        assert x <= 1040
        assert x + width >= 1250
        assert y <= 600 < y + height
        assert width < 400
        assert height < 150
        assert remaining["roi"] != [300, 120, 700, 260]

    challenge = nodes["guild.challenge.target"]
    x, y, width, height = challenge["roi"]
    assert x <= 1040
    assert x + width >= 1250
    assert y <= 640 < y + height
    assert width < 400
    assert height < 150


def test_guild_activity_policy_caps_all_mutating_phases_at_two_challenges() -> None:
    policy = TASK_POLICIES[GUILD_ACTIVITY.task_id]
    for action_id in (
        "challenge_guild_activity",
        "confirm_guild_challenge",
        "start_guild_challenge",
        "dismiss_guild_result",
    ):
        assert policy.action_caps[action_id] == 2
