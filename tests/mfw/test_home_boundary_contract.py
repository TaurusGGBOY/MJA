from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.custom.support.diagnostics import TaskDiagnostics
from agent.custom.support.models import TaskOutcomeStatus
from agent.custom.support.state import TaskRunStore


TASK_ID = "MAIL_REWARD_DAILY"


def test_run_store_seals_business_result_before_home_boundary() -> None:
    store = TaskRunStore()
    store.begin(TASK_ID)

    store.seal_business_result(TASK_ID, TaskOutcomeStatus.SUCCESS, "mail.empty", None)
    snapshot = store.snapshot(TASK_ID)

    assert snapshot["business_result_sealed"] is True
    assert snapshot["home_boundary_pending"] is True
    assert snapshot["home_boundary_status"] == "pending"
    assert snapshot["final_status"] is None
    assert snapshot["business_result"]["status"] is TaskOutcomeStatus.SUCCESS
    assert snapshot["events"][-1]["name"] == "business_result_sealed"

    with pytest.raises(PermissionError, match="sealed"):
        store.increment(TASK_ID, "claim_all_mail")


def test_sealed_run_allows_only_declared_boundary_cleanup_actions() -> None:
    store = TaskRunStore()
    store.begin(TASK_ID)
    store.seal_business_result(TASK_ID, TaskOutcomeStatus.SUCCESS, "mail.empty", None)

    assert store.increment(TASK_ID, "close_reward_popup") == 1
    assert store.increment(TASK_ID, "close_mail") == 1
    assert store.increment(TASK_ID, "close_function_panel") == 1

    with pytest.raises(PermissionError, match="action limit"):
        store.increment(TASK_ID, "close_mail")
    with pytest.raises(PermissionError, match="sealed"):
        store.increment(TASK_ID, "claim_all_mail")
    with pytest.raises(PermissionError, match="sealed"):
        store.set_marker(TASK_ID, "mail.closed", True)


def test_run_store_home_boundary_is_the_final_success_transition() -> None:
    store = TaskRunStore()
    store.begin(TASK_ID)
    store.seal_business_result(TASK_ID, TaskOutcomeStatus.SUCCESS, "mail.empty", None)

    store.complete_home_boundary(TASK_ID)
    snapshot = store.snapshot(TASK_ID)

    assert snapshot["status"] is TaskOutcomeStatus.SUCCESS
    assert snapshot["final_status"] is TaskOutcomeStatus.SUCCESS
    assert snapshot["home_boundary_pending"] is False
    assert snapshot["home_boundary_status"] == "completed"
    assert snapshot["events"][-1]["name"] == "home_boundary_completed"

    with pytest.raises(PermissionError, match="already closed"):
        store.complete_home_boundary(TASK_ID)


def test_run_store_boundary_failure_preserves_business_evidence() -> None:
    store = TaskRunStore()
    store.begin(TASK_ID)
    store.seal_business_result(TASK_ID, TaskOutcomeStatus.SUCCESS, "mail.empty", None)

    store.fail_home_boundary(TASK_ID, "home.boundary", "HOME_BOUNDARY_TIMEOUT")
    snapshot = store.snapshot(TASK_ID)

    assert snapshot["status"] is TaskOutcomeStatus.FAILED
    assert snapshot["final_status"] is TaskOutcomeStatus.FAILED
    assert snapshot["business_result_sealed"] is True
    assert snapshot["business_result"]["postcondition"] == "mail.empty"
    assert snapshot["home_boundary_status"] == "failed"
    assert snapshot["final_boundary_failure_reason"] == "HOME_BOUNDARY_FAILED"
    assert snapshot["error_code"] == "HOME_BOUNDARY_TIMEOUT"


def test_diagnostics_persists_two_phase_result_and_business_evidence(tmp_path: Path) -> None:
    diagnostics = TaskDiagnostics(tmp_path, run_id="home-boundary")
    diagnostics.begin(TASK_ID)
    diagnostics.seal_business_result(
        TASK_ID,
        TaskOutcomeStatus.SUCCESS,
        "mail.empty",
        None,
    )

    pending = json.loads(
        (tmp_path / "home-boundary" / TASK_ID / "result.json").read_text(encoding="utf-8")
    )
    assert pending["status"] == "success"
    assert pending["finished_at"] is None
    assert pending["business_result_sealed"] is True
    assert pending["home_boundary_pending"] is True

    diagnostics.complete_home_boundary(TASK_ID)
    result = json.loads(
        (tmp_path / "home-boundary" / TASK_ID / "result.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "success"
    assert result["finished_at"] is not None
    assert result["home_boundary_pending"] is False
    assert result["final_status"] == "success"
    assert [event["name"] for event in result["events"]] == [
        "business_result_sealed",
        "home_boundary_completed",
    ]


def test_diagnostics_boundary_failure_keeps_original_business_postcondition(
    tmp_path: Path,
) -> None:
    diagnostics = TaskDiagnostics(tmp_path, run_id="home-boundary-failed")
    diagnostics.begin(TASK_ID)
    diagnostics.seal_business_result(
        TASK_ID,
        TaskOutcomeStatus.SUCCESS,
        "mail.empty",
        None,
    )
    diagnostics.fail_home_boundary(TASK_ID, "home.boundary", "HOME_BOUNDARY_TIMEOUT")

    result = json.loads(
        (
            tmp_path
            / "home-boundary-failed"
            / TASK_ID
            / "result.json"
        ).read_text(encoding="utf-8")
    )
    assert result["status"] == "failed"
    assert result["postcondition"] == "mail.empty"
    assert result["error_code"] == "HOME_BOUNDARY_TIMEOUT"
    assert result["business_result"]["postcondition"] == "mail.empty"
    assert result["final_boundary_failure_reason"] == "HOME_BOUNDARY_FAILED"


def test_public_home_boundary_is_strict_and_records_failure_before_abort() -> None:
    resource = json.loads(
        (
            Path("assets/resource/base/pipeline/common/home_boundary.json")
        ).read_text(encoding="utf-8")
    )
    boundary = resource["MJA_HOME_BOUNDARY"]
    failure = resource["MJA_HOME_BOUNDARY_FAILURE"]

    assert boundary["custom_action"] == "CompleteTaskBoundary"
    assert boundary["custom_action_param"] == {"boundary": "home"}
    assert boundary["next"] == ["MJA_COMMON_STOP"]
    assert boundary["on_error"] == ["MJA_HOME_BOUNDARY_FAILURE"]
    assert failure["custom_action"] == "RecordActiveTaskFailure"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
