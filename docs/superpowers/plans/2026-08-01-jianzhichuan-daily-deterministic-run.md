# Jianzhichuan Daily Deterministic Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Android `daily_all` 在不重试业务任务的前提下，遇到异常立即停止而不级联，并在修复后按原执行顺序重新完成最近一次失败的 13 项任务。

**Architecture:** 在现有 Maa workflow engine 外增加只读 Android 运行时门禁；每个任务只执行一次，成功后由 Maa ADB Controller 把已识别页面归一化到主页并验证新帧。聚合器在第一个任务失败、边界失败或运行时失败时停止，保存剩余任务和诊断，不把失败画面交给后续任务。

**Tech Stack:** Python 3、pytest、MaaFramework CustomAction、Maa Android ADB Controller、现有 `AdbDevice`/`LoginGate`、Android 35 emulator、JSON pipeline/resource fixtures。

## Global Constraints

- 所有游戏输入继续通过 MaaFramework 的 Android ADB Controller；不使用 Computer Use、macOS 点击或裸 `adb shell input`。
- 启动阶段可以使用现有 `AdbDevice.start_app`、`LoginGate` 和运行时健康检查；不自动输入账号、验证码、支付或未知弹窗。
- 不清除游戏数据、不卸载、不重置模拟器；模拟器保持开启。
- 不为失败任务增加业务重跑、盲点点击或无限等待。
- 失败时保留诊断证据，但聚合器不得继续执行后续任务。
- 最终全量验收必须是 `completed`，所有任务必须是 `completed` 或 `already_complete`，且 `remaining_task_ids` 为空。
- 现有工作树包含用户修改；每次修改前先检查 `git diff`，只触碰本计划涉及的行和文件，不使用 `git reset --hard` 或 `git checkout --`。

---

## File Map

| File | Responsibility in this plan |
|---|---|
| `agent/android/runtime_gate.py` | 从当前 Android 环境创建只读运行时门禁，验证前台/健康状态。 |
| `agent/actions/daily_workflow.py` | 创建门禁、在聚合开始和任务边界调用门禁，移除失败后的隐式恢复。 |
| `agent/workflows/aggregate.py` | 增加任务失败停止状态和 fail-fast 调度。 |
| `agent/workflows/aggregate_report.py` | 为新的聚合停止状态提供 JSON/中文摘要/退出码。 |
| `agent/workflows/maa_android.py` | 补齐任务边界验证和已知页面清场，严禁 Launcher 盲点。 |
| `agent/workflows/definitions/batch1.py` | 修复邮件、商城、鉴宝、采集状态机和后置条件。 |
| `agent/workflows/definitions/batch23.py` | 修复蜃影、偃武凝晶、武学突破相关状态机。 |
| `agent/workflows/engine.py` | 只修复被当前帧证据证明的后置验证问题，不改变动作授权模型。 |
| `assets/resource_android/image/daily/**` | 只加入经 live capture 证明稳定的识别资源。 |
| `tests/test_android_runtime_gate.py` | 运行时门禁单元测试。 |
| `tests/test_daily_workflow_action.py` | 聚合动作和任务边界注入/停止测试。 |
| `tests/test_workflow_aggregate.py` | fail-fast、checkpoint、剩余任务顺序测试。 |
| `tests/test_maa_android_workflow.py` | Launcher 禁止输入和清场路径测试。 |
| `tests/workflows/test_batch23.py`、`tests/workflows/test_*daily.py` | 各业务状态机回归测试。 |
| `tools/android_daily_run.py` | 保持现有单任务与 `daily_all` 入口；仅在需要记录顺序时增加可审计的任务选择支持。 |
| `docs/superpowers/specs/2026-08-01-jianzhichuan-daily-deterministic-run-design.md` | 已批准的行为契约；实现不得偏离。 |

## Interfaces

Task 1 produces this interface for later tasks:

```python
class AndroidRuntimeGate:
    @classmethod
    def from_environment(cls) -> "AndroidRuntimeGate": ...

    def require_health(self) -> None: ...

    def require_foreground(self) -> None: ...

    @property
    def package_name(self) -> str: ...
```

`require_foreground()` must raise the existing `MJAError` with `ErrorCode.ANDROID_GAME_NOT_FOREGROUND` when `AdbDevice.foreground_package()` is not the configured game package. It must never call `start_app()`.

Task 2 produces this aggregate contract:

```python
class AggregateStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_TASK_FAILURES = "completed_with_task_failures"
    FAILED_TASK = "failed_task"
    FAILED_RUNTIME = "failed_runtime"
    INTERRUPTED = "interrupted"
```

`FAILED_TASK` means the current task returned `TaskStatus.FAILED`; `remaining_task_ids` contains the untouched suffix in catalog order. The existing `COMPLETED_WITH_TASK_FAILURES` value remains readable for old reports but is no longer emitted by the fail-fast scheduler.

Task 3 produces this driver/action boundary contract:

```python
def require_task_boundary(self, task_id: str | None = None) -> None: ...
```

It first checks the Android runtime gate when present, then captures and recognizes a supported game boundary. It may call `return_to_home()` only when the current frame contains a recognized game page and an authorized close path; it must raise on Launcher or unknown screens.

---

### Task 1: Add the read-only Android runtime gate

**Files:**
- Create: `agent/android/runtime_gate.py`
- Modify: `agent/android/__init__.py` only if the package exports are currently maintained there
- Create: `tests/test_android_runtime_gate.py`
- Reference: `agent/android/adb.py`, `agent/android/config.py`, `agent/android/sdk.py`, `agent/android/login.py`

**Interfaces:**
- Consumes: `AndroidConfig.load()`, `AndroidSdk.discover()`, `AdbDevice.foreground_package()`, `AdbDevice.require_runtime_health()`.
- Produces: `AndroidRuntimeGate.from_environment()`, `require_health()`, `require_foreground()`, `package_name`.

- [ ] **Step 1: Write failing gate tests.**

Add fakes for `AdbDevice` and `SdkPaths`; prove a game foreground passes, Launcher raises `ANDROID_GAME_NOT_FOREGROUND`, and `require_health()` delegates exactly once without starting the app.

```python
def test_require_foreground_rejects_launcher():
    gate = AndroidRuntimeGate(device=FakeDevice(foreground=None), package_name="com.game")
    with pytest.raises(MJAError) as error:
        gate.require_foreground()
    assert error.value.code is ErrorCode.ANDROID_GAME_NOT_FOREGROUND
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `pytest -q tests/test_android_runtime_gate.py`

Expected: collection or attribute failures because `runtime_gate.py` and `AndroidRuntimeGate` do not exist.

- [ ] **Step 3: Implement the gate without a launch or input path.**

Implement `from_environment()` by loading `AndroidConfig`, resolving the SDK with `AndroidSdk(config).discover()`, reading `MJA_ANDROID_SERIAL`/`MJA_ANDROID_ADB` when present, and constructing `AdbDevice`. Raise `MJAError(ErrorCode.ANDROID_SDK_UNAVAILABLE, ...)` if the SDK paths cannot be discovered. `require_foreground()` only compares packages; `require_health()` only delegates `require_runtime_health()`.

- [ ] **Step 4: Run the focused tests and the existing Android tests.**

Run: `pytest -q tests/test_android_runtime_gate.py tests/test_android_adb.py tests/test_android_login.py`

Expected: PASS, with no fake or real `start_app()` call from the gate.

- [ ] **Step 5: Review the diff before staging.**

Run: `git diff -- agent/android/runtime_gate.py tests/test_android_runtime_gate.py`; confirm no raw input command, data wipe, or user-owned unrelated hunk is present.

### Task 2: Make aggregate scheduling fail fast on a task failure

**Files:**
- Modify: `agent/workflows/aggregate.py`
- Modify: `agent/workflows/aggregate_report.py`
- Modify: `tests/test_workflow_aggregate.py`
- Modify: `tests/test_aggregate_report.py`

**Interfaces:**
- Consumes: `TaskStatus`, `TaskResult`, existing checkpoint callback.
- Produces: `AggregateStatus.FAILED_TASK`, early return with exact `remaining_task_ids`.

- [ ] **Step 1: Replace the old continue-on-failure assertions with a failing fail-fast test.**

Change the first aggregate test to assert:

```python
assert calls == ["MAIL_REWARD_DAILY"]
assert aggregate.status is AggregateStatus.FAILED_TASK
assert aggregate.remaining_task_ids == IDS[1:]
assert aggregate.last_task_id == "MAIL_REWARD_DAILY"
```

Add a checkpoint assertion that the checkpoint contains only the failed task and the untouched suffix.

- [ ] **Step 2: Run the aggregate tests and verify the changed behavior fails.**

Run: `pytest -q tests/test_workflow_aggregate.py tests/test_aggregate_report.py`

Expected: the old scheduler continues and returns `COMPLETED_WITH_TASK_FAILURES`, so the new assertion fails.

- [ ] **Step 3: Add `FAILED_TASK` and stop immediately after recording a failed `TaskResult`.**

After appending a task result, handle `TaskStatus.FAILED` before computing the normal completed status:

```python
if result.status is TaskStatus.FAILED:
    status = AggregateStatus.FAILED_TASK
    aggregate = self._result(
        results, status, started_at, selected_day, selected,
        attempted, "task_failed", result.error_code,
    )
    if checkpoint is not None:
        checkpoint(aggregate)
    return aggregate
```

Keep `KeyboardInterrupt` and `is_runtime_failure()` paths unchanged. `NOT_ELIGIBLE` remains a terminal non-failure result and may proceed when explicitly selected.

- [ ] **Step 4: Update report labels and exit codes.**

Map `FAILED_TASK` to a task-failure label and non-zero exit code in `aggregate_report.py`; add a report fixture proving the JSON status, summary, and exit code are stable.

- [ ] **Step 5: Run the focused tests.**

Run: `pytest -q tests/test_workflow_aggregate.py tests/test_aggregate_report.py`

Expected: PASS; no later runner invocation occurs after a failed task.

### Task 3: Inject runtime and enforce task boundaries in the aggregate action

**Files:**
- Modify: `agent/actions/daily_workflow.py`
- Modify: `agent/workflows/maa_android.py`
- Modify: `tests/test_daily_workflow_action.py`
- Modify: `tests/test_maa_android_workflow.py`

**Interfaces:**
- Consumes: `AndroidRuntimeGate` from Task 1 and fail-fast scheduler from Task 2.
- Produces: `MaaAndroidWorkflowDriver.require_task_boundary()` and a runner that never calls `can_resume_task()` to continue after a failure.

- [ ] **Step 1: Add failing action/driver tests.**

Cover three cases:

```python
def test_launcher_boundary_raises_without_starting_app(): ...
def test_successful_task_requires_home_after_boundary_cleanup(): ...
def test_failed_task_is_not_cleaned_or_followed_by_next_task(): ...
```

Use a fake runtime gate and fake recognition results; assert that Launcher causes a runtime/boundary error and that `start_app` is never called by the boundary.

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `pytest -q tests/test_daily_workflow_action.py tests/test_maa_android_workflow.py -k 'boundary or launcher or failure'`

Expected: missing `require_task_boundary()` or old `_runner()` behavior causes failure.

- [ ] **Step 3: Add optional runtime-gate injection and the boundary method.**

Extend `MaaAndroidWorkflowDriver.__init__` with an optional `runtime_gate: AndroidRuntimeGate | None`; preserve existing test constructors by defaulting to `None`. Implement `require_task_boundary()` so it calls `runtime_gate.require_foreground()` when injected, then uses a fresh Maa frame. If the frame is already `reset.home`, return; if it is a recognized supported game surface, call `return_to_home()` and require `True`; otherwise raise `MJAError` with the appropriate boundary code.

- [ ] **Step 4: Wire the default gate in `AggregateDailyWorkflowAction`.**

Create the gate from the Android environment for Android runs, allow the test `driver_factory` to inject a fake gate, call `require_health()` once before scheduling, and call `driver.require_task_boundary(policy.task_id)` before each task. Remove the current “if not `can_resume_task()` then call `return_to_home()` and ignore the boolean” behavior. Do not add a task rerun.

- [ ] **Step 5: Make successful cleanup a hard contract.**

Keep `_return_to_home_after_success()` as the only post-success cleanup path, but ensure the result is written as failed with `TASK_BOUNDARY_RETURN_FAILED` or `TASK_BOUNDARY_VERIFY_FAILED` when cleanup/after-frame verification fails. Failed task results must return untouched so the scheduler stops and diagnostics retain the failure surface.

- [ ] **Step 6: Run the focused tests and full workflow unit suite.**

Run: `pytest -q tests/test_daily_workflow_action.py tests/test_maa_android_workflow.py tests/test_workflow_aggregate.py`

Expected: PASS; a Launcher frame never receives a controller action and a failed task never starts a later task.

### Task 4: Harden known page-boundary cleanup and current-frame authorization

**Files:**
- Modify: `agent/workflows/maa_android.py`
- Modify: `agent/workflows/engine.py` only for the verified current-frame error path
- Modify: `tests/test_maa_android_workflow.py`
- Modify: `tests/test_workflow_engine.py`

**Interfaces:**
- Consumes: `require_task_boundary()` from Task 3 and existing `recognize()` evidence.
- Produces: deterministic, page-gated cleanup for known game pages; no input on Launcher or stale recognition boxes.

- [ ] **Step 1: Add regression tests for every observed cleanup surface.**

Use the existing recognition fake to test mail reward popup, appraisal, collection, shadow reward popup, martial page, bag, dungeon, hero dispatch, daily reward, battle pass, painting and shop. Each test must provide the page marker and close marker, assert the expected controller action, then provide a home frame and assert `True`.

- [ ] **Step 2: Add a regression test for stale current-frame boxes.**

Build two frames where `yanwu_world_tab` is recognized only in the first; assert the second action raises `RuntimeError("no current-frame recognition box for yanwu_world_tab")` and performs no tap.

- [ ] **Step 3: Run tests and observe the current failures.**

Run: `pytest -q tests/test_maa_android_workflow.py tests/test_workflow_engine.py -k 'home or popup or current_frame or launcher or yanwu'`

Expected: at least the observed Launcher and stale-box regressions fail before implementation.

- [ ] **Step 4: Implement only page/target-authorized cleanup branches.**

Extend `return_to_home()` with explicit page markers and bounded close ROIs already supported by the Android renderer. Keep `max_steps` finite. Do not add a generic top-right click. Clear `_boxes` on every fresh frame and keep action execution tied to `self._last_frame_id`.

- [ ] **Step 5: Run the boundary regression suite.**

Run: `pytest -q tests/test_maa_android_workflow.py tests/test_workflow_engine.py`

Expected: PASS, including a test that a Launcher frame causes `return_to_home()` to return `False` without controller calls.

### Task 5: Repair mail, shop, appraisal, and collection workflows

**Files:**
- Modify: `agent/workflows/definitions/batch1.py`
- Modify: `agent/workflows/maa_android.py` when an action requires a page-specific bounded tap
- Modify: `assets/resource_android/pipeline/daily/mail_reward_daily.json`
- Modify: `assets/resource_android/pipeline/daily/shop_free_gift_daily.json`
- Modify: `assets/resource_android/pipeline/daily/free_appraisal_daily.json`
- Modify: `assets/resource_android/pipeline/daily/collection_deployment_daily.json`
- Modify/add: relevant `assets/resource_android/image/daily/**` resources only from live captures
- Modify: `tests/workflows/test_mail_reward_daily.py`, `tests/workflows/test_shop_free_gift_daily.py`, `tests/workflows/test_collection_deployment_daily.py`

**Interfaces:**
- Consumes: current-frame evidence and boundary cleanup from Tasks 3–4.
- Produces: mail popup closure, shop already-claimed recognition, and verified home postconditions for appraisal/collection.

- [ ] **Step 1: Add fixture tests for the observed failure states.**

Assert that mail reward popup transitions to a recognized close state; shop `已领取` returns `TaskStatus.ALREADY_COMPLETE`; appraisal and collection do not finish until a home marker is present after the result overlay is dismissed.

- [ ] **Step 2: Run those workflow tests and record the failing assertions.**

Run: `pytest -q tests/workflows/test_mail_reward_daily.py tests/workflows/test_shop_free_gift_daily.py tests/workflows/test_collection_deployment_daily.py`

Expected: the observed popup/claimed/home assertions fail before the state transitions are corrected.

- [ ] **Step 3: Implement the minimal state transitions.**

Keep protected-claim and action-cap checks. Add only the missing result-popup and page-close transitions; do not mark an action complete solely from an earlier frame. Treat an explicitly recognized already-claimed/sold-out marker as `ALREADY_COMPLETE`.

- [ ] **Step 4: Run focused workflow tests and inspect resource manifests.**

Run: `pytest -q tests/workflows/test_mail_reward_daily.py tests/workflows/test_shop_free_gift_daily.py tests/workflows/test_collection_deployment_daily.py tests/test_android_resources.py`

Expected: PASS and no resource manifest references an absent file.

### Task 6: Repair shadow, spend-condensate, and martial-study workflows

**Files:**
- Modify: `agent/workflows/definitions/batch23.py`
- Modify: `agent/workflows/maa_android.py`
- Modify: `agent/workflows/engine.py` only if a postcondition needs a fresh-frame polling fix
- Modify/add: `assets/resource_android/pipeline/daily/shadow_ruins_daily.json`, `spend_condensate_daily.json`, `martial_study_breakthrough_daily.json`
- Modify/add: corresponding Android image resources
- Modify: `tests/workflows/test_batch23.py`
- Modify: `tests/test_maa_android_workflow.py`

**Interfaces:**
- Consumes: current-frame evidence and fail-fast boundary from Tasks 3–4.
- Produces: shadow reward dismissal before advance, current-frame-only Yanwu selection, and stable martial panel/card recognition.

- [ ] **Step 1: Add failing tests for the three live traces.**

Test that a second shadow battle cannot advance while `shadow_reward_popup` is visible; test that a stale Yanwu box is rejected; test that a rendered function panel with the known live marker is accepted even when the old `panel` template is absent.

- [ ] **Step 2: Run the focused batch tests.**

Run: `pytest -q tests/workflows/test_batch23.py tests/test_maa_android_workflow.py -k 'shadow or condensate or martial'`

Expected: FAIL at the pre-fix assertions.

- [ ] **Step 3: Implement each state transition using fresh evidence.**

For Shadow, require and dismiss the reward overlay, verify the exploration page, then allow the next movement. For Spend Condensate, store no cross-frame OCR box and make every tap depend on the current recognition frame. For Martial Study, wait for the final rendered page/card evidence already used by the Android driver, then claim only recognized success cards and close through the recognized page.

- [ ] **Step 4: Run batch tests and static resource validation.**

Run: `pytest -q tests/workflows/test_batch23.py tests/workflows/test_jianlin_resource_condensate_stamina_daily.py tests/test_android_resources.py`

Expected: PASS with no relaxed safety authorization.

### Task 7: Add regression coverage for all remaining cascade tasks and report semantics

**Files:**
- Modify: `tests/test_daily_workflow_action.py`
- Modify: `tests/test_workflow_aggregate.py`
- Modify: `tests/test_android_daily_run.py`
- Modify: `tests/test_mfa_daily_contract.py` if report schema coverage requires it
- Modify: `agent/workflows/aggregate_report.py` only for tested status/summary behavior

**Interfaces:**
- Consumes: fail-fast scheduler and boundary gate.
- Produces: tests proving the six formerly Launcher-only tasks are not invoked after an earlier failure and are eligible to run from a clean home in a new run.

- [ ] **Step 1: Add a table-driven sequence test.**

Use the catalog order and the latest failed set; make a fake runner fail at `SPEND_CONDENSATE_DAILY` and assert no later task is called, while a clean run records every selected ID exactly once.

- [ ] **Step 2: Add a CLI/report test for remaining IDs.**

Assert that a fail-fast aggregate report preserves the original selected order and lists the untouched suffix; `aggregate_exit_code()` returns non-zero for `failed_task` and zero only for `completed`.

- [ ] **Step 3: Run the complete Python test suite.**

Run: `pytest -q`

Expected: PASS. If an existing test assumes continue-on-failure, update that test to the approved fail-fast contract rather than weakening the implementation.

### Task 8: Run ordered Android verification and the final full aggregate

**Files:**
- No source changes by default.
- Evidence: `install/debug/runs/daily/**` and `install/debug/runs/android/**`.
- Optional modify: `tools/android_daily_run.py` only if an ordered task-list mode is needed for a reproducible run report.

**Interfaces:**
- Consumes: all implementation tasks and the current Android emulator session.
- Produces: one successful result for each of the 13 failed task IDs in the exact order below, then a successful full `daily_all` report.

- [ ] **Step 1: Run the full automated suite and verify the emulator preconditions.**

Run: `pytest -q`.

Before live execution, verify the emulator is already running, the game account is logged in, and the current Android runtime has at least the existing health-check requirements. Do not wipe data or stop the emulator.

- [ ] **Step 2: Execute the failed tasks in original order, one task per explicit run.**

Run each command only after the previous command produced `completed` or `already_complete`; do not execute a later command after a failure:

```bash
python tools/android_daily_run.py --task MAIL_REWARD_DAILY
python tools/android_daily_run.py --task SHOP_FREE_GIFT_DAILY
python tools/android_daily_run.py --task FREE_APPRAISAL_DAILY
python tools/android_daily_run.py --task COLLECTION_DEPLOYMENT_DAILY
python tools/android_daily_run.py --task SHADOW_RUINS_DAILY
python tools/android_daily_run.py --task SPEND_CONDENSATE_DAILY
python tools/android_daily_run.py --task MARTIAL_STUDY_BREAKTHROUGH_DAILY
python tools/android_daily_run.py --task EAT_STAMINA_FOOD_DAILY
python tools/android_daily_run.py --task DUNGEON_SWEEP_DAILY
python tools/android_daily_run.py --task JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY
python tools/android_daily_run.py --task RING_CHALLENGE_DAILY
python tools/android_daily_run.py --task DAILY_TASK_REWARD_CLAIM_DAILY
python tools/android_daily_run.py --task BATTLE_PASS_REWARD_DAILY
```

After each command, inspect the newly written task result and `after.png`; the task must end in a verified home boundary. A failure stops this sequence for diagnosis.

- [ ] **Step 3: Execute the complete aggregate once.**

Run: `python tools/android_daily_run.py`

Expected: `aggregate-latest.json` has `status: "completed"`, no remaining task IDs, all task statuses in `{completed, already_complete}`, and no Launcher evidence.

- [ ] **Step 4: Audit the final evidence against the specification.**

Check the 16 task result directories, the aggregate report, each `after` frame, and the absence of `WORKFLOW_POSTCONDITION_MISSING`, `WORKFLOW_DRIVER_FAILED`, `TASK_BOUNDARY_RETURN_FAILED`, and `ANDROID_GAME_NOT_FOREGROUND` in the final run.

- [ ] **Step 5: Record the final run paths and commit only the implementation changes.**

Run: `git status --short` and `git diff --check`; stage only files changed by this plan, leaving pre-existing user modifications untouched.

## Self-Review Checklist

- [ ] Every design requirement has a task: runtime gate (Task 1), fail-fast and remaining IDs (Task 2), boundary injection/cleanup (Tasks 3–4), seven known business areas (Tasks 5–6), regression/report semantics (Task 7), and ordered rerun/full acceptance (Task 8).
- [ ] No task introduces a business retry, raw Android input, automatic login, data wipe, or unknown-popup click.
- [ ] `FAILED_TASK`, `AggregateStatus`, report labels, and exit-code mappings use the same spelling everywhere.
- [ ] The final ordered list exactly matches the 13 failed task IDs in the latest aggregate and preserves catalog order.
- [ ] No step is allowed to continue after a live failure; this is an operational guard, not an implicit retry policy.

