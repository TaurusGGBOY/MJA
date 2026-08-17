from __future__ import annotations

import json
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

AFFAIRS = TaskContract("GUILD_AFFAIRS_DAILY", "daily/guild_affairs_daily.json")
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_PATH = (
    ROOT
    / "assets/resource/base/pipeline/daily/guild_affairs_daily.json"
)
MFW_INTERFACE_PATH = ROOT / "assets/interface.json"


def test_guild_affairs_uses_a_private_namespace_and_shared_terminals_only() -> None:
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    assert all(
        name.startswith("帮派事务-")
        for name in pipeline
    )
    assert pipeline["帮派事务-主页-探测"]["on_error"] == [
        "帮派事务-打开-帮派"
    ]
    assert pipeline["帮派事务-付费-或-歧义"]["next"] == [
        "公共-通用中止"
    ]
    assert pipeline["帮派事务-关闭"]["next"] == [
        "帮派事务-退出-帮派-页面-探测"
    ]
    assert pipeline["帮派事务-退出-清理-停止"]["next"] == [
        "公共-通用中止"
    ]


def test_guild_affairs_is_an_independent_mfw_task_contract() -> None:
    assert_task_contract(AFFAIRS, require_game_start_recovery=True)
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
            "close_guild_affairs",
            "close_guild_home",
            "close_function_panel",
        ],
    )
    assert TASK_POLICIES[AFFAIRS.task_id].action_caps == {
        "open_function_panel": 1,
        "open_guild": 1,
        "open_guild_affairs": 1,
        "claim_guild_affairs_reward": 6,
        "dismiss_guild_affairs_reward": 6,
        "scroll_guild_affairs": 8,
        "start_guild_affairs": 6,
        "close_guild_affairs": 1,
        "close_guild_home": 1,
        "close_function_panel": 1,
    }
    assert_no_side_effect_retry(nodes, "claim_guild_affairs_reward")
    assert_no_side_effect_retry(nodes, "dismiss_guild_affairs_reward")
    assert_no_side_effect_retry(nodes, "start_guild_affairs")


def test_guild_affairs_claims_consecutive_rewards_before_starting_a_row() -> None:
    nodes = load_task_nodes(AFFAIRS)

    open_affairs = nodes["帮派事务-打开-事务"]
    assert open_affairs["recognition"]["param"]["all_of"] == [
        "帮派事务-帮派事务-帮派-页面",
        "帮派事务-帮派事务-事务-入口",
    ]
    claim_probe = nodes["帮派事务-首个-行-领取-探测"]
    start_probe = nodes["帮派事务-首个-行-开始-探测"]
    assert claim_probe["on_error"] == ["帮派事务-首个-行-开始-探测"]
    fallback_nodes = [
        "帮派事务-首个-行-进行中-探测",
        "帮派事务-空页面-探测",
        "帮派事务-无可刷新-探测",
        "帮派事务-记录-失败",
    ]
    assert start_probe["on_error"] == fallback_nodes
    assert nodes["帮派事务-事务-页面-探测"]["on_error"] == fallback_nodes
    assert nodes["帮派事务-首个-行-完成-探测"]["on_error"] == [
        "帮派事务-首个-行-进行中-探测",
        "帮派事务-空页面-探测",
        "帮派事务-无可刷新-探测",
        "帮派事务-记录-失败",
    ]
    in_progress = nodes["帮派事务-首个-行-进行中-探测"]
    assert in_progress["next"] == ["帮派事务-已在进行中"]
    assert in_progress["on_error"] == ["帮派事务-空页面-探测"]
    assert_outcome(
        nodes,
        "帮派事务-已在进行中",
        "already_complete",
        "guild.affairs.daily.all_rows_started_or_no_action",
    )
    assert nodes["帮派事务-空页面-探测"]["next"] == [
        "帮派事务-无可处理事务"
    ]
    assert_outcome(
        nodes,
        "帮派事务-无可处理事务",
        "already_complete",
        "guild.affairs.daily.all_rows_started_or_no_action",
    )
    assert nodes["帮派事务-无可刷新-探测"]["next"] == [
        "帮派事务-无可处理事务"
    ]
    claim_action = nodes["帮派事务-领取-首个-行-奖励"]
    assert claim_action["recognition"]["param"] == {
        "all_of": [
            "帮派事务-帮派事务-事务-页面",
            "帮派事务-帮派事务-首个-行-可领取",
        ],
        "box_index": 1,
    }
    assert claim_action["next"] == [
        "帮派事务-领取-奖励-探测"
    ]
    assert claim_action["max_hit"] == 6
    assert nodes["帮派事务-关闭-奖励"]["next"] == [
        "帮派事务-首个-行-付费-防护",
        "帮派事务-首个-行-领取-探测",
        "帮派事务-首个-行-开始-探测",
        "帮派事务-首个-行-完成-探测",
    ]
    assert_reachable(
        nodes,
        "帮派事务-开始-首个-行",
        "帮派事务-首个-行-完成-探测",
    )
    assert_outcome(
        nodes,
        "帮派事务-已完成",
        "success",
        "guild.affairs.daily.all_rows_started_or_no_action",
    )
    assert_outcome(
        nodes,
        "帮派事务-成功",
        "success",
        "guild.affairs.daily.all_rows_started_or_no_action",
    )

    for row_index in range(1, 4):
        prefix = f"帮派事务-行{row_index}"
        assert_reachable(nodes, AFFAIRS.entry, f"{prefix}-付费-防护")
        assert nodes[f"{prefix}-开始"]["custom_action_param"]["action_id"] == (
            "start_guild_affairs"
        )
        assert nodes[f"{prefix}-开始"]["custom_action_param"]["evidence"][
            "row_index"
        ] == row_index
    assert nodes["帮派事务-行3-完成-探测"]["next"] == [
        "帮派事务-已完成"
    ]


def test_guild_affairs_normalizes_only_the_verified_claim_result_overlay() -> None:
    nodes = load_task_nodes(AFFAIRS)
    probe = nodes["帮派事务-领取-奖励-探测"]
    close = nodes["帮派事务-关闭-奖励"]

    expected_boundary = [
        "帮派事务-帮派事务-奖励-弹窗",
        "帮派事务-帮派事务-奖励-弹窗-关闭",
    ]
    assert probe["recognition"]["param"] == {
        "all_of": expected_boundary,
        "box_index": 1,
    }
    assert probe["timeout"] == 8_000
    assert probe["on_error"] == [
        "帮派事务-首个-行-进行中-探测",
        "帮派事务-空页面-探测",
        "帮派事务-无可刷新-探测",
        "帮派事务-记录-失败",
    ]

    assert close["recognition"]["param"] == {
        "all_of": expected_boundary,
        "box_index": 1,
    }
    assert close["custom_action_param"]["action_id"] == (
        "dismiss_guild_affairs_reward"
    )
    assert close["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "帮派事务-帮派事务-奖励-弹窗",
        "target_name": "帮派事务-帮派事务-奖励-弹窗-关闭",
    }
    assert close["retry_times"] == 0
    assert close["max_hit"] == 6
    assert close["post_delay"] == 500

    popup = nodes["帮派事务-帮派事务-奖励-弹窗"]
    prompt = nodes["帮派事务-帮派事务-奖励-弹窗-关闭"]
    assert popup["recognition"] == "TemplateMatch"
    assert popup["template"] == (
        "daily/GUILD_AFFAIRS_DAILY/reward_popup_live.png"
    )
    assert popup["roi"] == [120, 180, 180, 380]
    assert popup["threshold"] == 0.78
    assert prompt["recognition"] == "TemplateMatch"
    assert prompt["template"] == (
        "daily/GUILD_AFFAIRS_DAILY/reward_popup_close_live.png"
    )
    assert prompt["roi"] == [450, 600, 400, 120]
    assert prompt["threshold"] == 0.72


def test_guild_affairs_clicks_only_the_verified_first_row_and_rejects_paid_state() -> None:
    nodes = load_task_nodes(AFFAIRS)

    assert nodes["帮派事务-帮派事务-首个-行-可领取"]["expected"] == "领取奖励"
    assert nodes["帮派事务-帮派事务-首个-行-可开始"]["expected"] == "开始事务"
    assert nodes["帮派事务-帮派事务-首个-行-可领取"]["roi"] == [930, 150, 300, 120]
    assert nodes["帮派事务-帮派事务-首个-行-可开始"]["roi"] == [930, 150, 300, 120]
    assert nodes["帮派事务-帮派事务-首个-行-付费"]["roi"] == [930, 150, 300, 120]
    no_action = nodes["帮派事务-帮派事务-首个-行-无-动作"]
    assert no_action["roi"] == [1040, 95, 180, 70]
    assert "进行中" in no_action["expected"]
    in_progress_marker = nodes["帮派事务-帮派事务-首个-行-进行中"]
    assert in_progress_marker["roi"] == [800, 80, 400, 180]
    assert "事务进行中" in in_progress_marker["expected"]

    # The r17 Android frame placed `事务进行中` at [1062, 113, 106, 23].
    # Keep the postcondition inside the first row's right-hand status capsule;
    # it must not expand into another row, the page body, or the paid refresh UI.
    status_x, status_y, status_width, status_height = no_action["roi"]
    assert status_x <= 1062
    assert status_y <= 113
    assert status_x + status_width >= 1062 + 106
    assert status_y + status_height >= 113 + 23
    assert status_x >= 930
    assert status_y + status_height < 217

    for node_name in (
        "帮派事务-领取-首个-行-奖励",
        "帮派事务-开始-首个-行",
    ):
        evidence = nodes[node_name]["custom_action_param"]["evidence"]
        assert evidence["row_index"] == 0
        assert evidence["row_roi"] == [50, 150, 1180, 150]
        assert evidence["target_roi"] == [930, 150, 300, 120]

    assert nodes["帮派事务-首个-行-付费-防护"]["next"] == [
        "帮派事务-付费-或-歧义"
    ]
    action_ids = {
        node.get("custom_action_param", {}).get("action_id")
        for node in nodes.values()
    }
    click_targets = {
        node.get("custom_action_param", {}).get("evidence", {}).get("target_name")
        for node in nodes.values()
        if node.get("custom_action_param", {}).get("kind") == "click"
    }
    assert "refresh_guild_affairs" not in action_ids
    assert "refresh_guild_affairs_with_currency" not in action_ids
    assert "帮派事务-帮派事务-首个-行-付费" not in click_targets
    assert_abort_code(
        nodes,
        "帮派事务-付费-或-歧义",
        "GUILD_FIRST_ROW_PAID_OR_AMBIGUOUS",
    )
    assert_abort_code(
        nodes,
        "帮派事务-记录-失败",
        "GUILD_AFFAIRS_POSTCONDITION_MISSING",
    )


def test_guild_affairs_android_mfw_uses_the_canonical_base_pipeline() -> None:
    interface = json.loads(MFW_INTERFACE_PATH.read_text(encoding="utf-8"))
    android_resource = next(
        resource
        for resource in interface["resource"]
        if resource["name"] == "mja_android"
    )

    assert android_resource["controller"] == ["android"]
    assert android_resource["path"] == ["./resource/base"]


def test_guild_home_probe_matches_the_android_guild_home_evidence() -> None:
    nodes = load_task_nodes(AFFAIRS)
    expected = ["帮会名帖", "成员数量", "活跃度"]

    for node_name in (
        "帮派事务-帮派-页面-探测",
        "帮派事务-帮派事务-帮派-页面",
        "帮派事务-退出-帮派-页面-探测",
    ):
        assert nodes[node_name]["expected"] == expected
        assert nodes[node_name]["roi"] == [0, 180, 380, 300]

    assert nodes["帮派事务-帮派事务-事务-入口"]["expected"] == "帮会事务"
    assert nodes["帮派事务-帮派事务-事务-入口"]["roi"] == [900, 230, 330, 170]
    assert nodes["帮派事务-事务-页面-探测"]["roi"] == [
        0,
        0,
        1280,
        240,
    ]


def test_guild_affairs_launcher_recovery_is_single_shot_and_truthful() -> None:
    nodes = load_task_nodes(AFFAIRS)
    start = nodes["帮派事务-任务入口"]

    assert start["timeout"] == 8000
    assert start["next"] == [
        "帮派事务-事务-页面-探测",
        "帮派事务-帮派-页面-探测",
        "帮派事务-主页-探测",
        "帮派事务-打开-帮派",
    ]
    assert start["on_error"] == [
        "[JumpBack]启动-游戏启动",
        "帮派事务-记录-失败",
    ]
    assert "帮派事务-游戏启动恢复" not in nodes
    assert "帮派事务-恢复-状态-探测" not in nodes


def test_guild_affairs_recovery_delegates_to_shared_startup() -> None:
    nodes = load_task_nodes(AFFAIRS)
    assert nodes["帮派事务-任务入口"]["on_error"][0] == (
        "[JumpBack]启动-游戏启动"
    )


def test_guild_affairs_terminal_cleanup_is_bounded_and_verifies_guild_home() -> None:
    nodes = load_task_nodes(AFFAIRS)
    close = nodes["帮派事务-关闭"]
    exit_probe = nodes["帮派事务-退出-帮派-页面-探测"]
    close_target = nodes["帮派事务-帮派事务-事务-关闭"]

    assert close["recognition"]["param"] == {
        "all_of": [
            "帮派事务-帮派事务-事务-页面",
            "帮派事务-帮派事务-事务-关闭",
        ],
        "box_index": 1,
    }
    assert close["max_hit"] == 1
    assert close["retry_times"] == 0
    assert close["custom_action"] == "GuardedInput"
    assert close["custom_action_param"] == {
        "task_id": AFFAIRS.task_id,
        "action_id": "close_guild_affairs",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "帮派事务-帮派事务-事务-页面",
            "target_name": "帮派事务-帮派事务-事务-关闭",
        },
    }
    assert close["next"] == ["帮派事务-退出-帮派-页面-探测"]
    assert close["on_error"] == ["帮派事务-记录-失败"]

    # The archived r18 frame has the affairs X at [1205, 30, 31, 30]. Reuse
    # the proven guild-page ColorMatch instead of the 0.563 template match.
    assert close_target == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [125, 125, 125],
        "roi": [1180, 0, 100, 100],
        "connected": True,
        "count": 180,
        "action": "DoNothing",
    }
    assert exit_probe["timeout"] == 5_000
    assert exit_probe["max_hit"] == 1
    assert exit_probe["next"] == ["帮派事务-关闭-帮派-主页"]
    assert exit_probe["on_error"] == ["帮派事务-退出-清理-停止"]
    assert nodes["帮派事务-关闭-帮派-主页"]["next"] == [
        "帮派事务-退出-面板-探测"
    ]
    assert nodes["帮派事务-退出-面板-探测"]["next"] == [
        "帮派事务-关闭-面板"
    ]
    assert nodes["帮派事务-关闭-面板"]["next"] == [
        "帮派事务-主页-之后-关闭-探测"
    ]
    assert nodes["帮派事务-主页-之后-关闭-探测"]["next"] == [
        "公共-主页边界"
    ]
    assert nodes["帮派事务-退出-清理-停止"]["next"] == [
        "公共-通用中止"
    ]

    close_actions = [
        node
        for node in nodes.values()
        if node.get("custom_action_param", {}).get("action_id")
        == "close_guild_affairs"
    ]
    assert close_actions == [close]
    assert TASK_POLICIES[AFFAIRS.task_id].action_caps["close_guild_affairs"] == 1


def test_guild_affairs_normal_outcomes_share_bounded_home_cleanup() -> None:
    nodes = load_task_nodes(AFFAIRS)

    for outcome_name in ("帮派事务-已完成", "帮派事务-成功"):
        outcome = nodes[outcome_name]
        assert outcome["custom_action_param"]["defer_home_boundary"] is True
        assert outcome["next"] == ["帮派事务-完成-收尾"]
        assert_reachable(nodes, outcome_name, "公共-主页边界")
        assert_reachable(nodes, outcome_name, "公共-通用停止")

    cleanup = nodes["帮派事务-完成-收尾"]
    assert cleanup == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "timeout": 8000,
        "max_hit": 1,
        "next": [
            "帮派事务-关闭",
            "帮派事务-退出-帮派-页面-探测",
            "帮派事务-退出-面板-探测",
            "帮派事务-主页-之后-关闭-探测",
        ],
        "on_error": ["帮派事务-记录-失败"],
    }
    assert nodes["帮派事务-主页-之后-关闭-探测"]["next"] == [
        "公共-主页边界"
    ]
    assert nodes["公共-主页边界"]["next"] == ["公共-通用停止"]
    assert nodes["公共-通用停止"] == {
        "recognition": "DirectHit",
        "action": "StopTask",
    }


def test_guild_affairs_android_has_no_duplicate_pipeline_override() -> None:
    assert not (
        ROOT
        / "assets/resource_android/pipeline/daily/guild_affairs_daily.json"
    ).exists()
