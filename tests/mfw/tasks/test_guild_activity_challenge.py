from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_all_cycles_bounded, assert_native_failure_node
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

GUILD_ACTIVITY = TaskContract(
    "GUILD_ACTIVITY_CHALLENGE_DAILY",
    "daily/guild_activity_challenge_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / GUILD_ACTIVITY.pipeline_file


def _nodes() -> dict[str, dict]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_guild_activity_keeps_the_native_entry_and_cleanup_route() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    scoped = _nodes()
    entry = scoped[GUILD_ACTIVITY.entry]

    assert_task_contract(GUILD_ACTIVITY, require_game_start_recovery=False)
    assert entry["timeout"] == 5_000
    assert entry["on_error"] == [
        "MJA-任务入口失败-GUILD_ACTIVITY_CHALLENGE_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert_reachable(nodes, GUILD_ACTIVITY.entry, "1371-公共-原生成功-主页边界")
    assert_reachable(nodes, GUILD_ACTIVITY.entry, "1369-公共-通用停止")


def test_guild_activity_clicks_challenge_then_start_and_waits_for_battle() -> None:
    nodes = _nodes()
    challenge = nodes["0533-帮派活动挑战-帮派-挑战-循环"]
    start = nodes["0537-帮派活动挑战-帮派-挑战-开始"]

    assert challenge["next"] == ["0537-帮派活动挑战-帮派-挑战-开始"]
    assert challenge["custom_action_param"]["action_id"] == "challenge_guild_activity"
    assert start["custom_action_param"]["action_id"] == "start_guild_challenge"
    assert start["timeout"] == 120_000
    assert start["next"] == [
        "0583-帮派活动挑战-帮派-结果-胜利",
        "0584-帮派活动挑战-帮派-结果-失败-2",
    ]
    assert start["on_error"] == [
        "0590-帮派活动挑战-战斗结果-未知-失败"
    ]


def test_guild_activity_uses_only_zero_in_the_scoped_remaining_counter_as_completion() -> None:
    nodes = _nodes()
    available = nodes["0569-帮派活动挑战-帮派-剩余-可用"]
    zero = nodes["0570-帮派活动挑战-帮派-剩余-耗尽"]
    already_done = nodes["0527-帮派活动挑战-帮派-已完成-退出-活动"]

    assert available["expected"] == ["^1$", "^2$"]
    assert available["roi"] == [1060, 540, 100, 100]
    assert zero["expected"] == "^0$"
    assert zero["roi"] == available["roi"]
    assert "0569-帮派活动挑战-帮派-剩余-可用" in nodes[
        "0533-帮派活动挑战-帮派-挑战-循环"
    ]["recognition"]["param"]["all_of"]
    assert "0570-帮派活动挑战-帮派-剩余-耗尽" in already_done[
        "recognition"
    ]["param"]["all_of"]
    assert already_done["next"] == [
        "0529-帮派活动挑战-帮派-已完成-退出-帮派-主页"
    ]
    assert already_done["custom_action_param"]["fixed_click_mode"] == (
        "guild_activity_close"
    )


def test_guild_activity_checks_zero_after_battle_cleanup_and_retries_only_bounded_challenge() -> None:
    nodes = _nodes()
    for name in (
        "0583-帮派活动挑战-帮派-结果-胜利",
        "0584-帮派活动挑战-帮派-结果-失败-2",
    ):
        assert nodes[name]["next"] == [
            "0547-帮派活动挑战-帮派-恭喜获得-关闭"
        ]
    close_reward = nodes["0547-帮派活动挑战-帮派-恭喜获得-关闭"]
    assert close_reward["next"] == [
        "0527-帮派活动挑战-帮派-已完成-退出-活动",
        "[JumpBack]0533-帮派活动挑战-帮派-挑战-循环",
    ]
    assert close_reward["on_error"] == close_reward["next"]
    assert nodes["0533-帮派活动挑战-帮派-挑战-循环"]["max_hit"] == 2


def test_guild_activity_unknown_battle_result_is_native_failure() -> None:
    nodes = _nodes()
    assert_native_failure_node(nodes["0590-帮派活动挑战-战斗结果-未知-失败"])
    assert nodes["0582-帮派活动挑战-帮派-结果-页面"]["timeout"] == 30_000


def test_guild_activity_actions_are_guarded_and_cycles_are_bounded() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    assert_guarded_actions(
        nodes,
        GUILD_ACTIVITY.task_id,
        [
            "open_function_panel",
            "open_guild",
            "open_guild_activity",
            "challenge_guild_activity",
            "start_guild_challenge",
            "dismiss_guild_activity_reward_popup",
            "exit_guild_activity",
            "exit_guild_home",
            "close_function_panel",
        ],
    )
    for action_id in (
        "challenge_guild_activity",
        "start_guild_challenge",
        "dismiss_guild_activity_reward_popup",
    ):
        assert_no_side_effect_retry(nodes, action_id)
    assert_all_cycles_bounded(nodes)
