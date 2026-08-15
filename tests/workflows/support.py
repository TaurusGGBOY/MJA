"""Helpers for creating strict Android fixture manifests in tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from PIL import Image

from agent.safety import authorize_action
from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.models import (
    CapturedFrame,
    Recognition,
    StateSnapshot,
    VisualEvidence,
)


def write_fixture_manifest(root: Path, cases: list[dict[str, object]]) -> Path:
    image = root / "frame.png"
    Image.new("RGB", (1280, 720), "black").save(image)
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps({"capture_size": [1280, 720], "cases": cases}),
        encoding="utf-8",
    )
    return manifest


def snapshot(
    state: str,
    *markers: str,
    texts: tuple[str, ...] = (),
    danger_markers: tuple[str, ...] = (),
    resources: tuple[str, ...] = (),
) -> StateSnapshot:
    frame_id = "fixture-frame"
    hits = {marker: 1 for marker in markers}
    danger_hits = {marker: 1 for marker in danger_markers}
    all_markers = (*markers, *danger_markers)
    evidence = VisualEvidence(
        frame_id,
        hits,
        hits,
        danger_hits,
        {marker: frame_id for marker in all_markers},
        texts,
        resources,
    )
    recognitions = tuple(
        Recognition(marker, frame_id, 1, ((0, 0, 1, 1),)) for marker in all_markers
    )
    return StateSnapshot(
        CapturedFrame(frame_id, (1280, 720)),
        state,
        recognitions,
        evidence,
    )


def evaluate_decision(
    definition,
    state: str,
    markers: tuple[str, ...],
    counters: Mapping[str, int] | None = None,
    texts: tuple[str, ...] = (),
    danger_markers: tuple[str, ...] = (),
    resources: tuple[str, ...] = (),
):
    counts = {} if counters is None else counters
    current = snapshot(
        state,
        *markers,
        texts=texts,
        danger_markers=danger_markers,
        resources=resources,
    )
    decision = definition.decide(current, counts)
    safety = None
    if decision.transition is not None:
        safety = authorize_action(
            current.evidence,
            decision.transition.intent,
            TASK_POLICIES[definition.task_id],
            counts,
        )
    return decision, safety
