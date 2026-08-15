"""Assertions shared by MFW pipeline contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.check_mfw_resources import load_pipeline_nodes


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

    graph = {name: _targets(node) for name, node in nodes.items()}

    def visit(name: str, path: list[str], active: set[str]) -> None:
        if name in active:
            cycle = path[path.index(name) :]
            assert any(_bounded(nodes[item]) for item in cycle), (
                "unbounded pipeline cycle: " + " -> ".join(cycle)
            )
            return
        active.add(name)
        path.append(name)
        for target in graph[name]:
            visit(target, path, active)
        path.pop()
        active.remove(name)

    for name in nodes:
        visit(name, [], set())


def load_fixture_manifest(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("startup fixture manifest must contain cases")
    return cases


__all__ = [
    "assert_all_cycles_bounded",
    "assert_targets_exist",
    "load_fixture_manifest",
    "load_nodes",
]
