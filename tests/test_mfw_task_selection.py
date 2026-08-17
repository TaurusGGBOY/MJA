from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from tools import mfw_task_selection


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_task(candidate: Path, task_id: str, *, days: list[str] | None = None) -> None:
    payload: dict[str, object] = {
        "task": [
            {
                "name": task_id,
                "entry": f"MJA_{task_id}_START",
                "default_check": True,
            }
        ]
    }
    if days is not None:
        payload["task"][0]["eligible_weekdays"] = days  # type: ignore[index]
    write_json(candidate / f"tasks/{task_id}.json", payload)


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    imports = [
        "tasks/game.json",
        "tasks/alpha.json",
        "tasks/beta.json",
        "tasks/weekly.json",
    ]
    write_json(
        candidate / "interface.mfw.json",
        {"interface_version": 2, "import": imports},
    )
    write_json(
        candidate / "interface.json",
        {
            "task": [
                {"name": "BETA", "entry": "wrong-order"},
                {"name": "ALPHA", "entry": "wrong-order"},
            ]
        },
    )
    write_json(
        candidate / "tasks/game.json",
        {"task": [{"name": "GAME_START", "entry": "启动-游戏启动"}]},
    )
    write_json(
        candidate / "tasks/alpha.json",
        {"task": [{"name": "ALPHA", "entry": "MJA_ALPHA_START"}]},
    )
    write_json(
        candidate / "tasks/beta.json",
        {"task": [{"name": "BETA", "entry": "MJA_BETA_START"}]},
    )
    write_json(
        candidate / "tasks/weekly.json",
        {
            "task": [
                {
                    "name": "WEEKLY_FREE_GIFT_MONDAY",
                    "entry": "MJA_WEEKLY_START",
                    "eligible_weekdays": ["Monday"],
                }
            ]
        },
    )
    return candidate


def write_result(
    root: Path,
    task_id: str,
    *,
    operation_date: date,
    status: str,
    postcondition: str | None = None,
    native_terminal: object | None = "Tasker.Task.Succeeded",
    finished_at: str | None = None,
) -> Path:
    path = root / f"mfw-{task_id.lower()}" / task_id / "result.json"
    if finished_at is None:
        finished_at = f"{operation_date.isoformat()}T12:00:00+08:00"
    write_json(
        path,
        {
            "schema_version": 1,
            "task_id": task_id,
            "status": status,
            "started_at": finished_at,
            "finished_at": finished_at,
            "postcondition": postcondition,
            "native_terminal": native_terminal,
        },
    )
    return path


def test_full_scope_uses_mfw_import_order_and_current_weekday(
    candidate: Path, tmp_path: Path
) -> None:
    operation_date = date(2026, 8, 11)  # Tuesday
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=operation_date,
        status="success",
        postcondition="alpha.business_done",
    )
    write_result(
        result_root,
        "BETA",
        operation_date=operation_date,
        status="failed",
        postcondition="beta.failure_recorded",
        native_terminal="Tasker.Task.Failed",
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        result_root=result_root,
    )

    assert selection["scope_mode"] == "full"
    assert selection["eligible_tasks"] == ["ALPHA", "BETA"]
    assert selection["precompleted_tasks"] == ["ALPHA"]
    assert selection["pending_tasks"] == ["BETA"]
    assert selection["failed_task"] is None
    assert selection["unrun_after_first_failure"] == []
    assert selection["selected_tasks"] == ["BETA"]
    assert selection["evidence"]["ALPHA"]["result_path"].endswith("result.json")


def test_explicit_scope_blocks_a_weekly_task_outside_current_schedule(
    candidate: Path, tmp_path: Path
) -> None:
    operation_date = date(2026, 8, 11)  # Tuesday
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "WEEKLY_FREE_GIFT_MONDAY",
        operation_date=operation_date,
        status="success",
        postcondition="weekly_gift.claimed",
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        explicit_tasks=("WEEKLY_FREE_GIFT_MONDAY",),
        result_root=result_root,
    )

    assert selection["scope_mode"] == "explicit"
    assert selection["eligible_tasks"] == []
    assert selection["precompleted_tasks"] == []
    assert selection["pending_tasks"] == []
    assert selection["selected_tasks"] == []
    assert selection["scope_blockers"] == [
        {"task_id": "WEEKLY_FREE_GIFT_MONDAY", "reason": "not_eligible_today"}
    ]


def test_only_fresh_success_with_task_and_native_evidence_is_precompleted(
    candidate: Path, tmp_path: Path
) -> None:
    operation_date = date(2026, 8, 11)
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=operation_date,
        status="success",
        postcondition="alpha.business_done",
    )
    write_result(
        result_root,
        "BETA",
        operation_date=operation_date,
        status="success",
        postcondition="beta.business_done",
        native_terminal=None,
    )
    write_result(
        result_root,
        "WEEKLY_FREE_GIFT_MONDAY",
        operation_date=operation_date,
        status="success",
        postcondition="generic.terminal",
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        result_root=result_root,
    )

    assert selection["precompleted_tasks"] == ["ALPHA"]
    assert selection["pending_tasks"] == ["BETA"]
    assert selection["evidence"]["BETA"]["reason"] == "native_terminal_unverified"


@pytest.mark.parametrize(
    "status",
    ["failed", "blocked_safety", "already_complete", "not_eligible", "completed", "running"],
)
def test_non_success_statuses_stay_pending(
    candidate: Path, tmp_path: Path, status: str
) -> None:
    operation_date = date(2026, 8, 11)
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=operation_date,
        status=status,
        postcondition="alpha.business_done",
        native_terminal="Tasker.Task.Failed" if status in {"failed", "blocked_safety"} else None,
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        explicit_tasks=("ALPHA",),
        result_root=result_root,
    )

    assert selection["precompleted_tasks"] == []
    assert selection["pending_tasks"] == ["ALPHA"]


def test_missing_and_expired_results_stay_pending(
    candidate: Path, tmp_path: Path
) -> None:
    operation_date = date(2026, 8, 11)
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=operation_date - timedelta(days=1),
        status="success",
        postcondition="alpha.business_done",
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        result_root=result_root,
    )

    assert selection["precompleted_tasks"] == []
    assert selection["pending_tasks"] == ["ALPHA", "BETA"]
    assert selection["evidence"]["ALPHA"]["reason"] == "expired"
    assert selection["evidence"]["BETA"]["reason"] == "missing"


def test_first_failure_selects_failed_task_and_only_later_pending_tasks(
    candidate: Path, tmp_path: Path
) -> None:
    operation_date = date(2026, 8, 10)  # Monday
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=operation_date,
        status="success",
        postcondition="alpha.business_done",
    )
    write_result(
        result_root,
        "BETA",
        operation_date=operation_date,
        status="failed",
        postcondition="beta.failure_recorded",
        native_terminal="Tasker.Task.Failed",
    )
    write_result(
        result_root,
        "WEEKLY_FREE_GIFT_MONDAY",
        operation_date=operation_date,
        status="already_complete",
        postcondition="weekly_gift.claimed",
        native_terminal=None,
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        result_root=result_root,
    )

    assert selection["precompleted_tasks"] == ["ALPHA"]
    assert selection["pending_tasks"] == [
        "BETA",
        "WEEKLY_FREE_GIFT_MONDAY",
    ]
    assert selection["failed_task"] is None
    assert selection["unrun_after_first_failure"] == []
    assert selection["selected_tasks"] == [
        "BETA",
        "WEEKLY_FREE_GIFT_MONDAY",
    ]


def test_empty_pending_set_has_no_selected_tasks(candidate: Path, tmp_path: Path) -> None:
    operation_date = date(2026, 8, 11)
    result_root = tmp_path / "results"
    for task_id, postcondition in (
        ("ALPHA", "alpha.business_done"),
        ("BETA", "beta.business_done"),
    ):
        write_result(
            result_root,
            task_id,
            operation_date=operation_date,
            status="success",
            postcondition=postcondition,
        )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        result_root=result_root,
    )

    assert selection["pending_tasks"] == []
    assert selection["selected_tasks"] == []


def test_explicit_scope_keeps_a_fresh_success_in_the_requested_batch(
    candidate: Path, tmp_path: Path
) -> None:
    operation_date = date(2026, 8, 11)
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=operation_date,
        status="success",
        postcondition="alpha.business_done",
    )

    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=operation_date,
        explicit_tasks=("ALPHA",),
        result_root=result_root,
    )

    assert selection["precompleted_tasks"] == ["ALPHA"]
    assert selection["pending_tasks"] == []
    assert selection["selected_tasks"] == ["ALPHA"]


def test_retired_task_is_omitted_and_explicit_request_is_blocked(
    candidate: Path, tmp_path: Path
) -> None:
    interface_path = candidate / "interface.mfw.json"
    payload = json.loads(interface_path.read_text(encoding="utf-8"))
    payload["retired_tasks"] = ["BETA"]
    write_json(interface_path, payload)

    full = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 11),
        result_root=tmp_path / "full-results",
    )
    assert "BETA" not in full["eligible_tasks"]
    assert "BETA" in full["retired_tasks"]
    assert "BETA" in full["omitted_tasks"]

    explicit = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 11),
        explicit_tasks=("BETA",),
        result_root=tmp_path / "explicit-results",
    )
    assert explicit["selected_tasks"] == []
    assert explicit["scope_blockers"] == [{"task_id": "BETA", "reason": "retired"}]


def test_freshness_uses_operation_timezone_for_utc_result(
    candidate: Path, tmp_path: Path
) -> None:
    result_root = tmp_path / "results"
    write_result(
        result_root,
        "ALPHA",
        operation_date=date(2026, 8, 14),
        status="success",
        postcondition="alpha.business_done",
        finished_at="2026-08-13T16:30:00+00:00",
    )
    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 14),
        result_root=result_root,
    )
    assert selection["evidence"]["ALPHA"]["fresh"] is True
    assert selection["operation_timezone"] == "Asia/Shanghai"


def test_unknown_explicit_task_is_rejected(candidate: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown task"):
        mfw_task_selection.select_tasks(
            candidate,
            operation_date=date(2026, 8, 10),
            explicit_tasks=("NOT_DECLARED",),
            result_root=tmp_path / "results",
        )


def test_repair_task_success_postconditions_include_branch_specific_markers() -> None:
    assert "hero.claim_state_known" in mfw_task_selection.SUCCESS_POSTCONDITIONS[
        "HERO_DISPATCH_DAILY"
    ]
    assert "equipment.no_reward_popup" in mfw_task_selection.SUCCESS_POSTCONDITIONS[
        "EQUIPMENT_DECOMPOSE_DAILY"
    ]


def test_malformed_result_is_rejected_without_running_external_tools(
    candidate: Path, tmp_path: Path
) -> None:
    result_root = tmp_path / "results"
    path = result_root / "mfw-alpha/ALPHA/result.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed result"):
        mfw_task_selection.select_tasks(
            candidate,
            operation_date=date(2026, 8, 10),
            result_root=result_root,
        )


def test_selector_source_has_no_process_or_device_control_surface() -> None:
    source = Path(mfw_task_selection.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "Popen",
        "os.system",
        "adb",
        "sleep(",
        ".poll(",
    ):
        assert forbidden not in source


def test_formal_imported_interface_wins_over_legacy_task_list(
    candidate: Path, tmp_path: Path
) -> None:
    write_json(
        candidate / "interface.json",
        {
            "interface_version": 2,
            "import": [
                "tasks/game.json",
                "tasks/beta.json",
                "tasks/alpha.json",
                "tasks/weekly.json",
            ],
        },
    )
    selection = mfw_task_selection.select_tasks(
        candidate,
        operation_date=date(2026, 8, 11),
        explicit_tasks=("BETA", "ALPHA"),
        result_root=tmp_path / "results",
    )

    assert selection["eligible_tasks"] == ["BETA", "ALPHA"]
    assert selection["evidence"]["interface_path"].endswith("interface.json")
