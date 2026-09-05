from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_reachable,
    load_task_nodes,
)

ROOT = Path(__file__).parents[3]
BATTLE_PASS = TaskContract("BATTLE_PASS_REWARD_DAILY", "daily/battle_pass_reward_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / BATTLE_PASS.pipeline_file


def _scoped_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_r20_start_opens_battle_pass_directly_from_home() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    start = nodes["0001-战令奖励-任务入口"]
    assert start["next"] == ["0044-战令奖励-打开-战斗-战令"]
    assert start["on_error"] == [
        "MJA-任务入口失败-BATTLE_PASS_REWARD_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert "open_function_panel" not in TASK_POLICIES[BATTLE_PASS.task_id].action_caps


def test_r20_home_icon_is_gated_by_the_shared_home_surface() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    assert nodes["0075-战令奖励-战斗-战令-打开"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BATTLE_PASS_REWARD_DAILY/battle_pass_icon.png",
        "roi": [735, 10, 100, 90],
        "threshold": 0.8,
        "green_mask": True,
        "action": "DoNothing",
    }
    opened = nodes["0044-战令奖励-打开-战斗-战令"]
    assert opened["recognition"]["param"] == {
        "all_of": ["0070-战令奖励-战斗-战令-主页-页面", "0075-战令奖励-战斗-战令-打开"],
        "box_index": 1,
    }
    assert opened["next"] == ["0046-战令奖励-打开-任务"]


def test_r20_task_reward_claim_is_optional_and_bounded() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    assert nodes["0046-战令奖励-打开-任务"]["next"] == [
        "0048-战令奖励-任务-领取",
        "0054-战令奖励-打开-奖励",
    ]
    claim = nodes["0048-战令奖励-任务-领取"]
    assert claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0079-战令奖励-战斗-战令-任务",
        "target_name": "0082-战令奖励-战斗-战令-任务-奖励-领取",
    }
    assert claim["max_hit"] == 1 and claim["retry_times"] == 0
    assert claim["next"] == ["0052-战令奖励-任务-关闭-奖励"]
    assert nodes["0052-战令奖励-任务-关闭-奖励"]["next"] == ["0054-战令奖励-打开-奖励"]


def test_r20_basic_reward_paths_are_finite_and_converge_on_close() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    assert nodes["0054-战令奖励-打开-奖励"]["next"] == [
        "0057-战令奖励-基础-一键领取",
        "0056-战令奖励-基础-领取",
        "0063-战令奖励-关闭-成功",
    ]
    for name in ("0057-战令奖励-基础-一键领取", "0056-战令奖励-基础-领取"):
        claim = nodes[name]
        assert claim["max_hit"] == 1 and claim["retry_times"] == 0
        assert claim["next"] == ["0060-战令奖励-基础-关闭-奖励"]
        assert claim["on_error"] == ["0063-战令奖励-关闭-成功"]
    assert nodes["0060-战令奖励-基础-关闭-奖励"]["next"] == ["0063-战令奖励-关闭-成功"]


def test_r20_close_reaches_shared_native_success() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    close = nodes["0063-战令奖励-关闭-成功"]
    assert close["next"] == ["1371-公共-原生成功-主页边界"]
    assert close["max_hit"] == 1 and close["retry_times"] == 0
    assert_reachable(nodes, "1371-公共-原生成功-主页边界", "1369-公共-通用停止")
    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_r20_migrated_pipeline_has_only_native_terminals() -> None:
    scoped = _scoped_nodes()
    assert_no_custom_outcome_nodes(scoped)
    assert_on_error_contract(scoped, shared_targets={"1365-公共-主页边界-失败"})
    obsolete = {
        "0064-战令奖励-全部已领取",
        "0065-战令奖励-全部已领取-成功",
        "0066-战令奖励-任务-歧义",
        "0067-战令奖励-奖励-歧义",
        "0069-战令奖励-记录-失败",
    }
    assert obsolete.isdisjoint(scoped)


def test_r20_every_battle_pass_side_effect_is_non_retrying_and_capped() -> None:
    nodes = _scoped_nodes()
    policy = TASK_POLICIES[BATTLE_PASS.task_id]
    for action_id in policy.action_caps:
        assert_no_side_effect_retry(nodes, action_id)
    for node in nodes.values():
        params = node.get("custom_action_param", {})
        action_id = params.get("action_id")
        if params.get("task_id") == BATTLE_PASS.task_id and action_id in policy.action_caps:
            assert node["retry_times"] == 0
            assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
