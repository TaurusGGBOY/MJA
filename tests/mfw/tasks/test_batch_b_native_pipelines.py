"""Offline contracts for the resource-sensitive Batch-B MFW tasks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    assert_no_side_effect_retry,
    assert_resource_guard,
    assert_shared_resource_budget,
)

ROOT = Path(__file__).parents[3]
TASKS: tuple[tuple[str, str, str], ...] = (
    ("BUY_TEA_DAILY", "日常/BUY_TEA_DAILY.json", "daily/buy_tea_daily.json"),
    (
        "SPEND_CONDENSATE_DAILY",
        "日常/SPEND_CONDENSATE_DAILY.json",
        "daily/spend_condensate_daily.json",
    ),
    (
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "日常/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json",
        "daily/martial_study_breakthrough_daily.json",
    ),
    (
        "EAT_STAMINA_FOOD_DAILY",
        "日常/EAT_STAMINA_FOOD_DAILY.json",
        "daily/eat_stamina_food_daily.json",
    ),
    (
        "EQUIPMENT_DECOMPOSE_DAILY",
        "日常/EQUIPMENT_DECOMPOSE_DAILY.json",
        "daily/equipment_decompose_daily.json",
    ),
    (
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "日常/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json",
        "daily/jianlin_resource_condensate_stamina_daily.json",
    ),
)


def _json(relative: str) -> dict[str, Any]:
    payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _nodes(relative: str) -> dict[str, dict[str, Any]]:
    payload = _json(f"assets/resource/base/pipeline/{relative}")
    candidate = payload.get("pipeline", payload)
    assert isinstance(candidate, dict)
    assert all(isinstance(name, str) and isinstance(node, dict) for name, node in candidate.items())
    return candidate


def _targets(node: Mapping[str, Any]) -> list[str]:
    targets: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list):
            continue
        for target in values:
            if not isinstance(target, str):
                continue
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            targets.append(target)
    return targets


def _reachable(
    nodes: Mapping[str, Mapping[str, Any]], source: str, target: str
) -> bool:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target:
            return True
        pending.extend(_targets(nodes.get(current, {})))
    return False


def _guarded(nodes: Mapping[str, Mapping[str, Any]], task_id: str) -> list[dict[str, Any]]:
    return [
        dict(node)
        for node in nodes.values()
        if node.get("action") == "Custom"
        and node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == task_id
    ]


def _outcomes(
    nodes: Mapping[str, Mapping[str, Any]], task_id: str
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (name, dict(node))
        for name, node in nodes.items()
        if node.get("action") == "Custom"
        and node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id") == task_id
    ]


def test_batch_b_has_private_declarations_and_native_terminal_paths() -> None:
    for task_id, declaration_file, pipeline_file in TASKS:
        declaration = _json(f"assets/tasks/{declaration_file}")
        tasks = declaration.get("task")
        assert isinstance(tasks, list) and len(tasks) == 1
        task = tasks[0]
        assert task["name"] == task_id
        assert task["entry"] == f"MJA_{task_id}_START"
        assert task["default_check"] is True

        nodes = _nodes(pipeline_file)
        entry = task["entry"]
        assert entry in nodes
        assert _reachable(nodes, entry, "MJA_COMMON_STOP")
        assert _reachable(nodes, entry, "MJA_COMMON_ABORT")
        assert any(
            ("page" in name.lower() or "home" in name.lower())
            and isinstance(node.get("recognition"), (str, dict))
            for name, node in nodes.items()
            if name.startswith("MJA_") or "." in name
        )


def test_batch_b_side_effect_nodes_are_bounded_and_current_frame_guarded() -> None:
    for task_id, _, pipeline_file in TASKS:
        nodes = _nodes(pipeline_file)
        guarded = _guarded(nodes, task_id)
        assert guarded, task_id
        for node in guarded:
            params = node["custom_action_param"]
            max_hit = node.get("max_hit")
            assert isinstance(max_hit, int) and max_hit > 0
            assert max_hit <= TASK_POLICIES[task_id].action_caps[params["action_id"]]
            assert node.get("retry_times", 0) == 0
            evidence = params["evidence"]
            assert isinstance(evidence, Mapping)
            assert isinstance(evidence.get("page_index"), int)
            assert isinstance(evidence.get("target_index"), int)
            assert isinstance(evidence.get("page_name"), str)
            assert isinstance(evidence.get("target_name"), str)
            assert node.get("on_error"), f"{task_id}:{params.get('action_id')}"


def test_batch_b_failure_outcomes_persist_before_native_abort() -> None:
    for task_id, _, pipeline_file in TASKS:
        nodes = _nodes(pipeline_file)
        outcomes = _outcomes(nodes, task_id)
        assert outcomes, task_id
        for name, node in outcomes:
            params = node["custom_action_param"]
            status = params["status"]
            if status == "failed":
                assert params.get("native_fail_after_record") is True, (task_id, params)
                assert node.get("Abort") is True, (task_id, params)
                assert node.get("next") == ["MJA_COMMON_ABORT"], (task_id, params)
            else:
                assert status in {"success", "already_complete", "not_eligible"}
                assert _reachable(nodes, name, "MJA_COMMON_STOP")


def test_batch_b_resource_actions_have_identity_budget_and_no_replay() -> None:
    requirements = {
        "BUY_TEA_DAILY": (("buy_tea", "文", 500),),
        "SPEND_CONDENSATE_DAILY": (
            ("buy_yanwu_currency_max", "凝晶", 100_000),
            ("buy_yunzhou_currency_max", "凝晶", 100_000),
        ),
        "EAT_STAMINA_FOOD_DAILY": (("eat_longjing_shrimp", "龙井虾仁", 6),),
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": (
            ("buy_stamina_once", "紫色魂玉", 1),
            ("start_jianlin_battle", "体力", 120),
        ),
    }
    for task_id, actions in requirements.items():
        pipeline_file = next(item[2] for item in TASKS if item[0] == task_id)
        nodes = _nodes(pipeline_file)
        for action_id, resource_id, maximum in actions:
            assert_resource_guard(nodes, action_id, resource_id, maximum, task_id=task_id)
            assert_no_side_effect_retry(nodes, action_id)

    condensate = _nodes("daily/spend_condensate_daily.json")
    assert_shared_resource_budget(condensate, "凝晶", 100_000)
    assert TASK_POLICIES["JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"].resource_caps["体力"] == 360


def test_martial_claims_success_cards_or_succeeds_without_plus_slot_input() -> None:
    nodes = _nodes("daily/martial_study_breakthrough_daily.json")
    serialized = json.dumps(nodes, ensure_ascii=False)
    assert "plus_slot" not in serialized
    assert "study_martial_slot" not in serialized
    assert "breakthrough_martial_slot" not in serialized

    claim = nodes["MJA_MARTIAL_CLAIM_LOOP"]
    assert claim["custom_action_param"]["action_id"] == "claim_success_card"
    assert claim["max_hit"] == 3
    terminal = nodes["MJA_MARTIAL_SUCCESS_NO_CLAIM"]["custom_action_param"]
    assert terminal["status"] == "success"
    assert terminal["postcondition"] == "martial.successful_breakthroughs_claimed_or_none"
    assert _reachable(
        nodes,
        "MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH",
        "MJA_MARTIAL_SUCCESS_NO_CLAIM",
    )


@pytest.mark.parametrize("observed", ["级", "级以上", "80", "等级", "部分级及以下"])
def test_equipment_level_filter_requires_exact_label(observed: str) -> None:
    nodes = _nodes("daily/equipment_decompose_daily.json")
    expected = nodes["equipment.level.dialog"]["expected"]
    assert expected == "级及以下"
    assert observed != expected


def test_equipment_decompose_requires_exact_level_and_business_postcondition() -> None:
    nodes = _nodes("daily/equipment_decompose_daily.json")
    assert nodes["equipment.level.dialog"]["expected"] == "级及以下"
    assert nodes["equipment.level.filter"]["expected"] == "级"
    outcome = nodes["MJA_EQUIPMENT_DECOMPOSE_SUCCESS"]["custom_action_param"]
    assert outcome["postcondition"] == "equipment.decomposition_confirmed"
    assert nodes["MJA_EQUIPMENT_DECOMPOSE_SUCCESS"]["next"] == [
        "MJA_EQUIPMENT_CLOSE_PROBE"
    ]

