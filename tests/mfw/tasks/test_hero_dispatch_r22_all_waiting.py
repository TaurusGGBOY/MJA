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
        "hero.all_dispatch_slots_assigned": [51, 97, 74, 26],
        "hero.zero_completed_dispatches": [233, 101, 75, 20],
    }
    expected = {
        "hero.all_dispatch_slots_assigned": r"^任务\s*[:：]?\s*9\s*/\s*9$",
        "hero.zero_completed_dispatches": r"^已完成\s*[:：]?\s*0$",
    }

    for name, box in observed_boxes.items():
        assert base[name]["recognition"] == "OCR"
        assert base[name]["expected"] == expected[name]
        assert _contains(base[name]["roi"], box)

    assert base["hero.all_dispatched_waiting"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "hero.dispatch.page",
                "hero.all_dispatch_slots_assigned",
                "hero.zero_completed_dispatches",
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
    for name in (*observed_boxes, "hero.all_dispatched_waiting"):
        assert android[name] == base[name]


def test_claimable_wins_before_waiting_and_unknown_still_fails() -> None:
    nodes = load_task_nodes(HERO)
    page_probe = nodes["MJA_HERO_DISPATCH_PAGE_PROBE"]

    assert page_probe["next"] == [
        "MJA_HERO_INITIAL_CLAIM_GATE",
        "MJA_HERO_INITIAL_WAITING_GATE",
        "MJA_HERO_INITIAL_ALL",
        "MJA_HERO_INITIAL_PROGRESS",
        "MJA_HERO_INITIAL_NO_TASKS",
        "MJA_HERO_INITIAL_SELECT",
    ]
    assert page_probe["on_error"] == ["MJA_HERO_OPEN_DISPATCH"]
    assert nodes["MJA_HERO_INITIAL_CLAIM_GATE"]["next"] == [
        "MJA_HERO_INITIAL_CLAIM"
    ]


def test_waiting_sibling_is_finite_and_only_records_then_closes() -> None:
    nodes = load_task_nodes(HERO)
    gate = nodes["MJA_HERO_INITIAL_WAITING_GATE"]
    outcome = nodes["MJA_HERO_ALREADY_WAITING"]

    assert gate["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["hero.all_dispatched_waiting"],
            "box_index": 0,
        },
    }
    assert gate["action"] == "DoNothing"
    assert gate["max_hit"] == 1
    assert gate["retry_times"] == 0
    assert gate["next"] == ["MJA_HERO_ALREADY_WAITING"]
    assert gate["on_error"] == ["MJA_HERO_RECORD_FAILURE"]

    assert outcome["custom_action"] == "RecordTaskOutcome"
    assert outcome["custom_action_param"] == {
        "task_id": HERO.task_id,
        "status": "already_complete",
        "postcondition": "hero.all_dispatched_waiting",
    }
    assert outcome["max_hit"] == 1
    assert outcome["retry_times"] == 0
    assert outcome["next"] == ["MJA_HERO_CLOSE_DISPATCH"]

    forbidden = {
        "select_first_visible_dispatch",
        "claim_first_dispatch",
        "smart_configure_team",
        "dispatch_team",
    }
    waiting_route = (
        "MJA_HERO_INITIAL_WAITING_GATE",
        "MJA_HERO_ALREADY_WAITING",
        "MJA_HERO_CLOSE_DISPATCH",
        "MJA_HERO_CLOSE_PAINTING",
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
