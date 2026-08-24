from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from agent.custom.sink.task_flow import GlobalPrerequisiteStopSink
from agent.custom.support.state import SAFETY_BUDGETS
from agent.custom.support.task_session import TASK_SESSIONS


@dataclass
class FakeTasker:
    stop_calls: int = 0

    def post_stop(self) -> None:
        self.stop_calls += 1


def _detail(task_id: int, entry: str) -> SimpleNamespace:
    return SimpleNamespace(task_id=task_id, entry=entry)


def test_business_failure_continues_to_the_next_selected_task() -> None:
    tasker = FakeTasker()
    sink = GlobalPrerequisiteStopSink()
    started: list[str] = []

    for task_id, entry, status in (
        (1, "0023-启动-游戏入口", "Succeeded"),
        (2, "MAIL_REWARD_DAILY_ENTRY", "Failed"),
        (3, "SENTINEL_AFTER_FAILURE", "Succeeded"),
    ):
        started.append(entry)
        sink.on_raw_notification(
            tasker,
            f"Tasker.Task.{status}",
            {"task_id": task_id, "entry": entry},
        )

    assert started == [
        "0023-启动-游戏入口",
        "MAIL_REWARD_DAILY_ENTRY",
        "SENTINEL_AFTER_FAILURE",
    ]
    assert tasker.stop_calls == 0


def test_game_start_failure_stops_before_the_next_selected_task() -> None:
    tasker = FakeTasker()
    sink = GlobalPrerequisiteStopSink()
    started: list[str] = []

    for task_id, entry, status in (
        (1, "0023-启动-游戏入口", "Failed"),
        (2, "SENTINEL_AFTER_FAILURE", "Succeeded"),
    ):
        if tasker.stop_calls:
            break
        started.append(entry)
        sink.on_raw_notification(
            tasker,
            f"Tasker.Task.{status}",
            {"task_id": task_id, "entry": entry},
        )

    assert started == ["0023-启动-游戏入口"]
    assert tasker.stop_calls == 1


def test_duplicate_startup_failure_notifications_post_one_stop() -> None:
    tasker = FakeTasker()
    sink = GlobalPrerequisiteStopSink()
    details = {"task_id": 1, "entry": "0023-启动-游戏入口"}

    sink.on_raw_notification(tasker, "Tasker.Task.Failed", details)
    sink.on_tasker_task(tasker, "Failed", _detail(1, "0023-启动-游戏入口"))

    assert tasker.stop_calls == 1


def test_both_native_terminal_events_release_the_safety_session() -> None:
    TASK_SESSIONS.end(7001)
    TASK_SESSIONS.end(7002)
    SAFETY_BUDGETS.end("MAIL_REWARD_DAILY")
    for native_task_id, status in ((7001, "Succeeded"), (7002, "Failed")):
        TASK_SESSIONS.begin(native_task_id, "MAIL_REWARD_DAILY")
        sink = GlobalPrerequisiteStopSink()
        sink.on_raw_notification(
            FakeTasker(),
            f"Tasker.Task.{status}",
            {"task_id": native_task_id, "entry": "MAIL_REWARD_DAILY_ENTRY"},
        )
        assert TASK_SESSIONS.business_task_id(native_task_id) is None
