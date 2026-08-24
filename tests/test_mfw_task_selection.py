from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tools import mfw_task_selection


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    imports = []
    tasks = {
        "GAME_START": {"entry": "MJA_START"},
        "ALPHA": {"entry": "MJA_ALPHA"},
        "BETA": {"entry": "MJA_BETA", "eligible_weekdays": ["Monday"]},
        "WEEKLY_FREE_GIFT_DAILY": {
            "entry": "MJA_WEEKLY",
            "eligible_weekdays": ["Monday"],
        },
    }
    for task_id, values in tasks.items():
        relative = Path(f"tasks/{task_id}.json")
        imports.append(str(relative))
        write_json(candidate / relative, {"task": [{"name": task_id, **values}]})
    write_json(candidate / "interface.json", {"import": imports})
    return candidate


def test_full_scope_is_declaration_order_and_has_no_previous_run_fields(
    candidate: Path, tmp_path: Path
) -> None:
    # A malformed prior artifact must not be opened or suppress today's task.
    write_json(candidate / "debug/mfw-old/ALPHA/result.json", {"broken": True})

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 11),  # Tuesday
    )

    assert selection["eligible_tasks"] == ["ALPHA", "WEEKLY_FREE_GIFT_DAILY"]
    assert selection["selected_tasks"] == ["ALPHA", "WEEKLY_FREE_GIFT_DAILY"]
    assert "precompleted_tasks" not in selection
    assert "pending_tasks" not in selection
    assert "result_root" not in selection
    assert "result.json" not in json.dumps(selection)


def test_weekly_free_gift_is_runnable_every_day(candidate: Path) -> None:
    for operation_date in (date(2026, 8, 11), date(2026, 8, 16)):
        selection = mfw_task_selection.select_tasks(
            candidate,
            operation_date=operation_date,
            explicit_tasks=("WEEKLY_FREE_GIFT_DAILY",),
        )
        assert selection["selected_tasks"] == ["WEEKLY_FREE_GIFT_DAILY"]
        assert selection["scope_blockers"] == []


def test_explicit_scheduled_task_outside_date_is_blocked(candidate: Path) -> None:
    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 11),
        explicit_tasks=("BETA",),
    )

    assert selection["selected_tasks"] == []
    assert selection["scope_blockers"] == [
        {"task_id": "BETA", "reason": "not_eligible_today"}
    ]


def test_retired_task_is_omitted_and_explicit_request_is_blocked(candidate: Path) -> None:
    write_json(candidate / "interface.json", {"import": [
        "tasks/GAME_START.json",
        "tasks/ALPHA.json",
        "tasks/BETA.json",
        "tasks/WEEKLY_FREE_GIFT_DAILY.json",
    ], "retired_tasks": ["ALPHA"]})

    full = mfw_task_selection.select_tasks(candidate, operation_date=date(2026, 8, 10))
    assert full["selected_tasks"] == ["BETA", "WEEKLY_FREE_GIFT_DAILY"]
    explicit = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 10),
        explicit_tasks=("ALPHA",),
    )
    assert explicit["scope_blockers"] == [{"task_id": "ALPHA", "reason": "retired"}]


def test_unknown_explicit_task_is_rejected(candidate: Path) -> None:
    with pytest.raises(ValueError, match="unknown task"):
        mfw_task_selection.select_tasks(candidate, explicit_tasks=("NOT_DECLARED",))


def test_selector_has_no_runtime_or_previous_result_control_surface() -> None:
    source = Path(mfw_task_selection.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "Popen", "os.system", "adb", "result.json", "result_root"):
        assert forbidden not in source
