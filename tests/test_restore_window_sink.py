from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agent.errors import ErrorCode
from agent.sinks.restore_window import RestoreWindowSink


@dataclass
class FakeImage:
    saved: list[Path]

    def save(self, path: Path) -> None:
        self.saved.append(path)
        path.write_bytes(b"png")


class FakeController:
    def __init__(self) -> None:
        self.image = FakeImage([])

    @property
    def cached_image(self) -> FakeImage:
        return self.image


class FakeTasker:
    def __init__(self) -> None:
        self.controller = FakeController()


class FakeDiagnostics:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.calls: list[tuple[str, object]] = []

    def event(self, name: str, details: dict | None = None) -> None:
        self.calls.append((name, details or {}))

    def fail(self, error) -> None:
        self.calls.append(("fail", error))

    def succeed(self) -> None:
        self.calls.append(("succeed", None))


def test_only_first_terminal_event_for_a_task_restores() -> None:
    calls: list[str] = []
    sink = RestoreWindowSink(restore=lambda: calls.append("restore"))

    for message in (
        "Tasker.Task.Succeeded",
        "Tasker.Task.Failed",
        "Tasker.Task.Failed",
        "Tasker.Task.Stopped",
    ):
        sink.on_raw_notification(None, message, {"task_id": 7})

    assert calls == ["restore"]

    sink.on_raw_notification(None, "Tasker.Task.Succeeded", {"task_id": 8})
    assert calls == ["restore", "restore"]


def test_nonterminal_events_do_not_restore() -> None:
    calls: list[str] = []

    RestoreWindowSink(restore=lambda: calls.append("restore")).on_raw_notification(
        None, "Node.PipelineNode.Succeeded", {"task_id": 7}
    )

    assert calls == []


@pytest.mark.parametrize(
    ("node_name", "expected_code"),
    [
        ("MJA_Start", ErrorCode.HOME_RECOGNITION_TIMEOUT),
        ("MJA_ConfirmPanel", ErrorCode.MAIL_OPEN_TIMEOUT),
        ("MJA_ConfirmMail", ErrorCode.MAIL_OPEN_TIMEOUT),
        ("MJA_ConfirmPanelAfterMail", ErrorCode.HOME_RETURN_TIMEOUT),
        ("MJA_ConfirmHome", ErrorCode.HOME_RETURN_TIMEOUT),
    ],
)
def test_recognition_failure_maps_code_and_saves_failure_screen(
    tmp_path: Path, node_name: str, expected_code: ErrorCode
) -> None:
    diagnostics = FakeDiagnostics(tmp_path)
    tasker = FakeTasker()
    sink = RestoreWindowSink(restore=lambda: None, diagnostics=diagnostics)

    sink.on_raw_notification(
        tasker,
        "Node.Recognition.Failed",
        {"task_id": 7, "name": node_name},
    )

    assert (tmp_path / "failure-screen.png").read_bytes() == b"png"
    failures = [value for name, value in diagnostics.calls if name == "fail"]
    assert len(failures) == 1
    assert failures[0].code is expected_code


def test_unrelated_recognition_failure_does_not_invent_timeout_code(tmp_path: Path) -> None:
    diagnostics = FakeDiagnostics(tmp_path)
    sink = RestoreWindowSink(restore=lambda: None, diagnostics=diagnostics)

    sink.on_raw_notification(
        FakeTasker(),
        "Node.Recognition.Failed",
        {"task_id": 7, "name": "MJA_Unknown"},
    )

    assert not (tmp_path / "failure-screen.png").exists()
    assert [name for name, _ in diagnostics.calls if name == "fail"] == []


def test_success_saves_last_screen_and_succeeds_before_restore(tmp_path: Path) -> None:
    order: list[str] = []
    diagnostics = FakeDiagnostics(tmp_path)
    tasker = FakeTasker()
    sink = RestoreWindowSink(
        restore=lambda: order.append("restore"), diagnostics=diagnostics
    )

    original_succeed = diagnostics.succeed
    diagnostics.succeed = lambda: (order.append("succeed"), original_succeed())[1]
    tasker.controller.image.saved = []

    sink.on_raw_notification(tasker, "Tasker.Task.Succeeded", {"task_id": 7})

    assert (tmp_path / "last-screen.png").read_bytes() == b"png"
    assert order == ["succeed", "restore"]


def test_restore_failure_is_recorded_as_warning_without_raising(tmp_path: Path) -> None:
    diagnostics = FakeDiagnostics(tmp_path)
    sink = RestoreWindowSink(
        restore=lambda: (_ for _ in ()).throw(RuntimeError("restore failed")),
        diagnostics=diagnostics,
    )

    sink.on_raw_notification(None, "Tasker.Task.Failed", {"task_id": 7})

    warnings = [value for name, value in diagnostics.calls if name == "window_restore_failed"]
    assert len(warnings) == 1
    assert warnings[0]["code"] == ErrorCode.WINDOW_RESTORE_FAILED.value
