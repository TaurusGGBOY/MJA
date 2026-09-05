from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from agent.custom.support.params import parse_action_params
from agent.custom.support.policy import TASK_POLICIES
from agent.custom.support.state import TaskRunStore
from tools.check_mfw_resources import load_pipeline_nodes

ROOT = Path(__file__).resolve().parents[1]


def test_native_policies_are_complete_and_mfw_only_extensions_are_explicit():
    expected_tasks = {
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
        "BUY_TEA_DAILY",
        "FREE_APPRAISAL_DAILY",
        "TRIAL_SWORD_DAILY",
        "HERO_DISPATCH_DAILY",
        "COLLECTION_DEPLOYMENT_DAILY",
        "WEEKLY_FREE_GIFT_DAILY",
        "SHADOW_RUINS_DAILY",
        "SPEND_CONDENSATE_DAILY",
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "EAT_STAMINA_FOOD_DAILY",
        "EQUIPMENT_DECOMPOSE_DAILY",
        "DUNGEON_SWEEP_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "RING_CHALLENGE_DAILY",
        "BREAK_ARRAY_MARTIAL_DAILY",
        "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "GUILD_AFFAIRS_DAILY",
        "GUILD_DONATION_DAILY",
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "BATTLE_PASS_REWARD_DAILY",
    }
    assert set(TASK_POLICIES) == expected_tasks
    assert {
        "BREAK_ARRAY_MARTIAL_DAILY",
        "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "GUILD_AFFAIRS_DAILY",
        "GUILD_DONATION_DAILY",
        "EQUIPMENT_DECOMPOSE_DAILY",
    } <= set(TASK_POLICIES)

    for task_id, policy in TASK_POLICIES.items():
        assert policy.task_id == task_id
        assert not hasattr(policy, "entry")
        assert not hasattr(policy, "order_hint")
        assert not hasattr(policy, "task_order")

    guild = TASK_POLICIES["GUILD_ACTIVITY_CHALLENGE_DAILY"]
    assert guild.label == "帮会活动征讨"
    assert guild.action_caps["challenge_guild_activity"] == 2
    assert guild.action_caps["dismiss_guild_result"] == 2
    assert guild.action_caps["dismiss_guild_defeat_result"] == 1
    assert guild.action_caps["dismiss_guild_activity_reward_popup"] == 4

    food = TASK_POLICIES["EAT_STAMINA_FOOD_DAILY"]
    assert food.action_caps["close_bag"] == 2

    jianlin = TASK_POLICIES["JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"]
    assert "dismiss_guild_defeat_result" not in jianlin.action_caps
    assert jianlin.action_caps["start_jianlin_battle"] > 0
    assert jianlin.action_caps["wait_jianlin_battle"] == 12

    affairs = TASK_POLICIES["GUILD_AFFAIRS_DAILY"]
    assert affairs.label == "帮会事务"
    assert affairs.action_caps["claim_guild_affairs_reward"] == 6
    assert affairs.action_caps["dismiss_guild_affairs_reward"] == 6
    assert "close_reward_popup" not in affairs.action_caps
    assert not any("refresh" in action for action in affairs.action_caps)

    donation = TASK_POLICIES["GUILD_DONATION_DAILY"]
    assert donation.label == "帮会捐献"
    assert donation.action_caps["donate_guild_free_once"] == 1
    assert set(donation.action_caps) == {
        "open_function_panel",
        "open_guild",
        "open_guild_donation",
        "open_android_function_panel",
        "open_android_guild",
        "open_android_guild_donation",
        "donate_guild_free_once",
        "donate_android_guild_free_once",
        "close_android_donation_reward",
        "close_guild_member",
        "close_guild_donation",
        "close_guild_home",
        "close_function_panel",
    }

    break_array = TASK_POLICIES["BREAK_ARRAY_MARTIAL_DAILY"]
    assert break_array.label == "破阵演武"
    assert break_array.risk_levels == frozenset({"combat"})
    assert break_array.max_steps == 448
    assert dict(break_array.action_caps) == {
        "open_break_array_activity": 1,
        "open_break_array_activity_item": 1,
        "open_break_array": 1,
        "resume_break_array": 1,
        "start_break_array_challenge": 9,
        "confirm_break_array_challenge": 9,
        "scroll_break_array_activity": 1,
        "scroll_break_array_activity_second": 1,
        "scroll_break_array_activity_reverse": 1,
        "start_break_array_battle": 9,
        "wait_break_array_battle": 360,
        "wait_break_array_result": 9,
        "resume_break_array_result": 1,
        "dismiss_break_array_result": 9,
        "close_break_array_page": 1,
        "close_break_array_activity": 1,
    }


def test_policy_values_are_immutable():
    policy = TASK_POLICIES["MAIL_REWARD_DAILY"]

    with pytest.raises(TypeError):
        policy.action_caps["claim_all_mail"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        TASK_POLICIES["OTHER"] = policy  # type: ignore[index]


def test_jianlin_guarded_input_surface_keeps_all_budgeted_actions() -> None:
    nodes = load_pipeline_nodes(ROOT / "assets/resource/base/pipeline")
    task_id = "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"
    guarded = [
        node
        for node in nodes.values()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == task_id
    ]

    assert len(guarded) == 16
    assert {node["custom_action_param"]["action_id"] for node in guarded} >= {
        "buy_stamina_once",
        "confirm_jianlin_stamina_purchase",
        "challenge_condensate",
        "start_jianlin_battle",
        "wait_jianlin_battle",
    }
    for node in guarded:
        params = node["custom_action_param"]
        assert params["task_id"] == task_id
        if params["action_id"] in {
            "buy_stamina_once",
            "confirm_jianlin_stamina_purchase",
            "challenge_condensate",
            "start_jianlin_battle",
            "wait_jianlin_battle",
        }:
            assert node.get("retry_times", 0) == 0


def test_action_counter_rejects_limit_plus_one_without_mutating_count():
    store = TaskRunStore()
    store.begin("MAIL_REWARD_DAILY")
    allowed = TASK_POLICIES["MAIL_REWARD_DAILY"].action_caps["claim_all_mail"]

    for _ in range(allowed):
        assert store.increment("MAIL_REWARD_DAILY", "claim_all_mail") == allowed

    with pytest.raises(PermissionError, match="action limit"):
        store.increment("MAIL_REWARD_DAILY", "claim_all_mail")

    assert store.snapshot("MAIL_REWARD_DAILY")["actions"]["claim_all_mail"] == allowed


def test_guild_affairs_reward_caps_reject_a_seventh_row() -> None:
    store = TaskRunStore()
    task_id = "GUILD_AFFAIRS_DAILY"
    store.begin(task_id)

    for action_id in (
        "claim_guild_affairs_reward",
        "dismiss_guild_affairs_reward",
    ):
        allowed = TASK_POLICIES[task_id].action_caps[action_id]
        assert allowed == 6
        for count in range(1, allowed + 1):
            assert store.increment(task_id, action_id) == count
        with pytest.raises(PermissionError, match="action limit"):
            store.increment(task_id, action_id)
        assert store.snapshot(task_id)["actions"][action_id] == allowed


def test_resource_counter_rejects_limit_plus_one_without_mutating_count():
    store = TaskRunStore()
    store.begin("BUY_TEA_DAILY")
    allowed = TASK_POLICIES["BUY_TEA_DAILY"].resource_caps["文"]

    assert store.consume_resource("BUY_TEA_DAILY", "文", allowed) == allowed
    with pytest.raises(PermissionError, match="resource limit"):
        store.consume_resource("BUY_TEA_DAILY", "文", 1)

    assert store.snapshot("BUY_TEA_DAILY")["resources"]["文"] == allowed


def test_dungeon_result_dismiss_is_visual_bound_and_preserves_postcondition():
    nodes = load_pipeline_nodes(ROOT / "assets/resource/base/pipeline")

    assert nodes["0370-副本扫荡-副本-结果"]["recognition"]["param"]["all_of"] == [
        "0371-副本扫荡-副本-结果-面板-界面",
        "0372-副本扫荡-副本-结果-面板-徽标",
    ]
    assert nodes["0332-副本扫荡-关闭-结果"]["recognition"]["param"]["all_of"] == [
        "0370-副本扫荡-副本-结果",
        "0373-副本扫荡-副本-结果-关闭",
    ]
    assert nodes["0332-副本扫荡-关闭-结果"]["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0370-副本扫荡-副本-结果",
        "target_name": "0373-副本扫荡-副本-结果-关闭",
    }
    assert TASK_POLICIES["DUNGEON_SWEEP_DAILY"].action_caps["dismiss_sweep_result"] == 20
    assert nodes["0332-副本扫荡-关闭-结果"]["next"] == ["0337-副本扫荡-成功-关闭"]
    assert nodes["0337-副本扫荡-成功-关闭"]["next"] == ["1371-公共-原生成功-主页边界"]
    assert "0333-MJA_DUNGEON_POST_PROBE" not in nodes


def test_action_and_resource_operations_require_known_started_task():
    store = TaskRunStore()

    with pytest.raises(KeyError, match="unknown task"):
        store.begin("UNKNOWN_TASK")
    with pytest.raises(RuntimeError, match="has not begun"):
        store.increment("MAIL_REWARD_DAILY", "claim_all_mail")


def test_parse_action_params_accepts_mfw_run_arg_and_normalizes_ids():
    class Argv:
        custom_action_param = (
            '{"task_id":" mail_reward_daily ","action_id":" CLAIM_ALL_MAIL ",'
            '"kind":"click","resource_id":" MAIL ",'
            '"evidence":{"page_index":0,"target_index":1}}'
        )

    params = parse_action_params(Argv())

    assert params["task_id"] == "MAIL_REWARD_DAILY"
    assert params["action_id"] == "claim_all_mail"
    assert params["kind"] == "click"
    assert params["resource_id"] == "MAIL"
    assert isinstance(params["evidence"], Mapping)


@pytest.mark.parametrize(
    "payload",
    [
        '{"task_id":"UNKNOWN","action_id":"claim_all_mail","kind":"click","evidence":{}}',
        '{"task_id":"MAIL_REWARD_DAILY","action_id":"unknown","kind":"click","evidence":{}}',
    ],
)
def test_parse_action_params_rejects_unknown_policy_members(payload: str):
    with pytest.raises(ValueError, match="unknown"):
        parse_action_params(payload)


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"task_id":"MAIL_REWARD_DAILY","action_id":"claim_all_mail","kind":"tap","evidence":{}}',
        '{"task_id":"MAIL_REWARD_DAILY","action_id":"claim_all_mail","kind":"click","evidence":[]}',
    ],
)
def test_parse_action_params_rejects_invalid_payload(payload: str):
    with pytest.raises(ValueError):
        parse_action_params(payload)


def test_guild_activity_start_click_requires_connected_visual_target() -> None:
    nodes = load_pipeline_nodes(ROOT / "assets/resource/base/pipeline")

    target = nodes["0576-帮派活动挑战-帮派-挑战-开始-2"]
    assert target["recognition"] == "ColorMatch"
    assert "expected" not in target
    assert target["method"] == 4
    assert target["roi"] == [1110, 555, 130, 130]
    assert target["connected"] is True
    assert target["count"] == 5000
    assert target["order_by"] == "Area"
    assert target["index"] == 0

    start = nodes["0537-帮派活动挑战-帮派-挑战-开始"]
    assert start["recognition"]["param"] == {
        "all_of": ["0573-帮派活动挑战-帮派-挑战-准备-页面", "0576-帮派活动挑战-帮派-挑战-开始-2"],
        "box_index": 1,
    }
    assert start["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0573-帮派活动挑战-帮派-挑战-准备-页面",
        "target_name": "0576-帮派活动挑战-帮派-挑战-开始-2",
    }


def test_guild_activity_start_wait_is_bounded_and_routes_exact_results() -> None:
    nodes = load_pipeline_nodes(ROOT / "assets/resource/base/pipeline")

    start = nodes["0537-帮派活动挑战-帮派-挑战-开始"]
    assert start["timeout"] == 300000
    assert start["retry_times"] == 0
    assert start["next"] == [
        "0583-帮派活动挑战-帮派-结果-胜利",
        "0584-帮派活动挑战-帮派-结果-失败-2",
    ]
    assert start["on_error"] == ["0590-帮派活动挑战-战斗结果-未知-失败"]
    assert all(nodes[name]["action"] == "DoNothing" for name in start["next"])


def test_guild_activity_result_detection_is_read_only_exact_and_fail_closed() -> None:
    nodes = load_pipeline_nodes(ROOT / "assets/resource/base/pipeline")

    for name in (
        "0582-帮派活动挑战-帮派-结果-页面",
        "0583-帮派活动挑战-帮派-结果-胜利",
        "0584-帮派活动挑战-帮派-结果-失败-2",
        "0585-帮派活动挑战-帮派-结果-失败-提升",
        "0586-帮派活动挑战-帮派-结果-失败-页面",
    ):
        assert nodes[name]["action"] == "DoNothing"

    assert nodes["0583-帮派活动挑战-帮派-结果-胜利"]["expected"] == r"^战斗胜利$"
    assert nodes["0584-帮派活动挑战-帮派-结果-失败-2"]["expected"] == r"^战斗失败$"
    assert nodes["0585-帮派活动挑战-帮派-结果-失败-提升"]["expected"] == (r"^可以通过以下途径提升$")
    assert nodes["0586-帮派活动挑战-帮派-结果-失败-页面"]["recognition"]["param"] == {
        "all_of": ["0584-帮派活动挑战-帮派-结果-失败-2", "0585-帮派活动挑战-帮派-结果-失败-提升"],
        "box_index": 0,
    }
    for name in ("0584-帮派活动挑战-帮派-结果-失败-2", "0585-帮派活动挑战-帮派-结果-失败-提升"):
        assert nodes[name]["roi"] != [0, 0, 1280, 720]
    assert nodes["0583-帮派活动挑战-帮派-结果-胜利"]["next"] == [
        "0547-帮派活动挑战-帮派-恭喜获得-关闭"
    ]
    assert nodes["0584-帮派活动挑战-帮派-结果-失败-2"]["next"] == [
        "0547-帮派活动挑战-帮派-恭喜获得-关闭"
    ]
