# MJA MFW 全面迁移总 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **2026-08-05 target correction (authoritative):** MFW 的运行目标是本机 macOS 上的 iOS 版本《对决！剑之川》，使用 `MacOS` Controller、`ScreenCaptureKit` 和 `GlobalEvent`。游戏必须由用户预先打开；MacOS Controller 不支持 `StartApp`。本文件中早先遗留的 Android/ADB 表述不再是 MFW 迁移的验收条件，Android 文档仅作历史取证。

**Goal:** 将 MJA 的生产控制面完整迁移到 Maa_bbb 同构的 MFW + ProjectInterface v2 + 独立 Maa Pipeline 架构，并在 macOS/iOS 实机验收后原子退役旧聚合架构。

**Architecture:** MFW 是唯一任务队列控制面，17 个 canonical task 分别由自包含 Maa Pipeline 执行，嵌入式 Agent 只提供安全门禁、资源预算、复杂计算、运行时健康和结构化诊断。迁移在 `assets/interface.mfw.json` 与隔离安装目录中并行建设，最终通过两个连续、可回滚的提交完成入口切换和旧实现删除。

**Tech Stack:** MFW PyQt6 macOS arm64、MaaFramework、ProjectInterface v2、Maa Pipeline JSON、Python 3.12–3.14、pytest、Ruff、GitHub Actions、MaaFramework MacOS Controller

## Global Constraints

- 第一阶段只支持本机 macOS `MacOS` Controller；不声明 Android ADB 作为 MFW 迁移目标。`/Applications/对决！剑之川.app` 由用户预先启动并保持窗口可匹配。
- MFW 是唯一生产 GUI 和任务队列控制面；不保留 MFAAvalonia、`daily_all`、Python aggregate scheduler、外部 supervisor 或兼容双栈入口。
- MFW 每次构建只解析一次最新正式 release，目标资产必须唯一匹配 macOS arm64；失败时直接终止，不回退旧版。
- 构建元数据必须记录 MJA commit、MFW tag、MFW URL、MFW SHA-256、MaaFramework version、MaaFramework URL、MaaFramework SHA-256、解析时间和目标架构。
- ProjectInterface 使用 `interface_version: 2`，根 `task` 数组为空，业务任务来自拆分文件的 `import`。
- 嵌入式 Agent 必须兼容 Python `>=3.12,<3.15`，并只通过 MFW socket 与当前 Tasker/Controller 工作。
- 所有游戏输入只允许调用 `context.tasker.controller`；禁止裸 `adb shell input`、Computer Use、macOS 鼠标和外部 Controller 环境变量分支。
- 不使用 MFW `speedrun`；同日重跑必须依靠当前游戏画面判定 `already_complete` 或 `not_eligible`。
- 正常终态固定为 `success`、`already_complete`、`not_eligible`；受支持业务失败和安全阻止必须显式进入含 `"Abort": true` 的终点。
- 业务 `Abort` 必须让 MFW 标记当前任务失败后继续下一任务；Controller、Resource、Agent、runtime 或设备失联必须保留基础设施失败并停止队列。
- 业务任务不在 MFW 队列层重跑；识别、导航和已证明幂等动作只允许 Maa Pipeline 内的有限重试。
- 登录、密码、验证码、实名、安全验证、充值、支付、未知价格和未知弹窗不得自动处理。
- “日常-完整版”顺序固定为启动任务后依次执行 17 个 canonical task；每个业务 task 恰好出现一次。
- “日常-简化版”固定为启动、邮件、商城免费礼包、免费鉴宝、试剑、侠客派遣、采集、周一礼包、日常奖励、战令奖励。
- 旧生产入口在并行迁移期间冻结；通过全量自动化和 Android 实机门禁前不得提升 `interface.mfw.json`、不得删除旧入口。
- 现有未跟踪 `uv.lock` 不属于本计划，不修改、不暂存、不提交。

---

## 计划集合与依赖

| 顺序 | 计划 | 可独立验收的产物 | 进入下一计划的门禁 |
| --- | --- | --- | --- |
| 1 | [MFW 基座计划](2026-08-05-mja-mfw-foundation.md) | 最新版解析器、隔离安装器、v2 interface、公共资源、窄 Agent、启动恢复、失败传播探针、CI | MFW 能加载 interface/resource/Agent；Abort 继续与基础设施失败停止均有证据 |
| 2 | [任务批次 A](2026-08-05-mja-mfw-dailies-batch-a.md) | 9 个免费/领取/非战斗独立任务 | 每项 fixture、单项实机、同日重跑和 A 批串行通过 |
| 3 | [任务批次 B](2026-08-05-mja-mfw-dailies-batch-b.md) | 4 个普通资源消耗独立任务 | 每项预算门禁、实机副作用、重跑和 A+B 串行通过 |
| 4 | [任务批次 C](2026-08-05-mja-mfw-dailies-batch-c.md) | 4 个战斗/长流程独立任务 | 所有循环有界、后置条件明确，单项/重跑/A+B+C 串行通过 |
| 5 | [生产切换计划](2026-08-05-mja-mfw-cutover.md) | 正式 MFW 入口、发布文档、两个连续切换提交、旧架构退役 | 完整版与手工全选实机通过、依赖归零、候选产物可回滚 |

依赖顺序不可并行越过：

```text
最新版解析和隔离安装
  -> Interface/Resource/embedded Agent 加载
  -> 启动恢复、安全和失败传播契约
  -> 批次 A
  -> 批次 B
  -> 批次 C
  -> 完整版及手工全选验收
  -> 正式入口切换
  -> 旧实现删除
```

## 跨计划固定接口

以下名称在五份子计划中是公共 API，执行时不得自行改名：

```python
from enum import StrEnum


class TaskOutcomeStatus(StrEnum):
    SUCCESS = "success"
    ALREADY_COMPLETE = "already_complete"
    NOT_ELIGIBLE = "not_eligible"
    FAILED = "failed"
```

- `TaskRunStore.begin(task_id: str) -> None`
- `TaskRunStore.increment(task_id: str, action_id: str) -> int`
- `TaskRunStore.finish(task_id: str, status: TaskOutcomeStatus, postcondition: str, error_code: str | None) -> None`
- `parse_action_params(argv: CustomAction.RunArg) -> Mapping[str, Any]`
- `TASK_POLICIES: Mapping[str, TaskPolicy]`

嵌入式 Agent 的 Maa 注册名固定为：

```text
BeginTask
GuardedInput
RecordTaskOutcome
RuntimeHealth
PlanJianlinChallenge
```

公共 Pipeline 节点固定为：

```text
MJA_COMMON_STOP
MJA_COMMON_ABORT
MJA_GAME_START
MJA_GAME_READY
```

业务入口固定为 `MJA_{CANONICAL_ID}_START`。例如：

```text
MJA_MAIL_REWARD_DAILY_START
MJA_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_START
```

## Canonical task 与迁移归属

| 序号 | Canonical ID | 批次 | 任务文件 | Pipeline 文件 |
| ---: | --- | --- | --- | --- |
| 1 | `MAIL_REWARD_DAILY` | A | `assets/tasks/日常/MAIL_REWARD_DAILY.json` | `assets/resource/base/pipeline/daily/mail_reward_daily.json` |
| 2 | `SHOP_FREE_GIFT_DAILY` | A | `assets/tasks/日常/SHOP_FREE_GIFT_DAILY.json` | `assets/resource/base/pipeline/daily/shop_free_gift_daily.json` |
| 3 | `BUY_TEA_DAILY` | B | `assets/tasks/日常/BUY_TEA_DAILY.json` | `assets/resource/base/pipeline/daily/buy_tea_daily.json` |
| 4 | `FREE_APPRAISAL_DAILY` | A | `assets/tasks/日常/FREE_APPRAISAL_DAILY.json` | `assets/resource/base/pipeline/daily/free_appraisal_daily.json` |
| 5 | `TRIAL_SWORD_DAILY` | A | `assets/tasks/日常/TRIAL_SWORD_DAILY.json` | `assets/resource/base/pipeline/daily/trial_sword_daily.json` |
| 6 | `HERO_DISPATCH_DAILY` | A | `assets/tasks/日常/HERO_DISPATCH_DAILY.json` | `assets/resource/base/pipeline/daily/hero_dispatch_daily.json` |
| 7 | `COLLECTION_DEPLOYMENT_DAILY` | A | `assets/tasks/日常/COLLECTION_DEPLOYMENT_DAILY.json` | `assets/resource/base/pipeline/daily/collection_deployment_daily.json` |
| 8 | `WEEKLY_FREE_GIFT_MONDAY` | A | `assets/tasks/日常/WEEKLY_FREE_GIFT_MONDAY.json` | `assets/resource/base/pipeline/daily/weekly_free_gift_monday.json` |
| 9 | `SHADOW_RUINS_DAILY` | C | `assets/tasks/日常/SHADOW_RUINS_DAILY.json` | `assets/resource/base/pipeline/daily/shadow_ruins_daily.json` |
| 10 | `SPEND_CONDENSATE_DAILY` | B | `assets/tasks/日常/SPEND_CONDENSATE_DAILY.json` | `assets/resource/base/pipeline/daily/spend_condensate_daily.json` |
| 11 | `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | C | `assets/tasks/日常/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json` | `assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json` |
| 12 | `EAT_STAMINA_FOOD_DAILY` | B | `assets/tasks/日常/EAT_STAMINA_FOOD_DAILY.json` | `assets/resource/base/pipeline/daily/eat_stamina_food_daily.json` |
| 13 | `DUNGEON_SWEEP_DAILY` | C | `assets/tasks/日常/DUNGEON_SWEEP_DAILY.json` | `assets/resource/base/pipeline/daily/dungeon_sweep_daily.json` |
| 14 | `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | B | `assets/tasks/日常/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json` | `assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json` |
| 15 | `RING_CHALLENGE_DAILY` | C | `assets/tasks/日常/RING_CHALLENGE_DAILY.json` | `assets/resource/base/pipeline/daily/ring_challenge_daily.json` |
| 16 | `DAILY_TASK_REWARD_CLAIM_DAILY` | A | `assets/tasks/日常/DAILY_TASK_REWARD_CLAIM_DAILY.json` | `assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json` |
| 17 | `BATTLE_PASS_REWARD_DAILY` | A | `assets/tasks/日常/BATTLE_PASS_REWARD_DAILY.json` | `assets/resource/base/pipeline/daily/battle_pass_reward_daily.json` |

## 执行与评审协议

### Task 1: 建立执行基线

**Files:**
- Read: `docs/superpowers/specs/2026-08-05-mja-mfw-maa-bbb-architecture-design.md`
- Read: 本总计划和当前要执行的子计划
- Preserve: `uv.lock`

**Interfaces:**
- Consumes: 已批准设计和上述五份子计划。
- Produces: 可审计的干净任务分支状态与执行日志。

- [ ] **Step 1: 确认分支和用户改动**

```bash
git status --short --branch
git log -5 --oneline
```

Expected: 当前分支为执行者选择的工作分支；`uv.lock` 仍为未跟踪用户文件，任何已有改动都先记录归属。

- [ ] **Step 2: 运行旧架构基线测试**

```bash
uv run --no-project --with pytest pytest -q
uv run --no-project --with ruff ruff check .
```

Expected: 记录真实基线；若有既存失败，将命令、测试名和堆栈写入执行日志，不通过改删测试掩盖。

- [ ] **Step 3: 建立阶段验收目录**

```bash
mkdir -p verification/mfw
```

Expected: `verification/mfw/` 只存自动化/实机验收 JSON，不写虚构的 `passed`。

- [ ] **Step 4: 提交基线记录（仅当新增记录文件）**

```bash
git add verification/mfw
git commit -m "test: record MFW migration baseline"
```

Expected: 提交不包含 `uv.lock`，也不修改生产入口。

### Task 2: 按依赖顺序执行五份子计划

**Files:**
- Execute: `docs/superpowers/plans/2026-08-05-mja-mfw-foundation.md`
- Execute: `docs/superpowers/plans/2026-08-05-mja-mfw-dailies-batch-a.md`
- Execute: `docs/superpowers/plans/2026-08-05-mja-mfw-dailies-batch-b.md`
- Execute: `docs/superpowers/plans/2026-08-05-mja-mfw-dailies-batch-c.md`
- Execute: `docs/superpowers/plans/2026-08-05-mja-mfw-cutover.md`

**Interfaces:**
- Consumes: 上一子计划标明的全部自动化与实机门禁证据。
- Produces: 下一子计划可依赖的代码、资源、安装产物和验收记录。

- [ ] **Step 1: 执行基座计划并审查提交**

```bash
git log --oneline -- docs/superpowers/plans/2026-08-05-mja-mfw-foundation.md tools/mfw_install.py assets/interface.mfw.json agent/custom
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_python_contract.py tests/test_mfw_release.py tests/test_mfw_install.py tests/test_mfw_interface.py tests/test_mfw_pipeline_contract.py tests/test_mfw_safety.py tests/test_mfw_diagnostics.py tests/test_mfw_agent.py tests/test_mfw_agent_entry.py tests/test_mfw_startup_pipeline.py tests/test_capture_mfw_fixture.py tests/test_mfw_profile.py tests/test_mfw_failure_contract.py tests/test_mfw_ci_contract.py -q
```

Expected: 全部 PASS，隔离安装产物能被当前构建解析出的 MFW 加载；失败传播证据完整。

- [ ] **Step 2: 执行批次 A 并审查提交**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py tests/test_mfw_presets.py -q
python3 tools/check_mfw_resources.py assets/resource/base
```

Expected: 9 个任务全部 PASS，简化版顺序准确，批次 A 实机记录均为真实已执行结果。

- [ ] **Step 3: 执行批次 B 并审查提交**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py tests/test_mfw_safety.py tests/test_mfw_presets.py -q
python3 tools/check_mfw_resources.py assets/resource/base
```

Expected: 4 个资源消耗任务全部 PASS，资源名、单次与每日上限均受 GuardedInput 约束。

- [ ] **Step 4: 执行批次 C 并审查提交**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py tests/test_mfw_pipeline_contract.py tests/test_mfw_presets.py -q
python3 tools/check_mfw_resources.py assets/resource/base
```

Expected: 4 个长流程任务全部 PASS，所有循环有界、失败出口显式 Abort。

- [ ] **Step 5: 执行切换计划**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest -q
uv run --no-project --with ruff ruff check .
python3 tools/install.py --verify-candidate install/release-final
```

Expected: 正式入口只包含 MFW 架构，完整候选产物可加载，旧架构可由已标记 release 回滚。

### Task 3: 最终完成标准审计

**Files:**
- Verify: `assets/interface.json`
- Verify: `assets/tasks/`
- Verify: `assets/resource/base/`
- Verify: `agent/custom/`
- Verify: `install/candidate/build-metadata.json`
- Verify: `verification/mfw/`

**Interfaces:**
- Consumes: 五份子计划的最终产物与证据。
- Produces: 可以发布或明确拒绝发布的单一结论。

- [ ] **Step 1: 检查唯一控制面和禁用符号**

```bash
rg -n "daily_all|AggregateScheduler|run_selected_workflow|MaaAndroidWorkflowDriver|MJA_CONTROLLER|speedrun|MFAAvalonia" assets agent tools scripts README.md .github
```

Expected: 生产路径零匹配；只允许迁移历史文档或明确的负向契约测试出现这些字符串。

- [ ] **Step 2: 检查任务唯一性与预设顺序**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_interface.py tests/test_mfw_presets.py tests/test_mfw_cutover_contract.py -q
```

Expected: 启动任务第一，17 个 canonical task 各出现一次，手工全选不存在聚合任务。

- [ ] **Step 3: 检查自动化质量门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest -q
uv run --no-project --with ruff ruff check .
git diff --check
```

Expected: 全部成功且无格式错误。

- [ ] **Step 4: 检查实机证据而不是推断结果**

```bash
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-all-tasks --require-full-preset --require-manual-all
```

Expected: 17 个单项、同日重跑、串行、完整版、手工全选、Abort 继续和基础设施停止证据均存在且来自同一候选 build metadata。

- [ ] **Step 5: 发布或拒绝发布**

```bash
git status --short --branch
git log --oneline --decorate -20
```

Expected: 只有所有门禁均通过时发布；任一门禁缺失都保留候选状态，不把“未执行”写成“通过”。
