from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import maa.resource as _maa_resource
from maa.tasker import NotificationType

# The task-2 worktree starts at the pre-AgentServer migration commit, while
# the installed MaaFw is already 5.12.x.  Keep legacy action imports inert in
# this focused source test; production registrations under test are the new
# AgentServer decorators in task_lifecycle and task_flow.
if not hasattr(_maa_resource, "resource"):
    class _ResourceCompat:
        @staticmethod
        def custom_action(_name: str):
            return lambda action: action

    _maa_resource.resource = _ResourceCompat()

from agent.custom.action.task_lifecycle import (
    BeginTask,
    FailStartupRecovery,
    RecordTaskOutcome,
)
from agent.custom.sink.task_flow import TaskFlowStopSink
from agent.custom.support.models import TaskOutcomeStatus
from agent.custom.support.state import RUN_STORE
from tests.mfw.fakes import FakeArgv, FakeContext


class FakeTasker:
    def __init__(self) -> None:
        self.post_stop_calls = 0

    def post_stop(self):
        self.post_stop_calls += 1
        return SimpleNamespace()


def _task_detail(task_id: int = 17):
    return SimpleNamespace(task_id=task_id, entry="MJA_TEST", uuid="uuid", hash="hash")


def test_first_failed_task_posts_native_stop_only_once() -> None:
    sink = TaskFlowStopSink()
    tasker = FakeTasker()

    sink.on_tasker_task(tasker, NotificationType.Failed, _task_detail())
    sink.on_tasker_task(tasker, NotificationType.Failed, _task_detail())
    sink.on_raw_notification(tasker, "Tasker.Task.Failed", {"task_id": 17})

    assert tasker.post_stop_calls == 1


def test_successful_task_does_not_stop_the_native_queue() -> None:
    sink = TaskFlowStopSink()
    tasker = FakeTasker()

    sink.on_tasker_task(tasker, NotificationType.Succeeded, _task_detail())
    sink.on_raw_notification(tasker, "Tasker.Task.Succeeded", {"task_id": 17})

    assert tasker.post_stop_calls == 0


def test_failed_lifecycle_result_is_on_disk_before_native_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MJA_DIAGNOSTICS_ROOT", str(tmp_path))
    context = FakeContext()
    begin = FakeArgv(json.dumps({"task_id": "MAIL_REWARD_DAILY", "run_id": "run-1"}))
    failure = FakeArgv(
        json.dumps(
            {
                "task_id": "MAIL_REWARD_DAILY",
                "status": TaskOutcomeStatus.FAILED.value,
                "postcondition": "mail.state_known",
                "error_code": "MAIL_RESULT_UNKNOWN",
                "native_fail_after_record": True,
            }
        )
    )

    assert BeginTask().run(context, begin) is True
    assert RecordTaskOutcome().run(context, failure) is False

    result_path = tmp_path / "run-1/MAIL_REWARD_DAILY/result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == TaskOutcomeStatus.FAILED.value
    assert RUN_STORE.snapshot("MAIL_REWARD_DAILY")["status"] is TaskOutcomeStatus.FAILED

    sink = TaskFlowStopSink()
    tasker = FakeTasker()
    sink.on_tasker_task(tasker, NotificationType.Failed, _task_detail())
    assert tasker.post_stop_calls == 1


def test_common_terminals_keep_normal_stop_separate_from_abort() -> None:
    terminal_path = (
        Path(__file__).parents[1]
        / "assets/resource/base/pipeline/common/terminal.json"
    )
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))

    assert terminal["MJA_COMMON_STOP"] == {
        "recognition": "DirectHit",
        "action": "StopTask",
    }
    assert terminal["MJA_COMMON_ABORT"]["action"] == "StopTask"
    assert terminal["MJA_COMMON_ABORT"]["Abort"] is True
    startup_restart = terminal["MJA_COMMON_STARTUP_RECOVERY_RESTART"]
    assert startup_restart["custom_action"] == "RestartGameSurface"
    assert startup_restart["max_hit"] == 1
    assert startup_restart["next"] == ["MJA_GAME_START_AFTER_RESTART"]
    assert startup_restart["on_error"] == ["MJA_GAME_START_APP_RESTART_FAILED"]
    startup_exhausted = terminal["MJA_COMMON_STARTUP_RECOVERY_EXHAUSTED"]
    assert startup_exhausted["action"] == "Custom"
    assert startup_exhausted["custom_action"] == "FailStartupRecovery"
    assert startup_exhausted["custom_action_param"] == {
        "error_code": "GAME_START_RECOVERY_EXHAUSTED",
        "postcondition": "startup.game_ready",
    }
    assert startup_exhausted["Abort"] is True
    assert "on_error" not in terminal["MJA_COMMON_STARTUP_RECOVERY_EXHAUSTED"]


def test_startup_recovery_failure_is_control_plane_only() -> None:
    context = FakeContext()
    failure = FakeArgv(
        json.dumps(
            {
                "error_code": "GAME_START_RECOVERY_EXHAUSTED",
                "postcondition": "startup.game_ready",
            }
        )
    )

    assert FailStartupRecovery().run(context, failure) is False


def test_startup_failure_records_stage_and_root_cause(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MJA_DIAGNOSTICS_ROOT", str(tmp_path))
    context = FakeContext()
    failure = FakeArgv(
        json.dumps(
            {
                "error_code": "GAME_START_START_BUTTON_NOT_FOUND",
                "postcondition": "startup.start_game_button_visible",
                "stage": "after_wait_20s",
                "expected": "OCR 识别到 开始游戏",
                "observed": "20 秒后未找到开始游戏按钮",
                "root_cause": "APP 未到达开始游戏页",
            }
        )
    )

    assert FailStartupRecovery().run(context, failure) is False
    lines = (tmp_path / "game_start_failures.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record["error_code"] == "GAME_START_START_BUTTON_NOT_FOUND"
    assert record["stage"] == "after_wait_20s"
    assert record["root_cause"] == "APP 未到达开始游戏页"


def test_recorded_failure_terminals_never_route_action_error_to_successful_stop() -> None:
    pipeline_root = Path(__file__).parents[1] / "assets/resource/base/pipeline"
    for path in pipeline_root.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, node in payload.items():
            if not isinstance(node, dict):
                continue
            params = node.get("custom_action_param")
            if (
                node.get("custom_action") == "RecordTaskOutcome"
                and isinstance(params, dict)
                and params.get("status") == "failed"
                and params.get("native_fail_after_record") is True
            ) or (
                node.get("custom_action") == "RecordActiveTaskFailure"
                and isinstance(params, dict)
                and params.get("native_fail_after_record") is True
            ):
                assert "on_error" not in node, f"{path}:{name}"
