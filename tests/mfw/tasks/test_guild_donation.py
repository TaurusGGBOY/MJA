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
    assert_native_terminal_contract,
    assert_no_side_effect_retry,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

DONATION = TaskContract("GUILD_DONATION_DAILY", "daily/guild_donation_daily.json")
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_PATH = (
    ROOT / "assets/resource/base/pipeline/daily/guild_donation_daily.json"
)


def _load_local_pipeline() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_guild_donation_uses_only_native_terminals() -> None:
    pipeline = _load_local_pipeline()
    nodes = load_task_nodes(DONATION)

    assert_no_custom_outcome_nodes(pipeline)
    assert "0698-帮派捐献-记录-失败" not in pipeline
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={"1365-公共-主页边界-失败"},
    )
    assert_native_terminal_contract(
        nodes,
        success_nodes=["1369-公共-通用停止", "帮派捐献-退出-停止"],
        failure_nodes=[
            "0687-帮派捐献-不可用",
            "0694-帮派捐献-计数-未知",
            "0695-帮派捐献-安全-停止",
            "0696-帮派捐献-付费-停止",
            "0697-帮派捐献-未知-弹窗-停止",
        ],
    )


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

    scoped = {
        name: node
        for name, node in _load_local_pipeline().items()
        if name.startswith("帮派捐献-")
        or node.get("custom_action_param", {}).get("task_id") == DONATION.task_id
    }
    assert not any(
        node.get("action") in {"Click", "Swipe", "MultiSwipe", "Key", "Input"}
        for node in scoped.values()
    )


def test_guild_donation_unavailable_is_a_native_failure() -> None:
    nodes = load_task_nodes(DONATION)
    unavailable_probe = nodes["0676-帮派捐献-不可用-探测"]
    assert unavailable_probe["next"] == ["0687-帮派捐献-不可用"]
    assert unavailable_probe["on_error"] == ["0677-帮派捐献-剩余-门禁"]
    assert_native_failure_node(nodes["0687-帮派捐献-不可用"])


def test_guild_donation_retains_surface_and_remaining_count_gates() -> None:
    nodes = load_task_nodes(DONATION)

    assert nodes["0667-帮派捐献-开始-安全-探测"]["next"] == [
        "0695-帮派捐献-安全-停止"
    ]
    assert nodes["0668-帮派捐献-开始-付费-探测"]["next"] == [
        "0696-帮派捐献-付费-停止"
    ]
    assert nodes["0669-帮派捐献-开始-未知-弹窗-探测"]["next"] == [
        "0697-帮派捐献-未知-弹窗-停止"
    ]
    assert nodes["0685-帮派捐献-之后-付费-探测"]["next"] == [
        "0696-帮派捐献-付费-停止"
    ]
    assert nodes["0686-帮派捐献-之后-未知-弹窗-探测"]["next"] == [
        "0697-帮派捐献-未知-弹窗-停止"
    ]
    assert_native_failure_node(nodes["0695-帮派捐献-安全-停止"])
    assert_native_failure_node(nodes["0696-帮派捐献-付费-停止"])
    assert_native_failure_node(nodes["0697-帮派捐献-未知-弹窗-停止"])

    remaining_10 = nodes["0707-帮派捐献-帮派-捐献-剩余-10-共-10"]
    remaining_9 = nodes["0708-帮派捐献-帮派-捐献-剩余-9-共-10"]
    invalid = nodes["0709-帮派捐献-帮派-捐献-剩余-无效"]
    assert "10\\s*/\\s*10" in remaining_10["expected"]
    assert "9\\s*/\\s*10" in remaining_9["expected"]
    assert "[0-8]\\s*/\\s*10" in invalid["expected"]
    assert nodes["0677-帮派捐献-剩余-门禁"]["next"] == [
        "0678-帮派捐献-剩余-9-探测",
        "0679-帮派捐献-剩余-10-探测",
        "0680-帮派捐献-剩余-无效-探测",
    ]
    assert_reachable(
        nodes,
        "0679-帮派捐献-剩余-10-探测",
        "0681-帮派捐献-捐献-免费",
    )
    assert_reachable(
        nodes,
        "0681-帮派捐献-捐献-免费",
        "0684-帮派捐献-后置条件-探测",
    )
    assert_native_failure_node(nodes["0694-帮派捐献-计数-未知"])

    donation = nodes["0681-帮派捐献-捐献-免费"]
    assert donation["custom_action_param"]["action_id"] == "donate_guild_free_once"
    assert donation["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 0,
        "page_name": "0705-帮派捐献-帮派-捐献-免费",
        "target_name": "0705-帮派捐献-帮派-捐献-免费",
    }
    assert donation["retry_times"] == 0


def test_guild_donation_success_and_already_complete_use_native_cleanup() -> None:
    nodes = load_task_nodes(DONATION)
    pipeline = _load_local_pipeline()

    for name in ("0688-帮派捐献-已完成", "0689-帮派捐献-成功"):
        assert pipeline[name] == {
            "recognition": "DirectHit",
            "action": "DoNothing",
            "timeout": 8000,
            "next": ["0690-帮派捐献-关闭-捐献"],
        }

    postcondition = nodes["0684-帮派捐献-后置条件-探测"]
    assert postcondition["next"] == ["0689-帮派捐献-成功"]
    assert nodes["0678-帮派捐献-剩余-9-探测"]["next"] == [
        "0688-帮派捐献-已完成"
    ]
    assert nodes["0693-帮派捐献-收尾-主页-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert nodes["0693-帮派捐献-收尾-主页-探测"]["on_error"] == [
        "帮派捐献-退出-停止"
    ]
    assert_native_success_node(nodes["帮派捐献-退出-停止"])
    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_guild_donation_cleanup_failure_stops_without_reclassifying_success() -> None:
    pipeline = _load_local_pipeline()
    for name in (
        "0690-帮派捐献-关闭-捐献",
        "0691-帮派捐献-关闭-帮派",
        "0692-帮派捐献-关闭-面板",
        "0693-帮派捐献-收尾-主页-探测",
    ):
        assert pipeline[name]["on_error"] == ["帮派捐献-退出-停止"]
    assert pipeline["帮派捐献-退出-停止"] == {
        "recognition": "DirectHit",
        "action": "StopTask",
    }
