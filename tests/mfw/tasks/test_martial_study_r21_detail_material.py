from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES

ROOT = Path(__file__).resolve().parents[3]
PIPELINE = (
    ROOT
    / "assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json"
)
MARTIAL = "MARTIAL_STUDY_BREAKTHROUGH_DAILY"


def _nodes() -> dict[str, dict]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_martial_only_claims_existing_success_cards() -> None:
    nodes = _nodes()
    policy = TASK_POLICIES[MARTIAL]
    expected_actions = {
        "open_function_panel": 1,
        "open_martial_study": 1,
        "claim_success_card": 3,
        "close_reward_popup": 3,
        "close_martial_page": 1,
    }

    guarded = [
        node
        for node in nodes.values()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == MARTIAL
    ]
    assert {
        node["custom_action_param"]["action_id"] for node in guarded
    } == set(expected_actions)
    assert nodes["MJA_MARTIAL_CLAIM_LOOP"]["max_hit"] == 3
    assert dict(policy.action_caps) == expected_actions
    assert policy.risk_levels == frozenset({"stateful"})


def test_martial_page_falls_back_to_success_without_entering_a_slot() -> None:
    nodes = _nodes()
    page = nodes["MJA_MARTIAL_PAGE_PROBE"]
    assert page["next"] == [
        "MJA_MARTIAL_CLAIM_GATE",
        "MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH",
    ]

    no_successful = nodes["MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH"]
    assert no_successful["recognition"] == {
        "type": "And",
        "param": {"all_of": ["martial.page"], "box_index": 0},
    }
    assert no_successful["action"] == "DoNothing"
    assert no_successful["next"] == ["MJA_MARTIAL_CLOSE_PAGE_FOR_SUCCESS"]
    close_page = nodes["MJA_MARTIAL_CLOSE_PAGE_FOR_SUCCESS"]
    assert close_page["custom_action_param"]["action_id"] == "close_martial_page"
    assert close_page["next"] == ["MJA_MARTIAL_FINAL_PANEL_PROBE"]
    assert nodes["MJA_MARTIAL_FINAL_PANEL_PROBE"]["next"] == [
        "MJA_MARTIAL_SUCCESS_NO_CLAIM"
    ]
    assert nodes["MJA_MARTIAL_SUCCESS_NO_CLAIM"]["custom_action_param"] == {
        "task_id": MARTIAL,
        "status": "success",
            "postcondition": "martial.successful_breakthroughs_claimed_or_none",
    }

    claim_gate = nodes["MJA_MARTIAL_CLAIM_GATE"]
    assert claim_gate["next"] == ["MJA_MARTIAL_CLAIM_LOOP"]
    assert nodes["MJA_MARTIAL_CLOSE_REWARD"]["next"] == [
        "MJA_MARTIAL_PAGE_PROBE"
    ]


def test_martial_pipeline_contains_no_plus_or_breakthrough_side_effects() -> None:
    nodes = _nodes()
    serialized = json.dumps(nodes, ensure_ascii=False)
    forbidden = (
        "martial.plus.",
        "martial.detail.",
        "martial.material",
        "open_martial_plus_slot",
        "study_martial_slot",
        "breakthrough_martial_slot",
        "confirm_martial_breakthrough",
    )
    for marker in forbidden:
        assert marker not in serialized

    assert nodes["MJA_MARTIAL_CLAIM_LOOP"]["max_hit"] == 3
    assert nodes["MJA_MARTIAL_CLAIM_LOOP_EXHAUSTED"][
        "custom_action_param"
    ] == {
        "task_id": MARTIAL,
        "status": "failed",
        "error_code": "MARTIAL_CLAIM_LIMIT",
        "postcondition": "martial.claim_state_known",
        "native_fail_after_record": True,
    }
