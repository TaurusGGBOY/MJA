import json
from pathlib import Path

import numpy as np
import pytest

from agent.diagnostics import RunDiagnostics, write_android_result
from agent.errors import ErrorCode, MJAError
from agent.safety import SafetyReason
from agent.workflows.models import TaskResult, TaskStatus


def read_run(run: RunDiagnostics) -> dict:
    return json.loads((run.directory / "run.json").read_text(encoding="utf-8"))


def test_failure_is_written_with_stable_code(tmp_path: Path) -> None:
    run = RunDiagnostics.create(tmp_path, now=lambda: "20260727T120000.000000+0800")
    run.record_component("maafw", "5.12.2")
    run.record_window(window_id=41, pid=902, screenshot_size=(1280, 720))
    run.fail(MJAError(ErrorCode.MAIL_OPEN_TIMEOUT, "mail marker not found"))

    payload = read_run(run)

    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "MAIL_OPEN_TIMEOUT",
        "message": "mail marker not found",
    }
    assert not list(tmp_path.rglob("*.tmp"))
    run.close()


def test_success_records_components_window_events_and_duration(tmp_path: Path) -> None:
    run = RunDiagnostics.create(tmp_path, now=lambda: "20260727T120001.000000+0800")
    run.record_component("maafw", "5.12.2")
    run.record_component("mfa", "2.13.0-beta.5")
    run.record_window(window_id=41, pid=902, screenshot_size=(1280, 720))
    run.event("home_recognized", {"node": "MJA_Home"})
    run.event("mail_opened")
    run.succeed()

    payload = read_run(run)

    assert payload["status"] == "succeeded"
    assert payload["components"] == {"maafw": "5.12.2", "mfa": "2.13.0-beta.5"}
    assert payload["window"] == {
        "window_id": 41,
        "pid": 902,
        "screenshot_size": {"width": 1280, "height": 720},
    }
    assert [event["name"] for event in payload["events"]] == [
        "home_recognized",
        "mail_opened",
    ]
    assert all(isinstance(event["monotonic_ms"], int) for event in payload["events"])
    assert payload["duration_ms"] is not None
    assert payload["finished_at"] == "20260727T120001.000000+0800"
    run.close()


def test_event_details_do_not_persist_sensitive_fields(tmp_path: Path) -> None:
    run = RunDiagnostics.create(tmp_path, now=lambda: "20260727T120002.000000+0800")
    run.event(
        "diagnostic_event",
        {
            "node": "MJA_Home",
            "username": "private-user",
            "command_line": "secret command",
            "nested": {"account_id": "private-account", "attempt": 1},
        },
    )

    details = read_run(run)["events"][0]["details"]

    assert details == {"node": "MJA_Home", "nested": {"attempt": 1}}
    run.close()


def test_run_json_is_replaced_atomically_for_each_mutation(tmp_path: Path, monkeypatch) -> None:
    run = RunDiagnostics.create(tmp_path, now=lambda: "20260727T120003.000000+0800")
    replacements: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def record_replace(source: Path, target: Path) -> Path:
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", record_replace)
    run.event("state_changed")
    run.succeed()

    assert replacements
    assert all(source.name == "run.json.tmp" for source, _ in replacements)
    assert all(target.name == "run.json" for _, target in replacements)
    assert not (run.directory / "run.json.tmp").exists()
    run.close()


def test_mja_error_exposes_code_and_message() -> None:
    error = MJAError(ErrorCode.WINDOW_NOT_FOUND, "game window not found")

    assert error.code is ErrorCode.WINDOW_NOT_FOUND
    assert str(error) == "game window not found"


def test_android_result_is_redacted_to_the_runtime_contract(tmp_path: Path) -> None:
    path = tmp_path / "android" / "result.json"
    write_android_result(
        path,
        avd="mja-api35-apis",
        serial="emulator-5556",
        package="com.hanjiasongshu.dr22",
        display_size=(1280, 720),
        task_name="mail_smoke_test",
        started_at="20260728T120000+0800",
        finished_at="20260728T120001+0800",
        status="succeeded",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == {
        "avd",
        "serial",
        "package",
        "display_size",
        "task_name",
        "started_at",
        "finished_at",
        "status",
    }
    assert payload["display_size"] == {"width": 1280, "height": 720}
    assert not list(tmp_path.rglob("*.tmp"))


def test_task_diagnostics_write_result_trace_and_redacted_frame(tmp_path: Path) -> None:
    diagnostics = RunDiagnostics.create(tmp_path, now=lambda: "20260728T120000+0800")
    try:
        diagnostics.start_task("MAIL_REWARD_DAILY")
        diagnostics.record_action(
            type("Intent", (), {"action_id": "click"})(),
            type(
                "Decision",
                (),
                {
                    "allowed": False,
                    "reason": SafetyReason.PAID_SIGNAL,
                },
            )(),
            "frame-1",
        )
        diagnostics.record_frame(
            type("Frame", (), {"frame_id": "frame-1", "payload": b"png"})(),
            "failure",
        )
        result = TaskResult(
            "MAIL_REWARD_DAILY",
                    TaskStatus.FAILED,
            "mail",
            {"click": 0},
            "paid_signal",
        )
        diagnostics.write_task_result(result)
    finally:
        diagnostics.close()

    assert (next(tmp_path.rglob("failure.png"))).read_bytes() == b"png"
    trace = next(tmp_path.rglob("action-trace.jsonl")).read_text(encoding="utf-8")
    assert trace.count("frame-1") == 1
    assert json.loads(next(tmp_path.rglob("result.json")).read_text())[
        "status"
    ] == "failed"


def test_task_diagnostics_persists_array_frame_as_png(tmp_path: Path) -> None:
    diagnostics = RunDiagnostics.create(tmp_path, now=lambda: "20260728T120001+0800")
    try:
        diagnostics.record_frame(
            type(
                "Frame",
                (),
                {"frame_id": "array-frame", "payload": np.zeros((720, 1280, 3), dtype=np.uint8)},
            )(),
            "after",
        )
    finally:
        diagnostics.close()

    assert next(tmp_path.rglob("after.png")).read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("code", list(ErrorCode))
def test_error_codes_are_stable_strings(code: ErrorCode) -> None:
    assert code.value == str(code)
