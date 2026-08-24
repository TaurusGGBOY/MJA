# MAA_BBB 与 MJA 日常执行架构对比报告

日期：2026-08-03

审计对象：MJA 当前审计 HEAD `a00dc8c`（另以 `a146e67` 作为历史 fail-fast 基线）、MAA_BBB `51c42a6193e3b1db5fd60660db69b73352562324`

结论状态：已完成固定提交源码、Pipeline、任务接口、运行证据、既有计划与 daily skill 的联合复盘；已补核 MAA_BBB 当前远端提交和 2026-08-03 周一全量批次。该批次仍未通过最终验收。

## 1. 结论

MAA_BBB 比当前 MJA 好的核心，不是模板更多，也不是重试更激进，而是它顺着 MaaFramework 的原生模型组织系统：

- 启动游戏是独立任务。
- 每个业务任务有独立入口，由 GUI preset 排序组合。
- 每个任务的 Pipeline 自己识别当前页面、进入业务页、处理已知偏航、完成后回主页。
- 通用恢复通过 Pipeline 节点复用，Python Agent 只补 Maa Pipeline 不擅长的少数能力。
- 仓库里没有一个把全部日常包成单个 Python CustomAction 的 `daily_all` 聚合器。

MJA 当前形成了分裂的控制面：CLI 已经具备逐任务调度和独立子进程的部分隔离，但 GUI/兼容路径仍把 17 个任务放进同一个 `AggregateDailyWorkflowAction`，并共用同一个 2251 行 driver；即使走 CLI，业务导航、启动准备和回主页仍大量依赖这个中央 driver。基线版本在首个普通任务失败后立即返回；工作树中的临时加固虽已尝试继续，但任务 Pipeline、恢复边界和最终主页门禁尚未自包含，因此标题页识别失败仍可能被归责给 `MAIL_REWARD_DAILY`，共享恢复失败也仍可能污染后续任务。

正确方向不是照抄 MAA_BBB 的每一个点击，而是采用它的控制面架构，同时保留 MJA 已有的同帧授权、资源上限、结构化结果和诊断能力：

> 独立 Maa 任务入口 + 独立游戏就绪 Pipeline + 外部批次监督器 + 任务内局部恢复 + 精确结果记录。

## 2. 审计范围和证据

### 2.1 MAA_BBB

审计固定在 main 分支提交 `51c42a6`，避免把不同版本混在一起。系统扫描覆盖：

- 37 个 `assets/tasks/**/*.json` 任务定义文件；
- 100 个 `assets/resource/base/pipeline/**/*.json` Pipeline JSON；
- 145 个 resource JSON 总数（任务、Pipeline 及其他资源定义）；
- Git tree 中数百个 base image 资源；
- 19 个 Agent Python 文件；
- 若把 `agent`、`assets/custom` 和 `tools` 一并统计，共 26 个相关 Python 文件；
- `assets/interface.json` 的 import、preset、controller、resource overlay；
- 启动、邮件、材料远征、家园、舰团、奖励领取等代表性完整 Pipeline；
- CI 的 MaaFramework resource bundle 校验。

关键源码证据：

- [interface.json](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/assets/interface.json)
- [游戏启动任务](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/assets/tasks/%E6%B8%B8%E6%88%8F%E5%90%AF%E5%8A%A8.json)
- [打开游戏 Pipeline](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/assets/resource/base/pipeline/%E8%BF%9B%E5%85%A5%E6%B8%B8%E6%88%8F/%E6%89%93%E5%BC%80%E6%B8%B8%E6%88%8F.json)
- [邮箱任务](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/assets/tasks/%E6%97%A5%E5%B8%B8/%E5%A5%96%E5%8A%B1%E9%A2%86%E5%8F%96/%E9%82%AE%E7%AE%B1.json)
- [邮箱 Pipeline](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/assets/resource/base/pipeline/%E6%97%A5%E5%B8%B8/%E9%82%AE%E7%AE%B1.json)
- [CustomFile.py](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/agent/CustomFile.py)
- [resource CI](https://github.com/miaojiuqing/Maa_bbb/blob/51c42a6193e3b1db5fd60660db69b73352562324/.github/workflows/check.yml)

### 2.2 MJA

基线失败证据（`a146e67` 之前的正式批次）：

- `install/debug/runs/daily/aggregate-20260802T192213249537+0800.json`
- `install/debug/on_error/2026.08.02-19.22.37.894_MJA_Daily_All.png`
- `install/debug/runs/daily/mail_reward_daily/2026-08-02T19:22:13.249888+08:00/run.json`
- `install/debug/runs/daily-workflow-errors.log`

该次正式批次选择了 16 个周日适用任务，结果为：

- 聚合状态 `failed_task`；
- 首项 `MAIL_REWARD_DAILY` 被记为 `failed`；
- `postcondition=aggregate_child_exception`；
- `error_code=WORKFLOW_DRIVER_FAILED`；
- 后续 15 项未执行；
- 邮件任务的 `run.json` 仍停留在 `status=running`。

原始异常实际是：

```text
agent.errors.MJAError: no recognized game task boundary for MAIL_REWARD_DAILY
```

这说明当时结果层丢失了原始异常类型、阶段和错误码。

最新批次（`20260802T224059369761+0800`）已经包含工作树中的部分运行时加固，证据位于：

- `install/debug/runs/daily/aggregate-20260802T224059369761+0800.json`；
- `install/debug/runs/daily/mail_reward_daily/2026-08-02T22:40:59.370011+08:00/run.json`；
- `install/debug/runs/daily/shop_free_gift_daily/2026-08-02T22:41:56.622551+08:00/result.json`；
- `install/debug/runs/daily/shop_free_gift_daily/2026-08-02T22:41:56.622551+08:00/run.json`；
- `install/debug/on_error/2026.08.02-22.45.33.794_MJA_Daily_All.png`。

这次的实际过程是：

- `MAIL_REWARD_DAILY` 在标题页边界识别失败，`run.json` 已终结为 `failed`，原始消息仍为 `no recognized game task boundary for MAIL_REWARD_DAILY`；
- 批次确实继续启动了 `SHOP_FREE_GIFT_DAILY`，并完成了打开商店、进入周期福利、领取和关闭奖励等 5 个受保护动作；
- 商店任务随后在 `claimed` 后置阶段失败，`result.json` 的 `error_code` 为空，而 `run.json` 又被写成泛化的 `WORKFLOW_DRIVER_FAILED`；
- 任务恢复时前台已经是 `com.google.android.apps.nexuslauncher`，批次以 `ANDROID_GAME_NOT_FOREGROUND` 终止，仍有 14 个任务未执行。

因此，当前工作树已经部分消除了“首个普通任务失败立即 return”，但还没有实现 MAA_BBB 意义上的完整失败域隔离：CLI 已经能够逐任务启动独立 `AndroidRun`/MaaPiCli 子进程并继续调度，但 GUI/兼容路径仍共享一个 aggregate CustomAction、一个 driver 和一个恢复边界；任务逻辑本身也仍集中在中央 driver 中。于是 CLI 的进程隔离尚未转化为任务 Pipeline 的自包含边界，GUI 或共享恢复路径的故障仍可能终止或污染后续任务。

### 2.3 2026-08-03 周一第一轮失败批次（历史取证）

本次审计没有把“已执行过”当成“已成功”。批次 `20260803T012136213860+0800` 选择了周一应有的 17 项任务；在本报告取证时，`aggregate-latest.json` 的最新落盘 checkpoint 为 `completed_with_task_failures`，`stop_reason=WORKFLOW_TIMEOUT`，仍有未执行任务，runner 本身还在处理后续任务。因此这个 checkpoint 不是成功声明，反而证明父 runner 没有可验证的子任务硬超时边界。已确认的任务级证据如下：

| 任务 | 结果 | 最后阶段 | 错误码 | 证据目录 |
|---|---|---|---|---|
| `MAIL_REWARD_DAILY` | `already_complete` | `home` | — | `install/debug/runs/daily/mail_reward_daily/2026-08-03T01:21:57.237986+08:00/` |
| `SHOP_FREE_GIFT_DAILY` | `already_complete` | `home` | — | `install/debug/runs/daily/shop_free_gift_daily/2026-08-03T01:24:30.667687+08:00/` |
| `WEEKLY_FREE_GIFT_MONDAY` | `failed` | `weekly` | `WORKFLOW_TIMEOUT` | `install/debug/runs/daily/weekly_free_gift_monday/2026-08-03T01:27:29.616566+08:00/` |
| `TRIAL_SWORD_DAILY` | `completed` | `home` | — | `install/debug/runs/daily/trial_sword_daily/2026-08-03T01:29:03.466923+08:00/` |
| `FREE_APPRAISAL_DAILY` | `already_complete` | `home` | — | `install/debug/runs/daily/free_appraisal_daily/2026-08-03T01:31:24.598307+08:00/` |
| `BUY_TEA_DAILY` | `already_complete` | `home` | — | `install/debug/runs/daily/buy_tea_daily/2026-08-03T01:32:48.774598+08:00/` |
| `COLLECTION_DEPLOYMENT_DAILY` | `failed` | `collection` | `TASK_BOUNDARY_RETURN_FAILED` | `install/debug/runs/daily/collection_deployment_daily/2026-08-03T01:35:14.515175+08:00/` |
| `HERO_DISPATCH_DAILY` | `failed` | `painting` | `WORKFLOW_DRIVER_FAILED`（`run.json`；`result.json` 未写码） | `install/debug/runs/daily/hero_dispatch_daily/2026-08-03T01:38:54.344446+08:00/` |
| `SHADOW_RUINS_DAILY` | `already_complete` | `home` | — | `install/debug/runs/daily/shadow_ruins_daily/2026-08-03T01:40:18.770152+08:00/` |
| `SPEND_CONDENSATE_DAILY` | `completed` | `home` | — | `install/debug/runs/daily/spend_condensate_daily/2026-08-03T01:41:54.837633+08:00/` |
| `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | `failed` | `function_panel.page` | `WORKFLOW_POSTCONDITION_MISSING` | `install/debug/runs/daily/martial_study_breakthrough_daily/2026-08-03T01:44:37.296249+08:00/` |
| `EAT_STAMINA_FOOD_DAILY` | `running`（取证时） | 未终结 | — | `install/debug/runs/daily/eat_stamina_food_daily/2026-08-03T01:45:48.217460+08:00/` |

这组结果已经足够证明三个独立缺陷：周礼包是任务页识别问题，采集是任务结束边界问题，派遣是共享驱动/异常归因问题；它们不应由一个批次级 `WORKFLOW_TIMEOUT` 抹平。后续任务即使能够继续运行，也必须在每项拥有独立 Maa 子进程、独立恢复和独立终态后，才算真正实现“任务之间不耦合”。

## 3. MAA_BBB 是怎么做的

### 3.1 任务是独立入口，preset 只负责组合

MAA_BBB 的 `interface.json` 通过 `import` 引入各自独立的任务文件，`日常-简化版` 和 `日常-完整版` preset 只是按顺序启用这些任务：

```text
崩坏三 启动！
日常奖励领取-第一次
材料远征
家园远征派遣
家园资源领取
...
领取邮箱奖励
```

仓库的 `assets` 与 `agent` 中没有 `daily_all`、`Aggregate` 或“全部日常”自定义聚合实现。控制流不是“一个 CustomAction 内部调用所有任务”，而是“前端任务队列逐个提交独立 entry”。

这一区分非常重要：任务有业务顺序，不等于任务必须共享一个失败域。每日奖励适合排在其他任务后面，这是数据依赖；邮件失败导致副本、擂台、战令根本不启动，则是不应存在的控制流耦合。

### 3.2 启动游戏是独立能力，不冒充第一个业务任务

`assets/tasks/游戏启动.json` 暴露独立入口 `登录方式选择接口`。`启动并进入游戏` Pipeline 会在同一循环中处理：

- 已经进入主菜单；
- 点击任意位置进入游戏；
- 月卡、签到和领取弹层；
- 资源下载与热更新；
- 网络失败重试；
- 误入其他已知页面；
- 黑屏等待；
- 按资源 overlay 替换包名或启动方式。

它的成功条件不是“游戏包在前台”，而是模板识别到 `成功进入游戏主菜单`。

同时，42 个业务 Pipeline 文件包含 `[JumpBack]启动并进入游戏` 回退边。也就是说，即使显式启动任务没有运行，独立业务任务仍有自己的就绪回退，不会把启动责任永久绑定到 preset 中的第一个业务任务。

### 3.3 每个业务 Pipeline 自己拥有入口、偏航处理和结束边界

邮箱的结构很典型：

```text
邮箱-任务开始层
  -> 邮箱-总任务层
  -> [JumpBack]启动并进入游戏

邮箱-总任务层
  -> 邮箱-正处于邮箱界面
  -> [JumpBack]点击叉叉
  -> [JumpBack]邮箱-点击邮箱进入

邮箱-无可领取邮件
  -> 成功进入游戏主菜单
  -> [JumpBack]点击返回主菜单
```

材料远征、家园、舰团也采用相同模式：开始层接受“已经在业务页”“已经在中间页”“处于主页”“尚未进入游戏”等多种合法状态；任务结束时通过自己的页面路径回到主页，必要时在确认主页后 `StopTask`。

因此，页面恢复知识靠近拥有该页面的任务。它没有一个需要认识所有业务页面的 318 行 `return_to_home()`。

### 3.4 恢复是显式图，而不是隐藏在 Python 异常处理里

MAA_BBB 在 Pipeline 中广泛使用：

- `next`：按当前帧识别结果选择分支；
- `[JumpBack]`：执行可复用恢复节点后回到调用分支；
- `on_error`：对已知超时状态进入明确恢复节点；
- `max_hit`：限制循环或误触处理次数；
- `timeout`：给页面加载、战斗和资源下载不同预算；
- `StopTask`：在确认的终点停止当前任务。

全库中至少 7 个 Pipeline 文件使用 `on_error`，14 个使用 `max_hit`，11 个使用 `timeout`。这些不是无限盲重试，而是页面级、有上限、能读懂的恢复图。

### 3.5 Python Agent 是补充层，不是第二套工作流引擎

MAA_BBB 的 Python Agent 主要注册：

- `Count`：有限计数和分支；
- `OverridePipe`：运行时覆盖 Pipeline；
- `Notice`：识别并展示收益；
- 少量复杂战斗动作与分辨率检查。

普通日常导航和点击仍在 Maa Pipeline 中。Python 没有再实现一套通用的 capture → decide → execute → verify 状态机，也没有把每个游戏页面硬编码进一个 driver。

### 3.6 配置差异通过 resource overlay 解决

基础业务 Pipeline 放在 `resource/base`；B 服、小米、Win32 等只覆盖包名、启动方式、输入方式或渠道登录节点。业务流程不复制多份，也不在 Python 中堆平台分支。

26 个 task 文件通过 `pipeline_override` 暴露用户选项，例如是否吃体力药、是否领取月卡、是否启用特殊弹窗处理。选项修改的是节点参数或分支，不是另一套执行器。

### 3.7 CI 至少验证 MaaFramework 真能加载资源

MAA_BBB 的 CI 会安装 `maafw`，然后对 `interface.json` 中每组 resource path 调用 MaaFramework `Resource.post_bundle(...).wait()`。这能提前发现 JSON、引用和资源合并错误。

它的 CI 并不等于完整实机回归，但它验证的是 MaaFramework 最终消费的资源，而不只是 Python 自己能解析某些配置。

### 3.8 本次对 MAA_BBB 的复核边界

本报告不是依据项目名称或 README 推测。已用 GitHub 远端固定提交复核了 `interface.json`、游戏启动任务、邮箱任务、材料远征任务、家园远征任务、代表性 Pipeline、`agent/CustomFile.py` 和 `.github/workflows/check.yml`；该提交当前仍是仓库默认分支最新提交。固定提交的 tree 包含 37 个 task JSON、100 个 base Pipeline JSON、145 个 resource JSON 总数和 19 个 Agent Python 文件；若把 `agent`、`assets/custom` 与 `tools` 一并统计，则为 26 个相关 Python 文件。

从实际内容可以看到：

- `assets/interface.json` 的 preset 直接排列“启动、奖励、材料、家园、舰团、邮箱”等独立任务；它不是把所有任务传给一个 Python `CustomAction`。
- `assets/tasks/日常/材料远征.json` 和 `assets/tasks/日常/家园/远征派遣.json` 通过 `pipeline_override` 改变体力不足分支；选项差异没有复制整套业务流程。
- `assets/resource/base/pipeline/日常/邮箱.json` 的开始层同时接受当前在邮箱、主页入口和 `[JumpBack]启动并进入游戏`；邮箱结束层再回到主页。材料、家园和凭证 Pipeline 采用同一类任务自包含边界。
- 启动 Pipeline 的入口 `启动并进入游戏` 明确把主页、加载、资源下载、网络重试、签到、月卡、误触和已知返回路径作为自己的识别分支；业务任务不需要假设“第一个任务顺便完成启动”。
- `agent/CustomFile.py` 注册的是 `Notice`、`Count`、`OverridePipe`、分辨率识别及角色战斗等窄扩展，不是第二个覆盖所有日常的状态机。

因此，MAA_BBB 值得学习的是控制面和资源组织方式；其个别模板宽松、日志依赖较强、CI 不是实机视觉回归等不足，不能原样复制到 MJA。

## 4. MJA 当前为什么失败

### 4.1 “全部日常”是单失败域

当前存在两条不能混为一谈的调用路径：

```text
CLI（已有部分隔离）
scripts/run-all-dailies.sh
  -> tools.android_daily_run
  -> 逐任务 AndroidRun / MaaPiCli 子进程
  -> 每项 task result / checkpoint

GUI / 兼容聚合路径（仍然耦合）
MFA/Maa interface
  -> MJA_Daily_All
  -> AggregateDailyWorkflowAction
  -> AggregateScheduler.run(17 tasks, one shared driver)
```

在基线提交 `a146e67` 中，`AggregateScheduler.run()` 明确包含：

```python
if result.status is TaskStatus.FAILED:
    ...
    return aggregate
```

测试 `test_aggregate_uses_order_filters_monday_and_stops_on_task_failure` 又明确固定：

```python
assert calls == ["MAIL_REWARD_DAILY"]
assert aggregate.remaining_task_ids == IDS[1:]
```

所以历史基线版本的“第一个任务失败，后续全部不执行”不是意外，而是当时实现和测试共同规定的产品行为。当前 `a00dc8c` 的 CLI 已把普通任务调度改成逐项独立子进程，2026-08-03 批次也证明 17 项可以全部被调度并清空 `remaining_task_ids`；但这只是进程/调度层的部分隔离。GUI/兼容聚合路径仍保留共享 driver 和共享 CustomAction，CLI 的每项业务流程也仍主要调用中央 driver，任务自己的 Pipeline、恢复和回主页边界尚未完成。因此共享恢复、中央业务异常或 GUI 路径仍可能终止或污染后续任务，这与要求的完整任务独立仍然冲突。

### 4.2 登录门禁把标题页误判为 ready

`LoginGate.wait_until_ready()` 的 ready 条件只是：

1. UI XML 没出现登录标记；
2. 前台包名连续三次等于游戏包名。

标题页完全满足这两个条件。于是 Android 预检成功返回，Maa 正式批次随后才第一次尝试进入主页。

这不是登录检测的小误差，而是 readiness 定义错误：`foreground` 只能证明进程在前台，不能证明业务任务可执行。

### 4.3 启动准备被塞进了任务边界清理

`MaaAndroidWorkflowDriver.return_to_home()` 同时负责：

- 识别主页；
- 点击标题页开始游戏；
- 关闭邮件、商城、鉴宝、武学、背包、副本、剑林、派遣、采集、画卷、蜃影、日常和战令页面；
- 处理多种结果弹层。

当前 graph 显示该方法约 394 行、30 个入度调用，是明显的中心耦合热点。它既是“任务结束清理”，又是“下一任务前置恢复”，还是“启动游戏”。

本次标题页底部的“点击开始游戏”几乎与背景同色。`reset.start_game` 只依赖该低对比度文字 OCR，实际 OCR 只识别到了版权文字，边界函数返回 `False`。由于这一调用发生在 `MAIL_REWARD_DAILY` 前，启动失败被错误归责给邮件。

### 4.4 Pipeline 只是识别字典，业务状态机仍全部在 Python

以邮件为例，MJA 的 `mail_reward_daily.json` 入口只有一个 `DailyWorkflowAction`，其余节点主要是 recognizer 定义。当前 17 个日常入口仍都落到这个 CustomAction；真正的业务顺序在 Python definition、engine 和 driver 中。

当前相关体量：

- `agent/workflows/maa_android.py`：2475 行；
- `agent/workflows/engine.py`：312 行；
- `agent/workflows/aggregate.py`：217 行；
- `agent/actions/daily_workflow.py`：602 行；
- `agent/workflows/definitions/*.py`：20 个文件，共 3351 行；
- Android Pipeline JSON 总计约 1231 行，多数不承担控制流。

`engine.py` 甚至直接知道 Shadow、Dungeon、Jianlin 等任务特例。通用引擎已经被业务细节污染，新增一个任务会改变所有任务共享的执行核心。

### 4.5 异常被分层抹平

当前至少有三次信息损失：

1. `run_workflow()` 捕获任意 `Exception`，统一写 `WORKFLOW_DRIVER_FAILED`；
2. `AggregateScheduler` 再把普通异常改写成 `aggregate_child_exception`；
3. CustomAction 顶层捕获异常后只返回 `success=False`。

最终 aggregate 看不到原始 `MJAError`、阶段、异常消息和 traceback 位置。任务诊断又没有在异常路径 finalize，留下 `run.json: running`。

### 4.6 测试验证了“我们写了什么”，没有验证“现场能不能识别”

`test_android_start_game_recognizes_both_live_title_labels` 只断言 JSON 里写了两个 OCR 字符串；它没有把本次 1280×720 标题页截图交给 Maa OCR。

现有 workflow fixture 也主要把 manifest 中声明的 `page_hits`/`target_hits` 转成证据，并不执行真实图像识别。于是静态测试全部通过，仍然可能在第一张真实截图失败。

这正是本次事故：测试证明“配置包含点击开始游戏”，却没有证明“当前画面能识别点击开始游戏”。

## 5. 两个项目逐项对比

| 维度 | MAA_BBB | 当前 MJA | 直接后果 |
|---|---|---|---|
| 全量编排 | preset 组合独立任务 | CLI 已逐任务监督；GUI/兼容路径仍是单个 `daily_all` CustomAction | 两条路径行为不一致，聚合路径仍会扩大失败域 |
| 启动 | 独立任务，业务入口也可回退到启动 | CLI 有前置准备，但业务流程仍把启动/恢复知识带入中央 driver；GUI 仍藏在 `return_to_home()` | 启动失败可能被记到首个业务任务 |
| 任务入口 | 每项独立 entry | CLI 有独立子进程，GUI 仍是聚合 entry，业务入口未完全原生化 | 有进程隔离但没有任务自包含边界 |
| 状态机位置 | Maa Pipeline JSON | Python definition + engine + driver | 逻辑远离识别资源，中心代码膨胀 |
| 恢复 | 任务局部节点、`JumpBack`、`on_error` | 一个全局 `return_to_home()` | 任一页面变化影响全部任务 |
| 任务结束 | 任务自己的回主页路径 | 通用后置清理 | 清理函数必须认识所有业务页面 |
| 配置差异 | resource overlay | 多处 Python/JSON 分支 | 修改面更大 |
| Python Agent | 少量框架补充能力 | 第二套工作流运行时 | 重复 MaaFramework 能力 |
| 失败结果 | Maa 节点日志为主 | 结构化结果本应更强，但被泛化 | 原始根因不可见 |
| 安全 | 有些节点较宽松 | 同帧授权、资源 policy 更严格 | MJA 的这一部分必须保留 |
| 自动测试 | Resource bundle CI，实机成熟度来自长期使用 | Python 单测多，但真实识别门禁弱 | 测试数量没有转化为首帧可靠性 |

## 6. 对此前工作流程的反思

### 6.1 我把“写完代码”错当成了“任务已经可用”

17 份 `verification/tasks/*.json` 至今全部是 `live_pending`，但代码已经以 `feat: harden Jianzhichuan Android daily runner` 提交。真正的门槛应当是冷启动全量实跑，不是单测数、文件数或计划完成度。

### 6.2 验收顺序错误

正确顺序应是：

1. 冷启动进入主页；
2. 一个无副作用任务端到端；
3. 第一个真实任务端到端；
4. 两个独立任务串行且故障隔离；
5. 再扩展到 17 项。

此前却先堆完所有 definitions、policy、fixtures 和聚合器，最后才让真实标题页来验证地基。结果第一步没过，后面大量代码没有机会运行。

### 6.3 设计与实现发生了反向漂移

2026-07-28 的设计明确写过“单任务失败后继续”。2026-08-01 的实现又把方案改成 fail-fast，并新增测试固定首错即停；当前工作树虽已部分改回继续，但最新运行仍在共享恢复失败时终止。前后两次都把“不要在 Launcher 上盲跑”和“任务之间必须隔离”错误地放进了同一个全局控制流。

正确做法本应是增加独立恢复边界和失败域分类，而不是在“盲目继续”和“全部停止”之间二选一。

### 6.4 没有真正参考 MAA_BBB 的核心

此前所谓 MAA_BBB 对齐主要完成了：

- ADB Controller 路径；
- 16:9 分辨率；
- Agent 注册外形；
- GUI 任务列表。

没有完整采用它最有价值的部分：独立任务入口、preset 编排、Pipeline 状态机、任务局部恢复和 resource overlay。当前 CLI 已补上了“逐任务调度”的一部分，但业务控制流仍大量依赖自研聚合器/中央 driver；结果仍是“部分像 MAA_BBB，核心业务边界没有真正下沉到任务 Pipeline”。

### 6.5 计划和提交门禁不够严格

此前计划允许以下状态进入“完成”或提交：

- 全部 live verification 仍 pending；
- 没有从真实标题页执行 preflight；
- 没有首任务失败后后续任务仍运行的故障注入；
- `run.json` 可残留 `running`；
- 原始异常可被 `WORKFLOW_DRIVER_FAILED` 覆盖。

这些都必须升级为不可绕过的发布门禁。

## 7. 对 `maa-run-jianzhichuan-dailies` skill 的反思

当前 skill 不是中性的操作说明，它把“调用现有 wrapper”当成了默认行为，却没有把 wrapper 的实际失败域和终态契约写成强制门禁。

### 7.1 它盲目调用耦合入口

skill 规定全量任务直接执行：

```sh
scripts/run-all-dailies.sh
```

当前 CLI wrapper 已经通过 `tools.android_daily_run` 逐任务启动子进程；但 skill 没有先验证实际运行的是这条 CLI 路径，还是 GUI/兼容的 `daily_all` 聚合路径，也没有把独立 preflight、每项硬超时和失败域检查设成执行前门禁。因此它无法保证所有入口都具备同样的隔离语义。

### 7.2 它的承诺与可执行能力矛盾

skill 同时写着：

- 不要从第一个任务重新开始；
- 恢复失败任务后继续剩余序列；
- 同一步失败超过两次就停止并询问用户。

虽然现有 wrapper 已支持多个 `--task` 和默认的日期任务序列，但 skill 没有规定每个 task 必须拥有独立 MaaPiCli 生命周期、硬超时、恢复结果和可验证的主页交接；也没有把剩余队列、恢复监督器和终态完整性作为强制契约。历史上的聚合 fail-fast 和当前 CLI 的部分继续调度因此仍可能被混为同一种“成功运行”。

### 7.3 它把“保留失败现场”绝对化

保留截图、日志和结果是必要的；永久把游戏停在失败页面则不是。对于一次性全量执行，正确流程是先冻结诊断证据，再运行已验证的独立恢复 Pipeline。当前 skill 把诊断需求和运行恢复对立起来，导致一次卡住后整批失去进展。

### 7.4 它没有失败域分类

skill 没有区分：

- 任务局部失败；
- 可恢复会话失败；
- 设备/网络全局失败；
- 登录、支付和未知弹窗安全阻塞。

“失败两次就问用户”是按次数决策，不是按根因决策。它会在可自动恢复的问题上过早停止，也可能在不应重试的消费动作上重复尝试。

### 7.5 它没有最终全量审计

skill 要求逐项报告，但没有强制验证：

- 当日所有 eligible task 都有本次 run_id 的结果；
- `remaining_task_ids=[]`；
- 没有 stale `run.json: running`；
- source 与 `install/` 组装产物一致；
- 原始异常字段没有丢失；
- 周一任务在周一被纳入。

### 7.6 skill 应改成薄操作层

skill 不应自己发明恢复策略。它应当：

1. 检查没有重复 runner；
2. 调用 `--preflight-only` 并读取明确结果；
3. 调用独立任务监督器；
4. 按 supervisor 结果持续监控；
5. 只在安全或不可恢复环境阻塞时交接；
6. 对照当日任务目录做完整性审计；
7. 逐项报告真实状态和原始错误。

## 8. 应该学习什么，不应该照抄什么

### 8.1 必须采用

- 独立启动任务和明确主页成功节点；
- 每个业务任务独立 entry；
- preset/外部监督器组合任务，不用单 CustomAction 聚合全部任务；
- 每个任务开始层接受合法中间状态，并可回退到游戏就绪节点；
- 页面恢复靠近所属任务；
- 通用节点只处理真正通用的返回、弹层和主页判断；
- `next`、`JumpBack`、`on_error`、`max_hit`、`timeout` 构成可读的有限恢复图；
- resource overlay 处理控制器、渠道和平台差异；
- CI 用 MaaFramework 实际加载完整 resource bundle。

### 8.2 不能照抄

MAA_BBB 也有不适合直接搬进 MJA 的做法：

- 部分通用点击和 OCR 范围较宽；
- 启动任务说明中出现“最好重复执行两次”，不符合确定性目标；
- 主要依赖 Maa 日志，没有 MJA 现有的精确 `TaskResult`；
- CI 不是实机视觉回归；
- 一些 Pipeline 文件自己标注“待重构”。

MJA 必须保留并强化：

- 所有游戏输入走 MaaFramework ADB Controller；
- 页面与目标同帧授权；
- 资源白名单和动作上限；
- 付费、验证和未知弹窗禁止输入；
- `completed/already_complete/not_eligible/failed/blocked_safety` 精确结果；
- 每任务独立诊断与聚合报告；
- Python 单测和真实截图/实机验收双门禁。

## 9. 方案比较与决策

### 方案 A：MAA 原生独立任务 + 外部监督器（推荐）

业务导航迁回每个 Maa Pipeline；独立 `MJA_Game_Ready` 负责启动；Python supervisor 逐项启动带硬超时的独立 Maa 子进程、保存结果，并在任务局部失败或超时后先终止该子进程、恢复主页再继续。复杂资源决策保留为小型 CustomAction。

优点：真正隔离失败域，最接近 MAA_BBB，保留 MJA 安全与诊断。

代价：需要分批迁移现有 Python 状态机。

### 方案 B：保留当前聚合器，只把 `return` 改为 `continue`

优点：修改快。

缺点：仍共享一个 driver、一个 CustomAction、一个 318 行全局恢复器；失败页面和异常状态仍会污染后续任务。这只能消除“没调用”，不能消除耦合。

### 方案 C：把 17 项连成一个超大 Maa Pipeline

优点：减少 Python。

缺点：仍是单失败域，难以独立重跑和逐项报告，与用户要求相反。

最终选择方案 A。方案 B 可作为短期测试脚手架，但不能成为正式架构；方案 C 不采用。

## 10. 后续改造不可违反的原则

1. 设备/游戏就绪先于任何业务任务，并有独立结果。
2. `MAIL_REWARD_DAILY` 永远不负责启动游戏。
3. 每个任务是独立 job、独立 Maa entry、独立诊断目录和独立终态。
4. 任一任务局部失败不得阻止后续安全任务获得执行机会。
5. 每个 MaaPiCli 子进程必须有 catalog 硬超时；业务任务超时只终止当前子进程，不得无限等待或取消后续任务。
6. 任务失败后先保存证据，再运行独立恢复；不让下一任务直接继承未知页面。
7. 通用恢复层不得包含任务专有业务状态；任务页面的退出路径归该任务所有。
8. 业务消费动作不盲重试；截图、OCR、渲染和 ADB 传输可按类型有限重试。
9. 原始异常类型、错误码、消息、阶段和 traceback 必须进入结果；不得统一伪装成 `WORKFLOW_DRIVER_FAILED`。
10. 每个 `run.json` 必须在进程退出前终结为明确状态，不得残留 `running`。
11. 自动化测试不能只断言 JSON 里写了什么；关键识别必须通过真实截图和现场 preflight。
12. 正式提交前必须从标题页完成全量运行；静态测试通过不能替代实机通过。
13. 2026-08-02 周日有 16 个 eligible task；2026-08-03 周一必须纳入 `WEEKLY_FREE_GIFT_MONDAY`，共 17 项。

具体实施步骤、测试、提交顺序和验收矩阵见项目内实施计划
`docs/superpowers/plans/2026-08-02-mja-maa-bbb-decoupled-dailies.md`。

## 11. 2026-08-03 复核更新

本次重新从 GitHub 拉取并审计了 `miaojiuqing/Maa_bbb` 的 `main`，固定提交仍为
`51c42a6193e3b1db5fd60660db69b73352562324`。本地源码统计为 37 个 task JSON、100 个
base Pipeline JSON、145 个 resource JSON 总数、19 个 Agent Python 文件；若把 `agent`、
`assets/custom` 与 `tools` 一并统计，则为 26 个相关 Python 文件。Agent 源码同时通过 codebase-memory 建图
复核，确认 `CustomFile.py` 注册的是窄用途的 `Count`、`OverridePipe`、`Notice` 和少量
战斗/识别扩展，没有发现把全部日常包进一个 Python 聚合动作的实现。

MJA 当前工作树的自动化门已重新执行并通过：

```text
692 passed, 5 skipped
ruff check: passed
git diff --check: passed
```

此外，Android runner 的硬终止收尾已修正为：只有 `run.json` 仍是 `running` 或缺失状态
时才写入监督器错误；若 Maa 已经写出 `succeeded`/`failed` 终态，则保留它的原始错误码、
消息和时间信息。这个修复只保证证据不再被覆盖，不代表 17 项实机全量已经通过。

因此当前交付状态必须明确写成：

- MAA_BBB 对比报告：完成；
- MAA_BBB 风格的改造计划：完成，见
  [`docs/2026-08-03-maa-bbb-alignment-plan.md`](2026-08-03-maa-bbb-alignment-plan.md)；
- MJA 自动化门：通过；
- 2026-08-03 周一 17 项冷启动全量实机验收：尚未通过，不能把计划或单测结果冒充成功。

## 12. 2026-08-03 最终全量批次与 targeted 复核

随后完成的全量批次固定为
`install/debug/runs/daily/aggregate-20260803T032549812529+0800.json`，其事实是：

```text
CLI exit code = 1
aggregate.status = completed_with_task_failures
selected_task_ids = 17
remaining_task_ids = []
completed/already_complete = 11
not_eligible = 1
failed = 5
所有本次 run.json 均已终结，没有 running 记录
```

五项失败及其现场终态为：

| 任务 | 结果 | 最后后置条件 | 原始错误码 |
|---|---|---|---|
| `TRIAL_SWORD_DAILY`（全量旧 run） | `failed` | `trial` | `WORKFLOW_DRIVER_FAILED` |
| `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | `failed` | `panel` | `WORKFLOW_DRIVER_FAILED` |
| `DUNGEON_SWEEP_DAILY` | `failed` | `dungeon` | `WORKFLOW_DRIVER_FAILED` |
| `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | `failed` | `jianlin_battle_result` | `WORKFLOW_POSTCONDITION_MISSING` |
| `RING_CHALLENGE_DAILY` | `failed` | `custom_action_exception` | `WORKFLOW_POSTCONDITION_MISSING` |

此外，`COLLECTION_DEPLOYMENT_DAILY`、`EAT_STAMINA_FOOD_DAILY` 和
`BATTLE_PASS_REWARD_DAILY` 虽被结果层标成完成/已完成，但本次最后画面分别是
`collection`、`food` 和 `rewards`，没有满足统一的 `home` 交接边界；这三项不能作为严格
的一次性成功证据。

这轮实机运行证明了当前补丁已经具备“普通任务失败后继续调度”的部分隔离能力，但没有
证明 MAA_BBB 风格的任务独立入口、任务局部恢复和统一主页边界已经完成。因此验收结论仍是
未通过。

针对试剑的单项修复随后完成：领取动作允许“奖励弹层”或“领取后直接主页”两种合法视觉
后置条件，并新增了通用 Transition alternate-postcondition 测试。同步安装、串行安装校验
后，`scripts/run-all-dailies.sh --task trial_sword_daily` 返回 0，结果为
`TRIAL_SWORD_DAILY=completed`、`remaining_task_ids=[]`；证据目录为：

`install/debug/runs/daily/trial_sword_daily/2026-08-03T04:24:12.537268+08:00/`

这只证明试剑修复通过，
不改变上面的 17 项全量验收结论。

## 13. 05:15 邮件 canary 的新证据

标题页模板修复后，`MAIL_REWARD_DAILY` 的 targeted canary 使用批次
`20260803T051513646718+0800`。这次已经排除了“标题页无法识别”的旧根因：Maa 成功完成
`open_function_panel` 和 `open_mail`，游戏确实进入了邮件详情页；失败结果为：

```text
CLI exit code = 1
status = failed
postcondition = mail
error_code = WORKFLOW_TIMEOUT
action_counts = {open_function_panel: 1, open_mail: 1}
```

该任务的 `run.json` 已正常终结，且没有残留 runner、MaaPiCli 或 ADB 子进程，所以“证据收尾”
这部分已经生效。但失败发生在业务子进程的 300 秒预算内：`require_task_boundary()` 在标题页到
主页的恢复阶段耗时约 3 分 40 秒，随后邮件页面识别和收尾没有足够时间；失败现场停在邮件详情页，
画面显示“删除已读”，没有形成可领取标记的成功证据。

这暴露出当前设计仍把三个不同责任混在一个预算里：

1. `MJA_Game_Ready`：标题页/加载页到已验证主页；
2. 业务任务：邮件页面入口、领取或已完成判断；
3. 任务失败后的 `MJA_Game_Recover`：把当前页面交接回主页。

修复方向因此不是继续增加 `MAIL_REWARD_DAILY` 的总超时，而是把游戏就绪和失败恢复变成独立 Maa
entry，给它们独立、有限的预算；业务任务只在已验证主页后开始。邮件 Pipeline 还必须明确覆盖
“有可领取邮件”“没有可领取邮件/已读邮件”和“关闭邮件回主页”三个后置分支。这个证据已经写入
改造计划，未完成前不能宣称全量成功。

## 14. 11:39 蜃影推荐阵容现场复核

最新 targeted run 位于
`install/debug/runs/daily/shadow_ruins_daily/2026-08-03T11:18:00.273080+08:00/`，结果为：

```text
status = failed
postcondition = shadow_formation_page
error_code = WORKFLOW_POSTCONDITION_MISSING
```

Maa 日志同时确认了当前帧 OCR 框 `[1085,599,90,27]`、文本“使用阵容”，并确认 Maa
Controller 的输入作业已完成：11:38 的 `post_swipe(1130,613 -> 1131,614, 100ms)` 有
`touch_down` 和 `touch_up` 记录，但页面仍停在推荐阵容页。更早的同坐标普通
`post_click(1130,613)` 也没有页面变化；随后通过独立 Maa ADB Controller 做的
`touch_down -> 450ms -> touch_up` 复核同样没有变化。

所以这次失败不能再归因于“没有识别到按钮”或“坐标没有送到 Maa”。当前未确认的根因是该
Unity 推荐阵容控件对当前输入事件/页面状态的接受条件；在未建立可重复的状态变化证据前，
不能把动作计数当成成功，也不应继续堆叠未经验证的触控变体。这个问题应作为 Phase 3 的
独立控件 canary 处理，不得阻塞其他任务的独立调度。

## 15. 12:35 蜃影有界重试现场

随后启动的单项 runner 位于：

`install/debug/runs/daily/shadow_ruins_daily/2026-08-03T12:35:31.003532+08:00/`

该次运行实际通过 Maa ADB Controller 依次执行了：

```text
dismiss_shadow_battle_failure
advance_shadow_foreground_triplet
apply_shadow_recommended_team
use_shadow_recommended_team
close_shadow_recommended_team
battle
```

之后又重复经历了两轮“战斗失败 → 清理 → 再战斗”，`action-trace.jsonl` 中共有 3 次
`dismiss_shadow_battle_failure` 和 2 次重新 `battle`；页面没有形成成功、奖励或主页后置条件。
`run.json` 在中断前仍为 `running`，中断后被终结为 `failed`，但没有可信的业务错误码；外层
`aggregate-latest.json` 为 `interrupted`，`remaining_task_ids` 仍保留
`SHADOW_RUINS_DAILY`。当前没有残留 `android_daily_run`、`MaaPiCli` 或 Agent 子进程。

这次取证确认两点：

1. “输入作业完成”不等于“页面状态改变”，推荐阵容控件仍没有可重复的视觉后置条件；
2. 在同一战斗失败循环超过两次后继续增加总超时只会延长无效运行，不会提高成功概率。

因此本次 runner 按 skill 的有界重试规则中止并保留现场，是正确的操作结果；但它当然不是
全量成功。下一步必须先完成 `MJA_Game_Ready`/`MJA_Game_Recover` 的独立预算、蜃影控件
canary 和任务自有终态，再重新进入 17 项全量门禁。
