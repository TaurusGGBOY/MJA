from __future__ import annotations

import json
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
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

DONATION = TaskContract("GUILD_DONATION_DAILY", "daily/guild_donation_daily.json")
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline/daily/guild_donation_daily.json"


def _pipeline() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_guild_donation_uses_only_native_terminals() -> None:
    pipeline = _pipeline()
    nodes = load_task_nodes(DONATION)
    assert_no_custom_outcome_nodes(pipeline)
    assert_on_error_contract(
        pipeline, local_nodes=set(pipeline), shared_targets={"1365-公共-主页边界-失败"}
    )
    for name in (
        "0687-帮派捐献-不可用",
        "0695-帮派捐献-安全-停止",
        "0696-帮派捐献-付费-停止",
        "0697-帮派捐献-未知-弹窗-停止",
        "0707-帮派捐献-帮派-捐献-剩余-10-共-10",
        "0714-帮派捐献-付费确认-安全失败",
    ):
        assert_native_failure_node(nodes[name])
    assert_reachable(nodes, "1371-公共-原生成功-主页边界", "1369-公共-通用停止")
    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_guild_donation_preserves_guarded_actions_and_safety_caps() -> None:
    assert_task_contract(DONATION, require_game_start_recovery=False)
    nodes = load_task_nodes(DONATION)
    action_ids = [
        "open_function_panel",
        "open_guild",
        "open_guild_donation",
        "donate_guild_free_once",
        "close_android_donation_reward",
        "close_guild_donation",
        "close_guild_home",
        "close_function_panel",
    ]
    assert_guarded_actions(nodes, DONATION.task_id, action_ids)
    assert TASK_POLICIES[DONATION.task_id].action_caps == {
        "open_function_panel": 1,
        "open_guild": 1,
        "open_guild_donation": 1,
        "open_android_function_panel": 1,
        "open_android_guild": 1,
        "open_android_guild_donation": 1,
        "donate_guild_free_once": 1,
        "donate_android_guild_free_once": 1,
        "close_android_donation_reward": 1,
        "close_guild_member": 1,
        "close_guild_donation": 1,
        "close_guild_home": 1,
        "close_function_panel": 1,
    }
    assert_no_side_effect_retry(nodes, "donate_guild_free_once")


def test_guild_donation_requires_free_button_and_stops_before_paid_repeat() -> None:
    nodes = load_task_nodes(DONATION)
    donation = nodes["0681-帮派捐献-捐献-免费"]
    assert donation["recognition"]["param"] == {
        "all_of": ["0705-帮派捐献-帮派-捐献-免费", "0715-帮派捐献-免费按钮-文字"],
        "box_index": 1,
    }
    assert donation["custom_action_param"]["action_id"] == "donate_guild_free_once"
    assert donation["max_hit"] == 1 and donation["retry_times"] == 0
    assert donation["next"] == [
        "0707-帮派捐献-帮派-捐献-剩余-10-共-10",
        "0708-帮派捐献-帮派-捐献-剩余-9-共-10",
        "0714-帮派捐献-付费确认-安全失败",
        "0683-帮派捐献-捐献-关闭-奖励",
    ]


def test_guild_donation_remaining_count_controls_cleanup() -> None:
    nodes = load_task_nodes(DONATION)
    remaining_10 = nodes["0707-帮派捐献-帮派-捐献-剩余-10-共-10"]
    remaining_9 = nodes["0708-帮派捐献-帮派-捐献-剩余-9-共-10"]
    invalid = nodes["0709-帮派捐献-帮派-捐献-剩余-无效"]
    assert "10\\s*/\\s*10" in remaining_10["expected"]
    assert "9\\s*/\\s*10" in remaining_9["expected"]
    assert "[0-8]\\s*/\\s*10" in invalid["expected"]
    assert_native_failure_node(remaining_10)
    assert remaining_9["next"] == ["0690-帮派捐献-关闭-捐献"]


def test_guild_donation_cleanup_reaches_shared_home_success() -> None:
    nodes = load_task_nodes(DONATION)
    assert nodes["0690-帮派捐献-关闭-捐献"]["next"] == ["0691-帮派捐献-关闭-帮派"]
    assert nodes["0691-帮派捐献-关闭-帮派"]["next"] == ["0692-帮派捐献-关闭-面板"]
    assert nodes["0692-帮派捐献-关闭-面板"]["next"] == ["1371-公共-原生成功-主页边界"]
    for name in ("0690-帮派捐献-关闭-捐献", "0691-帮派捐献-关闭-帮派", "0692-帮派捐献-关闭-面板"):
        assert "on_error" not in nodes[name]
