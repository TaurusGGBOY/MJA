# MJA Morning Daily Run Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `MJA_Daily_All` a real, date-aware aggregate run that works from MFAAvalonia and one CLI launcher, records truthful per-task outcomes, and returns a failure exit code when any ordinary task fails.

**Architecture:** `AggregateScheduler` remains the sole domain orchestrator and gains explicit selection/checkpoint state. A focused reporting module atomically writes the same aggregate JSON and Chinese summary for the MFA custom action and CLI. The CLI launches the single `daily_all` Maa entry after synchronizing project payloads into `install/`; it does not independently loop over the workflow catalog.

**Tech Stack:** Python 3.12, MaaFramework Python custom actions and ADB Controller, MFAAvalonia interface/pipeline JSON, pytest, Ruff.

## Global Constraints

- Ordinary task outcomes `failed`, `blocked_safety`, and `not_eligible` are recorded and later tasks continue.
- Emulator, ADB, Maa Controller, game-login/runtime connectivity failures stop the aggregate run.
- All game input goes through MaaFramework's ADB Controller; no Computer Use, host UI clicking, or direct `adb shell input` is added.
- Failure leaves the emulator and game at the inspection point.
- No `verification/tasks/*.json` record is marked live-verified without real device evidence.
- This implementation pass runs offline tests and install verification only; it does not interact with the game.

## File Map

- `agent/workflows/aggregate.py`: selection, aggregate statuses, runtime-failure classification, checkpoint callback, interruption state.
- `agent/workflows/aggregate_report.py`: JSON serialization, atomic report writes, latest-report lookup, Chinese summary, exit-code mapping.
- `agent/actions/daily_workflow.py`: individual action plus registered `AggregateDailyWorkflowAction` adapter.
- `assets/resource_android/pipeline/daily/daily_all.json`: executable `MJA_Daily_All` pipeline entry.
- `tools/android_daily_run.py`: launch `daily_all` once and consume the aggregate report.
- `tools/setup.py`: safe project-payload-only synchronization into an existing installation.
- `tools/android_daily_run.sh`: one morning command performing sync, verification, then execution.
- `tools/project_interface.py`, `tests/test_mfa_daily_contract.py`, `tests/test_android_daily_acceptance.py`: enforce interface-to-pipeline contracts.
- `tests/test_workflow_aggregate.py`, `tests/test_aggregate_report.py`, `tests/test_daily_workflow_action.py`, `tests/test_android_daily_run.py`, `tests/test_setup.py`: focused behavior coverage.

---

### Task 1: Truthful aggregate state and checkpoint callbacks

**Files:**
- Modify: `agent/workflows/aggregate.py`
- Test: `tests/test_workflow_aggregate.py`

**Interfaces:**
- Consumes: `workflow_sequence_for_date(day) -> tuple[str, ...]`, `TaskResult`, `TaskStatus`.
- Produces: `AggregateStatus`, expanded `AggregateResult`, `AggregateScheduler.run(..., checkpoint=None)`, `aggregate_exit_code(result)` in Task 2.

- [ ] **Step 1: Write failing scheduler tests**

Add tests constructing real `TaskResult` values and assert exact preservation, continuation, runtime stop, and checkpoint progression:

```python
def test_aggregate_checkpoints_after_each_task_and_preserves_non_success_results():
    outcomes = iter((
        TaskResult("A", TaskStatus.BLOCKED_SAFETY, "blocked", {}, "SAFETY"),
        TaskResult("B", TaskStatus.NOT_ELIGIBLE, "weekday", {}, None),
    ))
    checkpoints = []
    scheduler = AggregateScheduler(
        lambda _: object(),
        definitions={"A": object(), "B": object()},
        policies={"A": object(), "B": object()},
        runner=lambda *_args, **_kwargs: next(outcomes),
    )
    scheduler._selected = lambda _selected, _day: ("A", "B")

    result = scheduler.run(checkpoint=checkpoints.append)

    assert [item.status for item in result.task_results] == [
        TaskStatus.BLOCKED_SAFETY,
        TaskStatus.NOT_ELIGIBLE,
    ]
    assert result.status is AggregateStatus.COMPLETED_WITH_TASK_FAILURES
    assert checkpoints[0].remaining_task_ids == ("B",)
    assert checkpoints[-1].remaining_task_ids == ()
```

Add a runtime exception test using `MJAError(ErrorCode.ADB_DEVICE_FAILED, ...)`, asserting status `FAILED_RUNTIME`, the failed task remains in `remaining_task_ids`, and no later runner call occurs. Add a `KeyboardInterrupt` test asserting `INTERRUPTED` and checkpoint emission before re-raising is not required.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `install/.venv/bin/python -m pytest tests/test_workflow_aggregate.py -q`

Expected: FAIL because `AggregateStatus`, checkpoint state, and expanded fields do not exist.

- [ ] **Step 3: Implement aggregate state**

Add:

```python
class AggregateStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_TASK_FAILURES = "completed_with_task_failures"
    FAILED_RUNTIME = "failed_runtime"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class AggregateResult:
    task_results: tuple[TaskResult, ...]
    status: AggregateStatus
    started_at: str
    finished_at: str
    selected_date: str
    selected_task_ids: tuple[str, ...]
    remaining_task_ids: tuple[str, ...]
    last_task_id: str | None = None
    stop_reason: str | None = None
    error_code: str | None = None
    evidence_paths: tuple[str, ...] = ()
```

Extend `run` with `checkpoint: Callable[[AggregateResult], None] | None = None`. Build a snapshot after every appended task result, after runtime failure, and after interruption. Treat `FAILED` and `BLOCKED_SAFETY` as failure-class outcomes; `NOT_ELIGIBLE` remains non-failing. Keep the unattempted runtime-failure task in `remaining_task_ids`.

Centralize runtime classification in public helpers:

```python
def error_code_for(exc: BaseException) -> str:
    return str(getattr(getattr(exc, "code", None), "value", "") or "")


def is_runtime_failure(exc: BaseException) -> bool:
    code = error_code_for(exc)
    return code.startswith(("ANDROID_", "ADB_", "CONTROLLER_", "WINDOW_", "LOGIN_"))
```

- [ ] **Step 4: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_workflow_aggregate.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1 files only**

```bash
git add agent/workflows/aggregate.py tests/test_workflow_aggregate.py
git commit -m "feat: track aggregate daily run state"
```

### Task 2: Atomic reports, Chinese summary, and exit codes

**Files:**
- Create: `agent/workflows/aggregate_report.py`
- Create: `tests/test_aggregate_report.py`

**Interfaces:**
- Consumes: `AggregateResult`, `AggregateStatus`, `TaskResult`, `TaskStatus` from Task 1.
- Produces: `write_aggregate_report(result, root, *, run_id=None) -> Path`, `load_latest_aggregate_report(root, *, newer_than=None) -> dict[str, Any] | None`, `render_chinese_summary(payload) -> str`, `aggregate_exit_code(payload) -> int`.

- [ ] **Step 1: Write failing report tests**

Cover enum/string serialization, atomic latest report, required checkpoint fields, Chinese per-task lines, and all four exit classes:

```python
def test_report_round_trip_and_partial_failure_exit_code(tmp_path):
    result = AggregateResult(
        task_results=(TaskResult("MAIL_REWARD_DAILY", TaskStatus.FAILED, "timeout", {}, "X"),),
        status=AggregateStatus.COMPLETED_WITH_TASK_FAILURES,
        started_at="2026-07-30T00:00:00+08:00",
        finished_at="2026-07-30T00:01:00+08:00",
        selected_date="2026-07-30",
        selected_task_ids=("MAIL_REWARD_DAILY", "BUY_TEA_DAILY"),
        remaining_task_ids=("BUY_TEA_DAILY",),
        last_task_id="MAIL_REWARD_DAILY",
    )

    path = write_aggregate_report(result, tmp_path, run_id="run-1")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "completed_with_task_failures"
    assert payload["remaining_task_ids"] == ["BUY_TEA_DAILY"]
    assert aggregate_exit_code(payload) == 1
    assert "MAIL_REWARD_DAILY：失败" in render_chinese_summary(payload)
    assert load_latest_aggregate_report(tmp_path) == payload
```

Assert exit codes `0`, `1`, `3`, and `130`; invalid/missing status raises `ValueError` so the CLI can map malformed reports to runtime failure.

- [ ] **Step 2: Run tests and confirm failure**

Run: `install/.venv/bin/python -m pytest tests/test_aggregate_report.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement reporting**

Write per-run reports under `<root>/daily/aggregate-<run_id>.json` and an atomically replaced `<root>/daily/aggregate-latest.json`. Serialize dataclasses recursively, convert `StrEnum` to `.value`, copy mappings to plain dictionaries, and use a same-directory `.tmp` file followed by `Path.replace()`. Include `run_id` and derive `completed_task_ids` from attempted results whose status is `completed` or `already_complete`.

Use these status labels in `render_chinese_summary`: `completed=完成`, `already_complete=已完成`, `not_eligible=今日不适用`, `blocked_safety=安全阻止`, `failed=失败`. Include totals and remaining task count.

- [ ] **Step 4: Run report tests**

Run: `install/.venv/bin/python -m pytest tests/test_aggregate_report.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 2 files only**

```bash
git add agent/workflows/aggregate_report.py tests/test_aggregate_report.py
git commit -m "feat: persist aggregate daily reports"
```

### Task 3: Real MFA `MJA_Daily_All` custom action and pipeline

**Files:**
- Modify: `agent/actions/daily_workflow.py`
- Create: `assets/resource_android/pipeline/daily/daily_all.json`
- Modify: `tests/test_daily_workflow_action.py`
- Modify: `tests/test_mfa_daily_contract.py`
- Modify: `tests/test_android_daily_acceptance.py`

**Interfaces:**
- Consumes: `AggregateScheduler.run(checkpoint=...)` and `write_aggregate_report(...)`.
- Produces: registered Maa custom action named `AggregateDailyWorkflowAction`; pipeline entry `MJA_Daily_All`.

- [ ] **Step 1: Write failing action and contract tests**

Test an injected scheduler returning `COMPLETED`, `COMPLETED_WITH_TASK_FAILURES`, and `FAILED_RUNTIME`; only `COMPLETED` yields `CustomAction.RunResult(success=True)`. Assert the checkpoint callback writes reports and the driver factory returns the same `MaaAndroidWorkflowDriver` instance for every child task.

Extend the MFA contract test:

```python
aggregate = ROOT / "assets/resource_android/pipeline/daily/daily_all.json"
payload = json.loads(aggregate.read_text(encoding="utf-8"))
entry = payload["MJA_Daily_All"]
assert entry["custom_action"] == "AggregateDailyWorkflowAction"
assert entry["custom_action_param"] == {"selection": ["daily_all"]}
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `install/.venv/bin/python -m pytest tests/test_daily_workflow_action.py tests/test_mfa_daily_contract.py tests/test_android_daily_acceptance.py -q`

Expected: FAIL because the action and pipeline do not exist.

- [ ] **Step 3: Implement the aggregate action**

Add `AggregateDailyWorkflowAction` with injectable scheduler/report factories. Parse `custom_action_param` using the same JSON handling pattern as `DailyWorkflowAction`. Create one `MaaAndroidWorkflowDriver(context)`, use `lambda _task_id: driver`, and create per-task diagnostics below `MJA_DEBUG_DIR/daily/<task_id>`. Pass this callback:

```python
def checkpoint(result: AggregateResult) -> None:
    write_aggregate_report(result, Path(debug_root))
```

Catch unexpected exceptions, write the existing traceback log, and return false without cleanup or emulator shutdown. Register it beside the individual action:

```python
AggregateDailyWorkflowAction = AgentServer.custom_action(
    "AggregateDailyWorkflowAction"
)(AggregateDailyWorkflowAction)
```

Create `daily_all.json`:

```json
{
  "MJA_Daily_All": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "AggregateDailyWorkflowAction",
    "custom_action_param": {"selection": ["daily_all"]}
  }
}
```

- [ ] **Step 4: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_daily_workflow_action.py tests/test_mfa_daily_contract.py tests/test_android_daily_acceptance.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 3 files only**

```bash
git add agent/actions/daily_workflow.py assets/resource_android/pipeline/daily/daily_all.json tests/test_daily_workflow_action.py tests/test_mfa_daily_contract.py tests/test_android_daily_acceptance.py
git commit -m "feat: add MFA aggregate daily action"
```

### Task 4: Canonical CLI runs the aggregate entry once

**Files:**
- Modify: `tools/android_daily_run.py`
- Modify: `tests/test_android_daily_run.py`

**Interfaces:**
- Consumes: `AndroidRun.run("daily_all", ...)`, `load_latest_aggregate_report`, `render_chinese_summary`, `aggregate_exit_code`.
- Produces: `tools.android_daily_run.main(argv) -> int` with truthful aggregate exit codes.

- [ ] **Step 1: Replace loop-oriented tests with aggregate-entry tests**

Use a fake `AndroidRun` and a temporary debug root. Assert exactly one call:

```python
assert module.main([]) == 1
assert _FakeAndroidRun.calls == [("daily_all", False, False, True)]
assert "完成但有任务失败" in capsys.readouterr().out
```

Add cases for missing report after a zero child exit (`3`), malformed report (`3`), runtime failure (`3`), interruption (`130`), and successful aggregate (`0`). Preserve explicit `--task TASK_ID` as a targeted single-task fallback, but reject multiple `--task` values because they cannot share the in-process aggregate action.

- [ ] **Step 2: Run CLI tests and confirm failure**

Run: `install/.venv/bin/python -m pytest tests/test_android_daily_run.py -q`

Expected: FAIL because the current CLI loops over every task and returns zero for partial failure.

- [ ] **Step 3: Implement single-entry CLI behavior**

Record `started_at = datetime.now().astimezone()`, call `AndroidRun().run("daily_all", ...)` once, then load only `aggregate-latest.json` whose modification time is not older than `started_at`. Print `render_chinese_summary(payload)` and the report path. Return the report-derived exit code; child process failure without a fresh readable report returns `3`. Catch `KeyboardInterrupt` and return `130`.

For `--task TASK_ID`, invoke the existing individual entry once and return its child exit code; this path is for targeted retry and does not claim to produce an aggregate report.

- [ ] **Step 4: Run CLI tests**

Run: `install/.venv/bin/python -m pytest tests/test_android_daily_run.py tests/test_android_run.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 4 files only**

```bash
git add tools/android_daily_run.py tests/test_android_daily_run.py
git commit -m "fix: return truthful daily aggregate status"
```

### Task 5: One morning launcher with payload sync and preflight

**Files:**
- Modify: `tools/setup.py`
- Create: `tools/android_daily_run.sh`
- Modify: `tests/test_setup.py`
- Modify: `tests/test_verify_install.py`

**Interfaces:**
- Consumes: `_assemble_install_in_place`, `verify_install`, `tools.android_daily_run`.
- Produces: `sync_project_payload(project_root: Path, install_root: Path) -> None`; executable `tools/android_daily_run.sh`.

- [ ] **Step 1: Write failing synchronization tests**

Create a minimal project/install fixture with stale agent/resource/interface content. Assert `sync_project_payload` replaces only project-owned payloads, updates `mja-workflow-manifest.json`, preserves `install/.venv` and runtime files, and includes `resource_android/pipeline/daily/daily_all.json`.

- [ ] **Step 2: Run setup tests and confirm failure**

Run: `install/.venv/bin/python -m pytest tests/test_setup.py tests/test_verify_install.py -q`

Expected: FAIL because the public payload-only synchronization function and aggregate install contract do not exist.

- [ ] **Step 3: Implement synchronization and launcher**

Add the public wrapper:

```python
def sync_project_payload(project_root: Path, install_root: Path) -> None:
    if not install_root.is_dir():
        raise RuntimeError(f"existing install is required: {install_root}")
    _assemble_install_in_place(install_root, {}, project_root=project_root)
```

Add a `--sync-only` setup CLI option that calls this wrapper without downloading artifacts or rebuilding MaaFramework.

Create `tools/android_daily_run.sh`:

```sh
#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
/opt/homebrew/bin/python3 -m tools.setup --root "$ROOT_DIR" --sync-only
"$ROOT_DIR/install/.venv/bin/python" -m tools.verify_install "$ROOT_DIR/install"
exec "$ROOT_DIR/install/.venv/bin/python" -m tools.android_daily_run "$@"
```

Make the script executable. It starts no extra Terminal windows and runs synchronization/preflight once before the aggregate session.

- [ ] **Step 4: Run focused tests and static shell check**

Run:

```bash
install/.venv/bin/python -m pytest tests/test_setup.py tests/test_verify_install.py -q
sh -n tools/android_daily_run.sh
```

Expected: all PASS and shell syntax check exits zero.

- [ ] **Step 5: Commit Task 5 files only**

```bash
git add tools/setup.py tools/android_daily_run.sh tests/test_setup.py tests/test_verify_install.py
git commit -m "feat: add verified morning daily launcher"
```

### Task 6: Full offline verification and installed payload validation

**Files:**
- Modify only if required by a failing check: files changed in Tasks 1-5

**Interfaces:**
- Consumes: all prior task deliverables.
- Produces: a source tree and synchronized installation that pass every offline gate.

- [ ] **Step 1: Fix the two pre-existing Ruff findings in touched runtime code**

Run: `install/.venv/bin/python -m ruff check agent tools tests`

Fix import ordering in `agent/macos/emulator_window.py` and wrap the overlong line in `agent/workflows/maa_android.py` without behavioral changes.

- [ ] **Step 2: Run focused aggregate suite**

Run:

```bash
install/.venv/bin/python -m pytest tests/test_workflow_aggregate.py tests/test_aggregate_report.py tests/test_daily_workflow_action.py tests/test_android_daily_run.py tests/test_mfa_daily_contract.py tests/test_android_daily_acceptance.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the complete test suite**

Run: `install/.venv/bin/python -m pytest -q`

Expected: all tests pass; existing intentional skips remain skips.

- [ ] **Step 4: Synchronize and verify without launching the game**

Run:

```bash
/opt/homebrew/bin/python3 -m tools.setup --root /Users/gaoguobin/project/MJA --sync-only
install/.venv/bin/python -m tools.verify_install install
```

Expected: both commands exit zero; installed `resource_android` and `agent` match source.

- [ ] **Step 5: Run final static checks**

Run:

```bash
install/.venv/bin/python -m ruff check agent tools tests
git diff --check
sh -n tools/android_daily_run.sh
```

Expected: all commands exit zero.

- [ ] **Step 6: Commit verification-only fixes if any**

```bash
git add agent/macos/emulator_window.py agent/workflows/maa_android.py
git commit -m "style: satisfy runtime lint checks"
```

- [ ] **Step 7: Record the morning command without running it**

The handoff command is:

```bash
cd /Users/gaoguobin/project/MJA && ./tools/android_daily_run.sh
```

Report that live task records remain `live_pending` until a real game run produces evidence.
