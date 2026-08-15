# MJA 对齐 MAA_BBB 的独立日常改造计划

日期：2026-08-03

依据：`Maa_bbb` main 固定提交
`51c42a6193e3b1db5fd60660db69b73352562324`，以及 MJA 当前工作树和真实 Android
运行证据。

这是一份实施计划，不是“已经全量成功”的声明。当前审计 HEAD 为 `a00dc8c`；自动化门为 `692 passed, 5 skipped`，
但 2026-08-03 的 17 项实机验收仍需完成。

## 一、从 MAA_BBB 得出的硬规则

MAA_BBB 的关键不是任务数量，而是控制面：

1. `interface.json` 通过 `import` 暴露独立 task；preset 只排列和启用任务。
2. 启动游戏是独立 task，有明确的“成功进入主菜单”终点；业务任务也能通过
   `[JumpBack]` 回到启动/就绪节点。
3. 每个业务 Pipeline 自己拥有开始层、页面入口、已知偏航、有限循环和结束回主页路径。
4. `next`、`[JumpBack]`、`on_error`、`max_hit`、`timeout` 和 `StopTask` 组成可读的
   有限状态图；恢复知识放在拥有该页面的任务附近。
5. Python Agent 只补 Maa Pipeline 不擅长的窄能力；`Count` 和 `OverridePipe` 是典型，
   不是第二套全局工作流引擎。
6. 基础资源和渠道/控制器差异通过 resource overlay 组合，不复制整套业务流程。
7. CI 至少让 MaaFramework 实际加载 resource bundle，避免只通过 Python 配置测试。

MJA 必须照搬这些控制面原则，但保留自身更严格的同帧授权、资源上限、付费/未知弹窗
安全门和结构化结果。

## 二、目标架构

```text
MJA_Game_Ready（独立 Maa task）
        │  已验证主页
        ▼
DailySupervisor（只负责编排、超时、checkpoint、恢复和报告）
        ├── MAIL_REWARD_DAILY（独立 MaaPiCli + 独立诊断）
        ├── SHOP_FREE_GIFT_DAILY
        ├── WEEKLY_FREE_GIFT_MONDAY
        ├── ...
        └── BATTLE_PASS_REWARD_DAILY

任务局部失败 → 冻结证据 → MJA_Game_Recover → 成功则继续下一任务
设备/登录/未知安全弹窗失败 → 保留剩余 ID 并安全交接
```

必须消除的结构是：

- 生产全量入口不再调用一个包住 17 项任务的 `AggregateDailyWorkflowAction`；
- 任务不共享可变的全局 `MaaAndroidWorkflowDriver` 状态；
- `return_to_home()` 不再认识所有业务页面；
- `engine.py` 不再成为 Shadow、Dungeon、Jianlin、Ring 等任务的中央状态机；
- 启动、恢复、业务动作和结果记录各自有独立终态。

## 三、分阶段实施

### Phase 0：冻结证据和接口

- 固定 17 个 canonical task ID、顺序、日期过滤和每项资源上限。
- 以 `result.json`、`run.json`、Maa 日志和截图作为唯一运行证据。
- 保持所有输入走 Maa Android ADB Controller；不使用 Computer Use、macOS 点击或裸
  `adb shell input`。
- 先通过 JSON/资源加载、Python 单测、Ruff 和 `git diff --check`，再做实机输入。

完成标志：任何任务都能产生终态结果；测试故障注入能证明首项失败不会静默跳过后续项。

### Phase 1：建立失败域和终态真值

- 扩展任务结果，保留原始 `error_code`、异常类型、消息、阶段和 traceback 路径。
- `run.json` 只允许从 `running` 进入 `succeeded` 或 `failed`；硬终止只收尾开放记录。
- 任务失败、会话失败、设备/网络失败、登录/支付/未知弹窗分别归类。
- 聚合报告只汇总子任务，不重新改写子任务原始错误。

完成标志：原始任务错误不会被 `WORKFLOW_DRIVER_FAILED`、`aggregate_child_exception` 或
`MAA_CHILD_EXIT_NONZERO` 覆盖。

### Phase 2：建立独立 Maa 子进程和游戏就绪任务

- 一次 Android session 负责 AVD、设备和包检查；每个业务 task 启动自己的 MaaPiCli
  子进程和 process group。
- 为每个 task 配置硬超时；超时只终止当前子进程，不能让父 supervisor 无限等待。
- 新增 `MJA_Game_Ready`：标题页、加载、已知可安全关闭弹层、主页识别都在该任务内；
  “包在前台”不能作为业务 ready 条件。该 entry 必须在业务 task 之前单独运行，不能让
  `require_task_boundary()` 消耗业务 task 的 300 秒预算。
- 新增 `MJA_Game_Recover`：任务失败后先冻结当前证据，再恢复到可验证主页；恢复失败按
  会话/安全域处理，不把失败页交给下一任务。
- `MJA_Game_Ready`、业务 task、`MJA_Game_Recover` 使用三套独立且有限的预算；不得通过
  无上限地提高业务 task timeout 掩盖启动或恢复路径过重。

完成标志：标题页冷启动 preflight 连续 10/10 识别到主页；第二个任务不依赖第一个任务
顺便启动游戏。

### Phase 3：把导航迁回任务自己的 Maa Pipeline

按风险分批，每批都要“资源加载 + 单项实机 + 已完成重跑”通过后才进入下一批：

| 批次 | 任务 | 迁移重点 |
|---|---|---|
| A | 邮件、商店、周礼包、试剑、鉴宝、日常/战令奖励 | 开始层、免费领取、无可领取分支、任务自有回主页 |
| B | 买茶、采集、英雄派遣、吃体力食物、武学突破 | 消费动作同帧授权，局部弹窗和结果页 |
| C | 暗影遗迹、凝晶、剑林、擂台/挑战、副本 | 有限战斗循环、次数/倍率纯规划、局部超时 |

每个 Pipeline 至少有：

- 主页/中间页/业务页三类合法入口；
- 独立的已完成分支和成功后置条件；
- 有上限的循环、超时和错误恢复；
- 任务自己的返回主页节点；
- 付费、验证、未知弹窗的安全停止分支。

Python 只保留：资源规划、同帧授权、少数复杂识别/战斗扩展、诊断和监督；不得再次
实现一套跨任务的 capture → decide → execute → verify 引擎。

### Phase 4：切换生产控制面

- 在 `assets/interface.json` 中注册独立启动 task、17 个独立 task 和一个 MAA_BBB 风格
  preset。
- shell wrapper 默认调用 supervisor/preset，显式 `--task` 只运行一个 canonical task。
- 删除或隔离旧 `daily_all` 生产注册；保留兼容代码时必须有测试证明它不会被正式入口调用。
- 把渠道、控制器和平台差异放进 resource overlay，不在业务 Python 中增加平台分支。

完成标志：静态检查能证明 17 个生产入口都没有 `DailyWorkflowAction` 聚合路径；任一任务
失败后的故障注入仍能执行后续任务。

### Phase 5：更新运行 skill、runbook 和发布门

`maa-run-jianzhichuan-dailies` skill 改为薄操作层：

1. 检查没有重复 runner；
2. 先执行只读 preflight 并确认游戏就绪；
3. 调用独立 supervisor，而不是盲跑隐藏聚合器；
4. 监控 checkpoint 和当前 task run；
5. 只有登录、支付、验证码、未知弹窗或设备不可用才安全阻塞；
6. 最后核对当日所有 eligible task 的本次 `run_id`、终态、证据和剩余列表；
7. 逐项报告 `completed`、`already_complete`、`not_eligible`、`failed` 或
   `blocked_safety`，失败时带最后动作、后置条件、原始错误码和证据目录。

skill 不负责发明业务恢复策略，避免把当前错误架构固化为运行说明。

## 四、强制验收矩阵

### 自动门

```bash
install/.venv/bin/pytest -q
install/.venv/bin/ruff check agent tools tests
install/.venv/bin/python -m tools.setup --root /Users/gaoguobin/project/MJA --sync-only
install/.venv/bin/python -m tools.verify_install install
git diff --check
```

### 实机门

1. 标题页冷启动 preflight 连续 10 次成功。
2. 每个 task 独立运行一次，保存 before/after、Maa 图像、`run.json`、`result.json`、
   action trace 和 Maa/Agent 日志。
3. 每个允许幂等的 task 立即重跑并得到 `already_complete`；消费任务不得重复消费。
4. 注入第一项失败，确认后续 2 项仍启动、恢复只调用一次、结果顺序不变。
5. 2026-08-03 周一完整运行必须满足：

```text
CLI exit code = 0
aggregate.status = completed
17 个 eligible task 全部有本次 run_id
remaining_task_ids = []
stop_reason = null
每项 status ∈ {completed, already_complete, not_eligible}
没有 running 的 run.json
每项最终边界为已识别主页
```

任何一条不满足，都只能报告“未通过”，不能用单测、点击记录或部分任务成功替代。

## 五、提交顺序和停止规则

1. 先提交结果/诊断终态和独立子进程边界；
2. 再提交 `MJA_Game_Ready` 和 supervisor；
3. 再按 A/B/C 批次提交 Pipeline 迁移；
4. 最后提交接口/preset、runbook、skill 和实机验证记录。

每次提交前只允许包含对应阶段的源代码、测试和文档；不提交账户信息、截图或含敏感信息
的日志。若遇到登录、支付、验证码、未知弹窗、设备死亡或无法确认安全性的画面，立即
保存现场并停止；若只是当前任务的普通业务失败，则先保存证据、执行独立恢复并继续后续
任务。

## 六、当前距离完成还差什么

已完成：MAA_BBB 源码对比、报告、自动化测试门、任务级硬超时、部分任务隔离和诊断收尾
修复。

未完成：`MJA_Game_Ready` 原生 Pipeline、17 个任务完全迁回原生 Pipeline、生产入口切换、
skill/runbook 改造，以及最重要的 10 次 preflight、17 项逐项 canary 和周一全量实机验收。

在这些未完成项全部有当前提交和当前资源产物的证据前，不得宣布“一次性成功”。

## 七、2026-08-03 现场更新

自动化门已更新为 `692 passed, 5 skipped`，Ruff、安装校验和 `git diff --check` 均通过。
周一全量批次 `20260803T032549812529+0800` 已经完整遍历 17 项并将
`remaining_task_ids` 清空，但 exit code 为 1，结果为 11 项完成/已完成、1 项不适用、5 项
失败；另外 3 项的结果虽标成成功，最后页面仍未统一回到 `home`。因此它是“调度隔离门
通过、业务完成门失败”，不能作为最终成功。

试剑随后完成了一个真实 targeted canary：入口坐标修复后，领取动作又新增了“领取后直接主页”
后置条件，单项命令返回 0，`TRIAL_SWORD_DAILY=completed`。这项修复只关闭了试剑的一个
真实根因；其余五项失败和非 home 交接问题仍按 Phase 2–4 的独立 Pipeline/恢复改造处理。

最新邮件 canary `20260803T051513646718+0800` 已成功从标题页进入游戏并完成
`open_function_panel`、`open_mail`，但仍以 `WORKFLOW_TIMEOUT` 失败。现场说明标题页模板已经不是
当前阻塞点；真正需要先处理的是：

1. 把标题页到主页从业务 task 中移出，作为独立 `MJA_Game_Ready` entry；
2. 让业务 task 的计时从“已验证主页”开始；
3. 把失败恢复从 394 行全局 `return_to_home()` 收缩为 `MJA_Game_Recover` 和任务局部 close path；
4. 为邮件增加“无可领取/已读邮件”与关闭回主页的明确视觉后置条件。

在这四项和其对应的 canary 通过前，不得用“标题页已修复”或“队列已清空”宣布完成。

## 八、最新现场门：蜃影推荐阵容控件

`SHADOW_RUINS_DAILY` 的最新 run 已经走到推荐阵容页，Maa OCR 能稳定识别
“使用阵容”框 `[1085,599,90,27]`；但普通点击、一像素受限 swipe，以及独立 Maa
Controller 的短按压事件都没有让页面离开推荐阵容页，最终仍为
`WORKFLOW_POSTCONDITION_MISSING`。

后续只允许按以下顺序收口：

1. 把“输入作业完成”和“推荐页消失/编队页出现”分成两个观测点；后者才是动作成功。
2. 在 Maa Controller 支持的有限输入类型中建立一个可复现的控件 canary；每个候选只允许
   有明确的前后截图、输入日志和页面后置条件。
3. 同一步超过两次仍无状态变化时停止猜测，保留现场并转入控件根因分析；不能靠增加总超时、
   无限重试或把 `shadow_formation_page` 写成无条件成功来掩盖问题。
4. 蜃影 canary 成功后，先单项重跑并确认最终 `home`，再进入全量运行；该单项失败不能取消
   其他任务的独立入口、恢复和结果记录。

这条门禁是 Phase 3 的局部验收项，不改变“任务之间失败域必须隔离”的总架构要求。

## 九、12:35 runner 收口状态

蜃影单项 runner
`install/debug/runs/daily/shadow_ruins_daily/2026-08-03T12:35:31.003532+08:00/`
已按有界重试规则收口：推荐阵容路径之后连续出现三轮战斗失败，未出现成功/奖励/home
后置条件，因此没有继续盲目加时或重复输入。该次结果为 task-local `failed`，外层批次为
`interrupted`，剩余任务 ID 保留；现场证据和 Maa/Agent 日志已保留，当前没有残留 runner
进程。

这条状态不关闭任何实机验收门。重新运行前必须完成：

- 把 `MJA_Game_Ready` 和 `MJA_Game_Recover` 从业务任务预算中拆出；
- 为推荐阵容输入建立“输入完成 + 推荐页消失/编队页出现”的双观测 canary；
- 为失败终态写入原始错误码、阶段和 traceback 路径，禁止空错误码收尾；
- 先通过蜃影单项 `home` 交接，再执行 17 项全量验收。
