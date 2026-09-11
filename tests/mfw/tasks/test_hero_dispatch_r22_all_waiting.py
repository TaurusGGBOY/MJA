from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract, load_task_nodes

ROOT = Path(__file__).parents[3]
HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / HERO.pipeline_file
FIXTURE_ROOT = ROOT / "tests/fixtures/HERO_DISPATCH_DAILY"


def test_archived_frame_is_actionable_not_all_dispatched() -> None:
    fixture = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    case = fixture["cases"]["r22_all_dispatched_waiting"]
    assert case["target_hits"] == {"0746-英雄派遣-英雄-首个-任务-可派遣": 1}
    assert case["observed_text"] == "耗时:4小时"


def test_waiting_requires_positive_progress_and_rejects_actionable_row() -> None:
    nodes = load_task_nodes(HERO)
    conditions = nodes["0750-英雄派遣-英雄-全部-已派遣-等待中"]["recognition"]["param"]["all_of"]
    assert "0747-英雄派遣-英雄-首个-任务-中-进度" in conditions
    # Maa 5.12's And sub-recognizer ignores node-level inverse flags.
    # A timer only enters a bounded full-list review, never direct success.
    assert "0761-英雄派遣-英雄-首个-任务-无耗时" not in nodes
    assert "0745-英雄派遣-英雄-首个-任务-无完成派遣" not in nodes
    for name in ("0719-英雄派遣-初始-就已完成", "0721-英雄派遣-非初始-已完成"):
        assert nodes[name]["custom_action"] == "VerifyDispatchList"
        assert nodes[name]["on_error"] == ["MJA-公共-原生失败-返回主页"]
    assert "0744-英雄派遣-英雄-首个-任务-有时钟" not in conditions
    assert "英雄派遣-之后-无-完成无耗时" not in nodes
    assert nodes["0718-英雄派遣-初始-已完成决策"]["next"] == ["0720-英雄派遣-初始-决策中"]
    decision = nodes["0720-英雄派遣-初始-决策中"]["next"]
    assert decision.index("[JumpBack]0722-英雄派遣-初始-领取") < decision.index(
        "0721-英雄派遣-非初始-已完成"
    )
    assert decision.index("[JumpBack]0724-英雄派遣-初始-选择") < decision.index(
        "0721-英雄派遣-非初始-已完成"
    )


def test_waiting_route_does_not_use_claim_or_dispatch_actions() -> None:
    nodes = load_task_nodes(HERO)
    forbidden = {
        "select_first_visible_dispatch",
        "claim_first_dispatch",
        "smart_configure_team",
        "dispatch_team",
    }
    waiting_route = (
        "0719-英雄派遣-初始-就已完成",
        "0731-英雄派遣-已完成-全部",
        "0733-英雄派遣-关闭-派遣",
        "0734-英雄派遣-关闭-画卷",
    )
    action_ids = {
        nodes[name].get("custom_action_param", {}).get("action_id") for name in waiting_route
    }
    assert forbidden.isdisjoint(action_ids)
    assert action_ids == {None, "close_hero_dispatch", "close_hero_dispatch_painting"}
    assert TASK_POLICIES[HERO.task_id].action_caps["close_hero_dispatch"] == 1
    assert TASK_POLICIES[HERO.task_id].action_caps["close_hero_dispatch_painting"] == 1


def test_r22_pipeline_has_native_success_and_no_legacy_outcome() -> None:
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert_no_custom_outcome_nodes(pipeline)
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={"1372-公共-原生成功-尝试返回", "MJA-公共-原生失败-返回主页"},
    )
    assert pipeline["0731-英雄派遣-已完成-全部"]["action"] == "DoNothing"
    assert pipeline["0731-英雄派遣-已完成-全部"]["next"] == ["0733-英雄派遣-关闭-派遣"]
    assert pipeline["0735-英雄派遣-主页边界-探测"]["next"] == ["1371-公共-原生成功-主页边界"]
