from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from agent.workflows.definitions.break_array_martial_daily import (
    BREAK_ARRAY_MARTIAL_DAILY_DEFINITION as DEFINITION,
)
from agent.workflows.maa_android import MaaAndroidWorkflowDriver
from agent.workflows.models import (
    CapturedFrame,
    InputKind,
    StateSnapshot,
    TaskStatus,
    VisualEvidence,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "BREAK_ARRAY_MARTIAL_DAILY"
    / "r20_prepare_page.json"
)
R21_TRANSITION_FIXTURE_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "BREAK_ARRAY_MARTIAL_DAILY"
    / "r21_confirm_transition.json"
)
R22_VICTORY_FIXTURE_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "BREAK_ARRAY_MARTIAL_DAILY"
    / "r22_victory.json"
)
PIPELINE_PATH = (
    ROOT
    / "assets"
    / "resource"
    / "base"
    / "pipeline"
    / "daily"
    / "break_array_martial_daily.json"
)
CANONICAL_MAIN = Path("/Volumes/my_disk/project/MJA")


class _Job:
    succeeded = True

    def __init__(self, image):
        self.image = image

    def wait(self):
        return self

    def get(self):
        return self.image


class _Controller:
    def post_screencap(self):
        return _Job(np.zeros((720, 1280, 3), dtype=np.uint8))


class _OcrResult:
    def __init__(self, text: str):
        self.text = text


class _Detail:
    def __init__(self, hit: bool, box, text: str | None = None):
        self.hit = hit
        self.box = box
        self.filtered_results = [_OcrResult(text)] if text else []
        self.all_results = list(self.filtered_results)
        self.best_result = self.filtered_results[0] if self.filtered_results else None


class _Context:
    def __init__(self, fixture: dict):
        self.tasker = type("Tasker", (), {"controller": _Controller()})()
        self.fixture = fixture
        self.requested: list[str] = []
        self.battle = False

    def run_recognition(self, name, _image):
        self.requested.append(name)
        if self.battle:
            if name == "break_array.battle":
                return _Detail(True, (20, 20, 120, 50), "自动战斗")
            # Exercise the adapter's mutual-exclusion guard with a stale
            # orange-color target while an independently proven battle is live.
            if name == "break_array.prepare_start":
                return _Detail(True, (1111, 560, 126, 125))
            return _Detail(False, None)
        row = self.fixture["recognitions"].get(name, {})
        return _Detail(row.get("hit", False), row.get("box"), row.get("text"))


def _snapshot(frame, state: str, evidence: VisualEvidence) -> StateSnapshot:
    return StateSnapshot(frame, state, evidence=evidence)


def _confirm_snapshot() -> StateSnapshot:
    frame = CapturedFrame("r20-confirm", (1280, 720))
    hits = {
        "break_array.start_confirm_dialog": 1,
        "break_array.start_confirm_button": 1,
    }
    return StateSnapshot(
        frame,
        "confirm_break_array:9_of_9",
        evidence=VisualEvidence(
            frame.frame_id,
            hits,
            hits,
            {},
            {marker: frame.frame_id for marker in hits},
        ),
    )


def test_r20_live_prepare_fixture_matches_resource_boundaries_and_archive():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    for marker in (
        "break_array.prepare_formation",
        "break_array.prepare_boss",
        "break_array.prepare_duration",
        "break_array.prepare_tactics",
    ):
        assert re.fullmatch(
            pipeline[marker]["expected"],
            fixture["recognitions"][marker]["text"],
        )

    start = fixture["recognitions"]["break_array.prepare_start"]
    assert start["color_count"] >= pipeline["break_array.prepare_start"]["count"]
    battle_texts = fixture["recognitions"]["break_array.battle"]["texts"]
    assert not any(
        re.fullmatch(pattern, text)
        for pattern in pipeline["break_array.battle"]["expected"]
        for text in battle_texts
    )

    archived = CANONICAL_MAIN / fixture["source"]
    if archived.is_file():
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]


def test_r21_archive_is_a_confirm_transition_not_prepare_or_battle():
    fixture = json.loads(R21_TRANSITION_FIXTURE_PATH.read_text(encoding="utf-8"))
    observations = fixture["observations"]

    assert observations["dark_field_count"] >= observations["dark_field_threshold"]
    assert max(observations["rumor_glyph_counts"]) < observations[
        "rumor_glyph_threshold"
    ]
    assert observations["prepare_page"] is False
    assert observations["battle"] is False
    assert observations["prepare_start"] is False
    assert fixture["result"] == {
        "status": "failed",
        "error_code": "WORKFLOW_POSTCONDITION_MISSING",
    }
    assert fixture["action_trace"][-1] == "confirm_break_array_challenge"
    assert "start_break_array_battle" not in fixture["action_trace"]
    assert "wait_break_array_battle" not in fixture["action_trace"]

    archived = CANONICAL_MAIN / fixture["source"]
    if archived.is_file():
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]

    archived_result = CANONICAL_MAIN / fixture["result_source"]
    archived_trace = CANONICAL_MAIN / fixture["action_trace_source"]
    archived_ticket = CANONICAL_MAIN / fixture["ticket_source"]
    if archived_result.is_file() and archived_trace.is_file() and archived_ticket.is_file():
        result = json.loads(archived_result.read_text(encoding="utf-8"))
        trace = [
            json.loads(line)["action_id"]
            for line in archived_trace.read_text(encoding="utf-8").splitlines()
        ]
        ticket = json.loads(archived_ticket.read_text(encoding="utf-8"))
        assert result["status"] == fixture["result"]["status"]
        assert result["error_code"] == fixture["result"]["error_code"]
        assert trace == fixture["action_trace"]
        assert ticket["expected_tasks"] == [
            "GAME_START",
            "BREAK_ARRAY_MARTIAL_DAILY",
        ]

    frame = CapturedFrame("r21-confirm-transition", (1280, 720))
    evidence = VisualEvidence(
        frame.frame_id,
        {"break_array.confirm_transition": 1},
        {"break_array.confirm_transition": 1},
        {},
        {"break_array.confirm_transition": frame.frame_id},
    )
    decision = DEFINITION.decide(
        _snapshot(frame, "post_confirm_break_array:9_of_9", evidence),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert decision.status is TaskStatus.FAILED
    assert decision.transition is None


def test_r20_live_snapshot_maps_prepare_before_battle_and_preserves_sequence():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    context = _Context(fixture)
    driver = MaaAndroidWorkflowDriver(context)

    prepare_frame = driver.capture()
    prepare_evidence = driver.recognize(
        prepare_frame,
        DEFINITION.recognizers("post_confirm_break_array:9_of_9"),
    )
    assert "break_array.prepare_page" not in context.requested
    assert prepare_evidence.page_hits["break_array.prepare_page"] == 1
    assert prepare_evidence.target_hits["break_array.prepare_start"] == 1
    assert prepare_evidence.target_hits.get("break_array.battle", 0) == 0
    assert prepare_evidence.target_hits.get("break_array.battle_loading", 0) == 0

    confirm = DEFINITION.decide(
        _confirm_snapshot(),
        {"start_break_array_challenge": 1},
    )
    start = DEFINITION.decide(
        _snapshot(
            prepare_frame,
            "post_confirm_break_array:9_of_9",
            prepare_evidence,
        ),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )

    context.battle = True
    battle_frame = driver.capture()
    battle_evidence = driver.recognize(
        battle_frame,
        DEFINITION.recognizers("battle"),
    )
    assert battle_evidence.target_hits["break_array.battle"] == 1
    assert battle_evidence.target_hits.get("break_array.prepare_page", 0) == 0
    assert battle_evidence.target_hits.get("break_array.prepare_start", 0) == 0
    wait = DEFINITION.decide(
        _snapshot(battle_frame, "battle", battle_evidence),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
            "start_break_array_battle": 1,
        },
    )

    decisions = (confirm, start, wait)
    assert all(decision.transition is not None for decision in decisions)
    assert [decision.transition.intent.action_id for decision in decisions] == [
        "confirm_break_array_challenge",
        "start_break_array_battle",
        "wait_break_array_battle",
    ]
    assert start.transition.intent.input_kind is InputKind.CLICK
    assert wait.transition.intent.input_kind is InputKind.NONE


def test_r22_victory_uses_tight_same_frame_anchors_and_bounded_blank_close():
    fixture = json.loads(R22_VICTORY_FIXTURE_PATH.read_text(encoding="utf-8"))
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    for name in (
        "break_array.result.victory_title",
        "break_array.result.brand",
    ):
        node = pipeline[name]
        observed = fixture["recognitions"][name]
        assert re.fullmatch(node["expected"], observed["text"])
        rx, ry, rw, rh = node["roi"]
        bx, by, bw, bh = observed["box"]
        assert rx <= bx and ry <= by
        assert bx + bw <= rx + rw and by + bh <= ry + rh

    expected_same_frame = [
        "break_array.result.victory_title",
        "break_array.result.brand",
    ]
    for name in ("break_array.result", "break_array.success"):
        assert pipeline[name]["recognition"]["param"] == {
            "all_of": expected_same_frame,
            "box_index": 0,
        }

    archived = CANONICAL_MAIN / fixture["source"]
    if archived.is_file():
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]

    context = _Context(fixture)
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        (
            "break_array.result",
            "break_array.success",
            "break_array.failure",
            "break_array.result_close",
        ),
    )
    assert evidence.target_hits["break_array.result"] == 1
    assert evidence.target_hits["break_array.success"] == 1
    assert evidence.target_hits.get("break_array.failure", 0) == 0
    assert evidence.target_hits["break_array.result_close"] == 1
    assert driver._boxes["break_array.result_close"] == (
        frame.frame_id,
        (1040, 600, 160, 70),
    )

    counters = {
        "start_break_array_challenge": 1,
        "confirm_break_array_challenge": 1,
        "start_break_array_battle": 1,
    }
    resume = DEFINITION.decide(_snapshot(frame, "battle", evidence), counters)
    dismiss = DEFINITION.decide(_snapshot(frame, "result", evidence), counters)
    assert resume.transition is not None
    assert resume.transition.intent.action_id == "resume_break_array_result"
    assert dismiss.transition is not None
    assert dismiss.transition.intent.action_id == "dismiss_break_array_result"
    assert dismiss.transition.intent.target_marker == "break_array.result_close"
