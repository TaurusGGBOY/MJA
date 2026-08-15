"""Assertions for one independent MFW business task."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tools.check_mfw_resources import load_pipeline_nodes

ROOT = Path(__file__).parents[2]


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    pipeline_file: str
    group: str = "日常"

    @property
    def entry(self) -> str:
        return f"MJA_{self.task_id}_START"


def _task_files() -> list[Path]:
    return sorted((ROOT / "assets/tasks").rglob("*.json"))


def load_task_declaration(task_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    key = task_id.strip().upper()
    for path in _task_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for task in payload.get("task", []):
            if isinstance(task, dict) and task.get("name") == key:
                matches.append(task)
    assert len(matches) == 1, f"expected exactly one declaration for {key}"
    return matches[0]


def load_task_nodes(contract: TaskContract) -> dict[str, dict[str, Any]]:
    pipeline_path = ROOT / "assets/resource/base/pipeline" / contract.pipeline_file
    assert pipeline_path.is_file(), f"missing task pipeline: {contract.pipeline_file}"
    nodes = load_pipeline_nodes(ROOT / "assets/resource/base/pipeline")
    assert any(name.startswith(f"MJA_{contract.task_id}_") for name in nodes)
    return nodes


def _targets(node: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if isinstance(values, list):
            for target in values:
                if not isinstance(target, str):
                    continue
                while target.startswith("[") and "]" in target:
                    target = target[target.index("]") + 1 :]
                targets.append(target)
    return targets


def assert_reachable(nodes: dict[str, dict[str, Any]], source: str, target: str) -> None:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target:
            return
        pending.extend(_targets(nodes.get(current, {})))
    raise AssertionError(f"{source} cannot reach {target}")


def _custom_nodes(nodes: dict[str, dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [
        node
        for node in nodes.values()
        if node.get("action") == "Custom" and node.get("custom_action") == action
    ]


def assert_guarded_actions(
    nodes: dict[str, dict[str, Any]], task_id: str, action_ids: list[str]
) -> None:
    task_prefix = f"MJA_{task_id}_"
    scoped = {
        name: node
        for name, node in nodes.items()
        if name.startswith(task_prefix)
        or node.get("custom_action_param", {}).get("task_id") == task_id
    }
    guarded = _custom_nodes(scoped, "GuardedInput")
    assert guarded, f"{task_id} has no GuardedInput nodes"
    scoped_task_ids = {
        node.get("custom_action_param", {}).get("task_id") for node in guarded
    }
    assert scoped_task_ids == {task_id}
    actual = {
        node.get("custom_action_param", {}).get("action_id")
        for node in guarded
    }
    assert actual == set(action_ids)
    assert not any(
        node.get("action") in {"Click", "Swipe", "MultiSwipe", "Key", "Input"}
        for node in scoped.values()
    )


def assert_outcome(
    nodes: dict[str, dict[str, Any]],
    node_name: str,
    status: str,
    postcondition: str,
) -> None:
    node = nodes[node_name]
    assert node["action"] == "Custom"
    assert node["custom_action"] == "RecordTaskOutcome"
    params = node["custom_action_param"]
    assert params["status"] == status
    assert params["postcondition"] == postcondition


def guarded_nodes_for_action(
    nodes: Mapping[str, Mapping[str, Any]], action_id: str
) -> list[dict[str, Any]]:
    """Return all guarded input nodes for one canonical action ID."""

    return [
        dict(node)
        for node in nodes.values()
        if node.get("action") == "Custom"
        and node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("action_id") == action_id
    ]


def _reachable_on_error_actions(
    nodes: Mapping[str, Mapping[str, Any]], node: Mapping[str, Any]
) -> set[str]:
    pending = list(_targets({"on_error": node.get("on_error", [])}))
    visited: set[str] = set()
    actions: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        candidate = nodes.get(current)
        if candidate is None:
            continue
        params = candidate.get("custom_action_param", {})
        action_id = params.get("action_id") if isinstance(params, Mapping) else None
        if isinstance(action_id, str):
            actions.add(action_id)
        pending.extend(_targets({"on_error": candidate.get("on_error", [])}))
    return actions


def assert_no_side_effect_retry(
    nodes: Mapping[str, Mapping[str, Any]], action_id: str
) -> None:
    """Ensure a consumptive guarded input cannot be replayed through on_error."""

    matches = guarded_nodes_for_action(nodes, action_id)
    assert matches, f"missing guarded action {action_id}"
    for node in matches:
        assert node.get("retry_times", 0) == 0
        assert action_id not in _reachable_on_error_actions(nodes, node)


def assert_resource_guard(
    nodes: Mapping[str, Mapping[str, Any]],
    action_id: str,
    resource: str,
    maximum: int,
    *,
    task_id: str | None = None,
    require_observed_amount: bool = True,
) -> None:
    """Check the same-frame OCR/resource budget contract for a guarded input."""

    matches = guarded_nodes_for_action(nodes, action_id)
    assert matches, f"missing guarded action {action_id}"
    assert isinstance(resource, str) and resource.strip()
    assert isinstance(maximum, int) and not isinstance(maximum, bool) and maximum > 0
    observed_tasks: set[str] = set()
    for node in matches:
        params = node["custom_action_param"]
        observed_tasks.add(params.get("task_id"))
        assert params.get("resource_id") == resource
        budget_amount = params.get("budget_amount")
        assert isinstance(budget_amount, int) and not isinstance(budget_amount, bool)
        assert 0 < budget_amount <= maximum
        observed_amount = params.get("observed_amount")
        if require_observed_amount:
            assert isinstance(observed_amount, int) and not isinstance(observed_amount, bool)
            assert observed_amount > 0
        else:
            assert observed_amount is None
        assert isinstance(params.get("resource_index"), int)
        assert isinstance(params.get("amount_index"), int)
        evidence = params.get("evidence")
        assert isinstance(evidence, Mapping)
        assert isinstance(evidence.get("page_index"), int)
        assert isinstance(evidence.get("target_index"), int)
        assert evidence.get("page_name")
        assert evidence.get("target_name")
        assert _targets(node)
    assert all(isinstance(value, str) for value in observed_tasks)
    if task_id is not None:
        assert observed_tasks == {task_id}
    else:
        assert len(observed_tasks) == 1


def assert_shared_resource_budget(
    nodes: Mapping[str, Mapping[str, Any]], resource: str, maximum: int
) -> None:
    """Require all guarded uses of one resource to fit one task budget."""

    matches = [
        node
        for node in nodes.values()
        if node.get("action") == "Custom"
        and node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("resource_id") == resource
    ]
    assert matches, f"missing guarded resource {resource}"
    budgets_by_action: dict[str, set[int]] = {}
    for node in matches:
        params = node["custom_action_param"]
        action_id = params.get("action_id")
        budget_amount = params.get("budget_amount")
        assert isinstance(action_id, str) and action_id
        assert isinstance(budget_amount, int) and budget_amount > 0
        budgets_by_action.setdefault(action_id, set()).add(budget_amount)
    assert all(len(values) == 1 for values in budgets_by_action.values())
    assert sum(next(iter(values)) for values in budgets_by_action.values()) <= maximum


def assert_loop_bound(
    nodes: Mapping[str, Mapping[str, Any]], node_name: str, maximum: int
) -> None:
    """Require a named pipeline loop to carry one explicit finite bound."""

    assert isinstance(maximum, int) and maximum > 0
    node = nodes.get(node_name)
    assert node is not None, f"missing bounded loop {node_name}"
    bounds = [
        node.get(field)
        for field in ("max_hit", "max_times", "retry_times", "limit")
        if field in node
    ]
    assert bounds == [maximum]


def assert_terminal_after_loop(
    nodes: Mapping[str, Mapping[str, Any]],
    loop_node: str,
    maximum: int,
    exhausted_code: str,
) -> None:
    """Require loop exhaustion to record a stable failure and Abort."""

    assert_loop_bound(nodes, loop_node, maximum)
    exhausted = nodes.get(f"{loop_node}_EXHAUSTED")
    assert exhausted is not None, f"missing exhaustion node for {loop_node}"
    params = exhausted.get("custom_action_param", {})
    assert params.get("error_code") == exhausted_code
    targets = exhausted.get("next", [])
    target = targets[0] if isinstance(targets, list) and targets else targets
    assert isinstance(target, str)
    assert_reachable(nodes, target, "MJA_COMMON_ABORT")


def assert_battle_result_partition(
    nodes: Mapping[str, Mapping[str, Any]], prefix: str
) -> None:
    """Require victory, defeat, and unknown battle outcomes to be distinct."""

    victory = f"{prefix}_VICTORY"
    defeat = f"{prefix}_DEFEAT"
    unknown = f"{prefix}_UNKNOWN_RESULT"
    assert victory in nodes
    assert defeat in nodes
    assert unknown in nodes
    assert victory != defeat != unknown
    assert_reachable(nodes, unknown, "MJA_COMMON_ABORT")


def assert_action_limit(task_id: str, action_id: str, maximum: int) -> None:
    """Assert a task action has the frozen policy cap."""

    assert TASK_POLICIES[task_id].action_caps[action_id] == maximum


def assert_material_guard(
    nodes: Mapping[str, Mapping[str, Any]], action_id: str
) -> None:
    """Require a same-frame material relation proof on a mutation."""

    matches = guarded_nodes_for_action(nodes, action_id)
    assert matches, f"missing guarded action {action_id}"
    for node in matches:
        params = node.get("custom_action_param", {})
        assert params.get("material_id")
        assert params.get("material_relation") == "owned>=required"
        relation_index = params.get("material_relation_index")
        if relation_index is not None:
            assert isinstance(relation_index, int)
            assert params.get("material_relation_name")
            continue
        for field in ("material_index", "owned_index", "required_index"):
            assert isinstance(params.get(field), int)


def assert_condition(
    nodes: Mapping[str, Mapping[str, Any]], node_name: str, expected: str
) -> None:
    """Assert a named pipeline node carries an explicit semantic condition."""

    node = nodes[node_name]
    params = node.get("custom_action_param", {})
    assert params.get("condition") == expected


def assert_ordered_actions(
    nodes: Mapping[str, Mapping[str, Any]], action_ids: list[str]
) -> None:
    """Require each action phase to be reachable from the preceding phase."""

    action_nodes: dict[str, list[str]] = {}
    for name, node in nodes.items():
        params = node.get("custom_action_param", {})
        action_id = params.get("action_id") if isinstance(params, Mapping) else None
        if isinstance(action_id, str):
            action_nodes.setdefault(action_id, []).append(name)
    for action_id in action_ids:
        assert action_id in action_nodes, f"missing action phase {action_id}"
    for previous, current in zip(action_ids, action_ids[1:]):
        reachable = False
        for source in action_nodes[previous]:
            for target in action_nodes[current]:
                try:
                    assert_reachable(nodes, source, target)
                except AssertionError:
                    continue
                reachable = True
                break
            if reachable:
                break
        assert reachable, f"action phase {previous} cannot reach {current}"


def assert_abort_code(
    nodes: Mapping[str, Mapping[str, Any]], node_name: str, error_code: str
) -> None:
    params = nodes[node_name].get("custom_action_param", {})
    assert params.get("status") == "failed"
    assert params.get("error_code") == error_code


def assert_task_contract(
    contract: TaskContract, *, require_game_start_recovery: bool = True
) -> None:
    declaration = load_task_declaration(contract.task_id)
    assert declaration["label"]
    assert declaration["default_check"] is True
    assert declaration["group"] == [contract.group]
    assert declaration["entry"] == contract.entry

    nodes = load_task_nodes(contract)
    assert contract.entry in nodes
    payload = json.loads(
        (ROOT / "assets/resource/base/pipeline" / contract.pipeline_file).read_text(
            encoding="utf-8"
        )
    )
    scoped_nodes = payload.get("pipeline", payload)
    has_game_start_recovery = any(
        raw_target == "[JumpBack]MJA_GAME_START"
        for node in scoped_nodes.values()
        for field in ("next", "on_error")
        for raw_target in (
            [node.get(field)]
            if isinstance(node.get(field), str)
            else node.get(field, [])
        )
    )
    if require_game_start_recovery:
        assert_reachable(nodes, contract.entry, "MJA_GAME_START")
        assert has_game_start_recovery, (
            f"{contract.task_id} must reuse [JumpBack]MJA_GAME_START"
        )
    else:
        assert not has_game_start_recovery, (
            f"{contract.task_id} must fail closed instead of jumping to MJA_GAME_START"
        )
    assert_reachable(nodes, contract.entry, "MJA_COMMON_STOP")
    assert_reachable(nodes, contract.entry, "MJA_COMMON_ABORT")


def assert_fixture_matrix(task_id: str, required: set[str]) -> None:
    manifest = json.loads(
        (ROOT / "tests/fixtures" / task_id / "manifest.json").read_text(encoding="utf-8")
    )
    cases = set(manifest["cases"])
    # Schema 2 names the stale daily-list terminal explicitly so it cannot be
    # confused with a fresh completed run.  Keep the older contract's
    # ``completed`` requirement as a compatibility alias in this offline
    # matrix helper.
    if "preexisting_done" in cases:
        cases.add("completed")
    assert required <= cases


__all__ = [
    "TaskContract",
    "assert_fixture_matrix",
    "assert_abort_code",
    "assert_guarded_actions",
    "assert_no_side_effect_retry",
    "assert_ordered_actions",
    "assert_outcome",
    "assert_resource_guard",
    "assert_shared_resource_budget",
    "assert_loop_bound",
    "assert_terminal_after_loop",
    "assert_battle_result_partition",
    "assert_action_limit",
    "assert_material_guard",
    "assert_condition",
    "assert_reachable",
    "guarded_nodes_for_action",
    "assert_task_contract",
    "load_task_declaration",
    "load_task_nodes",
]
