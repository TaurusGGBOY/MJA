from __future__ import annotations

import json
from datetime import datetime

import tools.android_daily_run as module
from agent.errors import ErrorCode, MJAError
from agent.workflows.aggregate import AggregateStatus
from agent.workflows.catalog import workflow_sequence_for_date


class _FakeAndroidRun:
    calls: list[tuple[str, bool, bool, bool, bool]] = []
    child_code = 0
    install_root = None

    def __init__(self) -> None:
        self.calls = []
        type(self).calls = self.calls
        self.install_root = type(self).install_root

    def run(
        self,
        task_name: str,
        *,
        stop: bool,
        wipe_data: bool,
        start_session: bool,
        fresh_process: bool,
    ) -> int:
        self.calls.append((task_name, stop, wipe_data, start_session, fresh_process))
        if self.install_root is not None:
            result_dir = self.install_root / "debug" / "runs" / "daily" / task_name
            result_dir.mkdir(parents=True, exist_ok=True)
            (result_dir / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": task_name.upper(),
                        "status": "completed",
                        "postcondition": "home",
                        "action_counts": {},
                        "error_code": None,
                    }
                ),
                encoding="utf-8",
            )
        return type(self).child_code


def payload(status="completed"):
    return {
        "status": status,
        "task_results": [
            {"task_id": "MAIL_REWARD_DAILY", "status": "completed"},
        ],
        "remaining_task_ids": [],
    }


def install_fake(monkeypatch, tmp_path, report):
    _FakeAndroidRun.install_root = tmp_path
    _FakeAndroidRun.child_code = 0
    _FakeAndroidRun.calls = []
    monkeypatch.setattr(module, "AndroidRun", _FakeAndroidRun)
    monkeypatch.setattr(
        module,
        "load_latest_aggregate_report",
        lambda root, *, newer_than: report,
    )


def test_daily_all_runs_each_date_eligible_task_in_order(monkeypatch, tmp_path, capsys):
    install_fake(monkeypatch, tmp_path, payload())

    assert module.main([]) == 0
    expected = [
        (
            task_id.lower(),
            False,
            False,
            True,
            False,
        )
        for index, task_id in enumerate(workflow_sequence_for_date(datetime.now().date()))
    ]
    assert _FakeAndroidRun.calls == expected
    assert "全量日常：全部完成" in capsys.readouterr().out


def test_partial_failure_report_returns_one_even_if_child_failed(
    monkeypatch, tmp_path, capsys
):
    report = payload("completed_with_task_failures")
    report["task_results"][0]["status"] = "failed"
    install_fake(monkeypatch, tmp_path, report)
    _FakeAndroidRun.child_code = 3

    assert module.main([]) == 1
    assert "完成但有任务失败" in capsys.readouterr().out


def test_missing_or_malformed_report_is_runtime_failure(monkeypatch, tmp_path):
    install_fake(monkeypatch, tmp_path, None)
    assert module.main([]) == 3

    install_fake(monkeypatch, tmp_path, {"status": "bad", "task_results": []})
    assert module.main([]) == 3


def test_interrupted_report_returns_130(monkeypatch, tmp_path):
    install_fake(monkeypatch, tmp_path, payload("interrupted"))
    assert module.main([]) == 130


def test_explicit_task_runs_only_that_task(monkeypatch, tmp_path):
    install_fake(monkeypatch, tmp_path, payload())
    assert module.main(["--task", "weekly_free_gift_monday"]) == 0
    assert _FakeAndroidRun.calls == [
        ("weekly_free_gift_monday", False, False, True, False),
    ]


def test_multiple_explicit_tasks_are_accepted_and_unknown_is_usage_error(monkeypatch, tmp_path):
    install_fake(monkeypatch, tmp_path, payload())
    assert module.main(["--task", "mail_reward_daily", "--task", "buy_tea_daily"]) == 0
    assert _FakeAndroidRun.calls == [
        ("mail_reward_daily", False, False, True, False),
        ("buy_tea_daily", False, False, True, False),
    ]
    install_fake(monkeypatch, tmp_path, payload())
    assert module.main(["--task", "no_such_task"]) == 2
    assert _FakeAndroidRun.calls == []


def test_report_loader_receives_run_start_time(monkeypatch, tmp_path):
    received = {}
    _FakeAndroidRun.install_root = tmp_path
    monkeypatch.setattr(module, "AndroidRun", _FakeAndroidRun)

    def load(root, *, newer_than):
        received.update(root=root, newer_than=newer_than)
        return payload()

    monkeypatch.setattr(module, "load_latest_aggregate_report", load)
    assert module.main([]) == 0
    assert received["root"] == tmp_path / "debug" / "runs"
    assert isinstance(received["newer_than"], datetime)


def test_real_latest_report_json_shape_is_not_used_from_stale_file(
    monkeypatch, tmp_path
):
    stale = tmp_path / "debug" / "runs" / "daily" / "aggregate-latest.json"
    stale.parent.mkdir(parents=True)
    stale.write_text(json.dumps(payload()), encoding="utf-8")
    install_fake(monkeypatch, tmp_path, None)
    assert module.main([]) == 3


def test_isolated_supervisor_continues_after_one_failed_task(tmp_path):
    class FakeAndroid:
        install_root = tmp_path

        def __init__(self):
            self.calls = []

        def run(self, task_name, *, stop, wipe_data, start_session, fresh_process):
            self.calls.append((task_name, stop, wipe_data, start_session, fresh_process))
            root = tmp_path / "debug" / "runs" / "daily" / task_name
            root.mkdir(parents=True, exist_ok=True)
            status = "failed" if task_name == "mail_reward_daily" else "completed"
            (root / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": task_name.upper(),
                        "status": status,
                        "postcondition": "mail_opened",
                        "action_counts": {},
                        "error_code": "MAIL_OPEN_TIMEOUT" if status == "failed" else None,
                    }
                ),
                encoding="utf-8",
            )
            return 3 if status == "failed" else 0

    android = FakeAndroid()
    result = module.run_isolated_dailies(
        android,
        ("MAIL_REWARD_DAILY", "BUY_TEA_DAILY"),
        debug_root=tmp_path / "debug" / "runs",
        stop=True,
        wipe_data=True,
        run_id="20260802T000000000000+0800",
        started_at="2026-08-02T00:00:00+08:00",
    )

    assert [item.status.value for item in result.task_results] == ["failed", "completed"]
    assert android.calls == [
        ("mail_reward_daily", False, True, True, False),
        ("buy_tea_daily", True, False, True, False),
    ]
    report = json.loads(
        (tmp_path / "debug" / "runs" / "daily" / "aggregate-latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["remaining_task_ids"] == []


def test_isolated_supervisor_fast_fails_after_live_shared_runtime_failure(tmp_path):
    class FakeAndroid:
        install_root = tmp_path

        def __init__(self):
            self.calls = []

        def run(self, task_name, *, stop, wipe_data, start_session, fresh_process):
            self.calls.append((task_name, stop, wipe_data, start_session, fresh_process))
            raise MJAError(
                ErrorCode.ANDROID_SYSTEM_UI_NOT_RESPONDING,
                "system UI ANR",
            )

    android = FakeAndroid()
    result = module.run_isolated_dailies(
        android,
        ("MAIL_REWARD_DAILY", "BUY_TEA_DAILY"),
        debug_root=tmp_path / "debug" / "runs",
        stop=True,
        wipe_data=True,
        run_id="20260805T000000000000+0800",
        started_at="2026-08-05T00:00:00+08:00",
    )

    assert result.status is AggregateStatus.FAILED_RUNTIME
    assert result.error_code == "ANDROID_SYSTEM_UI_NOT_RESPONDING"
    assert result.remaining_task_ids == ("BUY_TEA_DAILY",)
    assert [item.task_id for item in result.task_results] == ["MAIL_REWARD_DAILY"]
    assert android.calls == [
        ("mail_reward_daily", False, True, True, False),
    ]
    report = json.loads(
        (tmp_path / "debug" / "runs" / "daily" / "aggregate-latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "failed_runtime"
    assert report["remaining_task_ids"] == ["BUY_TEA_DAILY"]


def test_isolated_supervisor_fast_fails_after_no_action_runner_timeout(tmp_path):
    class FakeAndroid:
        install_root = tmp_path

        def __init__(self):
            self.calls = []

        def run(self, task_name, *, stop, wipe_data, start_session, fresh_process):
            self.calls.append(task_name)
            root = tmp_path / "debug" / "runs" / "daily" / task_name
            root.mkdir(parents=True, exist_ok=True)
            (root / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": task_name.upper(),
                        "status": "failed",
                        "postcondition": "android_runner",
                        "action_counts": {},
                        "error_code": "WORKFLOW_TIMEOUT",
                    }
                ),
                encoding="utf-8",
            )
            return 124

    android = FakeAndroid()
    result = module.run_isolated_dailies(
        android,
        ("MAIL_REWARD_DAILY", "BUY_TEA_DAILY"),
        debug_root=tmp_path / "debug" / "runs",
        stop=True,
        wipe_data=True,
        run_id="20260805T010000000000+0800",
        started_at="2026-08-05T01:00:00+08:00",
    )

    assert result.status is AggregateStatus.FAILED_RUNTIME
    assert result.error_code == "ANDROID_SHARED_RUNTIME_FAILURE"
    assert result.stop_reason == "ANDROID_SHARED_RUNTIME_FAILURE:WORKFLOW_TIMEOUT"
    assert result.remaining_task_ids == ("BUY_TEA_DAILY",)
    assert android.calls == ["mail_reward_daily"]
