"""Persistent reports and human summaries for aggregate daily runs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .aggregate import AggregateResult, AggregateStatus
from .models import TaskStatus

_RUN_ID = re.compile(r"^[A-Za-z0-9._+-]+$")
_TASK_LABELS = {
    TaskStatus.COMPLETED.value: "完成",
    TaskStatus.ALREADY_COMPLETE.value: "已完成",
    TaskStatus.NOT_ELIGIBLE.value: "今日不适用",
    TaskStatus.FAILED.value: "失败",
}
_AGGREGATE_LABELS = {
    AggregateStatus.COMPLETED.value: "全部完成",
    AggregateStatus.COMPLETED_WITH_TASK_FAILURES.value: "完成但有任务失败",
    AggregateStatus.FAILED_TASK.value: "任务失败，已停止",
    AggregateStatus.FAILED_RUNTIME.value: "运行环境故障，已停止",
    AggregateStatus.INTERRUPTED.value: "运行已中断",
}
_EXIT_CODES = {
    AggregateStatus.COMPLETED.value: 0,
    AggregateStatus.COMPLETED_WITH_TASK_FAILURES.value: 1,
    AggregateStatus.FAILED_TASK.value: 1,
    AggregateStatus.FAILED_RUNTIME.value: 3,
    AggregateStatus.INTERRUPTED.value: 130,
}


def aggregate_latest_path(root: Path) -> Path:
    return Path(root) / "daily" / "aggregate-latest.json"


def _default_run_id() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")


def _payload(result: AggregateResult, run_id: str) -> dict[str, Any]:
    completed = {
        TaskStatus.COMPLETED,
        TaskStatus.ALREADY_COMPLETE,
    }
    return {
        "schema_version": 1,
        "run_id": run_id,
        "status": result.status.value,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "selected_date": result.selected_date,
        "selected_task_ids": list(result.selected_task_ids),
        "completed_task_ids": [
            item.task_id for item in result.task_results if item.status in completed
        ],
        "remaining_task_ids": list(result.remaining_task_ids),
        "last_task_id": result.last_task_id,
        "stop_reason": result.stop_reason,
        "error_code": result.error_code,
        "evidence_paths": list(result.evidence_paths),
        "task_results": [item.as_dict() for item in result.task_results],
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_aggregate_report(
    result: AggregateResult,
    root: Path,
    *,
    run_id: str | None = None,
) -> Path:
    selected_run_id = run_id or _default_run_id()
    if not _RUN_ID.fullmatch(selected_run_id):
        raise ValueError("run_id contains unsupported characters")
    directory = Path(root) / "daily"
    report_path = directory / f"aggregate-{selected_run_id}.json"
    payload = _payload(result, selected_run_id)
    _atomic_json(report_path, payload)
    _atomic_json(aggregate_latest_path(root), payload)
    return report_path


def load_latest_aggregate_report(
    root: Path,
    *,
    newer_than: datetime | None = None,
) -> dict[str, Any] | None:
    path = aggregate_latest_path(root)
    try:
        if newer_than is not None and path.stat().st_mtime < newer_than.timestamp():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(payload, dict):
        raise ValueError("aggregate report must be a JSON object")
    return payload


def aggregate_exit_code(payload: Mapping[str, Any]) -> int:
    status = payload.get("status")
    try:
        return _EXIT_CODES[str(status)]
    except KeyError as exc:
        raise ValueError(f"invalid aggregate status: {status}") from exc


def render_chinese_summary(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status", ""))
    if status not in _AGGREGATE_LABELS:
        raise ValueError(f"invalid aggregate status: {status}")
    task_results = payload.get("task_results", [])
    if not isinstance(task_results, list):
        raise ValueError("task_results must be a list")
    lines = [f"全量日常：{_AGGREGATE_LABELS[status]}"]
    counts = {key: 0 for key in _TASK_LABELS}
    for item in task_results:
        if not isinstance(item, dict):
            raise ValueError("task result must be an object")
        task_status = str(item.get("status", ""))
        label = _TASK_LABELS.get(task_status, task_status or "未知")
        lines.append(f"{item.get('task_id', 'UNKNOWN')}：{label}")
        if task_status in counts:
            counts[task_status] += 1
    completed_count = counts[TaskStatus.COMPLETED.value] + counts[
        TaskStatus.ALREADY_COMPLETE.value
    ]
    failures = counts[TaskStatus.FAILED.value]
    remaining = payload.get("remaining_task_ids", [])
    remaining_count = len(remaining) if isinstance(remaining, list) else 0
    lines.append(
        "汇总："
        f"完成/已完成：{completed_count}，"
        f"今日不适用：{counts[TaskStatus.NOT_ELIGIBLE.value]}，"
        f"失败：{failures}，"
        f"剩余：{remaining_count}"
    )
    return "\n".join(lines)


__all__ = [
    "aggregate_exit_code",
    "aggregate_latest_path",
    "load_latest_aggregate_report",
    "render_chinese_summary",
    "write_aggregate_report",
]
