from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.diagnostics import TaskDiagnostics
from agent.custom.support.models import TaskOutcomeStatus
from agent.safety import SafetyDecision, SafetyReason
from agent.workflows.models import ActionIntent


def test_diagnostics_redacts_credentials(tmp_path: Path):
    diagnostics = TaskDiagnostics(tmp_path, run_id="run-1")
    diagnostics.begin("MAIL_REWARD_DAILY")
    diagnostics.record_action(
        "claim_all_mail",
        {"page": "mail", "password": "secret", "nested": {"token": "abc"}},
    )
    diagnostics.finish(
        "MAIL_REWARD_DAILY",
        TaskOutcomeStatus.FAILED,
        "mail",
        "password=secret token=abc",
    )

    result = json.loads(
        (tmp_path / "run-1/MAIL_REWARD_DAILY/result.json").read_text(encoding="utf-8")
    )
    trace = (tmp_path / "run-1/MAIL_REWARD_DAILY/action-trace.jsonl").read_text(
        encoding="utf-8"
    )

    assert result["status"] == TaskOutcomeStatus.FAILED.value
    assert "secret" not in json.dumps(result, ensure_ascii=False)
    assert "abc" not in trace


def test_diagnostics_accepts_workflow_engine_action_signature(tmp_path: Path):
    diagnostics = TaskDiagnostics(tmp_path, run_id="run-workflow")
    diagnostics.begin("MAIL_REWARD_DAILY")

    diagnostics.record_action(
        ActionIntent("claim_all_mail", "mail_page", "claim_all", input_kind="none"),
        SafetyDecision(True, SafetyReason.ALLOWED, ()),
        "frame-1",
    )

    task_dir = tmp_path / "run-workflow/MAIL_REWARD_DAILY"
    trace = json.loads(
        (task_dir / "action-trace.jsonl").read_text(encoding="utf-8").strip()
    )
    assert trace["action_id"] == "claim_all_mail"
    assert trace["details"] == {
        "frame_id": "frame-1",
        "allowed": True,
        "reason": "allowed",
    }
    assert diagnostics.status("MAIL_REWARD_DAILY") is None


def test_diagnostics_writes_atomic_result_trace_and_failure_images(tmp_path: Path):
    diagnostics = TaskDiagnostics(tmp_path, run_id="run-2")
    diagnostics.begin("MAIL_REWARD_DAILY")
    diagnostics.write_before_image("before")
    diagnostics.write_after_image(b"after")
    diagnostics.finish("MAIL_REWARD_DAILY", TaskOutcomeStatus.SUCCESS, "mail", None)

    task_dir = tmp_path / "run-2/MAIL_REWARD_DAILY"
    assert (task_dir / "result.json").is_file()
    assert (task_dir / "action-trace.jsonl").is_file()
    assert (task_dir / "before.png").read_bytes() == b"before"
    assert (task_dir / "after.png").read_bytes() == b"after"
    assert not (task_dir / "failure.png").exists()

    diagnostics.write_failure_image(b"failure")
    assert not (task_dir / "failure.png").exists()

    diagnostics.finish("MAIL_REWARD_DAILY", TaskOutcomeStatus.FAILED, "mail", "failed")
    diagnostics.write_failure_image(b"failure")
    assert (task_dir / "failure.png").read_bytes() == b"failure"


def test_diagnostic_io_failure_does_not_overwrite_verified_business_status(
    tmp_path: Path, monkeypatch
):
    diagnostics = TaskDiagnostics(tmp_path, run_id="run-3")
    diagnostics.begin("MAIL_REWARD_DAILY")
    diagnostics.finish("MAIL_REWARD_DAILY", TaskOutcomeStatus.SUCCESS, "mail", None)

    def fail_write(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(diagnostics, "_atomic_write_json", fail_write)
    diagnostics.finish("MAIL_REWARD_DAILY", TaskOutcomeStatus.FAILED, "mail", "io-error")

    assert diagnostics.status("MAIL_REWARD_DAILY") is TaskOutcomeStatus.FAILED
    result = json.loads(
        (tmp_path / "run-3/MAIL_REWARD_DAILY/result.json").read_text(encoding="utf-8")
    )
    assert result["status"] == TaskOutcomeStatus.SUCCESS.value
