from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from agent.workflows.definitions.batch23 import HERO_DISPATCH_DAILY_DEFINITION
from agent.workflows.models import TaskStatus
from agent.workflows.navigation import load_fixture_manifest, recognize_fixture
from tests.mfw.task_contract import TaskContract, load_task_nodes

ROOT = Path(__file__).parents[3]
HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
FIXTURE = ROOT / "tests/fixtures/HERO_DISPATCH_DAILY/r22_all_dispatched_waiting.png"
FRAME_SHA256 = "cf76575cbcedfe7d91c7c4b140c5cd58fa3bc1e6b4c9d530dff923323d35e4fe"


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_r22_fixture_is_the_archived_waiting_frame_and_decides_noop() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FRAME_SHA256

    manifest = load_fixture_manifest(FIXTURE.parent / "manifest.json")
    snapshot = recognize_fixture(manifest, "r22_all_dispatched_waiting")
    decision = HERO_DISPATCH_DAILY_DEFINITION.decide(snapshot, {})

    assert snapshot.state == "inspect"
    assert snapshot.evidence is not None
    assert snapshot.evidence.frame_id == "r22:HERO_DISPATCH_DAILY:20260809T111556403782Z"
    assert decision.status is TaskStatus.ALREADY_COMPLETE
    assert decision.transition is None


def test_r22_waiting_marker_requires_all_same_frame_positive_evidence() -> None:
    base = load_task_nodes(HERO)
    observed_boxes = {
        "英雄派遣-英雄-全部-派遣-槽位-已分配": [51, 97, 74, 26],
        "英雄派遣-英雄-零-已完成-派遣任务": [233, 101, 75, 20],
    }
    expected = {
        "英雄派遣-英雄-全部-派遣-槽位-已分配": r"^任务\s*[:：]?\s*9\s*/\s*9$",
        "英雄派遣-英雄-零-已完成-派遣任务": r"^已完成\s*[:：]?\s*0$",
    }

    for name, box in observed_boxes.items():
        assert base[name]["recognition"] == "OCR"
        assert base[name]["expected"] == expected[name]
        assert _contains(base[name]["roi"], box)

    assert base["英雄派遣-英雄-全部-已派遣-等待中"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "英雄派遣-英雄-派遣-页面",
                "英雄派遣-英雄-全部-派遣-槽位-已分配",
                "英雄派遣-英雄-零-已完成-派遣任务",
            ],
            "box_index": 1,
        },
    }

    android = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/hero_dispatch_daily.json"
        ).read_text(encoding="utf-8")
    )
    for name in (*observed_boxes, "英雄派遣-英雄-全部-已派遣-等待中"):
        assert android[name] == base[name]


def test_claimable_wins_before_waiting_and_unknown_still_fails() -> None:
    nodes = load_task_nodes(HERO)
    page_probe = nodes["英雄派遣-派遣-页面-探测"]

    assert page_probe["next"] == [
        "英雄派遣-初始-领取-门禁",
        "英雄派遣-初始-等待中-门禁",
        "英雄派遣-初始-全部",
        "英雄派遣-初始-进度",
        "英雄派遣-初始-无-任务",
        "英雄派遣-初始-选择",
    ]
    assert page_probe["on_error"] == ["英雄派遣-打开-派遣"]
    assert nodes["英雄派遣-初始-领取-门禁"]["next"] == [
        "英雄派遣-初始-领取"
    ]


def test_waiting_sibling_is_finite_and_only_records_then_closes() -> None:
    nodes = load_task_nodes(HERO)
    gate = nodes["英雄派遣-初始-等待中-门禁"]
    outcome = nodes["英雄派遣-已完成-等待中"]

    assert gate["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["英雄派遣-英雄-全部-已派遣-等待中"],
            "box_index": 0,
        },
    }
    assert gate["action"] == "DoNothing"
    assert gate["max_hit"] == 1
    assert gate["retry_times"] == 0
    assert gate["next"] == ["英雄派遣-已完成-等待中"]
    assert gate["on_error"] == ["英雄派遣-记录-失败"]

    assert outcome["custom_action"] == "RecordTaskOutcome"
    assert outcome["custom_action_param"] == {
        "task_id": HERO.task_id,
        "status": "already_complete",
        "postcondition": "hero.all_dispatched_waiting",
    }
    assert outcome["max_hit"] == 1
    assert outcome["retry_times"] == 0
    assert outcome["next"] == ["英雄派遣-关闭-派遣"]

    forbidden = {
        "select_first_visible_dispatch",
        "claim_first_dispatch",
        "smart_configure_team",
        "dispatch_team",
    }
    waiting_route = (
        "英雄派遣-初始-等待中-门禁",
        "英雄派遣-已完成-等待中",
        "英雄派遣-关闭-派遣",
        "英雄派遣-关闭-画卷",
    )
    action_ids = {
        nodes[name].get("custom_action_param", {}).get("action_id")
        for name in waiting_route
    }
    assert forbidden.isdisjoint(action_ids)
    assert action_ids == {
        None,
        "close_hero_dispatch",
        "close_hero_dispatch_painting",
    }
    assert TASK_POLICIES[HERO.task_id].action_caps["close_hero_dispatch"] == 1
    assert TASK_POLICIES[HERO.task_id].action_caps[
        "close_hero_dispatch_painting"
    ] == 1

    for name in waiting_route:
        assert name not in nodes[name].get("next", [])
        assert name not in nodes[name].get("on_error", [])
