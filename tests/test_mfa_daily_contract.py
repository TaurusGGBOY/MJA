from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _formal_tasks() -> list[dict]:
    interface = json.loads(
        (ROOT / "assets/interface.json").read_text(encoding="utf-8")
    )
    tasks: list[dict] = []
    for relative in interface["import"]:
        payload = json.loads(
            (ROOT / "assets" / relative).read_text(encoding="utf-8")
        )
        tasks.extend(payload["task"])
    return tasks


def test_formal_interface_exposes_only_imported_native_mfw_tasks() -> None:
    payload = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
    assert payload["task"] == []
    assert "daily_all" not in json.dumps(payload, ensure_ascii=False).casefold()
    assert "mja_daily_" not in json.dumps(payload, ensure_ascii=False).casefold()

    tasks = _formal_tasks()
    names = [task["name"] for task in tasks]
    assert len(names) == len(set(names))
    assert names[0] == "GAME_START"
    assert "GAME_STOP" in names
    assert len([name for name in names if name.endswith("_DAILY")]) == 21
    assert "WEEKLY_FREE_GIFT_MONDAY" in names


def test_imported_task_declarations_have_unique_native_entries() -> None:
    tasks = _formal_tasks()
    pairs = {(task["name"], task["entry"]) for task in tasks}
    assert len(pairs) == len(tasks)
    assert all(task["entry"].startswith("MJA_") for task in tasks)
