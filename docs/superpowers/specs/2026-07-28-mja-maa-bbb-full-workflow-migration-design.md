# MJA Maa_bbb 风格全量 Workflow 迁移设计

## 状态

已获得用户确认，本文档用于指导后续 implementation plan。当前阶段只定义设计，不开始代码实现。

## 背景与目标

MJA 需要将 `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py` 中的全部 17 个《对决！剑之川》日常 workflow 迁移到 MaaFramework/MFAAvalonia 可选任务体系，并参考 Maa_bbb 的任务组织、Agent 自定义动作注册和模拟器运行方式。

运行目标是 Android 模拟器。用户在 MFAAvalonia 中全选任务并点击开始后，MJA 按日期和依赖顺序自动执行全部适用任务；用户只在游戏登录、短信验证码和系统授权时介入。

当前已经完成的 Android runtime hardening、TapTap APK、中文 AVD、MaaPiCli plain-ADB 修复和邮件回归任务继续保留，作为后续 workflow 的运行底座。

## 参考资料与边界

- 业务真值：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py`
- 日常任务状态：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/daily_todo.py`
- UI 页面表面：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/ui_surfaces.json`
- 历史校准和失败证据：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa`
- 当前 MJA 计划：`docs/superpowers/plans/2026-07-28-mja-workflow-foundation.md`、`mja-daily-workflows-batch-1.md`、`mja-daily-workflows-batch-2.md`、`mja-daily-workflows-batch-3.md`、`mja-aggregate-live-verification.md`
- Maa_bbb：<https://github.com/miaojiuqing/Maa_bbb>
- Maa_bbb Agent 注册示例：<https://github.com/miaojiuqing/Maa_bbb/blob/main/agent/CustomFile.py>

参考 Maa_bbb 的任务列表、Agent custom action/custom recognition 注册、模拟器/ADB 运行和独立任务组织方式，但不复制其 Windows 控制代码、历史坐标、游戏资源或分辨率假设。MJA 继续使用 Android ADB、当前真实截图、MaaFramework Pipeline 和 ProjectInterface。

## 非目标

- 不迁移 Maa_bbb 的崩坏三业务逻辑、角色战斗脚本或 Windows 专用控制。
- 不保留 computer-use 作为第二套正式业务实现；它只提供业务步骤、历史校准和失败分析。
- 不把 17 个 workflow 合并成一个不可测试的大 Pipeline。
- 不自动执行真实货币支付、充值、付费礼包或需要账号安全确认的动作。
- 不把 fixture 识别通过误写成真实模拟器验收。

## 总体架构

```text
MFAAvalonia ProjectInterface
        │
        ├── 17 个独立任务入口
        ├── 今日全部任务入口
        └── mail_smoke_test 回归入口
        │
        ▼
AggregateScheduler
        │  日期过滤、依赖排序、任务级继续、汇总结果
        ▼
WorkflowDefinition × 17
        │
        ▼
Capture → Recognize → Same-frame Safety Gate → ADB Action
        │                                      │
        └────────── Postcondition Verify ◄─────┘
        │
        ▼
TaskResult + task-scoped diagnostics + MFA status
```

### 组件职责

1. `TaskPolicy` / catalog

   维护任务 ID、允许页面、允许资源、动作上限、步骤上限、超时、星期条件和危险信号。所有资源消耗策略只有一个业务真值来源，不在单个 definition 中复制第二份政策。

2. `WorkflowDefinition`

   每个任务只负责从 `StateSnapshot` 和计数器产生一个 `Decision`。definition 不直接点击、不调用 ADB、不写诊断；它只描述下一步动作、预期后置条件或终态。

3. `authorize_action` / safety gate

   消费同一帧的页面、目标、危险信号、文字和资源证据。只有页面正确、目标唯一、证据来自同一 frame、动作在 policy 内且无危险信号时才授权输入。

4. `run_workflow`

   统一执行 capture → decide → authorize → action → verify 循环，限制步骤、动作、重试和超时，写入 `TaskResult` 与诊断证据。

5. Maa Agent

   参考 Maa_bbb 的统一注册方式，将 Android 点击、滑动、长按和必要的识别能力注册为 Maa custom action/custom recognition。custom action 不绕过 safety gate，所有输入仍由 runner 提供经过授权的当前帧识别框。

6. `AggregateScheduler`

   接收 MFAAvalonia 的全选任务集合，按当前日期过滤并按业务顺序串行执行。任务失败、安全拦截或已经完成不会改变其他任务的注册状态；每个任务结束后独立生成结果。

7. ProjectInterface/MFAAvalonia adapter

   将 17 个 canonical task ID 和聚合入口渲染为 MFAAvalonia 可见任务。任务始终可见；当天不适用或已完成由运行时报告状态，不通过删除 GUI 条目隐藏。

## 全量任务目录

全部迁移以下 17 个任务：

```text
MAIL_REWARD_DAILY
SHOP_FREE_GIFT_DAILY
WEEKLY_FREE_GIFT_MONDAY
TRIAL_SWORD_DAILY
FREE_APPRAISAL_DAILY
BUY_TEA_DAILY
COLLECTION_DEPLOYMENT_DAILY
HERO_DISPATCH_DAILY
SHADOW_RUINS_DAILY
SPEND_CONDENSATE_DAILY
MARTIAL_STUDY_BREAKTHROUGH_DAILY
EAT_STAMINA_FOOD_DAILY
DUNGEON_SWEEP_DAILY
JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY
RING_CHALLENGE_DAILY
DAILY_TASK_REWARD_CLAIM_DAILY
BATTLE_PASS_REWARD_DAILY
```

迁移按风险分阶段，但最终 GUI 会展示全部任务：

1. 页面导航、邮件、免费领取、普通派遣。
2. 有限普通资源消耗和可确认的次数型任务。
3. 副本、战斗、擂台和有分支的任务。
4. 日常任务奖励汇总、战令奖励和聚合调度。
5. 全量 MFAAvalonia 选择、实机验收和无副作用重跑。

`MAIL_REWARD_DAILY` 是真正的普通邮件奖励任务；现有 `mail_smoke_test` 仍是只读导航回归任务，不领取邮件奖励，也不被聚合任务替换。

## 调度与用户交互

### MFAAvalonia 操作

1. 启动后显示全部 17 个任务、今日全部任务和邮件回归任务。
2. 用户点击全选。
3. 用户点击开始任务。
4. 聚合调度器根据当前日期过滤任务；星期条件不满足的任务返回 `not_eligible`。
5. 已经有独立后置证据的任务返回 `already_complete`，不重复执行有副作用动作。
6. 其他任务按业务顺序串行执行。
7. UI 显示每个任务的等待中、执行中、完成、跳过、失败或安全拦截状态。
8. 批次结束后显示汇总和每个任务的诊断目录。

### 失败继续策略

用户已选择“单任务失败后继续”。因此：

- 普通识别失败、动作超时、动作上限或后置条件失败：记录当前任务为 `failed`，尝试一次有限的已知页面恢复，然后继续下一个任务。
- 付费、充值、验证码、账号安全或未知弹窗：当前任务为 `blocked_safety`，只允许关闭明确识别的普通弹窗或恢复到已确认的主界面；无法确认状态时停止后续任务并标记环境阻塞。
- 设备断连、模拟器健康检查失败、MaaPiCli 无法启动：批次停止，不对后续任务进行盲操作。
- 任务内部只允许最新帧驱动的有限重试；不重复执行整任务的无限重试。

## 安全与资源消耗政策

### 永久禁止

- 真实货币、充值、支付、Apple Pay、付费礼包和价格不明的购买。
- 登录、密码、短信验证码、实名认证、生物识别和安全验证输入。
- 未知页面、未知弹窗、目标不唯一或页面/目标不在同一帧的输入。
- 键盘快捷键、固定历史坐标、盲点空白区域和未经过当前截图识别的目标。

### 允许的普通资源消耗

允许明确列入任务 policy 的普通游戏资源，但必须同时满足：

- 当前帧明确识别资源名称和数量。
- 资源属于任务批准白名单。
- 当前动作未超过单次、单任务和每日上限。
- 动作后能在新帧验证资源变化或任务后置条件。
- 任何资源、货币、次数或弹窗文字无法确认时阻止动作。

## 诊断和结果

每次任务使用独立诊断目录，至少保存：

```text
diagnostics/YYYY-MM-DD/{TASK_ID}/{run-id}/
├── result.json
├── agent.log
├── maafw.log
├── action-trace.jsonl
├── before.png
├── after.png
└── failure.png        # 仅失败或安全拦截时需要
```

结构化结果只写任务 ID、状态、时间、设备/AVD、资源版本、动作计数、错误码和证据路径；不写账号、手机号、验证码、UID、token 或完整日志内容。

运行态严格限制为：

```text
completed
already_complete
not_eligible
blocked_safety
failed
```

## 文件和接口布局

每个任务采用统一布局：

```text
agent/workflows/catalog.py
agent/workflows/models.py
agent/workflows/engine.py
agent/workflows/definitions/{lowercase_task_id}.py
agent/workflows/registry.py
agent/actions/daily_workflow.py
assets/resource/pipeline/daily/{lowercase_task_id}.json
assets/resource/image/daily/{TASK_ID}/
tests/fixtures/{TASK_ID}/manifest.json
tests/fixtures/{TASK_ID}/entry.png
tests/fixtures/{TASK_ID}/actionable.png
tests/fixtures/{TASK_ID}/completed.png
tests/fixtures/{TASK_ID}/danger.png
tests/workflows/test_{lowercase_task_id}.py
```

ProjectInterface 中每个任务使用 canonical lowercase name、`entry: MJA_Daily_{TASK_ID}`、MJA Android resource 和 Android controller；聚合入口使用独立的 `MJA_Daily_All` custom action，不复制 17 份调度逻辑。

## 测试与验收策略

### 自动化质量门

- 每个任务有 policy、decision、cap、danger 和资源边界测试。
- 每个任务有四态 fixture，fixture 识别测试禁止发送输入。
- 每个任务验证 MFA 单任务选择和任务 ID 映射。
- 聚合测试验证日期过滤、顺序、任务失败后继续、已完成跳过和设备级失败停止。
- 全量 pytest、Ruff、安装验证和 ProjectInterface 验证必须通过。

### Android 实机验收

- 使用当前 `mja-api35-apis`、`emulator-5556` 和中文 Android 15 AVD。
- 每个任务至少执行一次真实前台验证，记录当前 commit、配置、截图尺寸和诊断路径。
- 有副作用任务验证独立后置条件；不能用 Pipeline 日志单独宣称成功。
- 已完成任务执行一次无副作用重跑，必须得到 `already_complete` 或明确 `not_eligible`。
- 最后通过 MFAAvalonia 全选 17 个任务执行完整批次，验证失败后继续、汇总结果和恢复策略。
- 用户只介入登录、短信验证码和系统授权。

## 交付和回滚

按以下阶段交付，每阶段都能独立测试和回滚：

1. Foundation：catalog、safety、input、diagnostics、runner、ProjectInterface 基础。
2. Batch 1：导航、免费任务和普通派遣。
3. Batch 2：有限资源任务和常规副本任务。
4. Batch 3：Shadow、Jianlin、Ring 等复杂分支任务。
5. Aggregate：全选入口、日期调度、失败继续和最终 MFAAvalonia 验收。

任何新任务失败不影响已验收任务的 Pipeline 和入口；通过任务 registry 或 ProjectInterface 移除未验收任务即可回滚，不回滚 Android runtime hardening 和 `mail_smoke_test`。

## 完成标准

只有同时满足以下条件才算全量迁移完成：

- 17 个任务均有独立 definition、policy、Pipeline、资源、fixture 和测试。
- MFAAvalonia 能展示全部任务并支持全选开始。
- 聚合执行按日期排序，单任务失败后继续，设备级失败安全停止。
- 普通资源消耗受白名单和上限约束。
- 付费、验证和未知状态永远不会获得输入授权。
- 每个任务至少有一次真实 Android 验收和独立后置条件。
- 全量批次有脱敏汇总结果和可追溯诊断证据。
- 全量自动化测试、静态检查、安装验证和 MFAAvalonia 任务选择验证通过。
