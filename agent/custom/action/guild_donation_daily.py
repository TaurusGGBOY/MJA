"""Optional MAA workflow bridge for the bounded guild-donation task.

The shipped MFW pipeline uses the shared ``BeginTask``/``GuardedInput``/
``RecordTaskOutcome`` actions.  This task-local action keeps the same business
contract available to the legacy Python workflow runner without adding any
unbounded input path.  The main agent may import it when the legacy registry is
integrated; this file deliberately does not edit that shared registry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.android.runtime_gate import AndroidRuntimeGate
from agent.diagnostics import RunDiagnostics
from agent.workflows.definitions.guild_donation_daily import (
    GUILD_DONATION_DAILY_DEFINITION,
    GUILD_DONATION_DAILY_POLICY,
    terminal_postcondition,
)
from agent.workflows.engine import run_workflow
from agent.workflows.maa_android import MaaAndroidWorkflowDriver
from agent.workflows.models import TaskResult, TaskStatus


def _task_id(argv: Any) -> str | None:
    raw = getattr(argv, "custom_action_param", None)
    if isinstance(raw, dict):
        value = raw.get("task_id")
    elif isinstance(raw, str):
        try:
            value = json.loads(raw).get("task_id")
        except (TypeError, ValueError, json.JSONDecodeError):
            value = None
    else:
        value = None
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    return value or None


def _diagnostics(context: Any, task_id: str) -> tuple[Any, bool]:
    existing = getattr(context, "diagnostics", None)
    if existing is not None:
        return existing, False
    debug_root = os.environ.get("MJA_DEBUG_DIR")
    if debug_root:
        return RunDiagnostics.create(Path(debug_root) / "daily" / task_id.lower()), True
    return SimpleNamespace(), False


def _normalize_result(result: TaskResult) -> TaskResult:
    return TaskResult(
        result.task_id,
        result.status,
        terminal_postcondition(result.status),
        result.action_counts,
        result.error_code,
    )


@AgentServer.custom_action("GuildDonationDailyAction")
class GuildDonationDailyAction(CustomAction):
    """Run one finite donation task through the existing MAA Android driver."""

    def run(self, context: Any, argv: Any) -> Any:
        task_id = _task_id(argv)
        if task_id != GUILD_DONATION_DAILY_DEFINITION.task_id:
            return CustomAction.RunResult(success=False)

        diagnostics, owns_diagnostics = _diagnostics(context, task_id)
        try:
            runtime_gate = None
            if os.environ.get("MJA_CONTROLLER") == "android" or os.environ.get(
                "MJA_ANDROID_ADB"
            ):
                runtime_gate = AndroidRuntimeGate.from_environment()
            driver = getattr(context, "workflow_driver", None)
            if driver is None:
                driver = MaaAndroidWorkflowDriver(context, runtime_gate=runtime_gate)
            if runtime_gate is not None:
                runtime_gate.require_health()
            boundary = getattr(driver, "require_task_boundary", None)
            if callable(boundary):
                boundary(task_id)
            result = run_workflow(
                GUILD_DONATION_DAILY_DEFINITION,
                driver,
                GUILD_DONATION_DAILY_POLICY,
                diagnostics,
                timeout_seconds=300.0,
            )
            result = _normalize_result(result)
            writer = getattr(diagnostics, "write_task_result", None)
            if callable(writer):
                writer(result)
            return CustomAction.RunResult(
                success=result.status
                in {
                    TaskStatus.COMPLETED,
                    TaskStatus.ALREADY_COMPLETE,
                    TaskStatus.NOT_ELIGIBLE,
                }
            )
        except Exception as exc:
            failure = TaskResult(
                task_id,
                TaskStatus.FAILED,
                "guild.donation.postcondition_missing",
                {},
                type(exc).__name__,
            )
            writer = getattr(diagnostics, "write_task_result", None)
            if callable(writer):
                writer(failure)
            return CustomAction.RunResult(success=False)
        finally:
            if owns_diagnostics:
                close = getattr(diagnostics, "close", None)
                if callable(close):
                    close()


__all__ = ["GuildDonationDailyAction"]
