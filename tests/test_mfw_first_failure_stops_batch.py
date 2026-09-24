from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace

from agent.custom.sink.task_flow import GlobalPrerequisiteStopSink, NotificationType
from agent.custom.support.state import SAFETY_BUDGETS
from agent.custom.support.task_session import TASK_SESSIONS


class FakeResource:
    def __init__(self):
        self.nodes = {}

    def get_node_data(self, name):
        return deepcopy(
            self.nodes.setdefault(
                name,
                {"recognition": "DirectHit", "action": "DoNothing", "next": ["business_action"]},
            )
        )

    def override_pipeline(self, nodes):
        for name, data in nodes.items():
            self.nodes[name] = deepcopy(data)
        return True


@dataclass
class FakeTasker:
    stop_calls: int = 0
    resource: FakeResource = field(default_factory=FakeResource)

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


def test_late_gui_submission_executes_failure_instead_of_native_cancel_success():
    tasker = FakeTasker()
    sink = GlobalPrerequisiteStopSink()
    sink.on_raw_notification(
        tasker, "Tasker.Task.Failed", {"task_id": 1, "entry": "0023-启动-游戏入口"}
    )
    for task_id, entry in [(2, "MAIL"), (3, "SHOP")]:
        original = tasker.resource.get_node_data(entry)
        sink.on_tasker_task(tasker, NotificationType.Starting, _detail(task_id, entry))
        blocked = tasker.resource.nodes[entry]
        assert blocked["custom_action"] == "FailTask"
        assert blocked["recognition"] == "DirectHit"
        assert blocked["next"] == [] and blocked["on_error"] == []
        # A duplicate raw notification must not save the temporary failure
        # override as the original business entry.
        sink.on_raw_notification(
            tasker, "Tasker.Task.Starting", {"task_id": task_id, "entry": entry}
        )
        sink.on_tasker_task(tasker, "Failed", _detail(task_id, entry))
        assert tasker.resource.nodes[entry] == original
    assert tasker.stop_calls == 0


def test_new_startup_resets_block_and_keeps_business_entry_intact():
    tasker = FakeTasker()
    sink = GlobalPrerequisiteStopSink()
    sink.on_tasker_task(tasker, "Failed", _detail(1, "0023-启动-游戏入口"))
    sink.on_tasker_task(tasker, "Starting", _detail(2, "MaaTaskerPostStop"))
    sink.on_tasker_task(tasker, "Starting", _detail(3, "0023-启动-游戏入口"))
    original = tasker.resource.get_node_data("MAIL")
    sink.on_tasker_task(tasker, "Starting", _detail(4, "MAIL"))
    assert tasker.resource.nodes["MAIL"] == original
    assert tasker.stop_calls == 0


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
