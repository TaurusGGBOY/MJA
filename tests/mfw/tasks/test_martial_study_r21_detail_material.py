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
    assert nodes["武学突破-领取-循环"]["max_hit"] == 3
    assert dict(policy.action_caps) == expected_actions
    assert policy.risk_levels == frozenset({"stateful"})


def test_martial_page_falls_back_to_success_without_entering_a_slot() -> None:
    nodes = _nodes()
    page = nodes["武学突破-页面-探测"]
    assert page["next"] == [
        "武学突破-领取-门禁",
        "武学突破-无-成功-突破",
    ]

    no_successful = nodes["武学突破-无-成功-突破"]
    assert no_successful["recognition"] == {
        "type": "And",
        "param": {"all_of": ["武学突破-武学-页面"], "box_index": 0},
    }
    assert no_successful["action"] == "DoNothing"
    assert no_successful["next"] == ["武学突破-关闭-页面-用于-成功"]
    close_page = nodes["武学突破-关闭-页面-用于-成功"]
    assert close_page["custom_action_param"]["action_id"] == "close_martial_page"
    assert close_page["next"] == ["武学突破-最终-面板-探测"]
    assert nodes["武学突破-最终-面板-探测"]["next"] == [
        "武学突破-成功-无-领取"
    ]
    assert nodes["武学突破-成功-无-领取"]["custom_action_param"] == {
        "task_id": MARTIAL,
        "status": "success",
            "postcondition": "martial.successful_breakthroughs_claimed_or_none",
    }

    claim_gate = nodes["武学突破-领取-门禁"]
    assert claim_gate["next"] == ["武学突破-领取-循环"]
    assert nodes["武学突破-关闭-奖励"]["next"] == [
        "武学突破-页面-探测"
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

    assert nodes["武学突破-领取-循环"]["max_hit"] == 3
    assert nodes["武学突破-领取-循环-耗尽"][
        "custom_action_param"
    ] == {
        "task_id": MARTIAL,
        "status": "failed",
        "error_code": "MARTIAL_CLAIM_LIMIT",
        "postcondition": "martial.claim_state_known",
        "native_fail_after_record": True,
    }
