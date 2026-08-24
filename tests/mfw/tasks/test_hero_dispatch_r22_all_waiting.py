from __future__ import annotations

import hashlib
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
FRAME_SHA256 = "cf76575cbcedfe7d91c7c4b140c5cd58fa3bc1e6b4c9d530dff923323d35e4fe"


def test_r22_fixture_keeps_archived_waiting_frame_evidence() -> None:
    fixture = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    case = fixture["cases"]["r22_all_dispatched_waiting"]
    image = FIXTURE_ROOT / case["image"]

    assert hashlib.sha256(image.read_bytes()).hexdigest() == FRAME_SHA256
    assert case["state"] == "inspect"
    assert case["frame_id"] == "r22:HERO_DISPATCH_DAILY:20260809T111556403782Z"
    assert case["page_hits"] == {"0742-英雄派遣-英雄-派遣-页面": 1}
    assert case["target_hits"] == {"0750-英雄派遣-英雄-全部-已派遣-等待中": 1}


def test_r22_waiting_marker_requires_the_dispatch_page_and_clock() -> None:
    nodes = load_task_nodes(HERO)
    assert nodes["0750-英雄派遣-英雄-全部-已派遣-等待中"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0742-英雄派遣-英雄-派遣-页面",
                "0744-英雄派遣-英雄-首个-任务-有时钟",
            ],
            "box_index": 1,
        },
    }
    assert nodes["0744-英雄派遣-英雄-首个-任务-有时钟"]["recognition"] == (
        "TemplateMatch"
    )
    assert nodes["0744-英雄派遣-英雄-首个-任务-有时钟"]["roi"] == [100, 170, 55, 45]
    assert nodes["0748-英雄派遣-英雄-零-派遣-任务"]["expected"] == (
        r"任务\s*[:：]?\s*0\s*/\s*12"
    )
    assert nodes["0749-英雄派遣-英雄-零-已完成-派遣任务"]["expected"] == (
        r"已完成\s*[:：]?\s*0"
    )
    assert nodes["0752-英雄派遣-英雄-无-已选择-派遣-任务"]["expected"] == (
        "尚未选择派遣任务"
    )


def test_waiting_and_no_dispatch_siblings_are_ordered_before_actions() -> None:
    nodes = load_task_nodes(HERO)
    assert nodes["0718-英雄派遣-初始-已完成决策"]["next"] == [
        "0719-英雄派遣-初始-就已完成",
        "0720-英雄派遣-初始-决策中",
    ]
    assert nodes["0720-英雄派遣-初始-决策中"]["next"] == [
        "[JumpBack]0722-英雄派遣-初始-领取",
        "[JumpBack]0724-英雄派遣-初始-选择",
        "英雄派遣-初始-无-任务",
        "0721-英雄派遣-非初始-已完成",
        "英雄派遣-之后-无-完成无耗时",
    ]
    assert nodes["英雄派遣-初始-无-任务"]["next"] == ["英雄派遣-成功-无-任务"]
    assert nodes["英雄派遣-之后-无-任务"]["next"] == ["英雄派遣-成功-无-任务"]
    assert nodes["0719-英雄派遣-初始-就已完成"]["next"] == [
        "0731-英雄派遣-已完成-全部"
    ]
    assert nodes["0721-英雄派遣-非初始-已完成"]["next"] == [
        "0730-英雄派遣-成功-进度"
    ]


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
        nodes[name].get("custom_action_param", {}).get("action_id")
        for name in waiting_route
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
        shared_targets={"1372-公共-原生成功-尝试返回"},
    )
    assert pipeline["0731-英雄派遣-已完成-全部"]["action"] == "DoNothing"
    assert pipeline["0731-英雄派遣-已完成-全部"]["next"] == [
        "0733-英雄派遣-关闭-派遣"
    ]
    assert pipeline["0735-英雄派遣-主页边界-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
