"""Shared Android page markers and offline fixture recognition helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CapturedFrame, StateSnapshot, VisualEvidence

ANDROID_CAPTURE_SIZE = (1280, 720)

PAGE_MARKERS = {
    name: f"android.page.{name}"
    for name in (
        "home",
        "function_panel",
        "mail",
        "shop",
        "daily",
        "martial_study",
        "painting_scroll",
        "yanwu_world",
        "yunzhou",
        "universal_shop",
        "collection_deployment",
        "hero_dispatch",
        "shadow_ruins",
        "jianlin",
        "ring",
        "trial_sword",
        "appraisal",
        "dungeon",
    )
}


@dataclass(frozen=True, slots=True)
class FixtureManifest:
    path: Path
    capture_size: tuple[int, int]
    cases: dict[str, dict[str, Any]]
    task_id: str | None = None


def _strict_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown keys: {sorted(unknown)}")


def load_fixture_manifest(path: str | Path) -> FixtureManifest:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture manifest must be an object")
    _strict_keys(
        payload,
        {"capture_size", "schema_version", "task_id", "reference_size", "cases"},
        "fixture manifest",
    )
    if "schema_version" in payload and payload["schema_version"] not in {1, 2}:
        raise ValueError("fixture schema_version must be 1 or 2")
    raw_size = payload.get("reference_size", payload.get("capture_size", ANDROID_CAPTURE_SIZE))
    capture_size = tuple(raw_size)
    if capture_size != ANDROID_CAPTURE_SIZE:
        raise ValueError("fixture capture size must match Android 1280x720")
    raw_cases = payload.get("cases")
    if isinstance(raw_cases, dict):
        raw_cases = [dict(case, name=name) for name, case in raw_cases.items()]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("fixture manifest cases must be a non-empty list")
    cases: dict[str, dict[str, Any]] = {}
    allowed_case_keys = {
        "name",
        "image",
        "frame_id",
        "state",
        "page_hits",
        "target_hits",
        "danger_hits",
        "recognizer_frame_ids",
        "texts",
        "resource_hits",
        "expected_page",
        "expected_targets",
        "expected_status",
        "screenshot",
        "reason",
        "required_actions",
    }
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("fixture case must be an object")
        _strict_keys(raw_case, allowed_case_keys, "fixture case")
        name = raw_case.get("name")
        if not isinstance(name, str) or not name.strip() or name in cases:
            raise ValueError("fixture case names must be unique and non-empty")
        image_name = raw_case.get("image")
        if image_name is not None:
            image = manifest_path.parent / str(image_name)
            if not image.is_file():
                raise ValueError(f"fixture image does not exist: {image}")
            try:
                from PIL import Image

                with Image.open(image) as decoded:
                    if decoded.size != ANDROID_CAPTURE_SIZE:
                        raise ValueError("fixture image must be 1280x720")
            except ImportError as exc:  # pragma: no cover - Pillow is pinned in runtime.
                raise RuntimeError("Pillow is required to validate fixture images") from exc
        elif not raw_case.get("screenshot"):
            raise ValueError("fixture case must provide image or screenshot")
        cases[name] = dict(raw_case)
    task_id = payload.get("task_id")
    if task_id is not None and (not isinstance(task_id, str) or not task_id.strip()):
        raise ValueError("fixture task_id must be a non-empty string")
    return FixtureManifest(manifest_path, ANDROID_CAPTURE_SIZE, cases, task_id)


def recognize_fixture(manifest: FixtureManifest, case: str) -> StateSnapshot:
    """Turn a fixture case into evidence without importing or calling an input driver."""

    if not isinstance(manifest, FixtureManifest):
        raise TypeError("manifest must be a FixtureManifest")
    if case not in manifest.cases:
        raise KeyError(case)
    raw = manifest.cases[case]
    frame_id = raw.get("frame_id", f"fixture:{case}")
    expected_page = raw.get("expected_page")
    expected_targets = raw.get("expected_targets")
    page_hits = raw.get("page_hits", {})
    target_hits = raw.get("target_hits", {})
    danger_hits = raw.get("danger_hits", {})
    recognizer_frame_ids = raw.get("recognizer_frame_ids", {})
    if expected_page is not None:
        page_hits = {expected_page: 1}
    if expected_targets is not None:
        target_hits = {marker: 1 for marker in expected_targets}
        if "unknown_dialog" in expected_targets:
            danger_hits = {"unknown_dialog": 1}
    all_markers = (*page_hits, *target_hits, *danger_hits)
    if not recognizer_frame_ids:
        recognizer_frame_ids = {marker: frame_id for marker in all_markers}
    evidence = VisualEvidence(
        frame_id=frame_id,
        page_hits=page_hits,
        target_hits=target_hits,
        danger_hits=danger_hits,
        recognizer_frame_ids=recognizer_frame_ids,
        texts=tuple(raw.get("texts", ())),
        resource_hits=tuple(raw.get("resource_hits", ())),
    )
    return StateSnapshot(
        frame=CapturedFrame(frame_id, manifest.capture_size),
        state=raw.get("state", "fixture"),
        evidence=evidence,
    )


__all__ = [
    "ANDROID_CAPTURE_SIZE",
    "FixtureManifest",
    "PAGE_MARKERS",
    "load_fixture_manifest",
    "recognize_fixture",
]
