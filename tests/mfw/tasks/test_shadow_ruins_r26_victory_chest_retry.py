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


def test_r26_victory_chest_claim_has_one_distinct_retry_after_result_probes() -> None:
    """The first triplet can select the chest; the second opens its reward."""

    nodes = _nodes()
    first = nodes["MJA_SHADOW_CLAIM_VICTORY_CHEST_FIRST"]
    retry = nodes["MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY"]
    foreground = nodes["MJA_SHADOW_FOREGROUND_LOOP"]
    battle_cap = nodes["MJA_SHADOW_BATTLE_LOOP"]["max_hit"]

    assert first["max_hit"] == retry["max_hit"] == battle_cap
    assert first["retry_times"] == retry["retry_times"] == 0
    branches = first["next"]
    assert branches == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY",
    ]
    assert _first_matching_branch(
        branches,
        {
            "MJA_SHADOW_FINAL_PROBE": True,
            "MJA_SHADOW_REWARD_PROBE": True,
            "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE": True,
            "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY": True,
        },
    ) == "MJA_SHADOW_FINAL_PROBE"
    assert _first_matching_branch(
        branches,
        {
            "MJA_SHADOW_FINAL_PROBE": False,
            "MJA_SHADOW_REWARD_PROBE": True,
            "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE": True,
            "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY": True,
        },
    ) == "MJA_SHADOW_REWARD_PROBE"
    assert _first_matching_branch(
        branches,
        {
            "MJA_SHADOW_FINAL_PROBE": False,
            "MJA_SHADOW_REWARD_PROBE": False,
            "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE": True,
            "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY": True,
        },
    ) == "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE"
    assert _first_matching_branch(
        branches,
        {
            "MJA_SHADOW_FINAL_PROBE": False,
            "MJA_SHADOW_REWARD_PROBE": False,
            "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE": False,
            "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY": True,
        },
    ) == "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY"
    assert first["on_error"] == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_RECORD_FAILURE",
    ]
    assert retry["next"] == [
        "MJA_SHADOW_FINAL_PROBE",
        "MJA_SHADOW_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE",
        "MJA_SHADOW_VICTORY_CHEST_POST_RETRY_WAIT",
    ]
    assert "MJA_SHADOW_CLAIM_VICTORY_CHEST_FIRST" not in retry["next"]
    assert "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY" not in retry["next"]

    foreground_action = foreground["custom_action_param"]
    for claim in (first, retry):
        claim_action = claim["custom_action_param"]
        assert claim_action["action_id"] == "advance_shadow_foreground_triplet"
        assert claim_action["fixed_click_boxes"] == foreground_action["fixed_click_boxes"]
        assert claim_action["fixed_click_boxes"] == [
            [436, 536, 24, 24],
            [629, 536, 24, 24],
            [822, 536, 24, 24],
        ]

        claim_contract = json.dumps(claim, ensure_ascii=False)
        assert "transfer_shadow_stage" not in claim_contract
        assert "MJA_SHADOW_TRANSFER" not in claim_contract
        assert "shadow.transfer" not in claim_contract
