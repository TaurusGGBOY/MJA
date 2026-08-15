from __future__ import annotations

import json
from datetime import datetime

import pytest

from agent.workflows.aggregate import AggregateResult, AggregateStatus
from agent.workflows.aggregate_report import (
    aggregate_exit_code,
    load_latest_aggregate_report,
    render_chinese_summary,
    write_aggregate_report,
)
from agent.workflows.models import TaskResult, TaskStatus


def aggregate(status: AggregateStatus) -> AggregateResult:
    return AggregateResult(
        task_results=(
            TaskResult(
                "MAIL_REWARD_DAILY",
                TaskStatus.FAILED,
                "timeout",
                {"click": 2},
                "WORKFLOW_TIMEOUT",
            ),
        ),
        status=status,
        started_at="2026-07-30T00:00:00+08:00",
        finished_at="2026-07-30T00:01:00+08:00",
        selected_date="2026-07-30",
        selected_task_ids=("MAIL_REWARD_DAILY", "BUY_TEA_DAILY"),
        remaining_task_ids=("BUY_TEA_DAILY",),
        last_task_id="MAIL_REWARD_DAILY",
        evidence_paths=("evidence/mail.png",),
    )


def test_report_round_trip_and_partial_failure_exit_code(tmp_path):
    path = write_aggregate_report(
        aggregate(AggregateStatus.COMPLETED_WITH_TASK_FAILURES),
        tmp_path,
        run_id="run-1",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "run-1"
    assert payload["status"] == "completed_with_task_failures"
    assert payload["remaining_task_ids"] == ["BUY_TEA_DAILY"]
    assert payload["completed_task_ids"] == []
    assert payload["task_results"][0]["action_counts"] == {"click": 2}
    assert aggregate_exit_code(payload) == 1
    assert "MAIL_REWARD_DAILY：失败" in render_chinese_summary(payload)
    assert load_latest_aggregate_report(tmp_path) == payload


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("completed", 0),
        ("completed_with_task_failures", 1),
        ("failed_task", 1),
        ("failed_runtime", 3),
        ("interrupted", 130),
    ],
)
def test_aggregate_exit_codes(status, expected):
    assert aggregate_exit_code({"status": status}) == expected


def test_aggregate_exit_code_rejects_invalid_status():
    with pytest.raises(ValueError, match="aggregate status"):
        aggregate_exit_code({"status": "unknown"})


def test_latest_report_can_be_filtered_by_start_time(tmp_path):
    write_aggregate_report(aggregate(AggregateStatus.FAILED_RUNTIME), tmp_path)
    future = datetime.fromtimestamp(4_102_444_800).astimezone()
    assert load_latest_aggregate_report(tmp_path, newer_than=future) is None


def test_completed_ids_and_chinese_totals_are_derived(tmp_path):
    base = aggregate(AggregateStatus.COMPLETED)
    result = AggregateResult(
        task_results=(
            TaskResult("MAIL_REWARD_DAILY", TaskStatus.COMPLETED, "claimed", {}),
            TaskResult("BUY_TEA_DAILY", TaskStatus.ALREADY_COMPLETE, "sold out", {}),
            TaskResult("SHADOW_RUINS_DAILY", TaskStatus.NOT_ELIGIBLE, "weekday", {}),
        ),
        status=AggregateStatus.COMPLETED,
        started_at=base.started_at,
        finished_at=base.finished_at,
        selected_date=base.selected_date,
        selected_task_ids=(
            "MAIL_REWARD_DAILY",
            "BUY_TEA_DAILY",
            "SHADOW_RUINS_DAILY",
        ),
        remaining_task_ids=(),
        last_task_id="SHADOW_RUINS_DAILY",
    )

    payload = json.loads(
        write_aggregate_report(result, tmp_path).read_text(encoding="utf-8")
    )
    summary = render_chinese_summary(payload)

    assert payload["completed_task_ids"] == [
        "MAIL_REWARD_DAILY",
        "BUY_TEA_DAILY",
    ]
    assert "完成/已完成：2" in summary
    assert "今日不适用：1" in summary
