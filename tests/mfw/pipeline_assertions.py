"""Assertions shared by MFW pipeline contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.check_mfw_resources import load_pipeline_nodes

NATIVE_OUTCOME_ACTIONS = frozenset(
    {
        "CompleteTaskBoundary",
        "RecordActiveTaskFailure",
        "RecordTaskOutcome",
    }
)


def _normalized_targets(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    targets: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        target = value
        while target.startswith("[") and "]" in target:
            target = target[target.index("]") + 1 :]
        targets.append(target)
    return targets


def load_nodes(root: Path) -> dict[str, dict[str, Any]]:
    nodes = load_pipeline_nodes(Path(root))
    assert_targets_exist(nodes)
    return nodes


def _targets(node: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        if isinstance(value, str):
            target = value
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            result.append(target)
        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    continue
                target = item
                while target.startswith("[") and "]" in target:
                    target = target[target.index("]") + 1 :]
                result.append(target)
    return result


def assert_targets_exist(nodes: dict[str, dict[str, Any]]) -> None:
    missing = {
        target
        for node in nodes.values()
        for target in _targets(node)
        if target not in nodes
    }
    assert not missing, f"pipeline references missing nodes: {sorted(missing)}"


def _bounded(node: dict[str, Any]) -> bool:
    return any(
        key in node and node[key] is not None
        for key in ("max_hit", "max_times", "retry_times", "limit", "timeout")
    )


def assert_all_cycles_bounded(nodes: dict[str, dict[str, Any]]) -> None:
    """Reject every graph cycle that has no explicit bound on any cycle node."""

    # A cycle is unbounded exactly when it exists entirely in the subgraph of
    # nodes without an explicit bound.  Checking that subgraph once avoids
    # enumerating every path through the full pipeline graph, which becomes
    # exponential as independent task routes converge on shared cleanup.
    unbounded = {
        name
        for name, node in nodes.items()
        if not _bounded(node)
    }
    graph = {
        name: [target for target in _targets(nodes[name]) if target in unbounded]
        for name in unbounded
    }
    visited: set[str] = set()
    active: set[str] = set()
    path: list[str] = []
    path_index: dict[str, int] = {}

    def visit(name: str) -> None:
        if name in active:
            cycle = path[path_index[name] :]
            raise AssertionError("unbounded pipeline cycle: " + " -> ".join(cycle))
        if name in visited:
            return
        visited.add(name)
        active.add(name)
        path_index[name] = len(path)
        path.append(name)
        for target in graph[name]:
            visit(target)
        path.pop()
        path_index.pop(name)
        active.remove(name)

    for name in unbounded:
        visit(name)


def assert_native_success_node(node: dict[str, Any]) -> None:
    """Require a success endpoint to be a natural leaf or an explicit stop."""

    assert node.get("custom_action") not in NATIVE_OUTCOME_ACTIONS
    assert not node.get("Abort", False)
    if node.get("action") == "StopTask":
        assert not _normalized_targets(node.get("next"))
        assert not _normalized_targets(node.get("on_error"))
        return
    assert not _normalized_targets(node.get("next"))
    assert not _normalized_targets(node.get("on_error"))


def assert_native_failure_node(node: dict[str, Any]) -> None:
    """Require an explicit business failure to delegate to MFW."""

    assert node.get("action") == "Custom"
    assert node.get("custom_action") == "FailTask"
    assert node.get("Abort") is True
    assert "custom_action_param" not in node
    assert not _normalized_targets(node.get("next"))
    assert not _normalized_targets(node.get("on_error"))


def assert_no_custom_outcome_nodes(nodes: dict[str, dict[str, Any]]) -> None:
    """Reject legacy outcome actions in a pipeline selected for migration."""

    violations = [
        name
        for name, node in nodes.items()
        if node.get("custom_action") in NATIVE_OUTCOME_ACTIONS
    ]
    assert not violations, f"legacy outcome actions remain: {sorted(violations)}"


def assert_on_error_contract(
    nodes: dict[str, dict[str, Any]],
    *,
    local_nodes: set[str] | None = None,
    shared_targets: set[str] | None = None,
) -> None:
    """Require non-empty, local-only recovery edges without external routing."""

    local_nodes = set(nodes) if local_nodes is None else set(local_nodes)
    shared_targets = set() if shared_targets is None else set(shared_targets)
    violations: list[str] = []
    for source, node in nodes.items():
        if "on_error" not in node:
            continue
        targets = _normalized_targets(node.get("on_error"))
        if not targets:
            violations.append(f"{source}: empty on_error")
            continue
        for target in targets:
            if target.lower() == "external" or target.startswith("external:"):
                violations.append(f"{source}: external on_error target {target}")
            elif (
                source in local_nodes
                and target not in local_nodes
                and target not in shared_targets
                and not target.startswith("MJA-任务入口失败-")
                and target not in {
                    "MJA-公共-任务入口-重启游戏",
                    "MJA-公共-任务入口-恢复耗尽",
                }
            ):
                violations.append(f"{source}: cross-task on_error target {target}")
    assert not violations, "\n".join(violations)


def load_fixture_manifest(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("startup fixture manifest must contain cases")
    return cases


__all__ = [
    "assert_all_cycles_bounded",
    "assert_native_failure_node",
    "assert_native_success_node",
    "assert_no_custom_outcome_nodes",
    "assert_on_error_contract",
    "assert_targets_exist",
    "load_fixture_manifest",
    "load_nodes",
]
