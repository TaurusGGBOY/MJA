# MJA Native Maa_bbb Control-Plane Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MJA Android 模拟器的生产控制面收敛到 `Maa_bbb` 的 MFW + ProjectInterface + Maa Pipeline + embedded Agent 模式。MFW 负责任务选择和顺序，Pipeline 负责启动、页面状态、有限恢复、业务后置条件和原生终止，Agent 只保留窄的安全、识别、生命周期记录和 Tasker sink 能力；当前轮首个任务级失败后立即由原生 Tasker 停止队列，修复后只运行“首个失败任务 + 首次停止后未执行任务”。

**Architecture:** `interface.json` 通过 `import` 暴露独立任务和 MFW preset；`GAME_START` 是唯一公共启动任务；每个日常任务拥有自己的入口、页面恢复、动作上限、成功/已完成/不适用终点和 `Abort` 失败终点；嵌入式 Agent 通过 `AgentServer` 注册窄 CustomAction、CustomRecognition 和 Tasker sink，不创建调度器、不轮询进程、不替代 MFW 决定下一项任务。任务结果账本是只读的续跑选择依据，不是运行时 watchdog。

**Tech Stack:** MFW 最新正式版（构建时解析一次，macOS arm64）、MaaFramework Pipeline JSON、ProjectInterface v2、Maa ADB Controller、embedded Python 3.12 Agent、Android Studio Emulator、pytest、ruff。

## Implementation status (2026-08-13)

Tasks 1–8 are implemented. The formal `interface.json`, native Tasker sink,
22 independent Pipeline tasks, startup/recovery terminals, selector, and
candidate installer are now on the MFW control plane; the external watchdog
and legacy production queue paths are removed from the supported path.

The MFW-PyQt6 v4.8.23 packaged batch wrapper is patched reproducibly during
candidate construction (`native/mfw-pyqt6`): its task-failure branch now
returns `False`, allowing the native failure event to terminate the outer MFW
queue. Offline gates and the failure/sentinel probe pass.

Task 9 is in progress. The staged r13–r23 rounds identified and repaired the
hero task’s real empty-state, page-entry, OCR, loop-cap, and cleanup defects.
Strict candidate r26 acceptance now passes for `GAME_START +
HERO_DISPATCH_DAILY`; the remaining high-risk tasks still require their own
strict live acceptance before the final all-task coverage gate can be marked
complete. See `docs/verification/2026-08-12-mfw-native-control-plane.md`.

## Global Constraints

- `Maa_bbb` 的实现事实是本计划的控制面基准：`agent/main.py` 只启动并等待 `AgentServer`；`assets/interface.json` 用 `import` 和 `preset` 组织任务；Pipeline 用 `StartApp`、`next`、`[JumpBack]`、`max_hit`、`timeout`、`focus`、`StopTask` 表达有限状态机；Tasker sink 用原生 `post_stop()` 结束任务器。MJA 不复制其游戏资源，只移植这种边界。
- 禁止重新引入 `tools/mfw_runtime_watchdog.py`、外层 MFW PID/ADB 前台包/result.json 轮询调度器，或任何通过杀进程实现“首个失败即停”的 runner。结果读取工具只能做运行前选择和运行后验收。
- 首个 `failed`、`blocked_safety`、结果缺失/过期、`running` 未收尾或 native failure 的业务任务，必须先持久化失败证据，再在 Pipeline/Tasker 原生边界停止当前队列。若候选 MFW 的原生语义只能停止当前任务而不能阻止后续队列项，执行必须停在契约修复阶段，不能退回 watchdog。
- 修复后的下一轮只包含本轮首个失败任务和该失败之后未执行且没有 fresh 允许终态的任务，按 `interface.json` 原始顺序一次性运行；不得修一个任务就单独复跑，也不得为了收集更多失败继续消耗后续任务。
- `Tasker.Task.Succeeded`、MFW 绿色 UI、点击记录、旧截图和旧 result.json 都不能单独证明业务成功。成功必须同时有本轮新鲜 `result.json`、任务特定业务后置条件和 native terminal 证据。
- 结果状态约定：`success` 为业务动作完成；`already_complete` 和 `not_eligible` 是任务自身可识别的正常终态；任何缺失业务后置条件的路径都是 `failed`，不能用 `completed` 或 `Tasker.Task.Succeeded` 掩盖。
- 武学突破只领取已经成功突破的结果，不点击加号/槽位；没有成功突破可领取时直接记为成功。装备筛选的 OCR 必须匹配完整字符串 `级及以下`，不能放宽为只匹配 `级` 或其他模糊文本。帮会事务必须验证全部可见行都已点击“开始事务”或明确处于无动作状态。
- Android 模拟器始终使用 `-gpu host`，AVD 保持 `hw.gpu.enabled=yes`、`hw.gpu.mode=host`；任何启动脚本或构建改动后都要检查实际 QEMU 命令行，禁止 `auto`、`software`、SwiftShader 或覆盖 GPU 的环境变量。
- 所有游戏输入只能由 MFW/MaaFramework ADB Controller 发出；禁止裸 `adb shell input`、Computer Use 点击游戏和 macOS 原生《对决！剑之川》App。禁止项目代码启动或控制 `Terminal.app`。
- 真实 MFW、ADB、截图和模拟器操作使用当前执行环境及项目既有命令；同一时间只能有一个真实 MFW runner。每个正式 MFW 业务任务使用独立 worktree 的实现代理，真实模拟器只在当前环境操作。
- 工作区当前存在用户已有改动；执行阶段必须只修改本计划列出的文件，先检查重叠 diff，绝不使用 `git reset --hard` 或覆盖无关改动。
- 旧聚合器和旧 Android supervisor 在新控制面完全验收前只冻结、不删除；删除前必须用代码图谱入站依赖和字符串搜索双重确认，不能通过跳过旧测试制造绿色结果。

---

## Reference Findings and Migration Boundary

当前 MJA 的关键差距已经由代码证据固定：

- `assets/interface.json` 已切换为正式的 MFW `import`/`preset` 控制面；旧的 `assets/interface.mfw.json` 已从生产工作区移除，避免双接口漂移。
- `agent/workflows/aggregate.AggregateScheduler` 和 `tools/android_daily_run.run_isolated_dailies` 已与 MFW 生产入口断开；它们保留的旧实现不能重新成为任务调度器。
- `agent/custom/action/task_lifecycle.py` 与 `agent/custom/sink/task_flow.py` 现在分别负责写任务结果和在原生通知边界停止 Tasker，形成 Maa_bbb 风格的窄 AgentServer sink。
- 部分 Pipeline 已有 `MJA_COMMON_ABORT`，但仍需审计每个 `on_error` 和业务失败节点是否都先记录失败、带 `Abort`、不会落到普通 `StopTask` 成功分支。`GUILD_AFFAIRS_DAILY` 当前失败节点尤其需要补齐原生失败参数和完整“全部行已开始/无动作”后置条件。
- `tools/android_run.AndroidRun._wait_for_child_with_watchdog` 是现有旧 Android runner 的进程等待逻辑；它不能继续作为 MFW 生产控制面。迁移阶段要将 MFW 生产路径与该逻辑断开，并删除其基于日志/进程决定任务调度的职责。

本计划覆盖当前 `assets/tasks/日常/` 中的 22 个 canonical 任务，而不是沿用旧文档中已经过时的 17 项列表。`docs/superpowers/specs/2026-08-05-mja-mfw-maa-bbb-architecture-design.md` 中“业务失败后继续下一任务”的旧语义由本计划的最新用户要求覆盖，并在切换阶段同步改文档和测试。

## File Map

### Create

- `agent/custom/sink/__init__.py`
- `agent/custom/sink/task_flow.py`
- `tools/mfw_task_selection.py`
- `tests/test_mfw_first_failure_stops_batch.py`
- `tests/test_mfw_task_selection.py`
- `tests/test_mfw_tasker_sink.py`
- `tests/test_mfw_cutover_contract.py`
- `tests/mfw/tasks/test_batch_a_native_pipelines.py`
- `tests/mfw/tasks/test_batch_b_native_pipelines.py`
- `tests/mfw/tasks/test_batch_c_native_pipelines.py`

### Modify

- `assets/interface.json`
- `assets/tasks/游戏启动.json`
- `assets/tasks/日常/*.json`
- `assets/resource/base/pipeline/common/terminal.json`
- `assets/resource/base/pipeline/common/home_recovery.json`
- `assets/resource/base/pipeline/common/known_popups.json`
- `assets/resource/base/pipeline/startup/game_start.json`
- `assets/resource/base/pipeline/daily/*.json`
- `agent/main.py`
- `agent/custom/action/task_lifecycle.py`
- `agent/sinks/restore_window.py` or its migrated `agent/custom/sink` replacement
- `tools/mfw_live_acceptance.py`
- `tests/test_mfw_failure_contract.py`
- `tests/test_mfw_live_acceptance.py`
- `tests/test_mfw_presets.py`
- `tests/test_mfw_startup_pipeline.py`
- `tests/mfw/task_contract.py`
- `tests/mfw/pipeline_assertions.py`
- `/Users/gaoguobin/.codex/skills/mfw-batch-repair-jianzhichuan/SKILL.md`
- `docs/2026-08-03-maa-bbb-alignment-plan.md`
- `docs/superpowers/specs/2026-08-05-mja-mfw-maa-bbb-architecture-design.md`
- `docs/verification/maa-bbb-native-control-plane.md`

### Retire only after the cutover gate

- `agent/actions/daily_workflow.py`
- `agent/workflows/aggregate.py`
- `agent/workflows/aggregate_report.py`
- `agent/workflows/engine.py`
- `agent/workflows/maa_android.py`
- `agent/workflows/navigation.py`
- `agent/workflows/definitions/*.py`
- `tools/android_daily_run.py`
- the MFW production path in `tools/android_run.py`, including `_wait_for_child_with_watchdog` and log-driven task terminal dispatch
- tests that only protect the retired production scheduler, after the dependency audit proves they have no remaining supported caller

## Implementation Tasks

### Task 1: Freeze the native failure, freshness, and resume contracts

**Files:** create `tests/test_mfw_first_failure_stops_batch.py`, `tests/test_mfw_task_selection.py`; modify `tests/test_mfw_failure_contract.py`, `tests/test_mfw_live_acceptance.py`, `tests/mfw/task_contract.py`, `tests/mfw/pipeline_assertions.py`.

**Interfaces:**

- The native batch probe consumes an ordered task list and produces the native start/failed/succeeded event sequence plus task result artifacts.
- The read-only selector consumes candidate declarations, operation date, optional explicit scope, and fresh task result evidence; it produces `scope_mode`, `eligible_tasks`, `precompleted_tasks`, `pending_tasks`, `failed_task`, `unrun_after_first_failure`, `selected_tasks`, and evidence paths.
- A task acceptance record must contain `task_id`, `run_id`, `status`, `postcondition`, `error_code`, native terminal, and evidence directory. A native success event without the matching business result is rejected.

**Steps:**

- [ ] Write a failing fixture test with `GAME_START`, one passing business task, one failing business task, and one sentinel task; assert the sentinel never starts after the first native failure.
- [ ] Write failing selector tests for fresh `success`, `already_complete`, `not_eligible`, `failed`, `blocked_safety`, `running`, missing, stale, and native-terminal-missing results; assert only fresh allowed `success` enters `precompleted_tasks`.
- [ ] Write failing tests for a first failure in the middle of an ordered batch; assert the next selection is exactly the failed task plus all later unrun tasks, with earlier fresh successes excluded.
- [ ] Run `install/.venv/bin/python -m pytest -q tests/test_mfw_first_failure_stops_batch.py tests/test_mfw_task_selection.py tests/test_mfw_failure_contract.py tests/test_mfw_live_acceptance.py` and record the expected failures before implementation.
- [ ] Add shared contract helpers in `tests/mfw/task_contract.py` and pipeline assertions in `tests/mfw/pipeline_assertions.py`; keep the helper pure and free of ADB, process, or MFW launch calls.
- [ ] Re-run the focused tests and commit the contract-only changes as the migration baseline.

### Task 2: Implement native Tasker first-failure termination and truthful lifecycle recording

**Files:** create `agent/custom/sink/__init__.py`, `agent/custom/sink/task_flow.py`, `tests/test_mfw_tasker_sink.py`; modify `agent/main.py`, `agent/custom/action/task_lifecycle.py`, `agent/sinks/restore_window.py`, `tests/test_restore_window_sink.py`, `tests/test_agent_main.py`, `assets/resource/base/pipeline/common/terminal.json`.

**Interfaces:**

- `TaskFlowStopSink.on_raw_notification(tasker, noti_type, detail)` consumes native Tasker notifications and calls the current Tasker’s native stop API at most once for the first business failure in a session. It never starts a process, polls a PID, reads `result.json`, or sends game input.
- `RecordTaskOutcome` and `RecordActiveTaskFailure` persist the business terminal before returning the native-failure signal. The persisted status and postcondition remain authoritative even when the native action intentionally returns failure.
- Normal completion uses a separate `MJA_COMMON_STOP` path; failure uses one canonical `MJA_COMMON_ABORT` path. No failure node may fall through to a normal success terminal.

**Steps:**

- [ ] Write failing fake-Tasker tests proving one failed task causes exactly one native stop request, later notifications do not duplicate it, and a successful task does not stop the queue.
- [ ] Write a failing lifecycle test proving the failed `result.json` is durable before the native stop notification is handled; include a failure after a nested startup/recovery action.
- [ ] Run the focused sink, lifecycle, and agent-entry tests and confirm the current agent has no registered native stop sink.
- [ ] Add the Maa_bbb-style `AgentServer.tasker_sink()` implementation under `agent/custom/sink`, register it from `agent/main.py`, and keep `main()` limited to socket validation, `start_up`, `join`, and `shut_down`.
- [ ] Tighten the lifecycle actions so malformed payloads, multiple active tasks, or missing postconditions fail closed and never create a success-looking terminal.
- [ ] Migrate failure evidence capture from the legacy restore-window boundary into the registered sink/action path; preserve failure screenshots and diagnostic events without performing cross-task recovery.
- [ ] Normalize `terminal.json` so every failure route records a result, marks the native failure/abort boundary, and ends through `MJA_COMMON_ABORT`; retain `MJA_COMMON_STOP` only for a verified normal terminal.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/test_mfw_tasker_sink.py tests/test_restore_window_sink.py tests/test_agent_main.py tests/test_mfw_failure_contract.py` and commit the native termination boundary.

### Task 3: Add a read-only current-state selector for failed and incomplete tasks

**Files:** create `tools/mfw_task_selection.py`, `tests/test_mfw_task_selection.py`; modify `tools/mfw_live_acceptance.py`, `tests/test_mfw_live_acceptance.py`, `/Users/gaoguobin/.codex/skills/mfw-batch-repair-jianzhichuan/SKILL.md`.

**Interfaces:**

- `tools/mfw_task_selection.py` is a pure read-only command. It accepts `--candidate`, `--date`, optional repeated `--task`, and a result root; it emits the selection object from Task 1 as JSON and exits non-zero for malformed candidate/task evidence.
- `mfw_live_acceptance.py begin` consumes an explicit selected set by exclusions and records the exact `expected_tasks`; `finish` only verifies fresh native/business evidence and never launches, waits for, or stops MFW.
- The skill’s default no-task mode calls the selector, uses `GAME_START + pending_tasks`, and never includes `precompleted_tasks`; explicit user task names remain the hard authorization boundary.

**Steps:**

- [ ] Write failing tests for full-mode selection in the project’s `interface.json` order, Monday-only eligibility, explicit scope, empty pending set, and the first-failure continuation set.
- [ ] Write failing tests proving the selector does not treat `already_complete`, `not_eligible`, `completed`, stale results, or native success without a task-specific postcondition as completed evidence.
- [ ] Run the selector and acceptance tests; verify no process, ADB, screenshot, or MFW invocation is reachable from the selector module.
- [ ] Implement the selector against fresh result evidence and the declared 22-task import order; make its output the only input used to construct a repair batch.
- [ ] Extend the acceptance ticket with the selection snapshot, first-failure task, unrun list, and evidence paths while preserving the existing fresh-result protections.
- [ ] Update the MFW skill to describe native stop as the only first-failure boundary and the selector as read-only; remove any wording that could start an outer watchdog or one-task repair loop.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/test_mfw_task_selection.py tests/test_mfw_live_acceptance.py tests/test_mfw_failure_contract.py` and commit the resume-selection contract.

### Task 4: Align startup, recovery, and common terminals with the Maa_bbb pipeline model

**Files:** modify `assets/tasks/游戏启动.json`, `assets/resource/base/pipeline/startup/game_start.json`, `assets/resource/base/pipeline/common/home_recovery.json`, `assets/resource/base/pipeline/common/known_popups.json`, `assets/resource/base/pipeline/common/terminal.json`, `tests/test_mfw_startup_pipeline.py`, `tests/test_mfw_pipeline_contract.py`, `tests/test_android_resources.py`.

**Interfaces:**

- `GAME_START` consumes the selected Android ADB Controller and current game surface; it produces exactly one recognized `MJA_GAME_READY` home terminal or a recorded native startup failure.
- `[JumpBack]MJA_GAME_START` is the only common startup recovery entry available to business Pipelines. It may handle only known, bounded pages and safe dismissals.
- `MJA_COMMON_STOP` is a normal task terminal; `MJA_COMMON_ABORT` is a native failure terminal; `MJA_COMMON_STARTUP_RECOVERY_EXHAUSTED` records `GAME_START` failure before aborting.

**Steps:**

- [ ] Write failing resource tests that require a `StartApp`/known-launch path, a fresh home recognition, bounded startup recovery, and explicit failure on unknown/login/verification/update states.
- [ ] Write failing graph tests that every startup `next`/`on_error` path reaches a known node, has finite `timeout`/`max_hit`, and cannot loop indefinitely without a terminal.
- [ ] Run JSON/resource tests and inspect the failure paths before changing the startup resource.
- [ ] Refactor `game_start.json` into the Maa_bbb-style bounded start state machine: app start, title/loading, known safe popups, home recognition, and one explicit recovery-exhausted failure boundary.
- [ ] Keep runtime health and screenshot diagnostics as narrow Agent actions; remove business task selection, aggregate scheduling, and cross-task page knowledge from startup/recovery resources.
- [ ] Add a disposable native probe preset that proves a failed `GAME_START` stops the queue before any business sentinel; do not add the probe to production imports or presets.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/test_mfw_startup_pipeline.py tests/test_mfw_pipeline_contract.py tests/test_android_resources.py` and validate the candidate resource bundle loads in MFW.

### Task 5: Migrate claim, collection, and guild task Pipelines (Batch A)

**Files:** modify the following task declarations and Pipeline files, plus `tests/mfw/tasks/test_batch_a_native_pipelines.py` and the existing task-specific tests:

- `MAIL_REWARD_DAILY`: `assets/tasks/日常/MAIL_REWARD_DAILY.json`, `assets/resource/base/pipeline/daily/mail_reward_daily.json`
- `SHOP_FREE_GIFT_DAILY`: `assets/tasks/日常/SHOP_FREE_GIFT_DAILY.json`, `assets/resource/base/pipeline/daily/shop_free_gift_daily.json`
- `FREE_APPRAISAL_DAILY`: `assets/tasks/日常/FREE_APPRAISAL_DAILY.json`, `assets/resource/base/pipeline/daily/free_appraisal_daily.json`
- `TRIAL_SWORD_DAILY`: `assets/tasks/日常/TRIAL_SWORD_DAILY.json`, `assets/resource/base/pipeline/daily/trial_sword_daily.json`
- `HERO_DISPATCH_DAILY`: `assets/tasks/日常/HERO_DISPATCH_DAILY.json`, `assets/resource/base/pipeline/daily/hero_dispatch_daily.json`
- `COLLECTION_DEPLOYMENT_DAILY`: `assets/tasks/日常/COLLECTION_DEPLOYMENT_DAILY.json`, `assets/resource/base/pipeline/daily/collection_deployment_daily.json`
- `WEEKLY_FREE_GIFT_MONDAY`: `assets/tasks/日常/WEEKLY_FREE_GIFT_MONDAY.json`, `assets/resource/base/pipeline/daily/weekly_free_gift_monday.json`
- `GUILD_AFFAIRS_DAILY`: `assets/tasks/日常/GUILD_AFFAIRS_DAILY.json`, `assets/resource/base/pipeline/daily/guild_affairs_daily.json`
- `GUILD_DONATION_DAILY`: `assets/tasks/日常/GUILD_DONATION_DAILY.json`, `assets/resource/base/pipeline/daily/guild_donation_daily.json`
- `DAILY_TASK_REWARD_CLAIM_DAILY`: `assets/tasks/日常/DAILY_TASK_REWARD_CLAIM_DAILY.json`, `assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json`
- `BATTLE_PASS_REWARD_DAILY`: `assets/tasks/日常/BATTLE_PASS_REWARD_DAILY.json`, `assets/resource/base/pipeline/daily/battle_pass_reward_daily.json`

**Interfaces:** Each Pipeline consumes home, its own business page, or a supported known offset page and produces one task-local normal terminal or one native abort terminal. Claim tasks must distinguish empty/already claimed from an unverified action.

**Steps:**

- [ ] Write failing batch-A contract tests enumerating all 11 task IDs and asserting each has an independent entry, a home/page start layer, a bounded action loop, a business postcondition, a normal terminal, and an abort terminal.
- [ ] Write failing fixture tests for empty mail, already claimed free rewards, Monday-ineligible weekly reward, successful trial claim, collection harvested, and safe no-action states.
- [ ] Write failing guild-affairs tests requiring every visible row to be either started or explicitly no-action; a remaining “开始事务” button must produce failure, not success.
- [ ] Run the batch-A tests and resource loader before touching the Pipelines.
- [ ] Refactor each task to keep its own page entry, known popup handling, bounded `max_hit`/`timeout`, postcondition recognition, close/recovery path, and native abort on any unverified side effect.
- [ ] Fix `GUILD_AFFAIRS_DAILY` failure nodes to persist `native_fail_after_record`, mark `Abort`, and use the exact all-rows postcondition; do not let paid/ambiguous rows fall into a normal stop.
- [ ] Keep mail “无可领取/空邮件” as a verified normal outcome, and require the current round’s claim/empty evidence rather than a previous result.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/mfw/tasks/test_batch_a_native_pipelines.py tests/mfw/tasks/test_free_appraisal_shop_recovery.py tests/mfw/tasks/test_trial_sword_r22_postcondition.py tests/mfw/tasks/test_guild_affairs.py tests/test_mfw_presets.py` and load the batch-A resource bundle in MFW.
- [ ] Commit Batch A only after static contract and resource-load gates pass; do not start Batch B real-device work from a failing candidate.

### Task 6: Migrate resource-sensitive Pipelines and encode the confirmed martial/equipment rules (Batch B)

**Files:** modify the following task declarations and Pipeline files, plus `tests/mfw/tasks/test_batch_b_native_pipelines.py`, `tests/mfw/tasks/test_equipment_decompose.py`, and the martial workflow tests:

- `BUY_TEA_DAILY`: `assets/tasks/日常/BUY_TEA_DAILY.json`, `assets/resource/base/pipeline/daily/buy_tea_daily.json`
- `SPEND_CONDENSATE_DAILY`: `assets/tasks/日常/SPEND_CONDENSATE_DAILY.json`, `assets/resource/base/pipeline/daily/spend_condensate_daily.json`
- `MARTIAL_STUDY_BREAKTHROUGH_DAILY`: `assets/tasks/日常/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json`, `assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json`
- `EAT_STAMINA_FOOD_DAILY`: `assets/tasks/日常/EAT_STAMINA_FOOD_DAILY.json`, `assets/resource/base/pipeline/daily/eat_stamina_food_daily.json`
- `EQUIPMENT_DECOMPOSE_DAILY`: `assets/tasks/日常/EQUIPMENT_DECOMPOSE_DAILY.json`, `assets/resource/base/pipeline/daily/equipment_decompose_daily.json`
- `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`: `assets/tasks/日常/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json`, `assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`
- Any narrow Agent policy/resource helpers used by these Pipelines, without importing the old workflow engine or driver.

**Interfaces:** Resource actions consume current-frame page, target, item identity, and remaining budget; they produce bounded action counts and an explicit postcondition. Martial produces `martial.successful_breakthroughs_claimed_or_none` (or its separately verified no-success/claimed equivalent) without entering plus-slot selection. Equipment produces a filter-applied evidence record only after exact `级及以下` recognition.

**Steps:**

- [ ] Write failing tests proving all six task IDs have resource caps, current-frame authorization, no infinite retry, and native failure paths.
- [ ] Write failing martial tests for three cases: successful result cards are claimed; multiple successful cards are claimed within the configured cap; no successful card is present and the task succeeds without clicking `plus_slot`.
- [ ] Write failing equipment OCR tests that accept `级及以下` and reject `级`, `级以上`, partial OCR, and unrelated level text; retain the quality filter contract separately.
- [ ] Write failing resource-policy tests for tea, condensate, food, and Jianlin that reject missing identity, ambiguous target, insufficient budget, or postcondition absence without sending a second side-effect action.
- [ ] Run the focused Batch-B tests and resource loader; confirm failures are contract failures rather than emulator actions.
- [ ] Refactor the six Pipelines around local entry/page/exit nodes, bounded actions, and task-owned result postconditions; remove any branch that treats navigation completion as business completion.
- [ ] Update the acceptance success-signal table for the martial claimed-or-none result and the exact equipment decomposition result; do not broaden success to native task termination.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/mfw/tasks/test_batch_b_native_pipelines.py tests/mfw/tasks/test_equipment_decompose.py tests/mfw/tasks/test_spend_condensate_shadow_failure.py tests/test_mfw_evidence.py` and load the Batch-B resource bundle in MFW.
- [ ] Commit Batch B only after all six tasks pass the offline contract and resource-load gates.

### Task 7: Migrate battle and long-loop Pipelines with explicit failure convergence (Batch C)

**Files:** modify the following task declarations and Pipeline files, plus `tests/mfw/tasks/test_batch_c_native_pipelines.py` and the existing battle/task contract tests:

- `SHADOW_RUINS_DAILY`: `assets/tasks/日常/SHADOW_RUINS_DAILY.json`, `assets/resource/base/pipeline/daily/shadow_ruins_daily.json`
- `DUNGEON_SWEEP_DAILY`: `assets/tasks/日常/DUNGEON_SWEEP_DAILY.json`, `assets/resource/base/pipeline/daily/dungeon_sweep_daily.json`
- `RING_CHALLENGE_DAILY`: `assets/tasks/日常/RING_CHALLENGE_DAILY.json`, `assets/resource/base/pipeline/daily/ring_challenge_daily.json`
- `GUILD_ACTIVITY_CHALLENGE_DAILY`: `assets/tasks/日常/GUILD_ACTIVITY_CHALLENGE_DAILY.json`, `assets/resource/base/pipeline/daily/guild_activity_challenge_daily.json`
- `BREAK_ARRAY_MARTIAL_DAILY`: `assets/tasks/日常/BREAK_ARRAY_MARTIAL_DAILY.json`, `assets/resource/base/pipeline/daily/break_array_martial_daily.json`

**Interfaces:** Each long task consumes a recognized page and bounded battle/action state; it produces an explicit completion postcondition, a verified not-eligible outcome where applicable, or a native abort carrying the last known state and error code. No task may use an unbounded battle loop or infer completion from a click trace.

**Steps:**

- [ ] Write failing tests for every Batch-C task covering home entry, task-page entry, known result popup, finite loop exhaustion, unknown result, resource/attempt exhaustion, normal terminal, and native abort terminal.
- [ ] Write a sentinel integration fixture proving a shadow/dungeon/ring failure stops the native batch before the next sentinel task starts.
- [ ] Run Batch-C tests and static pipeline convergence checks; classify any existing failure using `systematic-debugging` evidence before editing resources.
- [ ] Refactor shadow formation/battle to require both input completion and the next-page/result postcondition; stop after the bounded retry cap when the recommended formation page does not change.
- [ ] Refactor dungeon sweep to require the current sweep control and a current reward/ticket postcondition; OCR absence alone must not be treated as not eligible.
- [ ] Refactor ring and guild-activity loops to distinguish attempts exhausted, battle result known, and unknown result; unknown result always records failure and aborts.
- [ ] Refactor break-array martial flow to keep any custom action narrow, with its own timeout, action cap, and postcondition; no central workflow engine call is allowed.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/mfw/tasks/test_batch_c_native_pipelines.py tests/mfw/tasks/test_hero_dispatch_r22_all_waiting.py tests/mfw/tasks/test_trial_sword_r22_postcondition.py tests/test_mfw_pipeline_contract.py` and load the Batch-C resource bundle in MFW.
- [ ] Commit Batch C only after all five task contracts and the native first-failure sentinel pass offline.

### Task 8: Switch the formal interface to MFW and retire the old production scheduler

**Files:** modify `assets/interface.json`, `agent/main.py`, `tools/mfw_live_acceptance.py`, `tests/test_mfw_interface.py`, `tests/test_mfw_presets.py`, `tests/test_mfw_cutover_contract.py`; retire the files listed in the cutover file map only after dependency checks; update `docs/2026-08-03-maa-bbb-alignment-plan.md` and `docs/superpowers/specs/2026-08-05-mja-mfw-maa-bbb-architecture-design.md`.

**Interfaces:** The final `interface.json` exposes only the ProjectInterface v2 controller/resource/embedded-agent declarations, imported independent tasks, and MFW presets. It contains no `daily_all`, no hidden aggregate task, no duplicate task declaration, and one `GAME_START` at the head of each preset. The old Python aggregate path has no production inbound callers after cutover.

**Steps:**

- [ ] Write failing cutover tests that detect `daily_all`, old `MJA_Daily_*` entries, imports of `AggregateDailyWorkflowAction`/`AggregateScheduler` from production MFW modules, and references to `mfw_runtime_watchdog.py`.
- [ ] Write failing dependency-audit checks using codebase graph inbound callers plus `rg` over JSON, shell, CI, and documentation; include the legacy Android runner and result-marker paths.
- [ ] Run the cutover tests and audit against the current dirty worktree; do not delete code while old production callers remain.
- [x] Promote the fully tested MFW interface content to formal `assets/interface.json`, preserve the 22-task import order, and expose only MFW-native presets.
- [ ] Remove the production import and registration of `DailyWorkflowAction`, `AggregateDailyWorkflowAction`, `AggregateScheduler`, and central `MaaAndroidWorkflowDriver`; keep only narrow custom actions/recognizers/sinks required by Pipeline resources.
- [ ] Remove `tools/android_daily_run.py` from the production command path and remove `_wait_for_child_with_watchdog`, log-driven task dispatch, and external terminal inference from `tools/android_run.py`; a retained standalone diagnostic command may only use a bounded child wait and may not schedule MFW tasks.
- [ ] After the graph and string audits show zero supported inbound callers, delete the retired workflow engine, definitions, aggregate report, and scheduler-only tests; update their replacement tests to protect the native Pipeline contracts.
- [ ] Re-run `install/.venv/bin/python -m pytest -q tests/test_mfw_interface.py tests/test_mfw_presets.py tests/test_mfw_cutover_contract.py tests/test_mfw_agent.py tests/test_mfw_agent_entry.py tests/test_mfw_python_contract.py` and run `git diff --check`.
- [ ] Build one isolated MFW candidate, record its MFW metadata and resource hashes, and verify the final bundle uses relative paths only.

### Task 9: Run staged Android/MFW acceptance and publish the new runbook

**Files:** modify `/Users/gaoguobin/.codex/skills/mfw-batch-repair-jianzhichuan/SKILL.md`, `tools/mfw_live_acceptance.py`, `tests/test_mfw_live_acceptance.py`, and `docs/verification/2026-08-12-mfw-native-control-plane.md`.

**Interfaces:** A real acceptance round consumes one immutable candidate, one MFW config, one selected ordered task set, and one acceptance ticket. It produces native logs, fresh screenshots, task result evidence, a first-failure boundary when applicable, and a final cross-round coverage report. No external process monitors the round.

**Steps:**

- [x] Write failing acceptance tests for the exact `GAME_START + selected_tasks` order, first-failure partial-stop semantics, fresh result selection, task-specific success signals, and expected non-zero `finish` for a deliberately stopped partial round.
- [x] Run the offline gates before Android: focused/full pytest gates, resource validation, and `git diff --check`.
- [x] Verify the actual emulator command contains `-gpu host`, the AVD configuration contains both host GPU keys, phantom-process monitoring is disabled as required, and no second MFW runner exists.
- [x] Run an isolated native probe proving first failure prevents the sentinel task from starting; when earlier probe iterations exposed a defect, use systematic-debugging before modifying business resources.
- [ ] Run single-task MFW acceptance for the eight previously incomplete/high-risk tasks—`RING_CHALLENGE_DAILY`, `DUNGEON_SWEEP_DAILY`, `MARTIAL_STUDY_BREAKTHROUGH_DAILY`, `SHADOW_RUINS_DAILY`, `COLLECTION_DEPLOYMENT_DAILY`, `TRIAL_SWORD_DAILY`, `MAIL_REWARD_DAILY`, and `GUILD_AFFAIRS_DAILY`—using only `GAME_START + specified task`, fresh screenshots, task result, and native terminal evidence.
- [x] Run the default full-mode selector and freeze the first failure/unrun set at the native Tasker boundary; do not wait for later tasks.
- [x] Apply evidence-backed repair batches r14–r23, rebuild immutable candidates, and run the strict failed-task continuation in r26. The remaining date-eligible tasks are intentionally not marked covered yet.
- [ ] Confirm martial evidence shows successful breakthrough claims or a verified absence of successful claims without plus-slot input; confirm equipment evidence contains exact `级及以下`; confirm guild affairs evidence shows every visible row started or no-action.
- [x] Update the skill/runbook to report `precompleted_tasks`, `pending_tasks`, `failed_task`, `unrun_after_first_failure`, each repair batch, native stop reason, and evidence paths; never report unrun tasks as failed task implementations or as success.
- [ ] Record final acceptance only when every date-eligible task has a fresh allowed business terminal, no task remains `running`, the native logs contain no unhandled failure, and all final screenshots/evidence belong to the current candidate and run IDs.

## Validation and Release Gates

The implementation is complete only when all gates below are satisfied:

- Automated: full pytest, ruff, JSON/resource reference validation, embedded Agent import under Python 3.12, MFW candidate loading, `git diff --check`, and the first-failure sentinel contract.
- Native semantics: a deliberate business failure records its result and prevents the next MFW queue task from starting; a normal `success`/`already_complete`/`not_eligible` terminal allows the queue to continue; Controller/Resource/Agent load failure remains a shared infrastructure stop.
- Task coverage: all 22 imported daily task IDs have independent declarations, independent Pipeline entries, task-specific postconditions, bounded recovery, normal terminal, and native abort terminal. No `daily_all` or hidden aggregate route remains.
- Real device: startup reaches a fresh home recognition, each task’s side-effect action is current-frame authorized, final page is known, and no task is accepted from a green UI or native success event alone.
- Resume: after a first failure, the next batch contains exactly the failed task plus unrun later tasks; already fresh-successful tasks are not rerun; no pair-by-pair repair loop exists.
- Runtime: MFW is the only production queue, no external watchdog exists, actual QEMU uses host GPU, and no Terminal.app or forbidden input path is used.
- Documentation: the old “business failure continues later tasks” language is removed or explicitly marked obsolete; the skill and verification record describe the native stop/resume contract and distinguish `unrun_after_first_failure` from task failure.

## Self-Review

- **Spec coverage:** Maa_bbb control-plane findings, first-failure stop, repair-plus-unrun resume, watchdog prohibition, exact equipment OCR, martial no-plus semantics, guild all-row requirement, Android host GPU, MFW-only input, and fresh business evidence are each represented in global constraints, implementation tasks, and release gates.
- **No placeholders:** Every task names concrete files, interfaces, tests, commands, and completion evidence. The only conditional deletion is guarded by a concrete zero-inbound-dependency audit and is not a placeholder for implementation.
- **Type/data consistency:** Task IDs use the current 22-entry `assets/interface.json` order; selector fields, result fields, native terminals, and acceptance ticket fields are named consistently across the plan.
- **Implementation boundary:** The plan has now been executed through the native control-plane cutover and the r26 strict hero acceptance. The existing dirty worktree remains preserved; unrelated user changes were not reset or overwritten.
- **Known semantic risk:** The native sentinel and r26 strict run demonstrate the required stop/continue boundary. Final release still depends on fresh task-specific acceptance for the remaining date-eligible tasks; that gap is recorded as incomplete coverage, not treated as success.
