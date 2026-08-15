from __future__ import annotations

from dataclasses import dataclass

from agent.custom.sink.task_flow import TaskFlowStopSink


@dataclass
class FakeTasker:
    stopped: bool = False
    stop_calls: int = 0

    def post_stop(self) -> None:
        self.stop_calls += 1
        self.stopped = True


def test_first_native_failure_stops_before_the_next_task_starts() -> None:
    tasker = FakeTasker()
    sink = TaskFlowStopSink()
    started: list[str] = []

    for task_id in ("GAME_START", "FIRST_FAILURE", "SENTINEL_AFTER_FAILURE"):
        if tasker.stopped:
            break
        started.append(task_id)
        if task_id == "FIRST_FAILURE":
            sink.on_raw_notification(
                tasker,
                "Tasker.Task.Failed",
                {"task_id": 2},
            )

    assert started == ["GAME_START", "FIRST_FAILURE"]
    assert tasker.stop_calls == 1


def test_duplicate_failure_notifications_do_not_post_a_second_native_stop() -> None:
    tasker = FakeTasker()
    sink = TaskFlowStopSink()

    sink.on_raw_notification(tasker, "Tasker.Task.Failed", {"task_id": 1})
    sink.on_tasker_task(tasker, "Failed", {"task_id": 1})

    assert tasker.stop_calls == 1

