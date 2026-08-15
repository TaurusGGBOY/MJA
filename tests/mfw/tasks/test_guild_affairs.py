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
        name.startswith("MJA_GUILD_AFFAIRS_DAILY_")
        or name.startswith("guild.affairs.daily.")
        for name in pipeline
    )
    assert pipeline["MJA_GUILD_AFFAIRS_DAILY_PANEL_PROBE"]["on_error"] == [
        "MJA_GUILD_AFFAIRS_DAILY_RECORD_FAILURE"
    ]
    assert pipeline["MJA_GUILD_AFFAIRS_DAILY_PAID_OR_AMBIGUOUS"]["next"] == [
        "MJA_COMMON_ABORT"
    ]
    assert pipeline["MJA_GUILD_AFFAIRS_DAILY_CLOSE"]["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_EXIT_GUILD_PAGE_PROBE"
    ]
    assert pipeline["MJA_GUILD_AFFAIRS_DAILY_EXIT_CLEANUP_STOP"]["next"] == [
        "MJA_COMMON_ABORT"
    ]


def test_guild_affairs_is_an_independent_mfw_task_contract() -> None:
    assert_task_contract(AFFAIRS, require_game_start_recovery=False)
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
        ],
    )
    assert TASK_POLICIES[AFFAIRS.task_id].action_caps == {
        "open_function_panel": 1,
        "open_guild": 1,
        "open_guild_affairs": 1,
        "claim_guild_affairs_reward": 6,
        "dismiss_guild_affairs_reward": 6,
        "start_guild_affairs": 4,
        "close_guild_affairs": 1,
    }
    assert_no_side_effect_retry(nodes, "claim_guild_affairs_reward")
    assert_no_side_effect_retry(nodes, "dismiss_guild_affairs_reward")
    assert_no_side_effect_retry(nodes, "start_guild_affairs")


def test_guild_affairs_claims_consecutive_rewards_before_starting_a_row() -> None:
    nodes = load_task_nodes(AFFAIRS)

    open_affairs = nodes["MJA_GUILD_AFFAIRS_DAILY_OPEN_AFFAIRS"]
    assert open_affairs["recognition"]["param"]["all_of"] == [
        "guild.affairs.daily.guild.page",
        "guild.affairs.daily.affairs.entry",
    ]
    claim_probe = nodes["MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_CLAIM_PROBE"]
    start_probe = nodes["MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_START_PROBE"]
    assert claim_probe["on_error"] == ["MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_START_PROBE"]
    assert start_probe["on_error"] == ["MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_DONE_PROBE"]
    claim_action = nodes["MJA_GUILD_AFFAIRS_DAILY_CLAIM_FIRST_ROW_REWARD"]
    assert claim_action["recognition"]["param"] == {
        "all_of": [
            "guild.affairs.daily.affairs.page",
            "guild.affairs.daily.first_row.claimable",
        ],
        "box_index": 1,
    }
    assert claim_action["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_CLAIM_REWARD_PROBE"
    ]
    assert claim_action["max_hit"] == 6
    assert nodes["MJA_GUILD_AFFAIRS_DAILY_CLOSE_REWARD"]["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_GATE"
    ]
    assert_reachable(
        nodes,
        "MJA_GUILD_AFFAIRS_DAILY_START_FIRST_ROW",
        "MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_POST_START_PROBE",
    )
    assert_outcome(
        nodes,
        "MJA_GUILD_AFFAIRS_DAILY_ALREADY_COMPLETE",
        "success",
        "guild.affairs.daily.all_rows_started_or_no_action",
    )
    assert_outcome(
        nodes,
        "MJA_GUILD_AFFAIRS_DAILY_SUCCESS",
        "success",
        "guild.affairs.daily.all_rows_started_or_no_action",
    )

    for row_index in range(1, 4):
        prefix = f"MJA_GUILD_AFFAIRS_DAILY_ROW{row_index}"
        assert_reachable(nodes, AFFAIRS.entry, f"{prefix}_GATE")
        assert nodes[f"{prefix}_START"]["custom_action_param"]["action_id"] == (
            "start_guild_affairs"
        )
        assert nodes[f"{prefix}_START"]["custom_action_param"]["evidence"][
            "row_index"
        ] == row_index
    assert nodes["MJA_GUILD_AFFAIRS_DAILY_ROW3_DONE_PROBE"]["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_SUCCESS"
    ]


def test_guild_affairs_normalizes_only_the_verified_claim_result_overlay() -> None:
    nodes = load_task_nodes(AFFAIRS)
    probe = nodes["MJA_GUILD_AFFAIRS_DAILY_CLAIM_REWARD_PROBE"]
    close = nodes["MJA_GUILD_AFFAIRS_DAILY_CLOSE_REWARD"]

    expected_boundary = [
        "guild.affairs.daily.reward.popup",
        "guild.affairs.daily.reward.popup.close",
    ]
    assert probe["recognition"]["param"] == {
        "all_of": expected_boundary,
        "box_index": 1,
    }
    assert probe["timeout"] == 8_000
    assert probe["on_error"] == ["MJA_GUILD_AFFAIRS_DAILY_RECORD_FAILURE"]

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
        "page_name": "guild.affairs.daily.reward.popup",
        "target_name": "guild.affairs.daily.reward.popup.close",
    }
    assert close["retry_times"] == 0
    assert close["max_hit"] == 6
    assert close["post_delay"] == 500

    popup = nodes["guild.affairs.daily.reward.popup"]
    prompt = nodes["guild.affairs.daily.reward.popup.close"]
    assert popup["recognition"] == "TemplateMatch"
    assert popup["template"] == (
        "daily/GUILD_AFFAIRS_DAILY/reward_popup_live.png"
    )
    assert popup["roi"] == [120, 180, 180, 380]
    assert popup["threshold"] == 0.39
    assert prompt["recognition"] == "TemplateMatch"
    assert prompt["template"] == (
        "daily/GUILD_AFFAIRS_DAILY/reward_popup_close_live.png"
    )
    assert prompt["roi"] == [450, 600, 400, 120]
    assert prompt["threshold"] == 0.36


def test_guild_affairs_clicks_only_the_verified_first_row_and_rejects_paid_state() -> None:
    nodes = load_task_nodes(AFFAIRS)

    assert nodes["guild.affairs.daily.first_row.claimable"]["expected"] == "领取奖励"
    assert nodes["guild.affairs.daily.first_row.startable"]["expected"] == "开始事务"
    assert nodes["guild.affairs.daily.first_row.claimable"]["roi"] == [930, 150, 300, 120]
    assert nodes["guild.affairs.daily.first_row.startable"]["roi"] == [930, 150, 300, 120]
    assert nodes["guild.affairs.daily.first_row.paid"]["roi"] == [930, 150, 300, 120]
    no_action = nodes["guild.affairs.daily.first_row.no_action"]
    assert no_action["roi"] == [1040, 95, 180, 70]
    assert "进行中" in no_action["expected"]

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
        "MJA_GUILD_AFFAIRS_DAILY_CLAIM_FIRST_ROW_REWARD",
        "MJA_GUILD_AFFAIRS_DAILY_START_FIRST_ROW",
    ):
        evidence = nodes[node_name]["custom_action_param"]["evidence"]
        assert evidence["row_index"] == 0
        assert evidence["row_roi"] == [50, 150, 1180, 150]
        assert evidence["target_roi"] == [930, 150, 300, 120]

    assert nodes["MJA_GUILD_AFFAIRS_DAILY_FIRST_ROW_PAID_GUARD"]["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_PAID_OR_AMBIGUOUS"
    ]
    assert nodes["MJA_GUILD_AFFAIRS_DAILY_AFTER_CLAIM_PAID_GUARD"]["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_PAID_OR_AMBIGUOUS"
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
    assert "guild.affairs.daily.first_row.paid" not in click_targets
    assert_abort_code(
        nodes,
        "MJA_GUILD_AFFAIRS_DAILY_PAID_OR_AMBIGUOUS",
        "GUILD_FIRST_ROW_PAID_OR_AMBIGUOUS",
    )
    assert_abort_code(
        nodes,
        "MJA_GUILD_AFFAIRS_DAILY_RECORD_FAILURE",
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
        "MJA_GUILD_AFFAIRS_DAILY_GUILD_PAGE_PROBE",
        "guild.affairs.daily.guild.page",
        "MJA_GUILD_AFFAIRS_DAILY_EXIT_GUILD_PAGE_PROBE",
    ):
        assert nodes[node_name]["expected"] == expected
        assert nodes[node_name]["roi"] == [0, 180, 380, 300]

    assert nodes["guild.affairs.daily.affairs.entry"]["expected"] == "帮会事务"
    assert nodes["guild.affairs.daily.affairs.entry"]["roi"] == [900, 230, 330, 170]
    assert nodes["MJA_GUILD_AFFAIRS_DAILY_AFFAIRS_PAGE_PROBE"]["roi"] == [
        0,
        0,
        1280,
        240,
    ]


def test_guild_affairs_launcher_recovery_is_single_shot_and_truthful() -> None:
    nodes = load_task_nodes(AFFAIRS)
    start = nodes["MJA_GUILD_AFFAIRS_DAILY_START"]
    recovery = nodes["MJA_GUILD_AFFAIRS_DAILY_GAME_START_RECOVERY"]
    wait = nodes["MJA_GUILD_AFFAIRS_DAILY_RECOVERY_STATE_PROBE"]

    assert start["timeout"] == 8000
    assert start["next"][-1] == "MJA_GUILD_AFFAIRS_DAILY_GAME_START_RECOVERY"
    assert start["on_error"] == [
        "MJA_GUILD_AFFAIRS_DAILY_GAME_START_RECOVERY",
        "MJA_GUILD_AFFAIRS_DAILY_RECORD_FAILURE",
    ]
    assert recovery["action"] == "StartApp"
    assert recovery["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert wait["timeout"] == 30_000
    assert wait["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_AFFAIRS_PAGE_PROBE",
        "MJA_GUILD_AFFAIRS_DAILY_GUILD_PAGE_PROBE",
        "MJA_GUILD_AFFAIRS_DAILY_HOME_PROBE",
        "MJA_GUILD_AFFAIRS_DAILY_PANEL_PROBE",
    ]
    assert "MJA_GUILD_AFFAIRS_DAILY_GAME_START_RECOVERY" not in wait["next"]
    assert wait["on_error"] == ["MJA_GUILD_AFFAIRS_DAILY_GAME_START_RECOVERY_FAILED"]
    assert_abort_code(
        nodes,
        "MJA_GUILD_AFFAIRS_DAILY_GAME_START_RECOVERY_FAILED",
        "GUILD_AFFAIRS_GAME_START_RECOVERY_EXHAUSTED",
    )
    assert (
        sum(
            name.startswith("MJA_GUILD_AFFAIRS_DAILY_")
            and node.get("action") == "StartApp"
            for name, node in nodes.items()
        )
        == 1
    )


def test_guild_affairs_recovery_does_not_delegate_to_shared_startup() -> None:
    nodes = load_task_nodes(AFFAIRS)
    assert nodes["MJA_GUILD_AFFAIRS_DAILY_RECOVERY_STATE_PROBE"]["next"] == [
        "MJA_GUILD_AFFAIRS_DAILY_AFFAIRS_PAGE_PROBE",
        "MJA_GUILD_AFFAIRS_DAILY_GUILD_PAGE_PROBE",
        "MJA_GUILD_AFFAIRS_DAILY_HOME_PROBE",
        "MJA_GUILD_AFFAIRS_DAILY_PANEL_PROBE",
    ]


def test_guild_affairs_terminal_cleanup_is_bounded_and_verifies_guild_home() -> None:
    nodes = load_task_nodes(AFFAIRS)
    close = nodes["MJA_GUILD_AFFAIRS_DAILY_CLOSE"]
    exit_probe = nodes["MJA_GUILD_AFFAIRS_DAILY_EXIT_GUILD_PAGE_PROBE"]
    close_target = nodes["guild.affairs.daily.affairs.close"]

    assert close["recognition"]["param"] == {
        "all_of": [
            "guild.affairs.daily.affairs.page",
            "guild.affairs.daily.affairs.close",
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
            "page_name": "guild.affairs.daily.affairs.page",
            "target_name": "guild.affairs.daily.affairs.close",
        },
    }
    assert close["next"] == ["MJA_GUILD_AFFAIRS_DAILY_EXIT_GUILD_PAGE_PROBE"]
    assert close["on_error"] == ["MJA_GUILD_AFFAIRS_DAILY_RECORD_FAILURE"]

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
    assert exit_probe["next"] == ["MJA_COMMON_STOP"]
    assert exit_probe["on_error"] == ["MJA_GUILD_AFFAIRS_DAILY_EXIT_CLEANUP_STOP"]
    assert nodes["MJA_GUILD_AFFAIRS_DAILY_EXIT_CLEANUP_STOP"]["next"] == [
        "MJA_COMMON_ABORT"
    ]

    close_actions = [
        node
        for node in nodes.values()
        if node.get("custom_action_param", {}).get("action_id")
        == "close_guild_affairs"
    ]
    assert close_actions == [close]
    assert TASK_POLICIES[AFFAIRS.task_id].action_caps["close_guild_affairs"] == 1


def test_guild_affairs_android_has_no_duplicate_pipeline_override() -> None:
    assert not (
        ROOT
        / "assets/resource_android/pipeline/daily/guild_affairs_daily.json"
    ).exists()
