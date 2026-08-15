"""Maa custom action adapter for registered daily workflow definitions."""

from __future__ import annotations

import json
import os
import traceback
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from agent.android.config import DEFAULT_AVD_NAME
from agent.android.runtime_gate import AndroidRuntimeGate
from agent.diagnostics import RunDiagnostics
from agent.errors import ErrorCode, MJAError
from agent.android.emulator_window import ensure_emulator_foreground
from agent.workflows.aggregate import (
    AggregateResult,
    AggregateScheduler,
    AggregateStatus,
    is_runtime_failure,
)
from agent.workflows.aggregate_report import write_aggregate_report
from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.engine import WorkflowDriver, run_workflow
from agent.workflows.maa_android import MaaAndroidWorkflowDriver
from agent.workflows.models import TaskResult, TaskStatus
from agent.workflows.registry import WORKFLOW_DEFINITIONS

# Food cards expose their names only after selection.  The bounded eight-card
# scan therefore needs more wall-clock time than the normal one-screen task,
# while remaining finite and below the Android tasker's outer run limit.
_WORKFLOW_TIMEOUT_SECONDS = {
    # Mail claims finish the business actions quickly, but the Android
    # renderer spends several seconds on each full-screen OCR verification.
    # Without an explicit budget the final function-panel close can be
    # reached after the default 60-second limit and strand the batch before
    # the next independent task starts.
    "MAIL_REWARD_DAILY": 180.0,
    # The shop page runs several full-screen OCR recognizers on the Android
    # renderer; the first-run reward animation can take just over one minute.
    "SHOP_FREE_GIFT_DAILY": 120.0,
    # The weekly gift route uses the same full-screen shop OCR boundary as
    # the daily gift route, but adds a second tab and a paid/free eligibility
    # check.  Without an explicit budget it fell back to the 60-second
    # default and timed out while entering the already-recognized weekly tab.
    "WEEKLY_FREE_GIFT_MONDAY": 240.0,
    # Keep the short direct-entry tasks explicit as well.  Their usual path
    # is quick, but a slow Unity transition must not silently inherit the
    # engine's generic 60-second budget.
    "TRIAL_SWORD_DAILY": 180.0,
    "FREE_APPRAISAL_DAILY": 180.0,
    # Buying tea traverses the painting page, two shop pages, and a quantity
    # dialog.  Each Android OCR frame is relatively expensive, so the default
    # one-minute budget can expire immediately after the final verified page
    # transition.
    "BUY_TEA_DAILY": 180.0,
    # Collection has a reward animation followed by a deliberately bounded
    # blank-area dismiss and a slow return to the world HUD.  The default
    # one-minute budget expires while that popup is still visible.
    "COLLECTION_DEPLOYMENT_DAILY": 180.0,
    # Six food uses can require one replacement confirmation per use. On the
    # Android renderer each OCR frame is relatively expensive, so keep the
    # finite budget above the full six-use route while still bounding a hung
    # screen.
    "EAT_STAMINA_FOOD_DAILY": 600.0,
    "HERO_DISPATCH_DAILY": 300.0,
    # These routes include several full-screen OCR transitions. The default
    # one-minute engine budget expires after a successful navigation before
    # the task can verify its final business postcondition.
    "SPEND_CONDENSATE_DAILY": 300.0,
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY": 600.0,
    "DUNGEON_SWEEP_DAILY": 180.0,
    "DAILY_TASK_REWARD_CLAIM_DAILY": 180.0,
    "BATTLE_PASS_REWARD_DAILY": 180.0,
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": 900.0,
    # The ring page can take several full-screen OCR frames to expose the
    # master-mode start button. It is an independent task and must not inherit
    # the generic one-minute default.
    "RING_CHALLENGE_DAILY": 1_200.0,
    # One Shadow run can traverse several grid rows and each auto battle may
    # legitimately take up to three minutes. Keep the complete run finite.
    "SHADOW_RUINS_DAILY": 1800.0,
}

_SUCCESSFUL_TASK_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.ALREADY_COMPLETE,
        TaskStatus.NOT_ELIGIBLE,
    }
)

def _task_status(result: Any) -> TaskStatus:
    status = getattr(result, "status", TaskStatus.FAILED)
    if isinstance(status, TaskStatus):
        return status
    try:
        return TaskStatus(status)
    except (TypeError, ValueError):
        return TaskStatus.FAILED


def _exception_code(error: BaseException, fallback: str = "WORKFLOW_DRIVER_FAILED") -> str:
    code = getattr(getattr(error, "code", None), "value", None)
    return str(code or fallback)


def _failure_result(task_id: str, error: BaseException, *, stage: str) -> TaskResult:
    return TaskResult(
        task_id,
        TaskStatus.FAILED,
        stage,
        {},
        _exception_code(error),
    )


def _remember_task_outcome(driver: WorkflowDriver, task_id: str, result: Any) -> None:
    """Scope failed-surface resume to the task that produced the failure."""

    context = getattr(driver, "context", None)
    if context is None:
        return
    # The Android adapter keeps the last action on the Maa context so a
    # same-task retry can recognize a fading result surface.  That marker is
    # not valid for the next independent daily task: carrying
    # ``open_battle_pass`` or ``dismiss_jianlin_stamina_result`` across the
    # boundary can promote an unrelated overlay into the next task's page.
    setattr(context, "_mja_last_action_id", None)
    if hasattr(driver, "_last_action_id"):
        driver._last_action_id = None
    if _task_status(result) is TaskStatus.FAILED:
        setattr(context, "_mja_failed_task_id", str(task_id).strip().upper())
    else:
        setattr(context, "_mja_failed_task_id", None)


def _workflow_date(day: Any) -> date:
    """Normalize an optional workflow date to the local calendar date."""

    if isinstance(day, datetime):
        return day.astimezone().date()
    if isinstance(day, date):
        return day
    if isinstance(day, str):
        try:
            return date.fromisoformat(day)
        except ValueError:
            pass
    return datetime.now().astimezone().date()


def _result_directory_date(path: Path) -> date | None:
    """Read the local date encoded by a diagnostic run directory."""

    try:
        return datetime.fromisoformat(path.name).astimezone().date()
    except ValueError:
        # RunDiagnostics appends ``-1`` if two runs share one timestamp.  The
        # directory mtime is only a fallback for that collision form and for
        # old artifacts; a malformed artifact is never treated as proof on
        # its own because the result payload is validated separately below.
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).astimezone().date()
        except OSError:
            return None


def _today_task_result_payloads(
    diagnostics: Any,
    task_id: str,
    *,
    day: Any,
):
    """Yield validated result payloads for one task on one local date."""

    directory = getattr(diagnostics, "directory", None)
    if directory is None:
        return
    run_directory = Path(directory)
    daily_root = run_directory.parent.parent
    task_root = daily_root / task_id.strip().lower()
    if not task_root.is_dir():
        return

    workflow_day = _workflow_date(day)
    result_paths: list[Path] = []
    for path in task_root.rglob("result.json"):
        try:
            if _result_directory_date(path.parent) == workflow_day:
                result_paths.append(path)
        except OSError:
            continue
    result_paths.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)

    for path in result_paths:
        if path.parent == run_directory:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            if str(payload.get("task_id", "")).strip().upper() != task_id.strip().upper():
                continue
            if isinstance(payload.get("action_counts"), dict):
                yield payload
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue


def _tea_verified_result_today(diagnostics: Any, *, day: Any) -> dict[str, Any] | None:
    """Return the prior tea result that proves today's business action.

    The game hides the tea card after its daily quota is consumed.  A retry
    started later the same day therefore cannot use card absence as evidence:
    it must reuse a prior, persisted terminal result.  Only a result generated
    for this exact task and local day qualifies.  A completed result must have
    a bounded ``buy_tea`` action.  Navigation-only or ``already_complete``
    artifacts are never proof because older runs could have stopped before
    reaching the product card.
    """

    for payload in _today_task_result_payloads(diagnostics, "BUY_TEA_DAILY", day=day):
        action_counts = payload["action_counts"]
        status = str(payload.get("status", "")).strip().lower()
        if status == TaskStatus.COMPLETED.value:
            if int(action_counts.get("buy_tea", 0)) >= 1:
                return payload
    return None


def _tea_was_verified_today(diagnostics: Any, *, day: Any) -> bool:
    return _tea_verified_result_today(diagnostics, day=day) is not None


def _trial_verified_result_today(diagnostics: Any, *, day: Any) -> dict[str, Any] | None:
    """Return the prior trial result that proves today's free claim.

    After the free duration is consumed the button changes to a sold-out
    control.  Replaying the click on that control is not a harmless retry and
    leaves the workflow waiting for a popup that cannot appear.  Reuse only a
    same-day completed result with a confirmed free claim.  A navigation-only
    or ``already_complete`` artifact is not evidence that the claim happened.
    """

    for payload in _today_task_result_payloads(
        diagnostics,
        "TRIAL_SWORD_DAILY",
        day=day,
    ):
        action_counts = payload["action_counts"]
        status = str(payload.get("status", "")).strip().lower()
        if status == TaskStatus.COMPLETED.value and (
            int(action_counts.get("confirm_free_trial", 0)) >= 1
            or int(action_counts.get("claim_free_trial", 0)) >= 1
        ):
            return payload
    return None


def _trial_was_verified_today(diagnostics: Any, *, day: Any) -> bool:
    return _trial_verified_result_today(diagnostics, day=day) is not None


def _appraisal_verified_result_today(
    diagnostics: Any, *, day: Any
) -> dict[str, Any] | None:
    """Return the same-day result that proves the free appraisal was claimed."""

    for payload in _today_task_result_payloads(
        diagnostics,
        "FREE_APPRAISAL_DAILY",
        day=day,
    ):
        action_counts = payload["action_counts"]
        status = str(payload.get("status", "")).strip().lower()
        if status == TaskStatus.COMPLETED.value and int(
            action_counts.get("claim_free_appraisal_once", 0)
        ) >= 1:
            return payload
    return None


def _appraisal_was_verified_today(diagnostics: Any, *, day: Any) -> bool:
    return _appraisal_verified_result_today(diagnostics, day=day) is not None


def _shop_free_gift_verified_result_today(
    diagnostics: Any, *, day: Any
) -> dict[str, Any] | None:
    """Return the prior shop result that proves today's free-gift claim."""

    for payload in _today_task_result_payloads(
        diagnostics,
        "SHOP_FREE_GIFT_DAILY",
        day=day,
    ):
        action_counts = payload["action_counts"]
        status = str(payload.get("status", "")).strip().lower()
        if status == TaskStatus.COMPLETED.value and int(
            action_counts.get("claim_free_gift", 0)
        ) >= 1:
            return payload
    return None


def _shop_free_gift_was_verified_today(diagnostics: Any, *, day: Any) -> bool:
    return _shop_free_gift_verified_result_today(diagnostics, day=day) is not None


def _finalize_diagnostics(
    diagnostics: Any,
    result: Any,
    *,
    error: BaseException | None = None,
) -> None:
    """Close the task's diagnostic state machine with a terminal status."""

    status = _task_status(result)
    if status is TaskStatus.FAILED:
        finish_failure = getattr(diagnostics, "fail", None)
        if not callable(finish_failure):
            return
        code = getattr(result, "error_code", None) or "WORKFLOW_DRIVER_FAILED"
        try:
            stable_code = ErrorCode(code)
        except (TypeError, ValueError):
            stable_code = ErrorCode.WORKFLOW_DRIVER_FAILED
        message = str(error) if error is not None else (
            f"task {getattr(result, 'task_id', 'unknown')} failed at "
            f"{getattr(result, 'postcondition', 'unknown')}"
        )
        try:
            finish_failure(MJAError(stable_code, message))
        except Exception:
            # A diagnostics sink must never turn a task result into a batch
            # exception. The result.json written by the workflow remains the
            # source of truth when an optional sink is unavailable.
            return
        return
    finish_success = getattr(diagnostics, "succeed", None)
    if callable(finish_success):
        try:
            finish_success()
        except Exception:
            return


def _recover_after_task_failure(driver: WorkflowDriver, diagnostics: Any) -> bool:
    """Return a shared Android driver to a recognized boundary after a task.

    The failed task's own result and evidence are already persisted.  This
    recovery is only the batch hand-off needed by the next independent task;
    it never changes the failed task into a success.
    """

    if not isinstance(driver, MaaAndroidWorkflowDriver):
        return False
    recover = getattr(driver, "return_to_home", None)
    if not callable(recover):
        return False
    try:
        try:
            recovered = bool(recover(check_foreground=False))
        except TypeError:
            recovered = bool(recover())
    except Exception as exc:
        event = getattr(diagnostics, "event", None)
        if callable(event):
            event(
                "task_recovery_failed",
                {"error_code": _exception_code(exc), "message": str(exc)},
            )
        return False
    event = getattr(diagnostics, "event", None)
    if callable(event):
        event("task_recovery_completed" if recovered else "task_recovery_failed")
    return recovered

try:
    from maa.custom_action import CustomAction
except ImportError:  # pragma: no cover
    class CustomAction:
        class RunResult:
            def __init__(self, success: bool) -> None:
                self.success = success


def run_selected_workflow(
    task_id: str,
    driver: WorkflowDriver,
    diagnostics: Any,
    *,
    day: Any = None,
) -> Any:
    """Validate a GUI-selected ID and run only that registered definition."""

    canonical_id = str(task_id).strip().upper()
    if canonical_id not in WORKFLOW_DEFINITIONS:
        raise ValueError(f"unknown workflow task: {task_id}")
    verified_payload: dict[str, Any] | None = None
    if canonical_id == "BUY_TEA_DAILY":
        verified_payload = _tea_verified_result_today(diagnostics, day=day)
    elif canonical_id == "TRIAL_SWORD_DAILY":
        verified_payload = _trial_verified_result_today(diagnostics, day=day)
    elif canonical_id == "FREE_APPRAISAL_DAILY":
        verified_payload = _appraisal_verified_result_today(diagnostics, day=day)
    elif canonical_id == "SHOP_FREE_GIFT_DAILY":
        verified_payload = _shop_free_gift_verified_result_today(diagnostics, day=day)
    if verified_payload is not None:
        # The previous result is the business postcondition for this date;
        # do not reopen the task surface or repeat a consumptive action on a
        # retry. Carry its bounded business-action counts forward so the new
        # result cannot look like an empty, navigation-only completion.
        prior_counts = verified_payload.get("action_counts", {})
        action_counts = dict(prior_counts) if isinstance(prior_counts, dict) else {}
        result = TaskResult(
            canonical_id,
            TaskStatus.ALREADY_COMPLETE,
            (
                "tea_daily_already_complete"
                if canonical_id == "BUY_TEA_DAILY"
                else (
                    "trial_daily_already_complete"
                    if canonical_id == "TRIAL_SWORD_DAILY"
                    else (
                        "appraisal_daily_already_complete"
                        if canonical_id == "FREE_APPRAISAL_DAILY"
                        else "shop_free_gift_daily_already_complete"
                    )
                )
            ),
            action_counts,
        )
        write_result = getattr(diagnostics, "write_task_result", None)
        if callable(write_result):
            write_result(result)
        return result
    return run_workflow(
        WORKFLOW_DEFINITIONS[canonical_id],
        driver,
        TASK_POLICIES[canonical_id],
        diagnostics,
        day=day,
        timeout_seconds=_WORKFLOW_TIMEOUT_SECONDS.get(canonical_id, 60.0),
    )


def _return_to_home_after_success(
    result: Any,
    driver: WorkflowDriver,
    diagnostics: Any,
) -> Any:
    """Close a recognized task surface before the next daily task starts.

    Maa_bbb treats the home screen as the task boundary.  Only a successful
    task may cross that boundary automatically; failures must remain on their
    current screen for diagnosis or user guidance.
    """

    if result.status not in _SUCCESSFUL_TASK_STATUSES:
        return result
    if not isinstance(driver, MaaAndroidWorkflowDriver):
        return result

    def ring_sweep_is_verified() -> bool:
        if getattr(result, "task_id", None) != "RING_CHALLENGE_DAILY":
            return False
        counts = getattr(result, "action_counts", {})
        return (
            _task_status(result) in {TaskStatus.COMPLETED, TaskStatus.ALREADY_COMPLETE}
            and isinstance(counts, dict)
            and int(counts.get("confirm_ring_sweep", 0)) >= 1
        )

    cleanup_error: BaseException | None = None
    try:
        returned = driver.return_to_home()
    except Exception as exc:
        returned = False
        cleanup_error = exc
    if returned:
        if not all(
            hasattr(result, attribute)
            for attribute in ("task_id", "postcondition", "action_counts", "error_code")
        ):
            return result
        final_status = (
            result.status
            if isinstance(result.status, TaskStatus)
            else TaskStatus(result.status)
        )
        final_result = TaskResult(
            result.task_id,
            final_status,
            "home",
            result.action_counts,
            result.error_code,
        )
        record_frame = getattr(diagnostics, "record_frame", None)
        write_result = getattr(diagnostics, "write_task_result", None)
        if callable(record_frame):
            try:
                record_frame(driver.capture(), "after")
            except Exception as exc:
                # A task result is not publishable until the shared hand-off
                # boundary is verified. Otherwise the next task can inherit a
                # reward/modal page while the aggregate falsely reports home.
                cleanup_error = exc
                event = getattr(diagnostics, "event", None)
                if callable(event):
                    event(
                        "task_boundary_verify_failed",
                        {"error_code": _exception_code(exc)},
                    )
                if ring_sweep_is_verified():
                    # The sweep result is the business boundary; best-effort
                    # cleanup must not downgrade a confirmed sweep.
                    final_result = result
                else:
                    final_result = TaskResult(
                        result.task_id,
                        TaskStatus.FAILED,
                        "home",
                        dict(result.action_counts),
                        ErrorCode.TASK_BOUNDARY_VERIFY_FAILED.value,
                    )
        if callable(write_result):
            write_result(final_result)
        return final_result
    # The home boundary is part of the task contract. Preserve the business
    # action counts for diagnosis, but make a missing hand-off a terminal
    # failure so the aggregate cannot claim success on a live task page.
    event = getattr(diagnostics, "event", None)
    if callable(event):
        details = {
            "error_code": (
                _exception_code(cleanup_error)
                if cleanup_error
                else ErrorCode.TASK_BOUNDARY_RETURN_FAILED.value
            )
        }
        event("task_boundary_return_failed", details)
    if ring_sweep_is_verified():
        # Closing the result sheet is cleanup; a confirmed sweep remains a
        # truthful business success if this hand-off cannot be verified.
        final_result = result
    else:
        final_result = TaskResult(
            result.task_id,
            TaskStatus.FAILED,
            "home",
            dict(result.action_counts),
            ErrorCode.TASK_BOUNDARY_RETURN_FAILED.value,
        )
    write_result = getattr(diagnostics, "write_task_result", None)
    if callable(write_result):
        write_result(final_result)
    return final_result


class DailyWorkflowAction(CustomAction):
    """Thin adapter; all task decisions remain in workflow definitions."""

    def __init__(
        self,
        *,
        driver_factory: Callable[[Any], WorkflowDriver] | None = None,
        diagnostics_factory: Callable[[], Any] | None = None,
        runtime_gate_factory: Callable[[], AndroidRuntimeGate | None] | None = None,
    ) -> None:
        super().__init__()
        self._driver_factory = driver_factory
        self._diagnostics_factory = diagnostics_factory
        self._runtime_gate_factory = runtime_gate_factory
        self._emulator_foregrounded = False

    def _make_runtime_gate(self) -> AndroidRuntimeGate | None:
        if self._runtime_gate_factory is not None:
            return self._runtime_gate_factory()
        if os.environ.get("MJA_CONTROLLER") != "android" and not os.environ.get(
            "MJA_ANDROID_ADB"
        ):
            return None
        return AndroidRuntimeGate.from_environment()

    def _prepare_emulator_window(self) -> None:
        if self._emulator_foregrounded:
            return
        avd_name = os.environ.get("MJA_ANDROID_AVD", DEFAULT_AVD_NAME)
        # Stage Manager only changes the host-side presentation. A failure to
        # activate the window must not disable otherwise healthy ADB tasks;
        # leave the flag unset so the next selected task can retry.
        try:
            self._emulator_foregrounded = ensure_emulator_foreground(avd_name)
        except Exception:
            self._emulator_foregrounded = False

    def run(self, context: Any, argv: Any) -> Any:
        task_id = getattr(argv, "task_id", None)
        if not isinstance(task_id, str):
            # Maa passes CustomAction.RunArg here.  The selected workflow ID
            # is carried by the node's JSON custom_action_param, not exposed
            # as a direct ``task_id`` attribute on RunArg.
            raw_param = getattr(argv, "custom_action_param", None)
            if isinstance(raw_param, str):
                try:
                    payload = json.loads(raw_param)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    task_id = payload.get("task_id")
        if not isinstance(task_id, str):
            return CustomAction.RunResult(success=False)
        diagnostics: Any | None = None
        owns_diagnostics = False
        try:
            self._prepare_emulator_window()

            # Create the task-local diagnostic sink before any Android
            # boundary or health check.  Those checks are part of this
            # task's failure domain; a failed boundary must still produce a
            # terminal result.json for the outer supervisor to consume.
            if self._diagnostics_factory is not None:
                diagnostics = self._diagnostics_factory()
            else:
                diagnostics = getattr(context, "diagnostics", None)
                if diagnostics is None:
                    debug_dir = os.environ.get("MJA_DEBUG_DIR")
                    if debug_dir:
                        diagnostics = RunDiagnostics.create(
                            Path(debug_dir) / "daily" / task_id.strip().lower()
                        )
                        owns_diagnostics = True
                    else:
                        diagnostics = SimpleNamespace()

            runtime_gate = self._make_runtime_gate()
            if self._driver_factory is None:
                driver = getattr(context, "workflow_driver", None)
                if driver is None:
                    driver = getattr(context.tasker, "workflow_driver", None)
                if driver is None:
                    driver = MaaAndroidWorkflowDriver(context, runtime_gate=runtime_gate)
            else:
                driver = self._driver_factory(context)
            if driver is None:
                failure = TaskResult(
                    task_id,
                    TaskStatus.FAILED,
                    "driver_missing",
                    {},
                    "WORKFLOW_DRIVER_FAILED",
                )
                write_result = getattr(diagnostics, "write_task_result", None)
                if callable(write_result):
                    write_result(failure)
                _finalize_diagnostics(diagnostics, failure)
                return CustomAction.RunResult(success=False)
            if isinstance(driver, MaaAndroidWorkflowDriver):
                if runtime_gate is not None and getattr(driver, "runtime_gate", None) is None:
                    driver.runtime_gate = runtime_gate
                if runtime_gate is not None:
                    runtime_gate.require_health()
                boundary = getattr(driver, "require_task_boundary", None)
                if callable(boundary):
                    boundary(task_id)
                else:
                    driver.return_to_home()
            result = run_selected_workflow(task_id, driver, diagnostics)
            result = _return_to_home_after_success(result, driver, diagnostics)
            _remember_task_outcome(driver, task_id, result)
            _finalize_diagnostics(diagnostics, result)
            return CustomAction.RunResult(
                success=_task_status(result) in _SUCCESSFUL_TASK_STATUSES
            )
        except Exception as exc:
            diagnostics = locals().get("diagnostics")
            if diagnostics is not None:
                failure = _failure_result(
                    task_id,
                    exc,
                    stage="custom_action_exception",
                )
                _record_diagnostic_error = getattr(diagnostics, "record_error", None)
                if callable(_record_diagnostic_error):
                    _record_diagnostic_error(exc)
                write_result = getattr(diagnostics, "write_task_result", None)
                if callable(write_result):
                    write_result(failure)
                _finalize_diagnostics(diagnostics, failure, error=exc)
            debug_dir = os.environ.get("MJA_DEBUG_DIR")
            if debug_dir:
                try:
                    path = Path(debug_dir) / "daily-workflow-errors.log"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(traceback.format_exc())
                        stream.write("\n")
                except OSError:
                    pass
            return CustomAction.RunResult(success=False)
        finally:
            if "owns_diagnostics" in locals() and owns_diagnostics:
                try:
                    diagnostics.close()
                except Exception:
                    pass


class AggregateDailyWorkflowAction(DailyWorkflowAction):
    """Run the date-filtered daily catalog through one Maa ADB driver."""

    def __init__(
        self,
        *,
        driver_factory: Callable[[Any], WorkflowDriver] | None = None,
        scheduler_factory: Callable[[WorkflowDriver], AggregateScheduler] | None = None,
        report_writer: Callable[..., Path] = write_aggregate_report,
        runtime_gate_factory: Callable[[], AndroidRuntimeGate | None] | None = None,
    ) -> None:
        super().__init__(
            driver_factory=driver_factory,
            runtime_gate_factory=runtime_gate_factory,
        )
        self._scheduler_factory = scheduler_factory
        self._report_writer = report_writer

    @staticmethod
    def _selection(argv: Any) -> list[str]:
        raw_param = getattr(argv, "custom_action_param", None)
        if isinstance(raw_param, str):
            try:
                payload = json.loads(raw_param)
            except json.JSONDecodeError:
                payload = None
        elif isinstance(raw_param, dict):
            payload = raw_param
        else:
            payload = None
        selection = payload.get("selection") if isinstance(payload, dict) else None
        if not isinstance(selection, list) or not all(
            isinstance(item, str) for item in selection
        ):
            return ["daily_all"]
        return selection

    @staticmethod
    def _make_diagnostics_factory(debug_root: Path) -> Callable[[str], Any]:
        def create(task_id: str) -> Any:
            return RunDiagnostics.create(debug_root / "daily" / task_id.lower())

        return create

    @staticmethod
    def _runner(
        definition: Any,
        driver: WorkflowDriver,
        policy: Any,
        diagnostics: Any,
        *,
        day: Any,
    ) -> Any:
        result: Any | None = None
        raised: BaseException | None = None
        try:
            if isinstance(driver, MaaAndroidWorkflowDriver):
                boundary = getattr(driver, "require_task_boundary", None)
                if callable(boundary):
                    boundary(policy.task_id)
                elif not driver.return_to_home():
                    event = getattr(diagnostics, "event", None)
                    if callable(event):
                        event(
                            "task_boundary_precondition_failed",
                            {"task_id": policy.task_id},
                        )
            result = run_selected_workflow(
                policy.task_id,
                driver,
                diagnostics,
                day=day,
            )
            if _task_status(result) in _SUCCESSFUL_TASK_STATUSES:
                result = _return_to_home_after_success(result, driver, diagnostics)
            if _task_status(result) is TaskStatus.FAILED:
                _recover_after_task_failure(driver, diagnostics)
            _remember_task_outcome(driver, policy.task_id, result)
            return result
        except Exception as exc:
            raised = exc
            record_error = getattr(diagnostics, "record_error", None)
            if callable(record_error):
                record_error(exc)
            if is_runtime_failure(exc):
                # A dead device, lost foreground app, or login/runtime fault
                # belongs to the batch/session failure domain. Preserve the
                # typed exception so AggregateScheduler stops with its real
                # code instead of inventing a child exception.
                result = _failure_result(
                    policy.task_id,
                    exc,
                    stage="task_runtime_exception",
                )
                raise
            result = _failure_result(
                policy.task_id,
                exc,
                stage="task_runner_exception",
            )
            _recover_after_task_failure(driver, diagnostics)
            _remember_task_outcome(driver, policy.task_id, result)
            return result
        finally:
            if result is not None:
                _finalize_diagnostics(diagnostics, result, error=raised)
            close = getattr(diagnostics, "close", None)
            if callable(close):
                close()

    def run(self, context: Any, argv: Any) -> Any:
        try:
            self._prepare_emulator_window()
            runtime_gate = self._make_runtime_gate()
            if self._driver_factory is None:
                driver = getattr(context, "workflow_driver", None)
                tasker = getattr(context, "tasker", None)
                if driver is None and tasker is not None:
                    driver = getattr(tasker, "workflow_driver", None)
                if driver is None:
                    driver = MaaAndroidWorkflowDriver(context, runtime_gate=runtime_gate)
            else:
                driver = self._driver_factory(context)
            if driver is None:
                return CustomAction.RunResult(success=False)
            if isinstance(driver, MaaAndroidWorkflowDriver):
                if runtime_gate is not None and getattr(driver, "runtime_gate", None) is None:
                    driver.runtime_gate = runtime_gate
                if runtime_gate is not None:
                    runtime_gate.require_health()

            debug_root = Path(os.environ.get("MJA_DEBUG_DIR", "debug/runs"))
            if self._scheduler_factory is None:
                def task_driver(_task_id: str) -> WorkflowDriver:
                    # Share the Maa controller/session, not mutable adapter
                    # state such as cached boxes and last-action markers.
                    if isinstance(driver, MaaAndroidWorkflowDriver):
                        return MaaAndroidWorkflowDriver(context, runtime_gate=runtime_gate)
                    return driver

                scheduler = AggregateScheduler(
                    task_driver,
                    diagnostics_factory=self._make_diagnostics_factory(debug_root),
                    runner=self._runner,
                )
            else:
                scheduler = self._scheduler_factory(driver)
            run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")

            def checkpoint(result: AggregateResult) -> None:
                self._report_writer(result, debug_root, run_id=run_id)

            result = scheduler.run(self._selection(argv), checkpoint=checkpoint)
            checkpoint(result)
            return CustomAction.RunResult(
                success=result.status is AggregateStatus.COMPLETED
            )
        except Exception:
            debug_dir = os.environ.get("MJA_DEBUG_DIR")
            if debug_dir:
                try:
                    path = Path(debug_dir) / "daily-workflow-errors.log"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(traceback.format_exc())
                        stream.write("\n")
                except OSError:
                    pass
            return CustomAction.RunResult(success=False)


try:
    from maa.agent.agent_server import AgentServer
except ImportError:  # pragma: no cover
    AgentServer = None  # type: ignore[assignment]

if AgentServer is not None:
    DailyWorkflowAction = AgentServer.custom_action("DailyWorkflowAction")(DailyWorkflowAction)
    AggregateDailyWorkflowAction = AgentServer.custom_action(
        "AggregateDailyWorkflowAction"
    )(AggregateDailyWorkflowAction)


__all__ = [
    "AggregateDailyWorkflowAction",
    "DailyWorkflowAction",
    "run_selected_workflow",
]
