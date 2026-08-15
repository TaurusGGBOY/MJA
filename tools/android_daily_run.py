"""Run Jianzhichuan daily tasks as isolated Maa Android jobs.

The GUI still exposes an aggregate entry for compatibility, but the command
line all-dailies entry is deliberately a supervisor: one task, one MaaPiCli
process, one task result, while the stable game process is reused across
tasks. A business-task failure is recorded and does not prevent later tasks
from being attempted; an explicit shared-runtime failure stops the sequence
with the remaining task IDs preserved.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from agent.errors import ErrorCode
from agent.workflows.aggregate import AggregateResult, AggregateStatus
from agent.workflows.aggregate_report import (
    aggregate_exit_code,
    aggregate_latest_path,
    load_latest_aggregate_report,
    render_chinese_summary,
    write_aggregate_report,
)
from agent.workflows.catalog import (
    WORKFLOW_DEFINITION_ORDER,
    workflow_sequence_for_date,
)
from agent.workflows.models import TaskResult, TaskStatus
from tools.android_run import AndroidRun

_SHARED_RUNTIME_FAST_FAIL_CODE = ErrorCode.ANDROID_SYSTEM_UI_NOT_RESPONDING.value
_SHARED_RUNTIME_NO_ACTION_CODE = ErrorCode.ANDROID_SHARED_RUNTIME_FAILURE.value


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _run_id() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")


def _error_code(error: BaseException, fallback: str = "ANDROID_RUN_FAILED") -> str:
    code = getattr(getattr(error, "code", None), "value", None)
    return str(code or fallback)


def _failure(
    task_id: str,
    *,
    postcondition: str,
    error_code: str,
) -> TaskResult:
    return TaskResult(
        task_id,
        TaskStatus.FAILED,
        postcondition,
        {},
        error_code,
    )


def _shared_runtime_fast_fail_code(result: TaskResult) -> str | None:
    """Classify only explicit shared-runtime failures as sequence hard stops."""

    if result.error_code == _SHARED_RUNTIME_FAST_FAIL_CODE:
        return _SHARED_RUNTIME_FAST_FAIL_CODE
    if result.postcondition in {
        "android_runner",
        "task_result",
        "maa_child_timeout",
        "maa_child_exit",
    } and not result.action_counts:
        # A runner-level failure with no action evidence cannot be attributed
        # to the current business page. Once this task's child budget ends,
        # starting more tasks would only repeat the same broken runtime.
        return _SHARED_RUNTIME_NO_ACTION_CODE
    return None


def _selected_tasks(requested: Sequence[str] | None, day: date) -> tuple[str, ...]:
    """Resolve CLI selection using the catalog's deterministic order.

    An omitted selection (or ``daily_all``) is date-filtered.  Explicit task
    selection is kept explicit, including a Monday-only task, so a targeted
    invocation can still produce the workflow's own ``not_eligible`` result.
    """

    if not requested:
        return workflow_sequence_for_date(day)
    daily_all = [item for item in requested if str(item).strip().lower() == "daily_all"]
    if daily_all:
        if len(daily_all) != len(requested):
            raise ValueError("daily_all 不能与其他任务混用")
        return workflow_sequence_for_date(day)
    normalized = {str(item).strip().upper() for item in requested}
    if "" in normalized:
        raise ValueError("任务名不能为空")
    unknown = normalized - set(WORKFLOW_DEFINITION_ORDER)
    if unknown:
        raise ValueError(f"未知任务 {sorted(unknown)[0]}")
    return tuple(task_id for task_id in WORKFLOW_DEFINITION_ORDER if task_id in normalized)


def _task_result_paths(debug_root: Path, task_id: str) -> list[Path]:
    task_root = Path(debug_root) / "daily" / task_id.lower()
    if not task_root.is_dir():
        return []
    paths = list(task_root.rglob("result.json"))
    paths.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return paths


def _read_task_result(
    debug_root: Path,
    task_id: str,
    *,
    started_at: datetime,
) -> TaskResult | None:
    """Read the newest task result created by this isolated child run."""

    minimum_mtime = started_at.timestamp() - 1.0
    paths = []
    for path in _task_result_paths(debug_root, task_id):
        try:
            if path.stat().st_mtime >= minimum_mtime:
                paths.append(path)
        except OSError:
            continue
    if not paths:
        return None

    path = paths[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("result.json must contain an object")
        if str(payload.get("task_id", "")).strip().upper() != task_id:
            raise ValueError("result.json task_id does not match the selected task")
        status = TaskStatus(str(payload["status"]))
        postcondition = payload.get("postcondition")
        action_counts = payload.get("action_counts", {})
        error_code = payload.get("error_code")
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("result.json postcondition is missing")
        if not isinstance(action_counts, dict):
            raise ValueError("result.json action_counts must be an object")
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("result.json error_code must be a string or null")
        return TaskResult(task_id, status, postcondition, action_counts, error_code)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _failure(
            task_id,
            postcondition=f"invalid_result:{path}",
            error_code="TASK_RESULT_INVALID",
        )


def _aggregate(
    task_results: Sequence[TaskResult],
    selected: tuple[str, ...],
    *,
    started_at: str,
    selected_date: date,
    interrupted: bool = False,
    stop_reason: str | None = None,
    finalized: bool = False,
    runtime_failed: bool = False,
    error_code: str | None = None,
) -> AggregateResult:
    failures = [item for item in task_results if item.status is TaskStatus.FAILED]
    status = (
        AggregateStatus.INTERRUPTED
        if interrupted
        else (
            AggregateStatus.FAILED_RUNTIME
            if runtime_failed
            else (
                AggregateStatus.COMPLETED_WITH_TASK_FAILURES
                if failures
                else AggregateStatus.COMPLETED
            )
        )
    )
    attempted = len(task_results)
    # A checkpoint after task N must expose tasks N+1.. as pending. Only the
    # final aggregate is allowed to report an empty remaining set.
    remaining = selected[attempted:] if not finalized else ()
    return AggregateResult(
        tuple(task_results),
        status,
        started_at,
        _now(),
        selected_date.isoformat(),
        selected,
        remaining,
        task_results[-1].task_id if task_results else None,
        stop_reason or (failures[0].error_code if failures else None),
        error_code or (failures[0].error_code if failures else None),
    )


def run_isolated_dailies(
    android: AndroidRun,
    selected: tuple[str, ...],
    *,
    debug_root: Path,
    stop: bool,
    wipe_data: bool,
    run_id: str,
    started_at: str,
) -> AggregateResult:
    """Run isolated tasks, stopping only for interruption or shared runtime failure."""

    selected_date = date.today()
    results: list[TaskResult] = []
    for index, task_id in enumerate(selected):
        task_started = datetime.now().astimezone()
        child_code: int | None = None
        try:
            child_code = android.run(
                task_id.lower(),
                stop=stop and index == len(selected) - 1,
                wipe_data=wipe_data and index == 0,
                start_session=True,
                # MaaPiCli remains isolated per task, but the Unity game
                # process is reused like the GUI's select-all run. A failed
                # task is left on its live surface for the next workflow's
                # bounded Maa lifecycle recovery; force-stopping this game
                # between tasks can make its native startup guard kill the
                # next process before Maa attaches.
                fresh_process=False,
            )
        except KeyboardInterrupt:
            interrupted = _aggregate(
                results,
                selected,
                started_at=started_at,
                selected_date=selected_date,
                interrupted=True,
                stop_reason="interrupted",
            )
            write_aggregate_report(interrupted, debug_root, run_id=run_id)
            return interrupted
        except Exception as exc:
            # Preserve a precise task-level runner error. The explicit shared
            # runtime classifier below decides whether the sequence continues
            # or becomes a failed_runtime aggregate.
            result = _failure(
                task_id,
                postcondition="android_runner",
                error_code=_error_code(exc),
            )
        else:
            result = _read_task_result(
                debug_root,
                task_id,
                started_at=task_started,
            )
            if result is None:
                result = _failure(
                    task_id,
                    postcondition="task_result",
                    error_code=(
                        "TASK_INTERRUPTED"
                        if child_code == 130
                        else "WORKFLOW_TIMEOUT"
                        if child_code == 124
                        else "TASK_RESULT_MISSING"
                    ),
                )
            elif child_code == 124 and result.status is not TaskStatus.FAILED:
                # The native child timeout is authoritative even if a stale
                # success-looking artifact was flushed during termination.
                result = _failure(
                    task_id,
                    postcondition="maa_child_timeout",
                    error_code="WORKFLOW_TIMEOUT",
                )
            elif child_code not in (None, 0) and result.status is not TaskStatus.FAILED:
                # A successful-looking click trace cannot override a failed
                # Maa child.  The result remains task-local and later jobs
                # are still allowed to continue.
                result = _failure(
                    task_id,
                    postcondition="maa_child_exit",
                    error_code="MAA_CHILD_EXIT_NONZERO",
                )

        results.append(result)
        if child_code == 130:
            interrupted = _aggregate(
                results,
                selected,
                started_at=started_at,
                selected_date=selected_date,
                interrupted=True,
                stop_reason="interrupted",
            )
            write_aggregate_report(interrupted, debug_root, run_id=run_id)
            return interrupted
        shared_runtime_code = _shared_runtime_fast_fail_code(result)
        if shared_runtime_code:
            fast_fail = _aggregate(
                results,
                selected,
                started_at=started_at,
                selected_date=selected_date,
                runtime_failed=True,
                stop_reason=(
                    shared_runtime_code
                    if result.error_code == shared_runtime_code
                    else f"{shared_runtime_code}:{result.error_code or 'unknown'}"
                ),
                error_code=shared_runtime_code,
            )
            write_aggregate_report(fast_fail, debug_root, run_id=run_id)
            return fast_fail
        checkpoint = _aggregate(
            results,
            selected,
            started_at=started_at,
            selected_date=selected_date,
            finalized=index == len(selected) - 1,
        )
        write_aggregate_report(checkpoint, debug_root, run_id=run_id)

    final = _aggregate(
        results,
        selected,
        started_at=started_at,
        selected_date=selected_date,
        finalized=True,
    )
    write_aggregate_report(final, debug_root, run_id=run_id)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行剑之川 Android 日常任务")
    parser.add_argument("--task", action="append", dest="tasks")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--wipe-data", action="store_true")
    args = parser.parse_args(argv)

    selected_date = date.today()
    try:
        selected = _selected_tasks(args.tasks, selected_date)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    started_at = _now()
    run_id = _run_id()
    try:
        android = AndroidRun()
        install_root = Path(getattr(android, "install_root", Path("install")))
        debug_root = install_root / "debug" / "runs"
        run_isolated_dailies(
            android,
            selected,
            debug_root=debug_root,
            stop=args.stop,
            wipe_data=args.wipe_data,
            run_id=run_id,
            started_at=started_at,
        )
        # Re-read the atomically written report.  The persisted artifact, not
        # an in-memory status, is the reporting source of truth.
        payload = load_latest_aggregate_report(
            debug_root,
            newer_than=datetime.fromisoformat(started_at),
        )
        if payload is None:
            print("ERROR: 本次运行没有生成聚合结果", file=sys.stderr)
            return 3
        print(render_chinese_summary(payload))
        print(f"结果文件：{aggregate_latest_path(debug_root)}")
        return aggregate_exit_code(payload)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"ERROR: 聚合结果无效：{exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"ERROR: 日常 supervisor 失败：{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "_read_task_result",
    "_selected_tasks",
    "main",
    "run_isolated_dailies",
]
