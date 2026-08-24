from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import assert_all_cycles_bounded
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

AFFAIRS = TaskContract("GUILD_AFFAIRS_DAILY", "daily/guild_affairs_daily.json")
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline/daily/guild_affairs_daily.json"


def _scoped_nodes() -> dict[str, dict]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_guild_affairs_is_a_native_task_with_the_current_entry_route() -> None:
    nodes = load_task_nodes(AFFAIRS)
    scoped = _scoped_nodes()
    entry = scoped["0011-帮派事务-任务入口"]

    assert_task_contract(AFFAIRS, require_game_start_recovery=False)
    assert entry["timeout"] == 5_000
    assert entry["next"] == ["0591-帮派事务-打开-面板"]
    assert entry["on_error"] == [
        "MJA-任务入口失败-GUILD_AFFAIRS_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert_reachable(nodes, AFFAIRS.entry, "1371-公共-原生成功-主页边界")
    assert_reachable(nodes, AFFAIRS.entry, "1369-公共-通用停止")


def test_guild_affairs_processes_exactly_four_visible_rows() -> None:
    nodes = _scoped_nodes()
    loop = nodes["0670-帮派事务-统一-处理-循环"]

    expected_branches = [
        "[JumpBack]0599-帮派事务-关闭-奖励",
        "[JumpBack]0597-帮派事务-领取-首个-行-奖励",
        "[JumpBack]0601-帮派事务-开始-首个-行",
        "[JumpBack]0605-帮派事务-行1-领取",
        "[JumpBack]0607-帮派事务-行1-开始",
        "[JumpBack]0611-帮派事务-行2-领取",
        "[JumpBack]0613-帮派事务-行2-开始",
        "[JumpBack]0617-帮派事务-行3-领取",
        "[JumpBack]0624-帮派事务-行3-开始",
        "0650-帮派事务-帮派事务-首个-行-进行中",
    ]
    assert loop["next"] == expected_branches

    action_nodes = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action_param", {}).get("action_id")
        in {"claim_guild_affairs_reward", "start_guild_affairs"}
        and node.get("custom_action_param", {}).get("evidence", {}).get("row_index", 0)
        < 4
    }
    assert {
        node["custom_action_param"]["evidence"]["row_index"]
        for node in action_nodes.values()
    } == {0, 1, 2, 3}
    assert all(node["max_hit"] == 4 for node in action_nodes.values())
    assert not any(
        target.endswith(("行4-领取", "行4-开始", "行5-领取", "行5-开始"))
        for target in loop["next"]
    )

    for name in (
        "0648-帮派事务-帮派事务-首个-行-可开始",
        "0655-帮派事务-帮派事务-行1-可开始",
        "0659-帮派事务-帮派事务-行2-可开始",
        "0663-帮派事务-帮派事务-行3-可开始",
    ):
        assert nodes[name]["expected"] == ["开始", "开始事务"]
    for name in (
        "0647-帮派事务-帮派事务-首个-行-可领取",
        "0654-帮派事务-帮派事务-行1-可领取",
        "0658-帮派事务-帮派事务-行2-可领取",
        "0662-帮派事务-帮派事务-行3-可领取",
    ):
        assert nodes[name]["expected"] == "领取奖励"


def test_guild_affairs_claims_or_starts_then_returns_to_the_four_row_scan() -> None:
    nodes = _scoped_nodes()

    assert nodes["0597-帮派事务-领取-首个-行-奖励"]["next"] == [
        "0599-帮派事务-关闭-奖励"
    ]
    assert nodes["0599-帮派事务-关闭-奖励"]["next"] == [
        "0670-帮派事务-统一-处理-循环"
    ]
    assert nodes["0599-帮派事务-关闭-奖励"]["on_error"] == [
        "0670-帮派事务-统一-处理-循环"
    ]
    for name in (
        "0601-帮派事务-开始-首个-行",
        "0607-帮派事务-行1-开始",
        "0613-帮派事务-行2-开始",
        "0624-帮派事务-行3-开始",
    ):
        assert nodes[name]["next"] == ["0670-帮派事务-统一-处理-循环"]
    for name in (
        "0605-帮派事务-行1-领取",
        "0611-帮派事务-行2-领取",
        "0617-帮派事务-行3-领取",
    ):
        assert nodes[name]["next"] == ["0599-帮派事务-关闭-奖励"]

    assert nodes["0670-帮派事务-统一-处理-循环"]["on_error"] == [
        "0689-帮派事务-向下滚动-到底",
        "0631-帮派事务-关闭",
    ]
    assert nodes["0650-帮派事务-帮派事务-首个-行-进行中"]["next"] == [
        "0631-帮派事务-关闭"
    ]
    assert nodes["0650-帮派事务-帮派事务-首个-行-进行中"]["roi"] == [
        800,
        80,
        400,
        580,
    ]


def test_guild_affairs_scrolls_from_the_fifth_row_upper_half_at_most_five_times() -> None:
    nodes = _scoped_nodes()
    scroll = nodes["0689-帮派事务-向下滚动-到底"]
    target = nodes["0688-帮派事务-事务-可滚动区域"]
    evidence = scroll["custom_action_param"]["evidence"]

    assert scroll["max_hit"] == 5
    assert scroll["on_error"] == ["0631-帮派事务-关闭"]
    assert target["roi"] == [50, 510, 1180, 80]
    assert evidence["target_name"] == "0688-帮派事务-事务-可滚动区域"
    assert evidence["dx"] == 0
    assert evidence["dy"] < -400
    assert evidence["duration_ms"] >= 350
    assert scroll["next"] == ["0670-帮派事务-统一-处理-循环"]


def test_guild_affairs_actions_are_guarded_and_cycles_are_bounded() -> None:
    nodes = load_task_nodes(AFFAIRS)
    assert_guarded_actions(
        nodes,
        AFFAIRS.task_id,
        [
            "open_function_panel",
            "open_guild",
            "open_guild_affairs",
            "claim_guild_affairs_reward",
            "dismiss_guild_affairs_reward",
            "start_guild_affairs",
            "scroll_guild_affairs",
            "close_guild_affairs",
            "close_guild_home",
            "close_function_panel",
        ],
    )
    assert_no_side_effect_retry(nodes, "claim_guild_affairs_reward")
    assert_no_side_effect_retry(nodes, "dismiss_guild_affairs_reward")
    assert_no_side_effect_retry(nodes, "start_guild_affairs")
    assert_no_side_effect_retry(nodes, "scroll_guild_affairs")
    assert_all_cycles_bounded(nodes)
    assert TASK_POLICIES[AFFAIRS.task_id].action_caps["scroll_guild_affairs"] >= 5
