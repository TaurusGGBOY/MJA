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
    recovery = nodes["帮派活动挑战-游戏启动恢复"]
    probes = [
        "帮派活动挑战-帮派-开始-安全-探测",
        "帮派活动挑战-帮派-开始-付费-探测",
        "帮派活动挑战-帮派-恢复继续-结果-探测",
        "帮派活动挑战-帮派-恢复-副本-页面-探测",
        "帮派活动挑战-帮派-恢复-剑林-页面-探测",
        "帮派活动挑战-帮派-恢复-日常-页面-探测",
        "启动-影-页面-返回",
        "帮派活动挑战-页面-探测",
        "帮派活动挑战-页面-探测-2",
        "帮派活动挑战-面板-探测",
        "帮派活动挑战-主页-探测",
    ]

    assert start["timeout"] == 8000
    assert start["retry_times"] == 0
    assert start["next"] == probes
    assert start["on_error"] == [
        "帮派活动挑战-游戏启动恢复",
        "帮派活动挑战-记录-失败",
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
        "帮派活动挑战-记录-失败"
    ]

    resume = nodes["帮派活动挑战-帮派-恢复继续-结果-探测"]
    assert resume["next"] == [
        "帮派活动挑战-帮派-结果-胜利-探测",
        "帮派活动挑战-帮派-结果-失败-探测",
    ]

    # A known home frame that fails to open the panel is a task failure; only
    # the root start boundary may request the one shared startup recovery.
    assert nodes["帮派活动挑战-主页-探测"]["on_error"] == [
        "帮派活动挑战-记录-失败"
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

    loop = nodes["帮派活动挑战-帮派-挑战-循环"]
    assert loop["max_hit"] == 2
    assert loop["retry_times"] == 0
    assert loop["on_error"] == ["帮派活动挑战-帮派-挑战-过渡-未知"]
    assert_reachable(nodes, "帮派活动挑战-帮派-挑战-循环", "帮派活动挑战-帮派-挑战-确认")
    assert_reachable(nodes, "帮派活动挑战-帮派-挑战-循环", "帮派活动挑战-帮派-挑战-开始")
    assert_reachable(nodes, "帮派活动挑战-帮派-挑战-循环", "帮派活动挑战-帮派-结果-关闭-探测")

    available = nodes["帮派活动挑战-帮派-剩余-可用"]["expected"]
    exhausted = nodes["帮派活动挑战-帮派-剩余-耗尽"]["expected"]
    assert all("0" not in pattern for pattern in available)
    assert any("0\\s*/\\s*2" in pattern for pattern in exhausted)
    final_zero_evidence = nodes["MJA_GUILD_FINAL_ZERO_PROBE"]["recognition"]["param"]["all_of"]
    assert "帮派活动挑战-帮派-剩余-耗尽" in final_zero_evidence
    assert_outcome(
        nodes,
        "帮派活动挑战-成功",
        "success",
        "guild.remaining_conquest_0_of_2",
    )
    assert_outcome(
        nodes,
        "帮派活动挑战-已完成",
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

    assert_reachable(nodes, "帮派活动挑战-帮派-结果-胜利-探测", "帮派活动挑战-帮派-结果-关闭-探测")
    assert_reachable(
        nodes,
        "帮派活动挑战-帮派-结果-失败-探测",
        "帮派活动挑战-帮派-结果-失败-关闭-探测",
    )
    assert_reachable(
        nodes,
        "帮派活动挑战-帮派-结果-失败-关闭-探测",
        "帮派活动挑战-帮派-结果-失败",
    )
    assert_outcome(
        nodes,
        "帮派活动挑战-帮派-结果-失败",
        "failed",
        "guild.challenge_result_known",
    )
    assert_abort_code(nodes, "帮派活动挑战-帮派-结果-失败", "GUILD_RESULT_DEFEAT")
    assert_reachable(nodes, "帮派活动挑战-帮派-未知结果", "公共-通用中止")
    assert_abort_code(nodes, "帮派活动挑战-帮派-未知结果", "GUILD_RESULT_UNKNOWN")
    assert_abort_code(
        nodes,
        "帮派活动挑战-帮派-挑战-过渡-未知",
        "GUILD_CHALLENGE_TRANSITION_UNKNOWN",
    )
    assert_abort_code(nodes, "帮派活动挑战-帮派-危险-停止", "GUILD_DANGEROUS_PAGE")
    assert_abort_code(
        nodes,
        "帮派活动挑战-记录-失败",
        "GUILD_POSTCONDITION_MISSING",
    )
    assert_abort_code(
        nodes,
        "帮派活动挑战-帮派-退出-记录-失败",
        "GUILD_HOME_RETURN_FAILED",
    )

    failure_nodes = (
        "帮派活动挑战-帮派-挑战-过渡-未知",
        "帮派活动挑战-帮派-结果-失败",
        "帮派活动挑战-帮派-未知结果",
        "帮派活动挑战-帮派-危险-停止",
        "帮派活动挑战-记录-失败",
        "帮派活动挑战-帮派-退出-记录-失败",
        "帮派活动挑战-帮派-未知-页面",
    )
    for node_name in failure_nodes:
        assert nodes[node_name]["custom_action_param"]["native_fail_after_record"] is True


def test_guild_activity_result_partition_is_exact_mutually_exclusive_and_fail_closed() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    page = nodes["帮派活动挑战-帮派-结果-页面"]
    known = nodes["帮派活动挑战-帮派-结果-已知"]
    victory = nodes["帮派活动挑战-帮派-结果-胜利"]
    defeat = nodes["帮派活动挑战-帮派-结果-失败-2"]

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

    victory_probe = nodes["帮派活动挑战-帮派-结果-胜利-探测"]
    defeat_probe = nodes["帮派活动挑战-帮派-结果-失败-探测"]
    dismiss_probe = nodes["帮派活动挑战-帮派-结果-关闭-探测"]
    assert victory_probe["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-结果-页面", "帮派活动挑战-帮派-结果-胜利"],
        "box_index": 1,
    }
    assert victory_probe["on_error"] == ["帮派活动挑战-帮派-结果-失败-探测"]
    assert dismiss_probe["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-结果-页面", "帮派活动挑战-帮派-结果-胜利"],
        "box_index": 1,
    }
    assert dismiss_probe["custom_action"] == "GuardedInput"
    assert dismiss_probe["custom_action_param"]["fixed_click_mode"] == "guild_result_blank"
    assert dismiss_probe["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "帮派活动挑战-帮派-结果-页面",
        "target_name": "帮派活动挑战-帮派-结果-胜利",
    }
    assert defeat_probe["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-结果-失败-页面"],
        "box_index": 0,
    }
    assert defeat_probe["next"] == ["帮派活动挑战-帮派-结果-失败-关闭-探测"]
    assert defeat_probe["on_error"] == ["帮派活动挑战-帮派-未知结果"]

    defeat_dismiss_probe = nodes["帮派活动挑战-帮派-结果-失败-关闭-探测"]
    assert defeat_dismiss_probe["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-结果-失败-2", "帮派活动挑战-帮派-结果-失败-提升"],
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
            "page_name": "帮派活动挑战-帮派-结果-失败-2",
            "target_name": "帮派活动挑战-帮派-结果-失败-提升",
        },
    }
    assert defeat_dismiss_probe["next"] == ["帮派活动挑战-帮派-结果-失败"]
    assert defeat_dismiss_probe["on_error"] == ["帮派活动挑战-帮派-结果-失败"]

    defeat_page = nodes["帮派活动挑战-帮派-结果-失败-页面"]
    assert defeat_page["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-结果-失败-2", "帮派活动挑战-帮派-结果-失败-提升"],
        "box_index": 0,
    }
    improve = nodes["帮派活动挑战-帮派-结果-失败-提升"]
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
        "帮派活动挑战-帮派-结果-页面",
        "帮派活动挑战-帮派-结果-已知",
        "帮派活动挑战-帮派-结果-胜利",
        "帮派活动挑战-帮派-结果-失败-2",
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
    improve_roi = nodes["帮派活动挑战-帮派-结果-失败-提升"]["roi"]
    improve_x, improve_y, improve_width, improve_height = improve_roi
    assert improve_x <= improve_box[0]
    assert improve_y <= improve_box[1]
    assert improve_x + improve_width >= improve_box[0] + improve_box[2]
    assert improve_y + improve_height >= improve_box[1] + improve_box[3]
    assert improve_width <= 340
    assert improve_height <= 90


def test_guild_activity_world_boss_prepare_page_uses_live_same_frame_boundary() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    prepare = nodes["帮派活动挑战-帮派-挑战-准备-页面"]
    assert prepare["recognition"]["param"] == {
        "all_of": [
            "帮派活动挑战-帮派-挑战-准备-世界-首领-标题",
            "帮派活动挑战-帮派-挑战-准备-战斗-标题",
        ],
        "box_index": 1,
    }

    world_boss = nodes["帮派活动挑战-帮派-挑战-准备-世界-首领-标题"]
    assert world_boss["expected"] == "世界首领"
    assert world_boss["roi"] == [60, 0, 180, 80]

    battle_title = nodes["帮派活动挑战-帮派-挑战-准备-战斗-标题"]
    assert battle_title["expected"] == "首领战斗"
    assert battle_title["roi"] == [1020, 60, 220, 100]

    start = nodes["帮派活动挑战-帮派-挑战-开始-2"]
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

    for node_name in ("帮派活动挑战-帮派-挑战-准备-探测", "帮派活动挑战-帮派-挑战-开始"):
        assert nodes[node_name]["recognition"]["param"] == {
            "all_of": ["帮派活动挑战-帮派-挑战-准备-页面", "帮派活动挑战-帮派-挑战-开始-2"],
            "box_index": 1,
        }

    start_action = nodes["帮派活动挑战-帮派-挑战-开始"]
    assert start_action["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "帮派活动挑战-帮派-挑战-准备-页面",
        "target_name": "帮派活动挑战-帮派-挑战-开始-2",
    }


def test_guild_activity_post_result_checks_zero_before_reentering_bounded_loop() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    assert nodes["MJA_GUILD_POST_RESULT_PROBE"]["next"] == [
        "MJA_GUILD_FINAL_ZERO_PROBE",
        "帮派活动挑战-帮派-挑战-循环",
    ]
    assert "帮派活动挑战-帮派-挑战-准备-探测" in nodes[
        "帮派活动挑战-帮派-挑战-确认"
    ]["next"]


def test_guild_activity_accepts_live_battle_then_waits_without_input() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    start_next = nodes["帮派活动挑战-帮派-挑战-开始"]["next"]
    assert start_next == [
        "帮派活动挑战-帮派-结果-危险-探测",
        "帮派活动挑战-帮派-结果-校验-探测",
        "帮派活动挑战-帮派-战斗-进行中-探测",
        "帮派活动挑战-帮派-结果-胜利-探测",
        "帮派活动挑战-帮派-结果-失败-探测",
    ]

    battle = nodes["帮派活动挑战-帮派-战斗-进行中-探测"]
    assert battle["recognition"]["param"] == {
        "all_of": [
            "帮派活动挑战-帮派-挑战-战斗-计时器",
            "帮派活动挑战-帮派-挑战-战斗-首领",
            "帮派活动挑战-帮派-挑战-战斗-自动-顶部",
            "帮派活动挑战-帮派-挑战-战斗-暂停",
            "帮派活动挑战-帮派-挑战-战斗-自动-底部",
        ],
        "box_index": 0,
    }
    assert battle["action"] == "DoNothing"
    assert "custom_action" not in battle
    assert battle["timeout"] == 180000
    assert battle["retry_times"] == 0
    assert battle["next"] == [
        "帮派活动挑战-帮派-结果-危险-探测",
        "帮派活动挑战-帮派-结果-校验-探测",
        "帮派活动挑战-帮派-结果-胜利-探测",
        "帮派活动挑战-帮派-结果-失败-探测",
    ]
    assert battle["on_error"] == ["帮派活动挑战-帮派-未知结果"]

    expected_controls = {
        "帮派活动挑战-帮派-挑战-战斗-计时器": ("^\\d{2}:\\d{2}$", [170, 5, 120, 65]),
        "帮派活动挑战-帮派-挑战-战斗-首领": ("^\\d+级.+", [390, 0, 240, 60]),
        "帮派活动挑战-帮派-挑战-战斗-自动-顶部": ("自动中", [1090, 25, 100, 65]),
        "帮派活动挑战-帮派-挑战-战斗-暂停": ("暂停", [1175, 25, 80, 65]),
        "帮派活动挑战-帮派-挑战-战斗-自动-底部": ("自动中", [1130, 590, 130, 70]),
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

    page_probe = nodes["帮派活动挑战-页面-探测-2"]
    assert page_probe["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-活动-挑战-页面", "帮派活动挑战-帮派-活动-入口"],
        "box_index": 1,
    }
    assert page_probe["next"] == ["帮派活动挑战-帮派-打开-活动"]

    guild_home = nodes["帮派活动挑战-帮派-活动-挑战-页面"]
    assert guild_home["expected"] == "浮生城"
    assert guild_home["roi"] == [0, 0, 380, 100]

    activity_entry = nodes["帮派活动挑战-帮派-活动-入口"]
    assert activity_entry["expected"] == "帮会活动"
    assert activity_entry["roi"] == [600, 250, 360, 230]

    open_activity = nodes["帮派活动挑战-帮派-打开-活动"]
    assert open_activity["recognition"]["param"] == {
        "all_of": ["帮派活动挑战-帮派-活动-挑战-页面", "帮派活动挑战-帮派-活动-入口"],
        "box_index": 1,
    }
    assert open_activity["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "帮派活动挑战-帮派-活动-挑战-页面",
        "target_name": "帮派活动挑战-帮派-活动-入口",
    }


def test_guild_activity_terminal_outcomes_restore_home_before_recording() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    branches = (
        (
            "帮派活动挑战-帮派-初始-零-探测",
            "帮派活动挑战-帮派-已完成-退出-活动",
            "帮派活动挑战-帮派-已完成-退出-帮派-主页",
            "帮派活动挑战-帮派-已完成-退出-功能-面板-探测",
            "帮派活动挑战-帮派-已完成-退出-功能-面板",
            "帮派活动挑战-帮派-已完成-退出-主页-探测",
            "帮派活动挑战-已完成",
        ),
        (
            "MJA_GUILD_FINAL_ZERO_PROBE",
            "帮派活动挑战-帮派-成功-退出-活动",
            "帮派活动挑战-帮派-成功-退出-帮派-主页",
            "帮派活动挑战-帮派-成功-退出-功能-面板-探测",
            "帮派活动挑战-帮派-成功-退出-功能-面板",
            "帮派活动挑战-帮派-成功-退出-主页-探测",
            "帮派活动挑战-成功",
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
            "帮派活动挑战-帮派-退出-记录-失败",
        ]
        assert_reachable(nodes, source, home_probe)
        assert_reachable(nodes, source, outcome)

        first_close = nodes[exit_activity]
        assert first_close["recognition"]["param"] == {
            "all_of": [
                "帮派活动挑战-帮派-活动-页面",
                "帮派活动挑战-帮派-活动-上下文",
                "帮派活动挑战-帮派-页面-关闭",
            ],
            "box_index": 2,
        }
        assert first_close["custom_action"] == "GuardedInput"
        assert first_close["custom_action_param"]["action_id"] == ("exit_guild_activity")
        assert first_close["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 2,
            "page_name": "帮派活动挑战-帮派-活动-页面",
            "target_name": "帮派活动挑战-帮派-页面-关闭",
        }
        assert first_close["max_hit"] == 1
        assert first_close["retry_times"] == 0
        assert first_close["next"] == [exit_guild]
        assert first_close["on_error"] == ["帮派活动挑战-帮派-退出-记录-失败"]

        second_close = nodes[exit_guild]
        assert second_close["recognition"]["param"] == {
            "all_of": ["帮派活动挑战-帮派-主页-页面", "帮派活动挑战-帮派-页面-关闭"],
            "box_index": 1,
        }
        assert second_close["custom_action"] == "GuardedInput"
        assert second_close["custom_action_param"]["action_id"] == "exit_guild_home"
        assert second_close["max_hit"] == 1
        assert second_close["retry_times"] == 0
        assert second_close["next"] == [panel_probe]
        assert second_close["on_error"] == ["帮派活动挑战-帮派-退出-记录-失败"]

        outer_panel = nodes[panel_probe]
        assert outer_panel == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": ["公共-游戏侧边面板-打开"],
                    "box_index": 0,
                },
            },
            "timeout": 8000,
            "max_hit": 1,
            "action": "DoNothing",
            "next": [panel_close],
            "on_error": ["帮派活动挑战-帮派-退出-记录-失败"],
            "retry_times": 0,
        }

        third_close = nodes[panel_close]
        assert third_close["recognition"]["param"] == {
            "all_of": ["帮派活动挑战-帮派-功能-面板-页面", "帮派活动挑战-帮派-功能-面板-关闭"],
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
                "page_name": "帮派活动挑战-帮派-功能-面板-页面",
                "target_name": "帮派活动挑战-帮派-功能-面板-关闭",
            },
        }
        assert third_close["max_hit"] == 1
        assert third_close["retry_times"] == 0
        assert third_close["next"] == [home_probe]
        assert third_close["on_error"] == ["帮派活动挑战-帮派-退出-记录-失败"]

        home = nodes[home_probe]
        assert home["template"] == "home/home_marker.png"
        assert home["roi"] == [1040, 0, 240, 110]
        assert home["threshold"] == 0.75
        assert home["timeout"] == 8000
        assert home["max_hit"] == 1
        assert home["next"] == [outcome]
        assert home["on_error"] == ["帮派活动挑战-帮派-退出-记录-失败"]

    close = nodes["帮派活动挑战-帮派-页面-关闭"]
    assert close == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [125, 125, 125],
        "roi": [1180, 0, 100, 100],
        "connected": True,
        "count": 180,
        "action": "DoNothing",
    }

    assert nodes["帮派活动挑战-帮派-主页-页面"]["expected"] == "浮生城"
    assert nodes["帮派活动挑战-帮派-主页-页面"]["roi"] == [0, 0, 380, 100]

    assert nodes["帮派活动挑战-帮派-功能-面板-页面"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏侧边面板-打开"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }
    assert nodes["帮派活动挑战-帮派-功能-面板-关闭"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏侧边面板-打开"],
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
        "帮派活动挑战-帮派-功能-面板-页面"
    ]["threshold"]
    assert evidence["template_scores"]["panel_close"] >= nodes[
        "帮派活动挑战-帮派-功能-面板-关闭"
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
        "帮派活动挑战-帮派-已完成-退出-功能-面板"
    ]
    assert already_complete_close["custom_action_param"]["action_id"] == (
        "close_function_panel"
    )
    assert already_complete_close["next"] == [
        "帮派活动挑战-帮派-已完成-退出-主页-探测"
    ]


def test_all_guild_activity_failures_persist_then_fail_native() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    failures = {
        name: node
        for name, node in nodes.items()
        if name.startswith("帮派活动挑战-")
        and node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id")
        == GUILD_ACTIVITY.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert failures
    for name, node in failures.items():
        assert node["custom_action_param"]["native_fail_after_record"] is True, name
        assert node["Abort"] is True, name
        assert node["next"] == ["公共-通用中止"], name
        assert "on_error" not in node, name


def test_guild_activity_uses_live_huanjing_title_with_context() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    activity_page = nodes["帮派活动挑战-帮派-活动-页面"]
    assert activity_page["recognition"] == "OCR"
    assert activity_page["expected"] == "幻境征讨"
    assert activity_page["roi"] == [0, 0, 620, 190]

    activity_context = nodes["帮派活动挑战-帮派-活动-上下文"]
    assert activity_context["expected"] == ["讨伐中", "今日剩余征讨次数"]
    context_x, context_y, context_width, _ = activity_context["roi"]
    assert context_x > 0
    assert context_y >= 120
    assert context_x + context_width == 1280
    assert activity_context["roi"] != [200, 120, 900, 500]

    context_bound_nodes = (
        "帮派活动挑战-页面-探测",
        "帮派活动挑战-帮派-初始-零-探测",
        "帮派活动挑战-帮派-挑战-循环",
        "MJA_GUILD_POST_RESULT_PROBE",
        "MJA_GUILD_FINAL_ZERO_PROBE",
        "帮派活动挑战-帮派-已完成-退出-活动",
        "帮派活动挑战-帮派-成功-退出-活动",
    )
    for node_name in context_bound_nodes:
        all_of = nodes[node_name]["recognition"]["param"]["all_of"]
        assert "帮派活动挑战-帮派-活动-页面" in all_of
        assert "帮派活动挑战-帮派-活动-上下文" in all_of


def test_guild_activity_live_controls_cover_the_right_edge_without_full_screen_ocr() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)

    for remaining_name in (
        "帮派活动挑战-帮派-剩余-可用",
        "帮派活动挑战-帮派-剩余-任意",
        "帮派活动挑战-帮派-剩余-耗尽",
    ):
        remaining = nodes[remaining_name]
        x, y, width, height = remaining["roi"]
        assert x <= 1040
        assert x + width >= 1250
        assert y <= 600 < y + height
        assert width < 400
        assert height < 150
        assert remaining["roi"] != [300, 120, 700, 260]

    challenge = nodes["帮派活动挑战-帮派-挑战-目标"]
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
