import json
from datetime import date
from types import SimpleNamespace

import agent.actions.daily_workflow as daily_workflow
from agent.actions.daily_workflow import (
    AggregateDailyWorkflowAction,
    DailyWorkflowAction,
    _remember_task_outcome,
    run_selected_workflow,
)
from agent.diagnostics import RunDiagnostics
from agent.workflows.aggregate import AggregateResult, AggregateStatus
from agent.workflows.catalog import WORKFLOW_DEFINITION_ORDER
from agent.workflows.models import CapturedFrame, TaskResult, TaskStatus, VisualEvidence


class Driver:
    def __init__(self):
        self.cleanup_calls = 0

    def capture(self):
        return CapturedFrame("f", (1280, 720))

    def recognize(self, frame, names):
        return VisualEvidence(frame.frame_id, {}, {}, {}, {})

    def execute(self, intent):
        raise AssertionError("metadata-only definitions must not execute")

    def return_to_home(self):
        self.cleanup_calls += 1
        return True


def test_selected_workflow_rejects_unknown_id():
    try:
        run_selected_workflow("NO_SUCH_TASK", Driver(), SimpleNamespace())
    except ValueError as exc:
        assert "unknown workflow" in str(exc)
    else:
        raise AssertionError("unknown task was accepted")


def test_task_outcome_clears_android_action_context_between_tasks():
    context = type("Context", (), {"_mja_last_action_id": "open_battle_pass"})()
    driver = type("Driver", (), {"context": context, "_last_action_id": "open_battle_pass"})()
    result = TaskResult(
        "BATTLE_PASS_REWARD_DAILY",
        TaskStatus.FAILED,
        "战令奖励-战斗-战令-页面",
        {"open_battle_pass": 1},
        "WORKFLOW_POSTCONDITION_MISSING",
    )

    _remember_task_outcome(driver, result.task_id, result)

    assert context._mja_last_action_id is None
    assert driver._last_action_id is None
    assert context._mja_failed_task_id == "BATTLE_PASS_REWARD_DAILY"


def test_buy_tea_reuses_verified_same_day_result_without_running_workflow(
    monkeypatch, tmp_path
):
    task_root = tmp_path / "daily" / "buy_tea_daily"
    previous = task_root / "2026-08-04T01:21:09.472148+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "BUY_TEA_DAILY",
                "status": "completed",
                "postcondition": "home",
                "action_counts": {"open_universal_shop": 1, "buy_tea": 1},
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T02:50:00+08:00",
    )
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified tea must not be purchased again")
        ),
    )

    result = run_selected_workflow(
        "BUY_TEA_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status is TaskStatus.ALREADY_COMPLETE
    assert result.postcondition == "tea_daily_already_complete"
    assert result.action_counts["buy_tea"] == 1
    diagnostics.close()


def test_buy_tea_does_not_reuse_a_result_from_another_day(monkeypatch, tmp_path):
    task_root = tmp_path / "daily" / "buy_tea_daily"
    previous = task_root / "2026-08-03T23:59:00+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "BUY_TEA_DAILY",
                "status": "completed",
                "postcondition": "home",
                "action_counts": {"open_universal_shop": 1, "buy_tea": 1},
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T00:01:00+08:00",
    )
    calls = []
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: calls.append(True)
        or SimpleNamespace(status="not_eligible"),
    )

    result = run_selected_workflow(
        "BUY_TEA_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status == "not_eligible"
    assert calls == [True]
    diagnostics.close()


def test_buy_tea_does_not_reuse_same_day_navigation_only_already_result(
    monkeypatch, tmp_path
):
    task_root = tmp_path / "daily" / "buy_tea_daily"
    previous = task_root / "2026-08-04T01:21:09.472148+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "BUY_TEA_DAILY",
                "status": "already_complete",
                "postcondition": "home",
                "action_counts": {"open_universal_shop": 1},
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T02:50:00+08:00",
    )
    calls = []
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: calls.append(True)
        or SimpleNamespace(status="not_eligible"),
    )

    result = run_selected_workflow(
        "BUY_TEA_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status == "not_eligible"
    assert calls == [True]
    diagnostics.close()


def test_trial_reuses_verified_same_day_free_claim_without_clicking_sold_out(
    monkeypatch, tmp_path
):
    task_root = tmp_path / "daily" / "trial_sword_daily"
    previous = task_root / "2026-08-04T01:59:27.585934+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "TRIAL_SWORD_DAILY",
                "status": "completed",
                "postcondition": "home",
                "action_counts": {
                    "open_trial_sword": 1,
                    "claim_free_trial": 1,
                    "confirm_free_trial": 1,
                    "close_trial": 1,
                },
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T03:00:00+08:00",
    )
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified free trial must not be claimed again")
        ),
    )

    result = run_selected_workflow(
        "TRIAL_SWORD_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status is TaskStatus.ALREADY_COMPLETE
    assert result.postcondition == "trial_daily_already_complete"
    assert result.action_counts["claim_free_trial"] == 1
    diagnostics.close()


def test_trial_does_not_reuse_same_day_navigation_only_already_result(
    monkeypatch, tmp_path
):
    task_root = tmp_path / "daily" / "trial_sword_daily"
    previous = task_root / "2026-08-04T01:59:27.585934+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "TRIAL_SWORD_DAILY",
                "status": "already_complete",
                "postcondition": "home",
                "action_counts": {"open_trial_sword": 1},
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T03:00:00+08:00",
    )
    calls = []
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: calls.append(True)
        or SimpleNamespace(status="not_eligible"),
    )

    result = run_selected_workflow(
        "TRIAL_SWORD_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status == "not_eligible"
    assert calls == [True]
    diagnostics.close()


def test_appraisal_reuses_verified_same_day_free_claim_without_clicking_again(
    monkeypatch, tmp_path
):
    task_root = tmp_path / "daily" / "free_appraisal_daily"
    previous = task_root / "2026-08-04T02:10:27.585934+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "FREE_APPRAISAL_DAILY",
                "status": "completed",
                "postcondition": "home",
                "action_counts": {
                    "open_appraisal": 1,
                    "claim_free_appraisal_once": 1,
                    "close_appraisal_popup": 1,
                },
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T03:00:00+08:00",
    )
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified free appraisal must not be clicked again")
        ),
    )

    result = run_selected_workflow(
        "FREE_APPRAISAL_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status is TaskStatus.ALREADY_COMPLETE
    assert result.postcondition == "appraisal_daily_already_complete"
    assert result.action_counts["claim_free_appraisal_once"] == 1
    diagnostics.close()


def test_shop_reuses_verified_same_day_claim_without_clicking_claimed_badge(
    monkeypatch, tmp_path
):
    task_root = tmp_path / "daily" / "shop_free_gift_daily"
    previous = task_root / "2026-08-04T03:05:06.750055+08:00"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text(
        json.dumps(
            {
                "task_id": "SHOP_FREE_GIFT_DAILY",
                "status": "completed",
                "postcondition": "benefits",
                "action_counts": {
                    "open_function_panel": 1,
                    "open_shop": 1,
                    "open_period_benefits": 1,
                    "claim_free_gift": 1,
                },
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    diagnostics = RunDiagnostics.create(
        task_root,
        now=lambda: "2026-08-04T08:10:00+08:00",
    )
    monkeypatch.setattr(
        daily_workflow,
        "run_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("claimed free gift must not be clicked again")
        ),
    )

    result = run_selected_workflow(
        "SHOP_FREE_GIFT_DAILY",
        Driver(),
        diagnostics,
        day=date(2026, 8, 4),
    )

    assert result.status is TaskStatus.ALREADY_COMPLETE
    assert result.postcondition == "shop_free_gift_daily_already_complete"
    diagnostics.close()


def test_food_workflow_has_a_finite_timeout(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    result = run_selected_workflow("EAT_STAMINA_FOOD_DAILY", Driver(), SimpleNamespace())

    assert result.status == "not_eligible"
    assert received["timeout_seconds"] == 600.0


def test_collection_workflow_allows_reward_popup_dismissal(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    result = run_selected_workflow(
        "COLLECTION_DEPLOYMENT_DAILY", Driver(), SimpleNamespace()
    )

    assert result.status == "not_eligible"
    assert received["timeout_seconds"] == 180.0


def test_hero_dispatch_workflow_allows_the_original_six_team_loop(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    result = run_selected_workflow("HERO_DISPATCH_DAILY", Driver(), SimpleNamespace())

    assert result.status == "not_eligible"
    assert received["timeout_seconds"] == 300.0


def test_jianlin_workflow_allows_two_full_auto_battles(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    run_selected_workflow("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", Driver(), SimpleNamespace())
    assert received["timeout_seconds"] == 900.0


def test_shadow_workflow_allows_full_grid_and_auto_battles(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    result = run_selected_workflow("SHADOW_RUINS_DAILY", Driver(), SimpleNamespace())

    assert result.status == "not_eligible"
    assert received["timeout_seconds"] == 1800.0


def test_long_ocr_daily_routes_have_explicit_timeouts(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    expected = {
        "MAIL_REWARD_DAILY": 180.0,
        "WEEKLY_FREE_GIFT_MONDAY": 240.0,
        "TRIAL_SWORD_DAILY": 180.0,
        "FREE_APPRAISAL_DAILY": 180.0,
        "BUY_TEA_DAILY": 180.0,
        "SPEND_CONDENSATE_DAILY": 300.0,
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY": 600.0,
        "DUNGEON_SWEEP_DAILY": 180.0,
        "DAILY_TASK_REWARD_CLAIM_DAILY": 180.0,
        "BATTLE_PASS_REWARD_DAILY": 180.0,
        "RING_CHALLENGE_DAILY": 1200.0,
    }
    for task_id, timeout in expected.items():
        run_selected_workflow(task_id, Driver(), SimpleNamespace())
        assert received["timeout_seconds"] == timeout


def test_every_registered_workflow_has_an_explicit_timeout(monkeypatch):
    received = {}

    def fake_run_workflow(*args, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(status="not_eligible")

    monkeypatch.setattr(daily_workflow, "run_workflow", fake_run_workflow)
    for task_id in WORKFLOW_DEFINITION_ORDER:
        run_selected_workflow(task_id, Driver(), SimpleNamespace())
        assert received["timeout_seconds"] > 60.0, task_id


def test_custom_action_returns_false_for_unimplemented_definition():
    context = SimpleNamespace(workflow_driver=Driver(), diagnostics=SimpleNamespace())
    result = DailyWorkflowAction().run(context, SimpleNamespace(task_id="MAIL_REWARD_DAILY"))
    assert result.success is False


def test_custom_action_reads_task_id_from_maa_run_arg():
    created = []
    context = SimpleNamespace(diagnostics=SimpleNamespace())
    action = DailyWorkflowAction(
        driver_factory=lambda _: created.append(True) or Driver(),
    )

    result = action.run(
        context,
        SimpleNamespace(custom_action_param='{"task_id":"MAIL_REWARD_DAILY"}'),
    )

    assert result.success is False
    assert created == [True]


def test_custom_action_activates_emulator_only_once(monkeypatch):
    foreground_calls = []
    monkeypatch.setattr(
        daily_workflow,
        "ensure_emulator_foreground",
        lambda avd_name: foreground_calls.append(avd_name) or True,
    )
    action = DailyWorkflowAction(
        driver_factory=lambda _: Driver(),
        diagnostics_factory=SimpleNamespace,
    )

    action.run(SimpleNamespace(), SimpleNamespace(task_id="MAIL_REWARD_DAILY"))
    action.run(SimpleNamespace(), SimpleNamespace(task_id="MAIL_REWARD_DAILY"))

    assert foreground_calls == ["mja-api35-apis"]


def test_custom_action_retries_failed_emulator_activation(monkeypatch):
    foreground_calls = []
    outcomes = iter((False, True))
    monkeypatch.setattr(
        daily_workflow,
        "ensure_emulator_foreground",
        lambda avd_name: foreground_calls.append(avd_name) or next(outcomes),
    )
    action = DailyWorkflowAction(
        driver_factory=lambda _: Driver(),
        diagnostics_factory=SimpleNamespace,
    )

    action.run(SimpleNamespace(), SimpleNamespace(task_id="MAIL_REWARD_DAILY"))
    action.run(SimpleNamespace(), SimpleNamespace(task_id="MAIL_REWARD_DAILY"))

    assert foreground_calls == ["mja-api35-apis", "mja-api35-apis"]


def test_custom_action_does_not_run_generic_cleanup_around_failed_workflow():
    driver = Driver()
    action = DailyWorkflowAction(
        driver_factory=lambda _: driver,
        diagnostics_factory=SimpleNamespace,
    )

    result = action.run(SimpleNamespace(), SimpleNamespace(task_id="MAIL_REWARD_DAILY"))

    assert result.success is False
    assert driver.cleanup_calls == 0


def test_real_android_driver_normalizes_previous_task_page_before_workflow(monkeypatch):
    events = []

    class FakeMaaDriver(Driver):
        def return_to_home(self):
            events.append("return_to_home")
            return True

    fake_driver = FakeMaaDriver()
    monkeypatch.setattr(daily_workflow, "MaaAndroidWorkflowDriver", FakeMaaDriver)
    monkeypatch.setattr(
        daily_workflow,
        "run_selected_workflow",
        lambda *_args: events.append("workflow")
        or SimpleNamespace(status="completed"),
    )
    action = DailyWorkflowAction(driver_factory=lambda _: fake_driver)

    result = action.run(
        SimpleNamespace(diagnostics=SimpleNamespace()),
        SimpleNamespace(task_id="MAIL_REWARD_DAILY"),
    )

    assert result.success is True
    assert events == ["return_to_home", "workflow", "return_to_home"]


def test_real_android_workflow_fails_when_boundary_cleanup_fails(
    monkeypatch,
):
    class FakeMaaDriver(Driver):
        def return_to_home(self):
            return False

    monkeypatch.setattr(daily_workflow, "MaaAndroidWorkflowDriver", FakeMaaDriver)
    monkeypatch.setattr(
        daily_workflow,
        "run_selected_workflow",
        lambda *_args: SimpleNamespace(
            status="completed",
            task_id="MAIL_REWARD_DAILY",
            postcondition="home",
            action_counts={},
        ),
    )

    result = DailyWorkflowAction(driver_factory=lambda _: FakeMaaDriver()).run(
        SimpleNamespace(diagnostics=SimpleNamespace()),
        SimpleNamespace(task_id="MAIL_REWARD_DAILY"),
    )

    assert result.success is False


def test_confirmed_ring_sweep_stays_successful_when_cleanup_is_unverified(
    monkeypatch,
):
    class FakeMaaDriver(Driver):
        def return_to_home(self):
            return False

    monkeypatch.setattr(daily_workflow, "MaaAndroidWorkflowDriver", FakeMaaDriver)
    monkeypatch.setattr(
        daily_workflow,
        "run_selected_workflow",
        lambda *_args: SimpleNamespace(
            status="completed",
            task_id="RING_CHALLENGE_DAILY",
            postcondition="sweep_result",
            action_counts={"confirm_ring_sweep": 1},
            error_code=None,
        ),
    )

    result = DailyWorkflowAction(driver_factory=lambda _: FakeMaaDriver()).run(
        SimpleNamespace(diagnostics=SimpleNamespace()),
        SimpleNamespace(task_id="RING_CHALLENGE_DAILY"),
    )

    assert result.success is True


def test_successful_real_android_workflow_rewrites_final_home_evidence(monkeypatch):
    events = []

    class FakeMaaDriver(Driver):
        def return_to_home(self):
            events.append("return_to_home")
            return True

    class Diagnostics:
        def record_frame(self, frame, role):
            events.append(("frame", role, frame.frame_id))

        def write_task_result(self, result):
            events.append(("result", result.status.value, result.postcondition))

    monkeypatch.setattr(daily_workflow, "MaaAndroidWorkflowDriver", FakeMaaDriver)
    monkeypatch.setattr(
        daily_workflow,
        "run_selected_workflow",
        lambda *_args: SimpleNamespace(
            status="completed",
            task_id="MAIL_REWARD_DAILY",
            postcondition="mail",
            action_counts={},
            error_code=None,
        ),
    )

    result = DailyWorkflowAction(driver_factory=lambda _: FakeMaaDriver()).run(
        SimpleNamespace(diagnostics=Diagnostics()),
        SimpleNamespace(task_id="MAIL_REWARD_DAILY"),
    )

    assert result.success is True
    assert events == [
        "return_to_home",
        "return_to_home",
        ("frame", "after", "f"),
        ("result", "completed", "home"),
    ]


def test_aggregate_runner_marks_boundary_cleanup_failure(monkeypatch):
    class FakeMaaDriver(Driver):
        def return_to_home(self):
            return False

    monkeypatch.setattr(daily_workflow, "MaaAndroidWorkflowDriver", FakeMaaDriver)
    monkeypatch.setattr(
        daily_workflow,
        "run_selected_workflow",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="already_complete",
            task_id="FREE_APPRAISAL_DAILY",
            postcondition="appraisal",
            action_counts={},
        ),
    )

    result = AggregateDailyWorkflowAction._runner(
        None,
        FakeMaaDriver(),
        SimpleNamespace(task_id="FREE_APPRAISAL_DAILY"),
        SimpleNamespace(),
        day=None,
    )

    assert str(result.status) == "failed"
    assert getattr(result, "error_code", None) == "TASK_BOUNDARY_RETURN_FAILED"


def test_aggregate_runner_finalizes_failed_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        daily_workflow,
        "run_selected_workflow",
        lambda *_args, **_kwargs: TaskResult(
            "MAIL_REWARD_DAILY",
            TaskStatus.FAILED,
            "mail_opened",
            {},
            "MAIL_OPEN_TIMEOUT",
        ),
    )
    diagnostics = RunDiagnostics.create(
        tmp_path,
        now=lambda: "20260802T120000.000000+0800",
    )

    result = AggregateDailyWorkflowAction._runner(
        None,
        Driver(),
        SimpleNamespace(task_id="MAIL_REWARD_DAILY"),
        diagnostics,
        day=None,
    )

    payload = json.loads(
        (diagnostics.directory / "run.json").read_text(encoding="utf-8")
    )
    assert result.status is TaskStatus.FAILED
    assert payload["status"] == "failed"
    assert payload["finished_at"] is not None
    diagnostics.close()


def aggregate_result(status):
    return AggregateResult(
        (),
        status,
        "2026-07-30T00:00:00+08:00",
        "2026-07-30T00:01:00+08:00",
        "2026-07-30",
        (),
        (),
    )


def test_aggregate_action_uses_one_driver_and_writes_checkpoint(monkeypatch, tmp_path):
    driver = Driver()
    received = {}
    reports = []

    class Scheduler:
        def run(self, selection, *, checkpoint):
            received["selection"] = selection
            result = aggregate_result(AggregateStatus.COMPLETED)
            checkpoint(result)
            return result

    monkeypatch.setenv("MJA_DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(daily_workflow, "ensure_emulator_foreground", lambda _: True)
    action = AggregateDailyWorkflowAction(
        driver_factory=lambda _: driver,
        scheduler_factory=lambda received_driver: received.update(
            driver=received_driver
        )
        or Scheduler(),
        report_writer=lambda result, root, **kwargs: reports.append(
            (result, root, kwargs["run_id"])
        )
        or root / "report.json",
    )

    outcome = action.run(
        SimpleNamespace(),
        SimpleNamespace(custom_action_param='{"selection":["daily_all"]}'),
    )

    assert outcome.success is True
    assert received == {"driver": driver, "selection": ["daily_all"]}
    assert len(reports) == 2
    assert reports[0][1] == tmp_path
    assert reports[0][2] == reports[1][2]


def test_aggregate_action_reports_partial_failure_as_false(monkeypatch, tmp_path):
    class Scheduler:
        def run(self, selection, *, checkpoint):
            return aggregate_result(AggregateStatus.COMPLETED_WITH_TASK_FAILURES)

    monkeypatch.setenv("MJA_DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(daily_workflow, "ensure_emulator_foreground", lambda _: True)
    outcome = AggregateDailyWorkflowAction(
        driver_factory=lambda _: Driver(),
        scheduler_factory=lambda _: Scheduler(),
        report_writer=lambda *_args, **_kwargs: tmp_path / "report.json",
    ).run(SimpleNamespace(), SimpleNamespace())

    assert outcome.success is False


def test_aggregate_action_default_scheduler_receives_diagnostics_factory(
    monkeypatch, tmp_path
):
    received = {}

    class Scheduler:
        def __init__(self, driver_factory, *, diagnostics_factory, runner):
            received["diagnostics_factory"] = diagnostics_factory

        def run(self, selection, *, checkpoint):
            return aggregate_result(AggregateStatus.COMPLETED)

    monkeypatch.setenv("MJA_DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(daily_workflow, "AggregateScheduler", Scheduler)
    monkeypatch.setattr(daily_workflow, "ensure_emulator_foreground", lambda _: True)
    outcome = AggregateDailyWorkflowAction(
        driver_factory=lambda _: Driver(),
        report_writer=lambda *_args, **_kwargs: tmp_path / "report.json",
    ).run(SimpleNamespace(), SimpleNamespace())

    assert outcome.success is True
    assert callable(received["diagnostics_factory"])
