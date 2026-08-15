from __future__ import annotations

import json
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def _first_matching_branch(
    branches: list[str], matches: dict[str, bool]
) -> str | None:
    return next((branch for branch in branches if matches.get(branch, False)), None)


def test_mixed_completed_and_active_cards_prioritize_active_selection() -> None:
    """r7 saw 已击破 and three 可探索 cards in the same Maa OCR frame."""

    nodes = _nodes()
    branches = nodes["MJA_SHADOW_PAGE_PROBE"]["next"]

    assert "可探索" in nodes["shadow.active"]["expected"]
    assert "已击破" in nodes["shadow.no_active"]["expected"]
    assert branches == [
        "MJA_SHADOW_SELECT_ACTIVE",
        "MJA_SHADOW_STATUS_PROBE",
    ]
    assert _first_matching_branch(
        branches,
        {
            "MJA_SHADOW_SELECT_ACTIVE": True,
            "MJA_SHADOW_STATUS_PROBE": True,
        },
    ) == "MJA_SHADOW_SELECT_ACTIVE"


def test_completed_card_is_terminal_only_when_no_active_card_matches() -> None:
    nodes = _nodes()
    branches = nodes["MJA_SHADOW_PAGE_PROBE"]["next"]

    assert _first_matching_branch(
        branches,
        {
            "MJA_SHADOW_SELECT_ACTIVE": False,
            "MJA_SHADOW_STATUS_PROBE": True,
        },
    ) == "MJA_SHADOW_STATUS_PROBE"
    assert nodes["MJA_SHADOW_STATUS_PROBE"]["next"] == [
        "MJA_SHADOW_NO_ACTIVE_CARD"
    ]
    assert nodes["MJA_SHADOW_NO_ACTIVE_CARD"]["next"] == [
        "MJA_SHADOW_RESTART_SURFACE"
    ]
