# MJA 全面迁移至 Maa_bbb/MFW 架构设计

日期：2026-08-05
状态：已完成方案确认与自审，待用户书面批准
范围：MJA Android ADB 生产控制面、ProjectInterface、任务 Pipeline、嵌入式 Agent、构建发布与旧架构退役

## 1. 背景

MJA 当前同时存在 MFA 任务入口、Python 聚合器、外部 supervisor、中央 workflow engine、超大 Android driver 和 Maa Pipeline。任务排序、运行时准备、页面导航、失败恢复、结果记录分散在多个控制面中，导致以下问题：

- GUI 全选时，独立任务与 `daily_all` 可能重复执行。
- 通过 shell supervisor 运行和直接从 GUI 运行具有不同的环境变量、恢复能力和失败语义。
- 业务任务依赖中央 Python driver，不能只靠自己的 Maa Pipeline 从已知状态开始并安全结束。
- 游戏返回 Launcher、任务边界失败或 Controller 异常可能被错误归因到后续业务任务。
- 运行链路与 Maa_bbb/MFW 的 ProjectInterface v2 原生模式偏离，维护成本高。

本设计采用 Maa_bbb 的生产架构作为基准：MFW 负责控制面和任务队列，ProjectInterface 负责声明，任务以独立 Maa Pipeline 为主体，Python Agent 只提供 Maa Pipeline 不擅长的窄能力。

## 2. 已确认决策

以下决策已经由用户明确确认：

1. 采用“生产架构全面迁移，保留安全内核”的方案。现有 Python 导航、调度和聚合退出生产；当前帧安全、资源上限、运行时健康和结构化诊断收缩为窄能力。
2. 第一阶段只支持 Android 模拟器 ADB。macOS 原生游戏以后通过新的 resource overlay 单独适配。
3. GUI 只展示独立任务和 MFW 预设，删除 `daily_all`，不保留隐藏的生产兼容入口。
4. 任务失败策略遵循 Maa_bbb/MFW：任务内有限恢复；已知业务失败通过 `Abort` 结束当前任务并继续；Controller、Resource、Agent 等基础设施致命失败终止任务流。
5. 不在 MFW 队列层自动重跑业务任务。
6. MFW 使用构建时最新正式发行版，不固定版本号；首期目标平台为 macOS arm64。
7. 完全遵循 Maa_bbb 的任务自判模式，不使用 MFW `speedrun`。每个 Pipeline 自己识别已完成、未开放和当天不适用。
8. 采用 Maa_bbb 骨架移植，不在现有中央架构上继续叠加适配层，也不从 Maa_bbb 新建独立仓库。
9. 新架构在当前仓库内并行建设；旧生产入口冻结。完成全量自动化与 Android 实机验收后一次性切换并删除旧生产编排。
10. MFW 使用嵌入式 Agent，运行环境按 MFW 当前要求兼容 Python 3.12。

## 3. 目标与非目标

### 3.1 目标

- 用户在 MFW 中选择“日常-完整版”或手工勾选全部任务后，每个任务只执行一次。
- 用户直接从 MFW 点击开始、使用计划任务或使用 `--direct-run` 时具有相同的执行语义。
- 每个业务任务能从主页、自己的业务页或受支持的偏航页开始；游戏未启动时可复用统一启动 Pipeline。
- 每个任务独立判断 `success`、`already_complete`、`not_eligible` 和失败，不依赖 Python 聚合器推断。
- 已知业务失败不会阻止后续独立任务；下一个任务重新经过自己的开始层和统一启动恢复。
- Controller、Resource、Agent、ADB 连接等共享基础设施失败停止整个任务流。
- 保留当前帧动作授权、资源消耗上限、运行时健康检查和任务级诊断，但这些能力不得拥有业务导航或任务排序权。
- 构建产物直接包含最新 MFW macOS arm64、MaaFramework runtime、ProjectInterface、任务资源和嵌入式 Agent。

### 3.2 非目标

- 首期不支持 `/Applications/对决！剑之川.app` 的 macOS 原生控制。
- 不保留 MFAAvalonia 作为生产 GUI。
- 不保留 `daily_all`、Python aggregate scheduler 或 shell supervisor 作为生产入口。
- 不使用 MFW `speedrun` 代替游戏内完成状态识别。
- 不自动输入账号、密码、短信验证码、实名信息或支付信息。
- 不处理未知弹窗，不进行盲点点击，不引入无限重试。
- 不复制 Maa_bbb 的崩坏三业务资源、坐标、角色脚本和 Win32 专用逻辑。

## 4. 总体架构

生产调用链固定为：

```text
MFW 最新正式版（macOS arm64）
  -> ProjectInterface v2
  -> MFW 配置档案与预设任务队列
  -> 独立任务入口
  -> 任务自己的 Maa Pipeline
  -> 可选的嵌入式窄 CustomAction/CustomRecognition
  -> MaaFramework ADB Controller
  -> Android 模拟器中的《对决！剑之川》
```

控制权必须单向流动。MFW 决定执行哪些任务及其顺序；Maa Pipeline 决定当前任务如何导航和完成；窄 Agent 只回答复杂识别、安全门禁、资源上限、运行时健康和诊断问题。Agent 不能再次建立任务队列、聚合多个业务任务或绕过 Maa Controller 发送游戏输入。

## 5. 最终目录与发布契约

最终源码布局采用 Maa_bbb 同构结构：

```text
MJA/
├── assets/
│   ├── interface.json
│   ├── tasks/
│   │   ├── 游戏启动.json
│   │   ├── 日常/
│   │   └── 工具/
│   └── resource/
│       ├── base/
│       │   ├── image/
│       │   ├── model/ocr/
│       │   └── pipeline/
│       │       ├── common/
│       │       ├── startup/
│       │       └── daily/
│       └── resource_macos/        # 后续阶段，不在首期启用
├── agent/
│   ├── main.py
│   └── custom/
│       ├── action/
│       ├── recognition/
│       └── support/
├── tools/
│   └── install.py
├── CFA_setting.json
├── requirements.txt
└── install/                       # 构建产物，不作为业务源码
```

并行迁移期间：

- 现有 `assets/interface.json` 保持旧生产入口；新接口先写入 `assets/interface.mfw.json`。
- 新增 `assets/tasks/`、`assets/resource/base/` 和 `agent/custom/`，不修改旧任务的生产入口。
- 新安装器先以 `tools/mfw_install.py` 存在，输出到隔离的验收目录。
- 切换提交将 `interface.mfw.json` 提升为 `interface.json`，将安装器提升为 `tools/install.py`，随后删除旧生产编排。

构建产物布局遵循 Maa_bbb：MFW 可执行文件与 `interface.json` 同级，资源、tasks、Agent、MaaFramework runtime 和 Python 环境使用相对路径。不得依赖开发机绝对路径。

## 6. MFW 与 ProjectInterface

### 6.1 MFW 职责

MFW 是唯一生产控制面，负责：

- 配置 ID 与多配置档案。
- Android ADB Controller 选择和连接。
- Resource 选择与加载。
- 任务勾选、排序、预设、单任务执行和批量执行。
- 计划任务、`--config-id`、`--direct-run` 和 `--force-restart`。
- 日志展示、任务状态与用户配置的外部通知。
- 嵌入式 Agent 加载。

MJA 不再实现与这些能力重复的 GUI 配置器、批次 supervisor 或生产 CLI 调度器。

### 6.2 版本策略

CI 和本地发布安装器从 `overflow65537/MFW-PyQt6` 获取构建时最新正式 release，并选择 `macos-aarch64` 资产。构建元数据记录实际 MFW tag、下载地址和校验值，以便诊断与回滚，但不在源码中固定版本。

如果最新 release 缺少 macOS arm64、产物无法加载 interface 或嵌入式 Agent，构建直接失败。没有 Android 验收环境的 CI 可以完成候选产物组装，但该产物在 ADB 连接与实机 smoke test 通过前不得发布。任何失败都不静默回退旧 MFW。

### 6.3 Interface 声明

`interface.json` 使用 interface v2 的以下原生结构：

- `controller`：首期只提供“安卓端”，类型为 `Adb`。
- `resource`：首期提供“Android 模拟器”，路径为 `./resource/base`，并限制只能搭配“安卓端”。
- `group`：至少包含“启动”“日常”“周常”“工具”。
- `import`：按功能导入 `tasks/` 下的拆分文件。
- `task`：根数组保持为空，业务任务全部来自 import。
- `preset`：提供“日常-简化版”和“日常-完整版”。
- `agent`：保留相对 Agent 入口；安装阶段根据 macOS 构建写入可执行路径并启用 embedded。

### 6.4 任务与预设

所有 17 个业务任务继续保留独立、稳定的 canonical ID：

1. `MAIL_REWARD_DAILY`
2. `SHOP_FREE_GIFT_DAILY`
3. `BUY_TEA_DAILY`
4. `FREE_APPRAISAL_DAILY`
5. `TRIAL_SWORD_DAILY`
6. `HERO_DISPATCH_DAILY`
7. `COLLECTION_DEPLOYMENT_DAILY`
8. `WEEKLY_FREE_GIFT_MONDAY`
9. `SHADOW_RUINS_DAILY`
10. `SPEND_CONDENSATE_DAILY`
11. `MARTIAL_STUDY_BREAKTHROUGH_DAILY`
12. `EAT_STAMINA_FOOD_DAILY`
13. `DUNGEON_SWEEP_DAILY`
14. `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`
15. `RING_CHALLENGE_DAILY`
16. `DAILY_TASK_REWARD_CLAIM_DAILY`
17. `BATTLE_PASS_REWARD_DAILY`

“日常-完整版”按上述业务顺序包含“启动并进入游戏”和全部 17 个任务。星期条件不满足的任务由自己的 Pipeline 返回不适用，不由 MFW 隐藏或过滤。

“日常-简化版”包含“启动并进入游戏”以及免费、非战斗、无普通资源消耗的任务：邮件、商城免费礼包、免费鉴宝、试剑免费领取、侠客派遣、采集收取、周一免费礼包、日常任务奖励和战令基础奖励。

所有业务任务仍可单独勾选。GUI 不提供 `daily_all`，因此“全选”和“完整版预设”都不会重复执行业务任务。

## 7. Maa Pipeline 设计

### 7.1 每个任务的标准结构

每个任务必须由一个自包含 Pipeline 实现：

```text
TASK-开始任务层
  -> 已完成/不适用判断
  -> 已在业务页
  -> 从主页进入业务页
  -> [JumpBack]启动并进入游戏
  -> 已知偏航恢复
  -> 有界业务动作
  -> 业务后置条件
  -> 任务成功终点 / Abort 失败终点
```

开始层必须能从主页、任务自己的业务页以及统一启动流程恢复。不得调用中央 Python driver，也不得假设前一个任务已经回到主页。

### 7.2 统一启动与回主页

公共启动 Pipeline 负责：

- 游戏未运行时执行 `StartApp`。
- 等待标题页、登录完成和主页。
- 处理已知签到、奖励、网络重试、资源更新提示和确认弹窗。
- 从已知游戏内页面通过识别到的返回或关闭控件回主页。
- 最终以新截图识别主页作为成功条件。

登录、验证码、更新客户端和未知弹窗只输出明确提示并终止当前任务，不进行猜测输入。

公共恢复节点通过 `[JumpBack]` 引用。每个任务仍拥有自己的开始层和结束语义；公共 Pipeline 不能知道业务任务列表或修改队列。

### 7.3 本地有限恢复

局部恢复使用 Maa 原生 `max_hit`、`timeout`、`on_error` 和 `[JumpBack]`：

- 只重试识别、导航和已证明幂等的动作。
- 购买、领取、消耗、挑战、确认等业务动作不能因为超时被无条件重放。
- 每个循环都有明确次数或超时上限。
- 每条 `on_error` 最终必须收敛到已知恢复节点或 `Abort`，不能形成无限环。

## 8. 嵌入式窄 Agent

### 8.1 允许职责

Agent 只保留下列能力：

- Maa 原生识别不足时的复杂图像/结构识别。
- 当前帧授权和高风险动作的组合条件验证。
- 普通游戏资源名称、数量、单次上限和每日上限验证。
- AVD/ADB、SELinux、游戏进程、前台包和内存状态的只读或项目限定健康检查。
- 任务级结构化结果、动作轨迹、截图索引和错误码记录。
- 向 MFW/Maa 发出明确的成功、已完成、不适用或 `Abort` 信号。

### 8.2 禁止职责

Agent 不得：

- 保存或执行任务队列。
- 聚合运行多个业务任务。
- 实现通用页面导航状态机。
- 根据 `MJA_CONTROLLER` 等外部环境变量猜测 MFW 已选择的 Controller。
- 绕过 `context.tasker.controller` 发送游戏输入。
- 直接处理账号、验证码、支付或未知弹窗。

### 8.3 运行时契约

Agent 从 MFW 传入的 socket 启动，并通过 `AgentServer` 使用已经建立的 Tasker/Controller。安装器将 Agent 配置为 embedded，并保证代码兼容 MFW 的 Python 3.12 环境。

AVD 创建、SDK 下载和 APK 安装属于一次性环境准备，不由 Agent 每次重做。运行时健康检查只针对配置中的项目 AVD 和游戏包，不扫描或修改其他设备。

## 9. 执行数据流

一次“日常-完整版”执行流程如下：

1. MFW 读取配置 ID，选择“安卓端”和“Android 模拟器”资源。
2. MFW 加载 `resource/base`、嵌入式 Agent 和任务配置。
3. MFW 连接 ADB Controller；连接失败时终止整个任务流。
4. MFW 执行第一个“启动并进入游戏”任务，确认项目 AVD、游戏进程和可交互游戏画面。
5. MFW 按预设顺序调用每个独立任务。
6. 任务开始层先识别已完成/不适用、自己的业务页、主页和统一启动恢复。
7. 业务动作只在当前截图满足页面、目标和资源条件时执行。
8. Pipeline 在新截图验证业务后置条件，并进入成功终点、已完成终点、正常不适用终点或 `Abort` 失败终点。
9. MFW 根据任务结果更新状态，然后执行下一项；每个下一任务重新从自己的开始层判断当前画面。
10. MFW 完成队列后执行用户配置的完成后动作和通知。

不使用 `speedrun`。同一天再次运行时，任务必须通过游戏画面识别已经完成，而不是依赖本地运行计数跳过。

## 10. 失败与恢复语义

失败分为两类：

### 10.1 任务局部失败

包括业务页面未收敛、业务后置条件缺失、执行任务所需的普通资源不足或受支持状态下的安全阻止。

- Pipeline 先进行有限的本地恢复。
- 仍不能完成时进入明确 `Abort` 终点。
- 当前任务在 MFW 中显示失败，并保存诊断。
- MFW 继续下一项；下一项通过自己的开始层和统一启动恢复重新建立状态。
- 不自动重新执行当前业务任务。

`success`、`already_complete` 和预期内的 `not_eligible` 都是正常终态。星期条件不满足、功能尚未开放或奖励已经领取时，Pipeline 不执行有副作用的动作，以成功状态结束 Maa 任务，并在结构化诊断中记录具体终态。MFW 原生任务状态只显示完成；MJA 不伪造一个 MFW 不支持的“不适用”队列状态。

### 10.2 共享基础设施失败

包括 ADB Controller 无法连接、Resource 无法加载、Agent 无法加载、MaaFramework runtime 缺失或设备不可用。

- MFW 终止整个任务流。
- 未开始任务保持等待状态。
- 不把共享故障伪装成业务任务失败。

MFW 当前版本必须通过一项兼容契约测试：`Abort` 会标记当前任务失败并继续，而显式基础设施失败会停止任务流。已观察到的“普通 Maa task failure 未发出 Abort 时可能被 UI 误标完成”不得成为 MJA 的业务失败路径；所有受支持失败出口都必须显式收敛到 `Abort`。

## 11. 安全策略

以下规则继续作为不可变约束：

- 游戏输入必须通过 MaaFramework 当前 Tasker 的 ADB Controller。
- 动作必须由当前截图中的页面和目标证据授权。
- 资源消耗必须同时满足白名单、名称/数量识别和动作上限。
- 真实货币、充值、支付、未知价格购买永久禁止。
- 登录、密码、验证码、实名和安全验证不自动输入。
- 未知页面、未知弹窗、目标不唯一和识别冲突时停止当前任务。
- 不使用裸 `adb shell input`、Computer Use 或 macOS 鼠标替代 Maa 游戏输入。
- 不清除游戏数据、不自动卸载游戏、不重置用户登录状态。

## 12. 诊断与可观测性

MFW 日志是运行主日志；MJA 窄 Agent 补充任务级结构化诊断。每次任务至少记录：

```text
debug/runs/<run-id>/<TASK_ID>/
├── result.json
├── action-trace.jsonl
├── before.png
├── after.png
└── failure.png          # 失败时
```

`result.json` 记录任务 ID、状态、开始/结束时间、动作计数、后置条件、错误码和证据相对路径。不得记录账号、密码、验证码、token 或完整个人信息。

诊断写入失败不能改变已经验证的游戏业务结果，但必须出现在 MFW 日志中。诊断模块只能观察和记录，不能决定下一个任务。

## 13. 迁移阶段

本项目过大，不作为一次无边界改动完成。实施计划按以下有序工作流拆分，但共享本设计的最终契约。

### Phase 0：冻结基线

- 保持旧生产入口可运行但停止增加新架构能力。
- 固化 17 个任务清单、顺序、资源政策、当前实机证据和回归测试。
- 为旧路径增加“冻结”标识，避免迁移期间继续扩张中央 driver。

### Phase 1：MFW 发布骨架

- 建立 Maa_bbb 同构的 tasks、resource、Agent 和安装目录。
- CI/安装器获取最新 MFW macOS arm64 与 MaaFramework runtime。
- 建立临时 `interface.mfw.json`、CFA 设置、embedded Agent 和隔离安装产物。
- 验证 MFW 启动、配置 ID、ADB 连接、资源加载、Agent 加载和直接运行。

### Phase 2：公共运行基础

- 迁移 OCR model、主页/标题页资源和 Android package 配置。
- 实现统一“启动并进入游戏”、登录等待、已知弹窗和回主页 Pipeline。
- 将运行时健康、安全门禁和诊断能力拆成窄 Agent 组件。
- 验证 MFW 的 `Abort` 继续与基础设施失败停止契约。

### Phase 3：任务迁移

按风险分三批迁移，每个任务必须完成单元、fixture、资源加载、单项实机、已完成重跑和预设串行验收后才能进入下一批。

批次 A：免费、领取和非战斗任务

- 邮件奖励
- 商城免费礼包
- 免费鉴宝
- 试剑免费领取
- 侠客派遣
- 采集收取
- 周一免费礼包
- 日常任务奖励
- 战令基础奖励

批次 B：普通资源消耗任务

- 购买茶
- 消耗凝晶
- 食用体力食物
- 剑林凝晶体力

批次 C：战斗与长流程任务

- 蜃影遗迹
- 武学研习突破
- 副本扫荡
- 擂台挑战

### Phase 4：生产切换

- 在 MFW 中执行“日常-完整版”全量 Android 实机验收。
- 将 `interface.mfw.json` 提升为正式 `interface.json`。
- 将 MFW 安装器设为默认发布入口。
- 更新 README、运行 skill、runbook 和 CI release。
- 删除 MFA 生产配置、`daily_all`、Python aggregate scheduler、外部 daily supervisor、中央业务 driver 和不再被窄 Agent 使用的 workflow engine。
- 保留一次性 Android 环境准备工具及仍被使用的安全/诊断模块。

### Phase 5：退役与回滚门

- 确认生产代码中不存在旧聚合入口和旧环境变量分支。
- 标记最后一个旧架构 release，保留可下载产物作为回滚点。
- 当前代码不保留运行时双栈开关；回滚通过发布版本完成。

## 14. 测试策略

### 14.1 静态与单元测试

- Interface v2 schema、import 路径、controller/resource 约束、预设顺序和 canonical ID。
- 安装器对最新 MFW 资产选择、校验、目录组装和相对路径的测试。
- Embedded Agent 在 Python 3.12 下的导入和注册测试。
- 窄 Action/Recognition 的安全门禁、资源上限和诊断测试。
- Pipeline JSON 解析、引用完整性、`on_error` 收敛和无无限循环检查。

### 14.2 Pipeline fixture 测试

每个任务至少覆盖：

- 主页入口。
- 已在业务页。
- 可执行状态。
- 已完成状态。
- 不适用状态。
- 已知偏航。
- 危险/未知状态。
- Abort 失败出口。

fixture 识别测试不得发送真实输入。

### 14.3 MFW 集成契约

- 完整版预设中启动任务始终第一，17 个业务任务各出现一次。
- 手工全选不会出现 `daily_all` 或重复任务。
- `Abort` 将当前任务标记为失败并继续下一任务。
- Controller/Resource/Agent 加载失败停止任务流。
- `--config-id --direct-run` 与 GUI 点击开始使用同一任务顺序和结果语义。
- 同日重跑由游戏状态判断，不依赖 speedrun 记录。

### 14.4 Android 实机验收

每个任务依次完成：

1. 从主页运行。
2. 从任务自己的业务页运行。
3. 已完成后重跑。
4. 在前一任务留下的受支持页面后串行运行。
5. 验证所有业务动作的当前帧证据和动作上限。

最终验收必须在 MFW macOS arm64 构建中完成：选择“日常-完整版”，点击开始，无外部 supervisor，17 个业务任务均只运行一次；所有适用任务成功或已完成，不适用任务明确退出，任务局部失败不会污染后续任务，共享基础设施失败会停止队列。

## 15. 发布、升级与回滚

- 每个发布产物记录 MJA commit、MFW tag、MaaFramework version、资源校验值和目标架构。
- CI 总是解析最新 MFW 正式 release，但必须先通过构建和集成契约，失败时不发布。
- 热更新配置遵循 MFW/Maa_bbb 的 `CFA_setting.json` 协议；资源与本地 `update_flag` 不一致时不得混用。
- 发布切换前保留旧架构最后一个可恢复产物和 Git tag。
- 新架构上线后若出现阻断问题，回滚整个发布产物，不在当前版本动态切回旧 supervisor。

## 16. 完成标准

只有同时满足以下条件，全面重构才算完成：

- MFW 是唯一生产 GUI 和任务队列控制面。
- 最新 MFW macOS arm64 构建能加载 MJA interface、resource 和 embedded Agent。
- 17 个任务均位于拆分的 `assets/tasks/` 中，并拥有自包含 Maa Pipeline。
- GUI 不存在 `daily_all`，完整版预设和手工全选都不会重复执行。
- 生产调用链不再导入 Python aggregate scheduler、外部 daily supervisor 或中央业务 driver。
- Agent 只包含本设计允许的窄能力，所有游戏输入仍通过当前 Maa ADB Controller。
- 每个任务可识别已完成和不适用，并且同日重跑安全。
- MFW `Abort` 继续和基础设施失败停止契约通过自动化与实机验证。
- 全量自动化测试、资源加载测试、安装验证和 Android 实机完整版验收全部通过。
- README、发布流程、运行 skill 和故障排查文档只描述 MFW 生产入口。

## 17. 实施约束与阶段门

本节是方案自审后的执行补充。后续详细实施计划必须遵守这些文件边界、依赖顺序和退出条件，不能把一个阶段简写成“整体迁移”。

### 17.1 源文件与目标文件映射

| 工作流 | 当前证据来源 | 并行建设目标 | 首批契约测试 |
| --- | --- | --- | --- |
| MFW Interface 与安装 | `assets/interface.json`、`tools/project_interface.py`、`tools/configure_mfa.py`、`tools/setup.py`、`tools/verify_install.py` | `assets/interface.mfw.json`、`tools/mfw_install.py`、`CFA_setting.json` | `tests/test_mfw_interface.py`、`tests/test_mfw_install.py` |
| 公共启动与恢复 | `assets/resource_android/pipeline/`、`agent/workflows/maa_android.py`、`agent/android/login.py` | `assets/resource/base/pipeline/common/`、`assets/resource/base/pipeline/startup/` | `tests/test_mfw_startup_pipeline.py`、`tests/test_mfw_pipeline_contract.py` |
| 窄 Agent | `agent/safety.py`、`agent/diagnostics.py`、`agent/android/runtime_gate.py`、`agent/android/config.py`、`agent/android/game.py` | `agent/custom/action/`、`agent/custom/recognition/`、`agent/custom/support/` | `tests/test_mfw_agent.py`、`tests/test_mfw_safety.py`、`tests/test_mfw_diagnostics.py` |
| 17 个独立任务 | `agent/workflows/definitions/`、`agent/workflows/catalog.py`、`agent/workflows/maa_android.py`、`assets/resource_android/pipeline/daily/` | `assets/tasks/日常/`、`assets/resource/base/pipeline/daily/` | `tests/mfw/tasks/`、`tests/test_mfw_presets.py` |
| 切换与退役 | `agent/actions/daily_workflow.py`、`agent/workflows/aggregate.py`、`agent/workflows/aggregate_report.py`、`agent/workflows/engine.py`、`tools/android_daily_run.py`、`tools/android_run.py`、`tools/run_cli.py`、`assets/resource_android/pipeline/daily/daily_all.json` | 正式 `assets/interface.json`、正式 `tools/install.py`、仅 MFW 的文档和 CI | `tests/test_mfw_cutover_contract.py` 与全量回归 |

“当前证据来源”不表示整文件复制。实施时先用测试固定可保留的安全、诊断和任务后置条件，再把这些能力移入目标边界；中央导航、任务队列和环境变量分支不得随代码一起搬入窄 Agent。

### 17.2 严格依赖顺序

后续实施计划按以下依赖图排序：

```text
MFW 版本解析与隔离安装
  -> Interface/Controller/Resource/embedded Agent 可加载
  -> 公共启动、回主页与失败传播契约
  -> 窄安全/健康/诊断组件
  -> 任务批次 A
  -> 任务批次 B
  -> 任务批次 C
  -> 完整版与手工全选实机验收
  -> 原子切换
  -> 旧生产编排删除
```

不得在公共启动和失败传播契约通过前迁移业务任务；不得在某一批任务通过单项、已完成重跑和串行验收前开始下一批；不得在完整实机验收前修改正式 `assets/interface.json` 或删除旧入口。

### 17.3 最新 MFW 的可复现构建

“使用最新正式版”只在一次构建开始时解析一次：

1. 安装器查询最新正式 release 并解析唯一的 macOS arm64 资产。
2. 立即计算资产 SHA-256，并把 tag、资产 URL、SHA-256、解析时间和 MJA commit 写入 `install/build-metadata.json`。
3. 同一次构建的安装、自动化、实机验收和发布全部使用该已解析资产，期间即使上游发布新版本也不重新解析。
4. 后续新构建再次解析最新正式版；回滚使用历史发布产物和其元数据，不重新下载“当时的最新”。

这样既不在源码固定 MFW 版本，又保证一次候选发布从测试到交付使用同一二进制。

### 17.4 失败传播实现门

在迁移第一个业务任务前，必须用最小测试任务证明以下四条路径：

- `success`、`already_complete`、`not_eligible`：Maa 任务正常完成，结构化结果保留具体终态。
- 已知业务失败和安全阻止：Pipeline 显式进入 `Abort`，MFW 标记本任务失败并继续下一个探针任务。
- 启动前的 Controller、Resource、Agent、runtime 检查失败：由 MFW 加载/连接或队列前置检查直接终止，不包装成业务 `Abort`。
- 运行中的 Controller/设备丢失：保留 Maa/MFW 的基础设施失败信号并停止队列，不由 Agent 捕获后降级为任务局部失败。

如果构建时最新 MFW 无法通过任一契约，该构建停止。不得通过本地补丁伪造通过，也不得静默降级到旧版本；先单独记录兼容性问题，再在新的设计变更中决定是否适配。

### 17.5 单任务完成门

每个 canonical task 只有同时满足以下条件才算迁移完成：

- Interface 中只有一个独立任务声明，且完整版预设中只出现一次。
- Pipeline 不调用 `daily_all`、`AggregateScheduler`、`run_selected_workflow` 或 `MaaAndroidWorkflowDriver`。
- 从主页、自己的业务页和统一启动恢复入口均可收敛。
- 可执行、已完成、正常不适用、已知偏航、危险状态和 `Abort` fixture 全部通过。
- 有副作用动作拥有当前帧证据、幂等约束、次数/资源上限和新截图后置条件。
- 单项 Android 实机通过；完成后同日重跑不重复副作用。
- 与已迁移的前后任务串行通过，且不依赖前一任务回到主页。
- 诊断结果包含 canonical ID、终态、后置条件和证据路径。

### 17.6 原子切换与删除门

并行阶段的旧、新控制面必须物理隔离：旧生产只读取正式 `assets/interface.json`；新架构只从隔离安装目录读取 `assets/interface.mfw.json`。源码测试不得把两者合并成同一个任务列表。

生产切换作为同一个不可拆分的发布变更完成，由两个连续且各自可回滚的提交组成：第一个提交提升新入口并移除旧生产入口，第二个提交在依赖归零后删除残余旧实现。两个提交必须在同一候选产物中一起验收和发布，不能把中间状态投入生产。

1. 将已验收的 MFW interface 和安装器提升为正式文件。
2. 同步更新 CI、README、运行 skill 和 runbook。
3. 在第一个提交中删除 `daily_all` 的任务声明、Pipeline 和旧生产调度入口，使正式 interface 只暴露 MFW 独立任务。
4. 重新索引代码知识图谱，检查旧聚合器、中央 driver 和旧环境变量分支的入站依赖；再用字符串搜索补查 JSON、shell、CI 和文档引用。
5. 在第二个提交中删除入站依赖归零且不再被窄 Agent 使用的残余旧实现及对应旧测试。
6. 运行 MFW 专项测试和全量 `pytest -q`，重新生成候选安装产物并做最终 smoke test。

只有入站依赖归零、全量测试通过且旧 release 产物可恢复时，才删除不再被窄 Agent 使用的 workflow engine 文件。测试文件与实现文件同步退役，不能通过跳过或批量删除测试制造绿色结果。

### 17.7 详细实施计划的最低粒度

设计批准后生成的实施计划必须：

- 按测试先行的小步骤列出准确的新建、修改和删除文件。
- 为每一步给出预期失败测试、最小实现、验证命令和预期结果。
- 把 17 个任务逐个列出，不使用“其余任务同理”代替。
- 在每个阶段门设置独立提交点；入口切换提交与残余旧代码删除提交可单独回滚，但只能作为同一个候选发布一起上线。
- 区分自动化验收和需要 Android 实机的验收，不把尚未执行的实机结果写成已通过。
