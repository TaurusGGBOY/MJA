# MJA Maa_bbb 风格全量 Workflow 迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `jianzhichuan_daily` 中的 17 个日常 workflow 迁移为 Android ADB + MaaFramework + MFAAvalonia 可选任务，并支持全选执行、单任务失败后继续、普通资源受限消耗和可审计安全结果。

**Architecture:** 先建立共享的 immutable workflow models、同帧 safety gate、受限输入、诊断和 capture-decide-act-verify engine；每个 workflow 只产生 `Decision`，不直接执行输入。参考 Maa_bbb 的 Agent custom action 注册和 GUI task list，把每个 definition 注册为独立 ProjectInterface task，再由 aggregate scheduler 按日期和业务顺序串行运行。现有 Android runtime hardening、`mail_smoke_test` 和 MaaPiCli native bundle 作为运行底座，不重新实现。

**Tech Stack:** Python 3.14、pytest、ruff、MaaFramework/MaaPiCli 5.12.2、Maa Agent API、Android SDK 35、ADB、Android 15 Google APIs AVD、Pillow/NumPy、ProjectInterface V2、MFAAvalonia。

## Global Constraints

- 业务真值固定为 `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py`；`daily_todo.py` 提供日期状态格式，`ui_surfaces.json` 提供页面层级。
- 运行平台固定为当前 Android AVD `mja-api35-apis` / `emulator-5556`，游戏包固定为 `com.hanjiasongshu.dr22`，显示契约固定为 `1280x720`，系统语言使用中文。
- 旧 `mja-api35` / `emulator-5554` 不得恢复；不得使用 Google Play 下载游戏。
- 现有 `mail_smoke_test` 保持只读，不领取邮件奖励；新增 `MAIL_REWARD_DAILY` 才负责普通邮件奖励。
- 全量注册 17 个 canonical task，并保留业务源文件的顺序：`MAIL_REWARD_DAILY`、`SHOP_FREE_GIFT_DAILY`、`WEEKLY_FREE_GIFT_MONDAY`、`TRIAL_SWORD_DAILY`、`FREE_APPRAISAL_DAILY`、`BUY_TEA_DAILY`、`COLLECTION_DEPLOYMENT_DAILY`、`HERO_DISPATCH_DAILY`、`SHADOW_RUINS_DAILY`、`SPEND_CONDENSATE_DAILY`、`MARTIAL_STUDY_BREAKTHROUGH_DAILY`、`EAT_STAMINA_FOOD_DAILY`、`DUNGEON_SWEEP_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`、`RING_CHALLENGE_DAILY`、`DAILY_TASK_REWARD_CLAIM_DAILY`、`BATTLE_PASS_REWARD_DAILY`。
- MFAAvalonia 中显示全部任务；用户点击全选和开始后，聚合调度器按日期过滤和排序。
- 单个任务的识别失败、动作超时、上限耗尽或后置条件失败必须记录后继续下一个任务；设备断连、模拟器健康检查失败、MaaPiCli 无法启动时停止整个批次。
- 付费、充值、真实货币、Apple Pay、付费礼包、登录、密码、验证码、实名认证、生物识别、安全验证、未知弹窗、未知货币和目标不唯一均禁止输入。
- 普通游戏资源只有在当前帧明确识别名称/数量、资源属于该任务白名单、未超过单次/任务/每日上限且动作后置条件可验证时才允许消耗。
- 所有副作用动作必须经过同帧页面证据、目标证据和危险证据检查；不使用固定历史坐标、键盘快捷键或未识别的空白区域点击。
- 运行态只能使用 `completed`、`already_complete`、`not_eligible`、`blocked_safety`、`failed`；`live_pending`/`live_verified` 只允许出现在 machine-checkable verification records。
- 每个任务必须有 `entry`、`actionable`、`completed`、`danger` 四态 fixture；fixture 识别测试不得发送输入。
- 不修改或暂存 `AGENTS.md`，不修改 `/Users/gaoguobin/project/MaaFramework` 参考 checkout；每次提交使用明确的 `git add -- <paths>`，禁止 `git add .`、`git add -A` 和宽目录暂存。
- 每个任务、每个质量门和每次真实验收都必须独立提交；提交前运行对应聚焦测试、ruff 和 `git diff --check`。

## Existing Plan Dependencies

本总计划将以下已存在文档作为子计划，不复制其中已经定义的每个 workflow 业务转换表：

- `docs/superpowers/plans/2026-07-28-mja-workflow-foundation.md`：models、catalog、safety、input、diagnostics、runner、navigation、fixture、interface 基础。
- `docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-1.md`：8 个导航/免费/派遣任务。
- `docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-2.md`：6 个常规资源/副本任务。
- `docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-3.md`：Shadow、Jianlin、Ring 和三任务入口。
- `docs/superpowers/plans/2026-07-28-mja-aggregate-live-verification.md`：verification record、聚合调度和 MFA 验收。

这些历史子计划中涉及 macOS controller 的内容必须按本计划的 Android 约束改写为 `mja_android` + `android`，不得把 macOS 坐标或 923×720/1051×820 校准带入 Android 资源。

## File Map Before Implementation

### Shared foundation

- Create: `agent/workflows/__init__.py` — 导出 canonical models、catalog、registry 和 aggregate API。
- Create: `agent/workflows/models.py` — immutable status、policy、frame、evidence、intent、transition、decision、result 类型。
- Create: `agent/workflows/catalog.py` — 唯一的 17-task policy catalog 和按日期的 workflow order。
- Create: `agent/safety.py` — `SafetyReason`、`SafetyDecision`、`authorize_action`。
- Create: `agent/workflows/input.py` — Android click/swipe/long-press 的受限 driver 和 box 映射。
- Create: `agent/workflows/engine.py` — `WorkflowDriver`、`run_workflow`、有限重试、后置条件和终态。
- Create: `agent/workflows/navigation.py` — 主界面、功能面板、画卷、日常、页面关闭的共享 graph/recognizer contract。
- Create: `agent/actions/daily_workflow.py` — Maa custom action `DailyWorkflowAction`，唯一进入 engine 的 Pipeline action。
- Modify: `agent/actions/android_foreground_click.py` — 复用现有 ADB foreground input contract，不绕过 safety gate。
- Modify: `agent/diagnostics.py` — 扩展为 task-scoped schema，保留现有 Android result writer 和脱敏规则。
- Modify: `agent/errors.py` — 添加 workflow/safety/aggregate stable error codes。

### Task resources and interface

- Create: `assets/resource_android/pipeline/common/navigation.json` — 只含页面识别和可复用关闭节点。
- Create: `assets/resource_android/pipeline/daily/{lowercase_task_id}.json` — 每个任务的 Pipeline entry。
- Create: `assets/resource_android/image/daily/{TASK_ID}/` — 当前 Android AVD 实拍模板。
- Modify: `assets/resource_android/calibration.json` — 增加 workflow template contract 和采集版本，不改变已验证 1280×720 基线。
- Create: `tools/project_interface.py` — deterministic ProjectInterface V2 renderer/validator。
- Modify: `assets/interface.json` — 17 个任务、`daily_all` 聚合任务和既有回归任务。
- Modify: `tools/setup.py` — 将 workflow resources、interface、agent 注册纳入 install assembly。

### Per-task source and verification

- Create: `agent/workflows/definitions/{lowercase_task_id}.py` — 每个任务一个 `WorkflowDefinition`。
- Create: `agent/workflows/registry.py` — 显式 registry，拒绝隐式 import/重复 task ID。
- Create: `tests/fixtures/{TASK_ID}/manifest.json`、`entry.png`、`actionable.png`、`completed.png`、`danger.png`。
- Create: `tests/workflows/test_{lowercase_task_id}.py` — policy、decision、fixture、cap、safety 测试。
- Create: `verification/tasks/{TASK_ID}.json` — 仅保存真实证据 admission metadata，不能用 fixture 冒充 live result。

### Aggregate and documentation

- Create: `agent/workflows/aggregate.py` — `AggregateScheduler`、日期过滤、任务级继续和汇总。
- Create: `tools/android_daily_run.py` — Android aggregate CLI，与现有 `tools/android_run.sh` 单任务 smoke 入口并存。
- Create: `tests/test_workflow_aggregate.py` — scheduler/failure/skip/restore 测试。
- Create: `tests/test_project_interface.py` — deterministic interface and task selection contract。
- Create: `docs/testing/android-daily-workflows.md` — operator workflow。
- Create: `docs/verification/mja-daily-workflows-batch-{1,2,3}.md` — 每批真实证据索引。
- Create: `docs/verification/mja-daily-aggregate.md` — 全选批次汇总和 MFA 验收。

---

### Task 1: Define canonical workflow models and the 17-task policy catalog

**Files:**
- Create: `agent/workflows/__init__.py`
- Create: `agent/workflows/models.py`
- Create: `agent/workflows/catalog.py`
- Create: `agent/workflows/registry.py`
- Create: `tests/test_workflow_models.py`
- Create: `tests/test_workflow_catalog.py`
- Modify: `agent/errors.py`

**Interfaces:**
- Produces `TaskStatus`, `TaskPolicy`, `ActionIntent`, `CapturedFrame`, `Recognition`, `VisualEvidence`, `StateSnapshot`, `Transition`, `Decision`, `TaskResult`, `WorkflowDefinition`.
- Produces `TASK_POLICIES: Mapping[str, TaskPolicy]`, `WORKFLOW_DEFINITION_ORDER: tuple[str, ...]`, `workflow_sequence_for_date(day: date | None = None) -> tuple[str, ...]` and `WORKFLOW_DEFINITIONS: Mapping[str, WorkflowDefinition]`.
- `TaskStatus` values are exactly `completed`, `already_complete`, `not_eligible`, `blocked_safety`, `failed`.

- [ ] **Step 1: Write failing model tests.** Assert frozen/slot dataclasses reject missing required values, enum values are exact, `Decision.act()` requires a transition, `Decision.finish()` requires a permitted status, and `TaskResult` rejects unknown runtime statuses.

  ```python
  def test_task_status_has_only_runtime_values():
      assert {item.value for item in TaskStatus} == {
          "completed", "already_complete", "not_eligible",
          "blocked_safety", "failed",
      }
  ```

- [ ] **Step 2: Run `./install/.venv/bin/python -m pytest -q tests/test_workflow_models.py` and confirm the imports/types are absent.** Expected result: collection fails because `agent.workflows.models` does not exist.
- [ ] **Step 3: Implement immutable models.** Use `@dataclass(frozen=True, slots=True)` for value objects; validate non-empty frame IDs, non-negative counters, finite caps, supported input kinds (`click`, `swipe`, `long_press`, `none`) and transition postcondition markers. Keep `WorkflowDefinition` as a Protocol with `task_id`, `initial_state`, `recognizers(state)` and `decide(snapshot, counters)`.
- [ ] **Step 4: Write failing catalog tests for all 17 IDs.** Assert exact IDs, unique lowercase interface names, finite caps, Monday-only `WEEKLY_FREE_GIFT_MONDAY`, correct dependency/order hints, and non-empty approved resource sets for resource-consuming tasks.
- [ ] **Step 5: Implement `catalog.py` and `registry.py`.** Copy only task names and business step semantics from `workflows.py`; do not duplicate a second workflow implementation. Define conservative policies first, including hard stops for paid/verification/unknown signals and explicit caps for Shadow, Jianlin and Ring.
- [ ] **Step 6: Run focused tests and Ruff.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_workflow_models.py tests/test_workflow_catalog.py
  ./install/.venv/bin/python -m ruff check agent/workflows agent/errors.py tests/test_workflow_models.py tests/test_workflow_catalog.py
  ```

- [ ] **Step 7: Commit only Task 1 files.**

  ```bash
  git add -- agent/workflows/__init__.py agent/workflows/models.py agent/workflows/catalog.py agent/workflows/registry.py agent/errors.py tests/test_workflow_models.py tests/test_workflow_catalog.py
  git commit -m "feat: add canonical daily workflow models and policies"
  ```

### Task 2: Implement same-frame safety authorization and bounded Android input

**Files:**
- Create: `agent/safety.py`
- Create: `agent/workflows/input.py`
- Modify: `agent/actions/android_foreground_click.py`
- Create: `tests/test_safety.py`
- Create: `tests/test_workflow_input.py`

**Interfaces:**
- Produces `SafetyReason`, `SafetyDecision`, `authorize_action(evidence, intent, policy, action_counts) -> SafetyDecision`.
- Produces `map_box_center(box, frame_size, calibration_size) -> tuple[int, int]`, `AndroidWorkflowDriver.click`, `.swipe`, `.long_press` and `.execute(intent)`.
- `authorize_action` must reject any positive danger hit, page mismatch, target ambiguity, frame mismatch, disallowed resource, exceeded cap, paid text, verification text or unknown currency.

- [ ] **Step 1: Write failing parameterized safety tests.** Cover correct same-frame page/target approval, missing page, missing target, two targets, mismatched recognizer frame IDs, `¥`/`充值`/`支付`, login/verification, unknown dialog, unknown currency, resource not in policy, one-purchase cap and action cap.
- [ ] **Step 2: Run `./install/.venv/bin/python -m pytest -q tests/test_safety.py tests/test_workflow_input.py` and confirm the safety module is absent.**
- [ ] **Step 3: Implement `authorize_action`.** Normalize OCR text only for matching; preserve raw evidence in diagnostics. Check danger before target, target before resource, and resource before cap. Return a stable reason instead of raising for an ordinary safety denial.
- [ ] **Step 4: Implement calibration-aware ADB input.** Map current recognition boxes from the current screenshot size to the Android controller size; execute only the authorized action. Do not accept raw historical coordinates from a definition or fixture. Make swipe and long-press duration explicit and bounded.
- [ ] **Step 5: Add regression tests proving the existing `AndroidForegroundClick` action remains the only low-level click path and cannot receive a denied action.**
- [ ] **Step 6: Run focused tests and Ruff.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_safety.py tests/test_workflow_input.py tests/test_android_foreground_click.py
  ./install/.venv/bin/python -m ruff check agent/safety.py agent/workflows/input.py agent/actions/android_foreground_click.py tests/test_safety.py tests/test_workflow_input.py
  ```

- [ ] **Step 7: Commit only Task 2 files.**

  ```bash
  git add -- agent/safety.py agent/workflows/input.py agent/actions/android_foreground_click.py tests/test_safety.py tests/test_workflow_input.py
  git commit -m "feat: add same-frame safety gate and bounded Android input"
  ```

### Task 3: Implement the capture-decide-act-verify engine and task diagnostics

**Files:**
- Create: `agent/workflows/engine.py`
- Create: `agent/actions/daily_workflow.py`
- Modify: `agent/diagnostics.py`
- Modify: `agent/errors.py`
- Create: `tests/test_workflow_engine.py`
- Create: `tests/test_daily_workflow_action.py`
- Modify: `tests/test_diagnostics.py`

**Interfaces:**
- Produces `WorkflowDriver` Protocol with `capture()`, `recognize(frame, recognizer_names)` and `execute(intent)`.
- Produces `run_workflow(definition, driver, policy, diagnostics, *, day=None) -> TaskResult`.
- Produces Maa custom action `DailyWorkflowAction.run(...) -> bool`, which loads the selected definition and delegates to `run_workflow`; it must not contain task-specific transitions.
- Extends `RunDiagnostics` with task-local `result.json`, `action-trace.jsonl`, before/after/failure PNG paths and redacted error details while preserving existing Android result compatibility.

- [ ] **Step 1: Write failing engine tests.** Cover normal transition, same-frame authorization before execution, postcondition verification, `already_complete`, `not_eligible`, denied action, step cap, action cap, timeout, driver exception, task failure continuation signal and no-input terminal states.
- [ ] **Step 2: Run `./install/.venv/bin/python -m pytest -q tests/test_workflow_engine.py tests/test_daily_workflow_action.py tests/test_diagnostics.py` and confirm the engine/action modules are absent.**
- [ ] **Step 3: Implement the bounded loop.** On every iteration capture a new frame, recognize only the definition’s requested markers, create one `StateSnapshot`, call `decide`, call `authorize_action` for a transition, execute once, capture again, and verify the declared postcondition. Never execute an intent returned by an earlier frame.
- [ ] **Step 4: Implement terminal and exception mapping.** Map safety denials to `blocked_safety`, planned weekday skips to `not_eligible`, verified no-op state to `already_complete`, verified completion to `completed`, and cap/timeout/technical errors to `failed`. Persist the latest frame before returning a non-success result.
- [ ] **Step 5: Implement the Maa custom action adapter.** Register one `DailyWorkflowAction` with AgentServer, validate task ID against `WORKFLOW_DEFINITIONS`, receive the Android controller context, and return false on a non-completed child result without swallowing diagnostics.
- [ ] **Step 6: Run focused tests, full existing tests and Ruff.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_workflow_engine.py tests/test_daily_workflow_action.py tests/test_diagnostics.py
  ./install/.venv/bin/python -m pytest -q
  ./install/.venv/bin/python -m ruff check .
  ```

- [ ] **Step 7: Commit only Task 3 files.**

  ```bash
  git add -- agent/workflows/engine.py agent/actions/daily_workflow.py agent/diagnostics.py agent/errors.py tests/test_workflow_engine.py tests/test_daily_workflow_action.py tests/test_diagnostics.py
  git commit -m "feat: add bounded workflow engine and task diagnostics"
  ```

### Task 4: Add shared Android navigation, fixture harness and ProjectInterface renderer

**Files:**
- Create: `agent/workflows/navigation.py`
- Create: `tools/project_interface.py`
- Create: `tests/test_workflow_navigation.py`
- Create: `tests/test_project_interface.py`
- Create: `tests/workflows/support.py`
- Create: `assets/resource_android/pipeline/common/navigation.json`
- Modify: `assets/resource_android/calibration.json`
- Modify: `assets/interface.json`

**Interfaces:**
- Produces shared page markers for `home`, `function_panel`, `mail`, `shop`, `daily`, `martial_study`, `painting_scroll`, `yanwu_world`, `yunzhou`, `universal_shop`, `collection_deployment`, `hero_dispatch`, `shadow_ruins`, `jianlin`, `ring`, `trial_sword`, `appraisal` and `dungeon`.
- Produces `load_fixture_manifest(path)`, `recognize_fixture(manifest, case) -> StateSnapshot` and `render_interface(task_ids, *, base) -> dict[str, object]`.
- Canonical task entry is `MJA_Daily_{TASK_ID}`, resource is `mja_android`, controller is `android`, and `default_check` remains false until live admission.

- [ ] **Step 1: Write failing navigation and fixture tests.** Assert every shared marker has a unique ID, fixture manifests reject unknown keys, PNG dimensions match the current Android calibration, and fixture recognition never calls an input driver.
- [ ] **Step 2: Write failing interface tests.** Assert deterministic order, all 17 task names, one `daily_all` entry, exact resource/controller mapping, no duplicate names, and preservation of `mail_smoke_test`.
- [ ] **Step 3: Run focused tests and confirm the new modules/resources are absent.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_workflow_navigation.py tests/test_project_interface.py
  ```

- [ ] **Step 4: Implement the shared navigation graph and strict fixture loader.** Read `assets/resource_android/calibration.json`; reject old macOS/legacy capture sizes instead of projecting them. Use fixture support objects only for recognition tests, never for live success.
- [ ] **Step 5: Implement deterministic ProjectInterface rendering.** Preserve the two existing controller/resource definitions, add all individual task entries and `daily_all`, and make task labels/status metadata explicit. Do not manually append entries in arbitrary order.
- [ ] **Step 6: Run focused tests, install verification and Ruff.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_workflow_navigation.py tests/test_project_interface.py tests/test_project_contract.py
  ./install/.venv/bin/python tools/verify_install.py install
  ./install/.venv/bin/python -m ruff check agent/workflows/navigation.py tools/project_interface.py tests/test_workflow_navigation.py tests/test_project_interface.py
  ```

- [ ] **Step 7: Commit only Task 4 files.**

  ```bash
  git add -- agent/workflows/navigation.py tools/project_interface.py tests/test_workflow_navigation.py tests/test_project_interface.py tests/workflows/support.py assets/resource_android/pipeline/common/navigation.json assets/resource_android/calibration.json assets/interface.json
  git commit -m "feat: add Android navigation fixtures and task interface renderer"
  ```

### Task 5: Implement Batch 1 workflows from the business source

**Scope:** `MAIL_REWARD_DAILY`, `SHOP_FREE_GIFT_DAILY`, `WEEKLY_FREE_GIFT_MONDAY`, `TRIAL_SWORD_DAILY`, `FREE_APPRAISAL_DAILY`, `COLLECTION_DEPLOYMENT_DAILY`, `DAILY_TASK_REWARD_CLAIM_DAILY`, `BATTLE_PASS_REWARD_DAILY`.

**Files:**
- Create the eight definitions under `agent/workflows/definitions/`.
- Create the eight Android Pipeline files under `assets/resource_android/pipeline/daily/`.
- Create the eight `assets/resource_android/image/daily/{TASK_ID}/` directories.
- Create the eight fixture manifests and four PNG cases under `tests/fixtures/{TASK_ID}/`.
- Create eight `tests/workflows/test_{lowercase_task_id}.py` files.
- Modify: `agent/workflows/registry.py`, `agent/workflows/catalog.py`, `assets/interface.json`.

**Interfaces:**
- Each definition implements the Task 1 `WorkflowDefinition` Protocol and returns only `Decision.act`/`Decision.finish`.
- Each Pipeline has entry `MJA_Daily_{TASK_ID}` and delegates side effects to `DailyWorkflowAction`.
- Each test uses `tests/workflows/support.py` to prove decision behavior without live input.

- [ ] **Step 1: Copy the exact transition requirements into failing tests.** Use the existing Batch 1 plan and source workflow definitions to encode navigation, normal state, already-complete state, danger state, finite action caps and postconditions; do not invent a second business sequence.
- [ ] **Step 2: Run each new test file before implementation and record the expected import/registry failures.**
- [ ] **Step 3: Implement `MAIL_REWARD_DAILY` and `SHOP_FREE_GIFT_DAILY` first.** Keep `mail_smoke_test` read-only; permit only ordinary mail reward and free-gift targets under policy; reject any payment prompt and verify the page after closing.
- [ ] **Step 4: Implement Monday/free tasks `WEEKLY_FREE_GIFT_MONDAY`, `TRIAL_SWORD_DAILY` and `FREE_APPRAISAL_DAILY`.** The Monday workflow must return `not_eligible` on non-Monday without capturing or clicking; each free-once task must return `already_complete` from an independent visual postcondition.
- [ ] **Step 5: Implement `COLLECTION_DEPLOYMENT_DAILY`, `DAILY_TASK_REWARD_CLAIM_DAILY` and `BATTLE_PASS_REWARD_DAILY`.** Bound row/chest/basic-track loops, never click paid/premium controls, and leave unrelated rewards to the dedicated reward workflow.
- [ ] **Step 6: Capture Android templates from the current logged-in `emulator-5556`, then fill manifests with actual decoded PNG dimensions and calibration version.** Do not copy macOS or historical fixture PNGs.
- [ ] **Step 7: Run Batch 1 focused tests and install validation.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/workflows/test_mail_reward_daily.py tests/workflows/test_shop_free_gift_daily.py tests/workflows/test_weekly_free_gift_monday.py tests/workflows/test_trial_sword_daily.py tests/workflows/test_free_appraisal_daily.py tests/workflows/test_collection_deployment_daily.py tests/workflows/test_daily_task_reward_claim_daily.py tests/workflows/test_battle_pass_reward_daily.py
  ./install/.venv/bin/python -m pytest -q tests/test_project_interface.py tests/test_android_resources.py tests/test_verify_install.py
  ./install/.venv/bin/python tools/verify_install.py install
  ```

- [ ] **Step 8: Perform independent foreground checks and safe no-op reruns for all eight tasks.** Record current commit, AVD serial, before/after/failure evidence and postcondition; mark unavailable branches pending rather than claiming success.
- [ ] **Step 9: Commit each Batch 1 workflow using the exact file list in the corresponding task's `Files` block in `docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-1.md`; do not pass a directory to `git add`.** The final Batch 1 evidence commit must contain only the explicit report path `docs/verification/mja-daily-workflows-batch-1.md` and its listed metadata files.

### Task 6: Implement Batch 2 resource and ordinary dungeon workflows

**Scope:** `HERO_DISPATCH_DAILY`, `BUY_TEA_DAILY`, `SPEND_CONDENSATE_DAILY`, `MARTIAL_STUDY_BREAKTHROUGH_DAILY`, `EAT_STAMINA_FOOD_DAILY`, `DUNGEON_SWEEP_DAILY`.

**Files:**
- Create six definitions, six Android Pipelines, six Android template directories, six fixture manifests/cases and six workflow test files using the Task 5 layout.
- Modify: `agent/workflows/catalog.py`, `agent/workflows/registry.py`, `assets/interface.json`.
- Create: `docs/verification/mja-daily-workflows-batch-2.md`.

**Interfaces:**
- Definitions consume `TaskPolicy`, `StateSnapshot`, `ActionIntent`, `Decision`, `authorize_action` and `run_workflow` from Tasks 1–3.
- Resource-consuming definitions must set `approved_resource` and exact action caps; they cannot authorize from an unlabeled currency value.

- [ ] **Step 1: Write failing tests for each source-defined path.** Cover first-visible hero dispatch item and six-team cap, tea stock/usable inventory, both condensate stores and 10000 verification, three martial-study attempts per slot, named food/overfull stop, and exact 燕王秘陵(大师) sweep/ticket/bag-full handling.
- [ ] **Step 2: Run all six tests before implementation and confirm registry/definition failures.**
- [ ] **Step 3: Implement the six definitions with explicit resource policies.** Read resource name and count from the same frame, enforce per-task caps, verify postconditions after every consumptive action, and return `blocked_safety` when resource identity or amount is ambiguous.
- [ ] **Step 4: Implement Android Pipelines and collect four-state fixtures from the current emulator.** Every side-effect node must use `DailyWorkflowAction`; no standard blind Click or StartApp action.
- [ ] **Step 5: Run focused Batch 2 tests, full resource/interface verification and Ruff.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/workflows/test_hero_dispatch_daily.py tests/workflows/test_buy_tea_daily.py tests/workflows/test_spend_condensate_daily.py tests/workflows/test_martial_study_breakthrough_daily.py tests/workflows/test_eat_stamina_food_daily.py tests/workflows/test_dungeon_sweep_daily.py
  ./install/.venv/bin/python -m pytest -q tests/test_project_interface.py tests/test_android_resources.py tests/test_verify_install.py
  ./install/.venv/bin/python -m ruff check .
  ```

- [ ] **Step 6: Perform live foreground checks and safe reruns for all six tasks.** Verify resource deltas, ticket counts, bag-full stop and independent daily postconditions; write the Batch 2 evidence report.
- [ ] **Step 7: Commit each Batch 2 workflow using the exact file list in the corresponding task's `Files` block in `docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-2.md`; do not pass a directory to `git add`.** The final Batch 2 evidence commit must contain only explicit paths from that plan and `docs/verification/mja-daily-workflows-batch-2.md`.

### Task 7: Implement Batch 3 complex branching workflows

**Scope:** `SHADOW_RUINS_DAILY`, `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`, `RING_CHALLENGE_DAILY`.

**Files:**
- Create three definitions, three Android Pipelines, three Android template directories, three fixture manifests/cases and three workflow test files using the Task 5 layout.
- Modify: `agent/workflows/catalog.py`, `agent/workflows/registry.py`, `assets/interface.json`.
- Create: `docs/verification/mja-daily-workflows-batch-3.md`.

**Interfaces:**
- Shadow definition must map reference anchors through current calibration and expose reference/mapped coordinates in diagnostics.
- Jianlin definition must enforce exactly one `+80`/`10 紫色魂玉` purchase when the same frame proves it and calculate safe count/multiplier before each challenge.
- Ring definition must branch from labeled `擂台积分`/mode evidence, never from an unrelated top-right currency.

- [ ] **Step 1: Write failing direct-route, anchor-order, purchase-count, score-branch and danger tests.** Assert Shadow direct `前往` before fallback, left/center/right anchor order with 20-round cap, Jianlin one-purchase and 12-cycle cap, and Ring 12-fight/one-sweep caps.
- [ ] **Step 2: Run the three test files and confirm the expected missing definition/policy failures.**
- [ ] **Step 3: Implement Shadow direct navigation and only the explicit navigation-error fallback.** Map all three historical anchors through `assets/resource_android/calibration.json`; authorize only on recognized stage page and verify progress after each complete round.
- [ ] **Step 4: Implement Jianlin safe purchase/planner and Ring labeled-score branching.** Require same-frame resource evidence, do not fall back to unsafe `x1`, do not spend a second purchase, and stop when score/mode is unlabeled or ambiguous.
- [ ] **Step 5: Add Pipelines, collect current Android fixtures and run focused tests.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/workflows/test_shadow_ruins_daily.py tests/workflows/test_jianlin_resource_condensate_stamina_daily.py tests/workflows/test_ring_challenge_daily.py
  ./install/.venv/bin/python -m pytest -q tests/test_android_resources.py tests/test_project_interface.py tests/test_verify_install.py
  ./install/.venv/bin/python -m ruff check .
  ```

- [ ] **Step 6: Perform live foreground calibration checks, then full bounded task runs and no-op reruns.** Do not mark a task completed when the required branch is unavailable; record the exact pending reason and evidence path.
- [ ] **Step 7: Commit each Batch 3 workflow using the exact file list in the corresponding task's `Files` block in `docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-3.md`; do not pass a directory to `git add`.** The final Batch 3 evidence commit must contain only explicit paths from that plan and `docs/verification/mja-daily-workflows-batch-3.md`.

### Task 8: Implement aggregate scheduling with task-level continuation

**Files:**
- Create: `agent/workflows/aggregate.py`
- Create: `tools/android_daily_run.py`
- Create: `tests/test_workflow_aggregate.py`
- Modify: `agent/workflows/catalog.py`, `agent/diagnostics.py`, `agent/errors.py`
- Modify: `docs/superpowers/plans/2026-07-28-mja-aggregate-live-verification.md` to replace fail-fast task semantics with the user-approved task-level continuation semantics.

**Interfaces:**
- Produces `AggregateScheduler.run(selected_task_ids, *, day=None) -> AggregateResult`.
- Produces `AggregateResult(task_results: tuple[TaskResult, ...], status: str, started_at: str, finished_at: str)` with redacted per-task evidence paths.
- Produces `workflow_sequence_for_date(day)` that includes `WEEKLY_FREE_GIFT_MONDAY` only on Monday and places reward collection before `BATTLE_PASS_REWARD_DAILY`.

- [ ] **Step 1: Write failing scheduler tests.** Assert canonical order, Monday filtering, selected-task filtering, `already_complete`/`not_eligible` continuation, ordinary `failed`/`blocked_safety` continuation, and device-level exception stopping before the next task.
- [ ] **Step 2: Run `./install/.venv/bin/python -m pytest -q tests/test_workflow_aggregate.py` and confirm the scheduler is absent.**
- [ ] **Step 3: Implement the scheduler.** Before each child create a task-scoped diagnostic directory; run one task only; append its `TaskResult`; attempt bounded known-page recovery; continue after task-level results; stop on `ANDROID_*` device/runtime errors.
- [ ] **Step 4: Implement `tools/android_daily_run.py`.** Reuse `AndroidConfig`, `AndroidSdk`, `AndroidAvd`, `AdbDevice`, `LoginGate`, existing `MaaPiCli` and `mja_android`; do not duplicate emulator health checks or native bundle logic.
- [ ] **Step 5: Add aggregate replay tests with fake definitions and driver.** Verify task order, no input for skipped tasks, one child result per task, aggregate summary redaction and stable exit codes.
- [ ] **Step 6: Run focused/full tests, Ruff and install verification.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_workflow_aggregate.py tests/test_workflow_engine.py tests/test_project_interface.py
  ./install/.venv/bin/python -m pytest -q
  ./install/.venv/bin/python -m ruff check .
  ./install/.venv/bin/python tools/verify_install.py install
  ```

- [ ] **Step 7: Commit only aggregate files and the explicitly updated aggregate plan.**

  ```bash
  git add -- agent/workflows/aggregate.py tools/android_daily_run.py tests/test_workflow_aggregate.py agent/workflows/catalog.py agent/diagnostics.py agent/errors.py docs/superpowers/plans/2026-07-28-mja-aggregate-live-verification.md
  git commit -m "feat: add task-continuing daily aggregate scheduler"
  ```

### Task 9: Wire Maa_bbb-style Agent registration, MFA interface and install assembly

**Files:**
- Modify: `agent/main.py`
- Modify: `tools/setup.py`
- Modify: `assets/interface.json`
- Modify: `tests/test_agent_main.py`, `tests/test_setup.py`, `tests/test_project_interface.py`
- Create: `tests/test_mfa_daily_contract.py`
- Modify: `docs/testing/android-daily-workflows.md`

**Interfaces:**
- `agent.main` registers exactly one daily custom action entry point plus any shared recognition registrations; importing the module in tests must not start an AgentServer.
- `tools.setup._assemble_install_in_place` copies workflow source/resources and emits a manifest that includes task registry and interface digest.
- `assets/interface.json` contains all 17 individual names, `daily_all`, `mail_smoke_test`, and no duplicate entry/resource/controller mapping.

- [ ] **Step 1: Write failing registration and install tests.** Assert `DailyWorkflowAction` is registered once, interface task selection writes the selected task to `maa_pi_config.json`, aggregate selection is accepted, unknown task names fail before launch, and install assembly includes all daily Pipeline/image/fixture-independent runtime files.
- [ ] **Step 2: Run the focused tests and record failures.**
- [ ] **Step 3: Implement lazy Maa Agent registration modeled on Maa_bbb `CustomFile.py`.** Keep imports safe when Maa is unavailable; use the current Android action implementation; do not add Windows paths, direct coordinate tables or a second runner.
- [ ] **Step 4: Extend setup and verification.** Copy `agent/workflows`, `agent/safety.py`, daily resources, `assets/interface.json`, and registry metadata into `install`; reject missing task entries, mismatched resource/controller, stale asset digest and unsafe action names.
- [ ] **Step 5: Run interface/agent/setup tests and verify install.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_agent_main.py tests/test_mfa_daily_contract.py tests/test_project_interface.py tests/test_setup.py
  ./install/.venv/bin/python tools/verify_install.py install
  ./install/.venv/bin/python -m ruff check agent/main.py tools/setup.py tests/test_mfa_daily_contract.py
  ```

- [ ] **Step 6: Commit only Agent/MFA/setup files and operator documentation.**

  ```bash
  git add -- agent/main.py tools/setup.py assets/interface.json tests/test_agent_main.py tests/test_mfa_daily_contract.py tests/test_project_interface.py tests/test_setup.py docs/testing/android-daily-workflows.md
  git commit -m "feat: expose daily workflows through Maa Agent and MFA interface"
  ```

### Task 10: Capture Android resources and admit individual live verification records

**Files:**
- Modify: `tools/capture_android_templates.py`
- Modify: `assets/resource_android/calibration.json`
- Create/replace: `assets/resource_android/image/daily/{TASK_ID}/**.png`
- Create: `verification/tasks/{TASK_ID}.json` for each actually verified task
- Create: `tests/test_live_verification_records.py`
- Modify: `docs/verification/mja-daily-workflows-batch-{1,2,3}.md`

**Interfaces:**
- `capture_android_templates` must capture from current `emulator-5556`, write actual PNGs atomically, and record frame size/calibration digest.
- Each verification record must contain task ID, checkout revision, AVD/serial, resource digest, fixture paths, diagnostic path, result status, postcondition evidence and redacted limitations; it must reject paths outside the task diagnostic root.

- [ ] **Step 1: Write failing record-schema tests.** Reject missing task ID, unknown status, fixture-only evidence claimed as live, missing independent after frame, account/phone/code/token keys and paths outside `diagnostics/YYYY-MM-DD/{TASK_ID}/`.
- [ ] **Step 2: Run the focused record tests and confirm the schema/loader is absent.**
- [ ] **Step 3: Implement strict record loader/writer and path containment.** Keep ignored PNG/log bytes separate from committed metadata; use atomic JSON writes and stable schema version.
- [ ] **Step 4: Re-capture each required task’s Android entry/actionable/completed/danger images from the logged-in current AVD.** Validate every decoded image against the current Android calibration and never copy assets from old macOS or historical environments.
- [ ] **Step 5: Run resource and record tests, then verify device/runtime prerequisites.**

  ```bash
  ./install/.venv/bin/python -m pytest -q tests/test_live_verification_records.py tests/test_android_resources.py tests/test_project_contract.py
  ./install/.venv/bin/python -m tools.android_setup --check
  ./install/.venv/bin/python -m tools.android_device
  ```

- [ ] **Step 6: Commit only the capture tooling, calibration metadata, task records and verification reports.** The explicit `verification/tasks/*.json` paths in the command below follow the canonical order above.

  ```bash
  git add -- tools/capture_android_templates.py assets/resource_android/calibration.json verification/tasks/MAIL_REWARD_DAILY.json verification/tasks/SHOP_FREE_GIFT_DAILY.json verification/tasks/WEEKLY_FREE_GIFT_MONDAY.json verification/tasks/TRIAL_SWORD_DAILY.json verification/tasks/FREE_APPRAISAL_DAILY.json verification/tasks/BUY_TEA_DAILY.json verification/tasks/COLLECTION_DEPLOYMENT_DAILY.json verification/tasks/HERO_DISPATCH_DAILY.json verification/tasks/EAT_STAMINA_FOOD_DAILY.json verification/tasks/SPEND_CONDENSATE_DAILY.json verification/tasks/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json verification/tasks/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json verification/tasks/RING_CHALLENGE_DAILY.json verification/tasks/DUNGEON_SWEEP_DAILY.json verification/tasks/DAILY_TASK_REWARD_CLAIM_DAILY.json verification/tasks/SHADOW_RUINS_DAILY.json verification/tasks/BATTLE_PASS_REWARD_DAILY.json docs/verification/mja-daily-workflows-batch-1.md docs/verification/mja-daily-workflows-batch-2.md docs/verification/mja-daily-workflows-batch-3.md tests/test_live_verification_records.py
  git commit -m "test: record Android daily workflow live admission evidence"
  ```

### Task 11: Run individual Android acceptance and the MFAAvalonia full-batch gate

**Files:**
- Create: `tests/test_android_daily_acceptance.py`
- Create: `docs/verification/mja-daily-aggregate.md`
- Modify: `docs/testing/android-daily-workflows.md`
- Modify: `verification/tasks/{TASK_ID}.json` only when new real evidence is observed.

**Interfaces:**
- `tools/android_daily_run.py --task <name>` runs one selected task.
- `tools/android_daily_run.py --all` runs the MFA-equivalent selected-all aggregate.
- Both commands reuse the same Android health checks, LoginGate, task engine, task-scoped diagnostics and redacted result schema.

- [ ] **Step 1: Record checkout and clean install before live tests.** Run `git rev-parse HEAD`, `git status --short`, `tools/verify_install.py install`, Android setup check and device check; save the values in the human report without staging `AGENTS.md`.
- [ ] **Step 2: Run every individual task once in the current foreground emulator.** Never run two tasks in parallel; verify the independent postcondition and record `completed`, `already_complete`, `not_eligible`, `blocked_safety` or `failed` exactly as observed.
- [ ] **Step 3: Perform safe no-op reruns.** For tasks whose postcondition is already visible, rerun and prove zero side effects plus `already_complete`; for Monday-only tasks test a non-Monday `not_eligible` path with no capture/input if the task engine supports it.
- [ ] **Step 4: Launch the installed MFAAvalonia-compatible interface and visually verify all 17 tasks, `daily_all`, `mail_smoke_test`, controller/resource labels and the select-all/start path.** If the GUI process is unavailable, record the exact missing executable/configuration as an environment blocker rather than claiming GUI live verification.
- [ ] **Step 5: Use the GUI-equivalent selected-all entry to run the aggregate.** Verify task-level failure continuation, device-level stop, per-task status updates, final summary counts and diagnostic links; user intervention is limited to login/SMS/system authorization.
- [ ] **Step 6: Capture after-state and audit every child result.** Confirm no forbidden input action appears in action traces, no sensitive field appears in JSON, and the game/emulator is either at the verified main page or explicitly marked blocked.
- [ ] **Step 7: Commit only the aggregate acceptance report and any newly observed verification metadata.**

  ```bash
  git add -- tests/test_android_daily_acceptance.py docs/verification/mja-daily-aggregate.md docs/testing/android-daily-workflows.md verification/tasks/MAIL_REWARD_DAILY.json verification/tasks/SHOP_FREE_GIFT_DAILY.json verification/tasks/WEEKLY_FREE_GIFT_MONDAY.json verification/tasks/TRIAL_SWORD_DAILY.json verification/tasks/FREE_APPRAISAL_DAILY.json verification/tasks/BUY_TEA_DAILY.json verification/tasks/COLLECTION_DEPLOYMENT_DAILY.json verification/tasks/HERO_DISPATCH_DAILY.json verification/tasks/EAT_STAMINA_FOOD_DAILY.json verification/tasks/SPEND_CONDENSATE_DAILY.json verification/tasks/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json verification/tasks/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json verification/tasks/RING_CHALLENGE_DAILY.json verification/tasks/DUNGEON_SWEEP_DAILY.json verification/tasks/DAILY_TASK_REWARD_CLAIM_DAILY.json verification/tasks/SHADOW_RUINS_DAILY.json verification/tasks/BATTLE_PASS_REWARD_DAILY.json
  git commit -m "test: verify Android daily aggregate and MFA task selection"
  ```

### Task 12: Final repository quality, safety and handoff gate

**Files:**
- Modify: `docs/testing/android-daily-workflows.md`
- Modify: `docs/verification/mja-daily-aggregate.md`
- Modify: existing subplan checkboxes only for completed work.
- Test: all repository tests and install/runtime verification commands.

**Interfaces:**
- Final operator command is `./tools/android_daily_run.py --all` after login/authorization.
- Existing read-only regression remains `./tools/android_run.sh --task mail_smoke_test`.

- [ ] **Step 1: Scan for forbidden remnants.** Search tracked source and resources for `StartApp`, standard blind `Click`, payment/claim vocabulary in forbidden pipelines, hard-coded old serial `emulator-5554`, stale macOS coordinates in Android resources, account/phone/code/token writes and direct modifications to the MaaFramework reference checkout.
- [ ] **Step 2: Run the complete automated gate.**

  ```bash
  ./install/.venv/bin/python -m pytest -q
  ./install/.venv/bin/python -m ruff check .
  git diff --check
  ./install/.venv/bin/python tools/verify_install.py install
  ./install/.venv/bin/python -m tools.android_setup --check
  ./install/.venv/bin/python -m tools.android_device
  ```

- [ ] **Step 3: Verify both smoke paths.** Run `./tools/android_run.sh --task mail_smoke_test` and `./tools/android_daily_run.py --all`; require the smoke task to end in `Tasker.Task.Succeeded`, aggregate results to match per-task records, and no stale log failure marker to affect a later run.
- [ ] **Step 4: Review the working tree and commits.** Confirm only intended project files changed, generated `install/`, `debug/`, `diagnostics/` and `.codebase-memory` artifacts follow ignore rules, and `AGENTS.md` was never staged.
- [ ] **Step 5: Update every completed checkbox in the five dependency plans and this plan.** Leave unavailable live branches explicitly pending with evidence and reason; do not mark them complete because fixtures passed.
- [ ] **Step 6: Commit the final documentation only.**

  ```bash
  git add -- docs/testing/android-daily-workflows.md docs/verification/mja-daily-aggregate.md docs/superpowers/plans/2026-07-28-mja-maa-bbb-full-workflow-migration.md docs/superpowers/plans/2026-07-28-mja-workflow-foundation.md docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-1.md docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-2.md docs/superpowers/plans/2026-07-28-mja-daily-workflows-batch-3.md docs/superpowers/plans/2026-07-28-mja-aggregate-live-verification.md
  git commit -m "docs: complete daily workflow migration handoff"
  ```

## Final Execution Checklist

- [ ] Task 1 canonical models/catalog committed.
- [ ] Task 2 same-frame safety and bounded Android input committed.
- [ ] Task 3 engine, diagnostics and Maa custom action committed.
- [ ] Task 4 shared navigation, fixtures and ProjectInterface renderer committed.
- [ ] Task 5 Batch 1 implementation and live evidence committed.
- [ ] Task 6 Batch 2 implementation and live evidence committed.
- [ ] Task 7 Batch 3 implementation and live evidence committed.
- [ ] Task 8 aggregate task-continuation scheduler committed.
- [ ] Task 9 Maa Agent/MFA/install integration committed.
- [ ] Task 10 individual live verification records admitted.
- [ ] Task 11 MFAAvalonia full-batch acceptance completed.
- [ ] Task 12 final automated, safety and repository gates passed.
