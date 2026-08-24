from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import load_task_declaration

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


def _load(name: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / "daily" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_batch_a_has_one_declared_begin_task_per_pipeline() -> None:
    for task_id, filename in TASKS.items():
        declaration = load_task_declaration(task_id)
        nodes = _load(filename)
        entry = declaration["entry"]
        assert entry in nodes
        assert nodes[entry]["custom_action"] == "BeginTask"
        assert nodes[entry]["custom_action_param"]["task_id"] == task_id


def test_batch_a_has_no_result_recorders_or_business_status_fields() -> None:
    shared = set(json.loads((PIPELINE_ROOT / "common/home_boundary.json").read_text()))
    shared |= set(json.loads((PIPELINE_ROOT / "common/terminal.json").read_text()))
    for filename in TASKS.values():
        nodes = _load(filename)
        assert_no_custom_outcome_nodes(nodes)
        assert '"status"' not in json.dumps(nodes, ensure_ascii=False)
        assert_on_error_contract(nodes, local_nodes=set(nodes), shared_targets=shared)
        for node in nodes.values():
            if node.get("custom_action") == "FailTask":
                assert_native_failure_node(node)


def test_batch_a_preserves_page_evidence_and_finite_side_effects() -> None:
    for filename in TASKS.values():
        nodes = _load(filename)
        assert any(node.get("recognition") for node in nodes.values())
        for name, node in nodes.items():
            if node.get("custom_action") in {"BeginTask", "GuardedInput"}:
                assert any(key in node for key in ("timeout", "max_hit", "retry_times")), name
