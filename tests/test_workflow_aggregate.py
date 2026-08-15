from datetime import date

import pytest

from agent.errors import ErrorCode, MJAError
from agent.workflows.aggregate import AggregateScheduler, AggregateStatus
from agent.workflows.models import TaskResult, TaskStatus

IDS = (
    "MAIL_REWARD_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
)


def result(task_id, status):
    return TaskResult(task_id, status, "done", {})


def test_aggregate_uses_order_filters_monday_and_continues_after_task_failure():
    calls = []

    def runner(definition, driver, policy, diagnostics, *, day):
        calls.append(policy.task_id)
        status = (
            TaskStatus.FAILED
            if policy.task_id == "MAIL_REWARD_DAILY"
            else TaskStatus.ALREADY_COMPLETE
        )
        return result(policy.task_id, status)

    scheduler = AggregateScheduler(lambda task_id: object(), runner=runner)
    aggregate = scheduler.run(IDS, day=date(2026, 7, 27))
    assert calls == list(IDS)
    assert aggregate.status is AggregateStatus.COMPLETED_WITH_TASK_FAILURES
    assert aggregate.remaining_task_ids == ()
    assert aggregate.last_task_id == IDS[-1]
    assert [item.status for item in aggregate.task_results] == [
        TaskStatus.FAILED,
        TaskStatus.ALREADY_COMPLETE,
        TaskStatus.ALREADY_COMPLETE,
        TaskStatus.ALREADY_COMPLETE,
    ]


def test_aggregate_stops_on_device_failure():
    calls = []

    def runner(definition, driver, policy, diagnostics, *, day):
        calls.append(policy.task_id)
        raise MJAError(ErrorCode.ANDROID_GAME_NOT_FOREGROUND, "game stopped")

    scheduler = AggregateScheduler(lambda task_id: object(), runner=runner)
    aggregate = scheduler.run(IDS, day=date(2026, 7, 27))
    assert calls == ["MAIL_REWARD_DAILY"]
    assert aggregate.status is AggregateStatus.FAILED_RUNTIME
    assert aggregate.remaining_task_ids == IDS
    assert aggregate.error_code == "ANDROID_GAME_NOT_FOREGROUND"


def test_aggregate_checkpoints_after_each_task_and_preserves_statuses():
    checkpoints = []

    def runner(definition, driver, policy, diagnostics, *, day):
        return result(policy.task_id, TaskStatus.FAILED)

    scheduler = AggregateScheduler(lambda task_id: object(), runner=runner)
    aggregate = scheduler.run(
        IDS[:2],
        day=date(2026, 7, 27),
        checkpoint=checkpoints.append,
    )

    assert [item.status for item in aggregate.task_results] == [
        TaskStatus.FAILED,
        TaskStatus.FAILED,
    ]
    assert aggregate.status is AggregateStatus.COMPLETED_WITH_TASK_FAILURES
    assert checkpoints[0].remaining_task_ids == (IDS[1],)
    assert checkpoints[-1].remaining_task_ids == ()
    assert aggregate.selected_date == "2026-07-27"


def test_aggregate_preserves_non_runtime_runner_failure_without_generic_child_error():
    def runner(definition, driver, policy, diagnostics, *, day):
        raise MJAError(ErrorCode.WORKFLOW_POSTCONDITION_MISSING, "task boundary missing")

    scheduler = AggregateScheduler(lambda task_id: object(), runner=runner)
    aggregate = scheduler.run(IDS[:2], day=date(2026, 7, 27))

    assert aggregate.status is AggregateStatus.COMPLETED_WITH_TASK_FAILURES
    assert aggregate.remaining_task_ids == ()
    assert [item.error_code for item in aggregate.task_results] == [
        "WORKFLOW_POSTCONDITION_MISSING",
        "WORKFLOW_POSTCONDITION_MISSING",
    ]
    assert all(
        item.postcondition != "aggregate_child_exception"
        for item in aggregate.task_results
    )


def test_aggregate_records_interruption_without_running_later_tasks():
    calls = []
    checkpoints = []

    def runner(definition, driver, policy, diagnostics, *, day):
        calls.append(policy.task_id)
        raise KeyboardInterrupt

    scheduler = AggregateScheduler(lambda task_id: object(), runner=runner)
    aggregate = scheduler.run(
        IDS,
        day=date(2026, 7, 27),
        checkpoint=checkpoints.append,
    )

    assert calls == [IDS[0]]
    assert aggregate.status is AggregateStatus.INTERRUPTED
    assert aggregate.remaining_task_ids == IDS
    assert checkpoints[-1] == aggregate


def test_aggregate_rejects_unknown_selection():
    scheduler = AggregateScheduler(lambda task_id: object())
    with pytest.raises(ValueError, match="unknown workflow"):
        scheduler.run(["NO_SUCH_TASK"])
