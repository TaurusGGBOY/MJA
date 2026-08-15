"""Deterministically render the MFAAvalonia ProjectInterface task list."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

# Allow direct execution from the repository root, matching agent/main.py.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.workflows.catalog import TASK_POLICIES, WORKFLOW_DEFINITION_ORDER


def _load_base(base: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(base, (str, Path)):
        return json.loads(Path(base).read_text(encoding="utf-8"))
    if isinstance(base, dict):
        return deepcopy(base)
    raise TypeError("base must be an interface path or object")


def render_interface(
    task_ids: tuple[str, ...] | list[str] | None = None,
    *,
    base: str | Path | dict[str, Any],
) -> dict[str, object]:
    """Return a stable Android-only interface with generated daily tasks."""

    interface = _load_base(base)
    controllers = interface.get("controller", [])
    controller_names = {
        item.get("name")
        for item in controllers
        if isinstance(item, dict)
    }
    if controller_names != {"android"}:
        raise ValueError("MJA interface must declare only the android controller")
    resources = interface.get("resource", [])
    resource_names = {
        item.get("name")
        for item in resources
        if isinstance(item, dict)
    }
    if resource_names != {"mja_android"}:
        raise ValueError("MJA interface must declare only the mja_android resource")
    selected = tuple(task_ids or WORKFLOW_DEFINITION_ORDER)
    if len(set(selected)) != len(selected):
        raise ValueError("task IDs must be unique")
    unknown = set(selected) - set(WORKFLOW_DEFINITION_ORDER)
    if unknown:
        raise ValueError(f"unknown workflow task: {sorted(unknown)[0]}")
    existing = list(interface.get("task", []))
    for task in existing:
        if not isinstance(task, dict):
            raise ValueError("MJA interface tasks must be objects")
        if task.get("controller") != ["android"]:
            raise ValueError("MJA interface tasks must use the android controller")
        if task.get("resource") != ["mja_android"]:
            raise ValueError("MJA interface tasks must use the mja_android resource")
    names = {item.get("name") for item in existing}
    generated: list[dict[str, object]] = []
    for task_id in selected:
        name = task_id.lower()
        if name in names:
            continue
        generated.append(
            {
                "name": name,
                "label": TASK_POLICIES[task_id].label,
                "entry": f"MJA_Daily_{task_id}",
                "default_check": False,
                "resource": ["mja_android"],
                "controller": ["android"],
            }
        )
        names.add(name)
    if "daily_all" not in names:
        generated.append(
            {
                "name": "daily_all",
                "label": "全部日常任务",
                "entry": "MJA_Daily_All",
                "default_check": False,
                "resource": ["mja_android"],
                "controller": ["android"],
            }
        )
    interface["task"] = existing + generated
    return interface


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rendered = render_interface(base=args.base)
    args.output.write_text(
        json.dumps(rendered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["render_interface"]
