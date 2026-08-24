from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    assert_native_failure_node,
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import load_task_declaration
from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes

ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"
TASKS = {
    "MAIL_REWARD_DAILY": "mail_reward_daily.json",
    "SHOP_FREE_GIFT_DAILY": "shop_free_gift_daily.json",
    "FREE_APPRAISAL_DAILY": "free_appraisal_daily.json",
    "TRIAL_SWORD_DAILY": "trial_sword_daily.json",
    "HERO_DISPATCH_DAILY": "hero_dispatch_daily.json",
    "COLLECTION_DEPLOYMENT_DAILY": "collection_deployment_daily.json",
    "WEEKLY_FREE_GIFT_DAILY": "weekly_free_gift_daily.json",
    "GUILD_AFFAIRS_DAILY": "guild_affairs_daily.json",
    "GUILD_DONATION_DAILY": "guild_donation_daily.json",
    "DAILY_TASK_REWARD_CLAIM_DAILY": "daily_task_reward_claim_daily.json",
    "BATTLE_PASS_REWARD_DAILY": "battle_pass_reward_daily.json",
}


def _local(name: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / "daily" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _targets(node: dict) -> list[str]:
    result: list[str] = []
    for field in ("next", "on_error"):
        raw = node.get(field, [])
        values = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list):
            continue
        for target in values:
            if not isinstance(target, str):
                continue
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            result.append(target)
    return result


def _reachable(nodes: dict[str, dict], source: str, target: str) -> bool:
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


def test_batch_a_entries_are_declared_and_end_in_native_success() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    for task_id, filename in TASKS.items():
        declaration = load_task_declaration(task_id)
        local = _local(filename)
        entry = declaration["entry"]
        assert entry in local
        assert local[entry]["custom_action"] == "BeginTask"
        assert _reachable(nodes, entry, "1369-公共-通用停止") or any(
            node.get("action") == "StopTask"
            for node in _local(filename).values()
        )


def test_batch_a_has_no_custom_outcomes_and_only_legal_error_topology() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    shared = set(
        json.loads((PIPELINE_ROOT / "common/home_boundary.json").read_text())
    ) | set(json.loads((PIPELINE_ROOT / "common/terminal.json").read_text()))
    for filename in TASKS.values():
        local = _local(filename)
        assert_no_custom_outcome_nodes(local)
        assert_on_error_contract(local, local_nodes=set(local), shared_targets=shared)
    assert not validate_nodes(nodes)


def test_batch_a_native_terminals_and_bounds_are_framework_owned() -> None:
    nodes = load_pipeline_nodes(PIPELINE_ROOT)
    assert_native_success_node(nodes["1369-公共-通用停止"])
    for node in nodes.values():
        if node.get("custom_action") == "FailTask":
            assert_native_failure_node(node)
    assert_all_cycles_bounded(nodes)


def test_weekly_gift_declares_daily_eligibility() -> None:
    declaration = load_task_declaration("WEEKLY_FREE_GIFT_DAILY")
    assert declaration["name"] == "WEEKLY_FREE_GIFT_DAILY"
    assert declaration.get("weekdays") in (None, [], "")
