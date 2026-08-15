from __future__ import annotations

import json
from pathlib import Path

from agent.workflows.catalog import WORKFLOW_DEFINITION_ORDER
from tools.verify_live_tasks import verify_live_tasks


def test_gate_reports_all_pending_canonical_tasks(tmp_path: Path):
    records = tmp_path / "verification" / "tasks"
    records.mkdir(parents=True)
    for task_id in WORKFLOW_DEFINITION_ORDER:
        (records / f"{task_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "task_id": task_id,
                    "state": "live_pending",
                    "implementation_commit": "1ef968d3be174f2b327e3ee485b49077ac413367",
                    "verified_at": "2026-07-28T00:00:00+08:00",
                    "controller_backend": "ScreenCaptureKit",
                    "logical_window_size": [1280, 720],
                    "maa_capture_size": [1280, 720],
                    "normal_run_status": "already_complete",
                    "noop_run_status": "already_complete",
                    "evidence": [],
                    "postcondition_evidence": [],
                    "pending_branches": ["live capture pending"],
                }
            ),
            encoding="utf-8",
        )
    errors = verify_live_tasks(tmp_path)
    assert len(errors) == len(WORKFLOW_DEFINITION_ORDER)
    assert errors[0] == "MAIL_REWARD_DAILY: state=live_pending"


def test_gate_reports_missing_record(tmp_path: Path):
    errors = verify_live_tasks(tmp_path, required_task_ids=("MAIL_REWARD_DAILY",))
    assert errors == ["MAIL_REWARD_DAILY: missing record"]
