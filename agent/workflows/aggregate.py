"""Task-continuing aggregate scheduler for MFAAvalonia daily selections."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from agent.errors import MJAError

from .catalog import TASK_POLICIES, WORKFLOW_DEFINITION_ORDER, workflow_sequence_for_date
from .engine import WorkflowDriver, run_workflow
from .models import TaskResult, TaskStatus, WorkflowDefinition
from .registry import WORKFLOW_DEFINITIONS


class AggregateStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_TASK_FAILURES = "completed_with_task_failures"
    FAILED_TASK = "failed_task"
    FAILED_RUNTIME = "failed_runtime"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class AggregateResult:
    task_results: tuple[TaskResult, ...]
    status: AggregateStatus
    started_at: str
    finished_at: str
    selected_date: str
    selected_task_ids: tuple[str, ...]
    remaining_task_ids: tuple[str, ...]
    last_task_id: str | None = None
    stop_reason: str | None = None
    error_code: str | None = None
    evidence_paths: tuple[str, ...] = ()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class AggregateScheduler:
    def __init__(
        self,
        driver_factory: Callable[[str], WorkflowDriver],
        *,
        diagnostics_factory: Callable[[str], Any] | None = None,
        definitions: Mapping[str, WorkflowDefinition] = WORKFLOW_DEFINITIONS,
        policies: Mapping[str, Any] = TASK_POLICIES,
        runner: Callable[..., TaskResult] = run_workflow,
    ) -> None:
        self.driver_factory = driver_factory
        self.diagnostics_factory = diagnostics_factory or (lambda _task_id: None)
        self.definitions = definitions
        self.policies = policies
        self.runner = runner

    def run(
        self,
        selected_task_ids: Sequence[str] | None = None,
        *,
        day: date | None = None,
        checkpoint: Callable[[AggregateResult], None] | None = None,
    ) -> AggregateResult:
        started_at = _now()
        selected_day = day or date.today()
        selected = self._selected(selected_task_ids, selected_day)
        results: list[TaskResult] = []
        status = AggregateStatus.COMPLETED
        stop_reason: str | None = None
        error_code: str | None = None
        attempted = 0
        for index, task_id in enumerate(selected):
            try:
                diagnostics = self.diagnostics_factory(task_id)
                result = self.runner(
                    self.definitions[task_id],
                    self.driver_factory(task_id),
                    self.policies[task_id],
                    diagnostics,
                    day=selected_day,
                )
            except KeyboardInterrupt:
                status = AggregateStatus.INTERRUPTED
                stop_reason = "interrupted"
                attempted = index
                aggregate = self._result(
                    results,
                    status,
                    started_at,
                    selected_day,
                    selected,
                    attempted,
                    stop_reason,
                    error_code,
                )
                if checkpoint is not None:
                    checkpoint(aggregate)
                return aggregate
            except Exception as exc:
                if is_runtime_failure(exc):
                    status = AggregateStatus.FAILED_RUNTIME
                    stop_reason = str(exc)
                    error_code = error_code_for(exc) or type(exc).__name__
                    attempted = index
                    aggregate = self._result(
                        results,
                        status,
                        started_at,
                        selected_day,
                        selected,
                        attempted,
                        stop_reason,
                        error_code,
                    )
                    if checkpoint is not None:
                        checkpoint(aggregate)
                    return aggregate
                result = TaskResult(
                    task_id,
                    TaskStatus.FAILED,
                    "runner_exception",
                    {},
                    error_code_for(exc) or type(exc).__name__,
                )
            results.append(result)
            attempted = index + 1
            if result.status is TaskStatus.FAILED:
                # A business-task failure belongs to this task's failure
                # domain.  The next task gets its own boundary check and is
                # still invoked; only session/runtime failures above stop the
                # batch.  This is the same isolation property as a Maa preset
                # containing independent task entries.
                status = AggregateStatus.COMPLETED_WITH_TASK_FAILURES
                if error_code is None:
                    error_code = result.error_code
            if any(item.status is TaskStatus.FAILED for item in results):
                status = AggregateStatus.COMPLETED_WITH_TASK_FAILURES
            aggregate = self._result(
                results,
                status,
                started_at,
                selected_day,
                selected,
                attempted,
                stop_reason,
                error_code,
            )
            if checkpoint is not None:
                checkpoint(aggregate)
        return self._result(
            results,
            status,
            started_at,
            selected_day,
            selected,
            attempted,
            stop_reason,
            error_code,
        )

    @staticmethod
    def _result(
        results: Sequence[TaskResult],
        status: AggregateStatus,
        started_at: str,
        selected_day: date,
        selected: tuple[str, ...],
        attempted: int,
        stop_reason: str | None,
        error_code: str | None,
    ) -> AggregateResult:
        return AggregateResult(
            tuple(results),
            status,
            started_at,
            _now(),
            selected_day.isoformat(),
            selected,
            selected[attempted:],
            results[-1].task_id if results else None,
            stop_reason,
            error_code,
        )

    def _selected(self, selected: Sequence[str] | None, day: date | None) -> tuple[str, ...]:
        sequence = workflow_sequence_for_date(day)
        if selected is None or any(str(item).strip().lower() == "daily_all" for item in selected):
            return sequence
        requested = {str(item).strip().upper() for item in selected}
        unknown = requested - set(WORKFLOW_DEFINITION_ORDER)
        if unknown:
            raise ValueError(f"unknown workflow task: {sorted(unknown)[0]}")
        return tuple(task_id for task_id in sequence if task_id in requested)

def error_code_for(exc: BaseException) -> str:
    return str(getattr(getattr(exc, "code", None), "value", "") or "")


def is_runtime_failure(exc: BaseException) -> bool:
    code = error_code_for(exc)
    return isinstance(exc, MJAError) and code.startswith(
        ("ANDROID_", "ADB_", "CONTROLLER_", "WINDOW_", "LOGIN_")
    )


__all__ = [
    "AggregateResult",
    "AggregateScheduler",
    "AggregateStatus",
    "error_code_for",
    "is_runtime_failure",
]
