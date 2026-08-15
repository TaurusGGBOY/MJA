from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES


ROOT = Path(__file__).parents[2]
PIPELINE_ROOT = ROOT / "assets" / "resource" / "base" / "pipeline"


def test_deferred_task_paths_only_use_declared_cleanup_actions() -> None:
    violations: list[str] = []

    for pipeline_path in sorted(PIPELINE_ROOT.rglob("*.json")):
        payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
        nodes = payload.get("nodes", payload)
        if not isinstance(nodes, dict):
            continue

        deferred_roots: dict[str, list[str]] = defaultdict(list)
        for node_name, node in nodes.items():
            if not isinstance(node, dict):
                continue
            params = node.get("custom_action_param")
            if (
                node.get("custom_action") == "RecordTaskOutcome"
                and isinstance(params, dict)
                and params.get("defer_home_boundary") is True
            ):
                deferred_roots[params["task_id"]].append(node_name)

        for task_id, roots in deferred_roots.items():
            cleanup_actions = TASK_POLICIES[task_id].cleanup_action_ids
            queue = deque(roots)
            visited = set(roots)

            while queue:
                node_name = queue.popleft()
                node = nodes[node_name]
                if node.get("custom_action") == "GuardedInput":
                    params = node.get("custom_action_param", {})
                    if (
                        isinstance(params, dict)
                        and params.get("task_id") == task_id
                        and params.get("action_id") not in cleanup_actions
                    ):
                        violations.append(
                            f"{pipeline_path}: {task_id} -> "
                            f"{node_name} uses non-cleanup action "
                            f"{params.get('action_id')}"
                        )

                next_nodes = node.get("next", [])
                if isinstance(next_nodes, str):
                    next_nodes = [next_nodes]
                if not isinstance(next_nodes, list):
                    continue
                for next_name in next_nodes:
                    if next_name in nodes and next_name not in visited:
                        visited.add(next_name)
                        queue.append(next_name)

    assert not violations, "\n".join(violations)
