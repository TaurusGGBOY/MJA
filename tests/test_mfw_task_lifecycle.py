from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.custom.action.fail_task import FailTask
from agent.custom.action.task_lifecycle import BeginTask
from agent.custom.sink.task_flow import GlobalPrerequisiteStopSink
from agent.custom.support.state import SAFETY_BUDGETS
from agent.custom.support.task_session import TASK_SESSIONS, TaskSessionRegistry
from tests.mfw.fakes import FakeArgv, FakeContext

_LIFECYCLE_NATIVE_TASK_ID = 9001
_LIFECYCLE_BUSINESS_TASK_ID = "MAIL_REWARD_DAILY"


def _begin_argv(
    task_id: int, business_task_id: str = "MAIL_REWARD_DAILY"
) -> SimpleNamespace:
    return SimpleNamespace(
        custom_action_param=json.dumps({"task_id": business_task_id}),
        task_detail=SimpleNamespace(task_id=task_id),
    )


def test_fail_task_returns_false_without_writing_files(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert FailTask().run(FakeContext(), FakeArgv("{}")) is False
    assert list(tmp_path.iterdir()) == []


def test_native_task_session_rejects_duplicate_native_id_and_releases_budget():
    from agent.custom.support.state import SafetyBudgetStore

    budgets = SafetyBudgetStore()
    sessions = TaskSessionRegistry(budgets)

    sessions.begin(41, "MAIL_REWARD_DAILY")
    assert sessions.business_task_id(41) == "MAIL_REWARD_DAILY"
    assert budgets.increment("MAIL_REWARD_DAILY", "claim_all_mail") == 1

    with pytest.raises(PermissionError, match="already has an active session"):
        sessions.begin(41, "SHOP_FREE_GIFT_DAILY")
    with pytest.raises(PermissionError, match="already has an active safety run"):
        sessions.begin(42, "MAIL_REWARD_DAILY")

    assert sessions.end(41) == "MAIL_REWARD_DAILY"
    assert sessions.business_task_id(41) is None
    with pytest.raises(RuntimeError, match="has not begun"):
        budgets.snapshot("MAIL_REWARD_DAILY")
    assert sessions.end(41) is None


def test_safety_budget_snapshot_contains_no_business_outcome_fields():
    from agent.custom.support.state import SafetyBudgetStore

    budgets = SafetyBudgetStore()
    budgets.begin("BUY_TEA_DAILY")

    snapshot = budgets.snapshot("BUY_TEA_DAILY")

    assert snapshot["max_steps"] > 0
    assert set(snapshot) == {"actions", "resources", "markers", "steps", "max_steps"}


def test_begin_task_starts_native_safety_session_without_result_file(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    TASK_SESSIONS.end(_LIFECYCLE_NATIVE_TASK_ID)
    SAFETY_BUDGETS.end(_LIFECYCLE_BUSINESS_TASK_ID)
    try:
        context = FakeContext()
        argv = _begin_argv(
            _LIFECYCLE_NATIVE_TASK_ID,
            _LIFECYCLE_BUSINESS_TASK_ID,
        )

        assert BeginTask().run(context, argv) is True
        assert BeginTask().run(context, argv) is True
        assert (
            TASK_SESSIONS.business_task_id(_LIFECYCLE_NATIVE_TASK_ID)
            == _LIFECYCLE_BUSINESS_TASK_ID
        )
        assert SAFETY_BUDGETS.snapshot(_LIFECYCLE_BUSINESS_TASK_ID)["actions"] == {}
        assert not list(tmp_path.rglob("result.json"))

        # Native terminal notification is the only lifecycle close operation.
        sink = GlobalPrerequisiteStopSink()
        sink.on_raw_notification(
            SimpleNamespace(post_stop=lambda: None),
            "Tasker.Task.Succeeded",
            {
                "task_id": _LIFECYCLE_NATIVE_TASK_ID,
                "entry": _LIFECYCLE_BUSINESS_TASK_ID,
            },
        )
        assert TASK_SESSIONS.business_task_id(_LIFECYCLE_NATIVE_TASK_ID) is None
        with pytest.raises(RuntimeError, match="has not begun"):
            SAFETY_BUDGETS.snapshot(_LIFECYCLE_BUSINESS_TASK_ID)
    finally:
        TASK_SESSIONS.end(_LIFECYCLE_NATIVE_TASK_ID)
        SAFETY_BUDGETS.end(_LIFECYCLE_BUSINESS_TASK_ID)
