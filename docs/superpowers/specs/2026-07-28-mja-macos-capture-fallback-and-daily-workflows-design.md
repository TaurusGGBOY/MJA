# MJA macOS 截图回退与剑之川日常任务迁移设计

## 1. 目标

本阶段解决 MJA 在当前 macOS 27 Apple Silicon 环境下无法通过 MaaFramework `MacOSController` 截取《对决！剑之川》iOS 兼容窗口的问题，并将既有稳定人工工作流中的 17 个日常任务迁移为可由 MaaFramework 和 MFAAvalonia 前台运行的任务。

交付结果必须同时满足：

- MFAAvalonia 和 MaaPiCli 继续使用标准 `MacOS` 控制器，无需额外后台服务。
- 当前游戏窗口可稳定截图、识别和输入。
- 17 个任务均有独立入口、明确安全边界和可审计结果。
- 每个任务完成单元、夹具和真实游戏验收后，才标记为通过。
- 允许验收过程消耗非付费游戏资源；任何真实付费入口都必须停止。

## 2. 已确认约束

- 目标机器：当前 Apple Silicon Mac。
- 目标系统：macOS 27.0（26A5388g）。
- 目标游戏：本机 `/Applications/对决！剑之川.app` 中运行的 iOS 版本。
- 游戏 Bundle Identifier：`com.hanjiasongshu.dr22`。
- MaaFramework 基线：`v5.12.2`。
- GUI 目标：MFAAvalonia。
- 自动化以前台方式运行；不增加 LaunchAgent、守护进程或常驻 PlayTools 服务。
- 用户已授权实机执行全部 17 个任务，并允许消耗体力、食物、凝晶、扫荡券等非付费资源。
- Apple Pay、人民币价格、充值、付费礼包或其他真实付费确认不在授权范围内。
- 不修改或覆盖用户在 `/Users/gaoguobin/project/MaaFramework` 中的未提交内容。
- 不提交或暂存用户当前对 `AGENTS.md` 的修改。

## 3. 问题诊断

当前运行中的游戏窗口由 iOS 兼容包装进程提供：

- 进程可执行文件位于临时 `Wrapper/ProductName.app/ProductName` 路径。
- 窗口所有者显示为“对决！剑之川”。
- 主窗口为 layer 0，当前逻辑边界为 `1051×820`。
- 游戏进程没有监听 PlayTools 默认端口或其他本地控制端口，因此不能直接改用 `PlayCoverController`。

MaaFramework `v5.12.2` 的 `ScreenCaptureKitScreencap` 在调用 `SCShareableContent` 时返回失败，导致每次 MAA 截图失败。系统设置中的终端、ChatGPT、MFAAvalonia、Python 和 python3.14 均已启用录屏权限，因此继续重复请求权限不能解决该窗口的枚举失败。

同一环境下已验证以下 CoreGraphics 路径可用：

1. 通过 `CGWindowListCopyWindowInfo` 读取窗口 ID 1828 的逻辑边界。
2. 以该边界调用 `CGWindowListCreateImage`，使用 `OnScreenOnly` 和 `NominalResolution`。
3. 返回图像尺寸为 `1051×820`，与 MaaFramework 历史成功截图一致。

直接使用 `IncludingWindow` 截取该 iOS 窗口仍会失败，因此回退实现必须截取前台可见的窗口矩形，而不是依赖 WindowServer 单窗口图像。

## 4. 方案选择

### 4.1 采用：修补 Maa macOS 控制单元

保留 ProjectInterface 中的 `MacOS` 控制器，并为 `libMaaMacOSControlUnit.dylib` 增加 CoreGraphics 区域截图回退。MFAAvalonia、MaaPiCli、Tasker 和现有 Python Agent 无需改变控制器协议。

该方案兼顾当前问题修复、GUI 兼容和后续任务复用。

### 4.2 不采用：Python CustomController

Python `CustomController` 可快速实现截图和输入，但 MaaPiCli/MFAAvalonia 不能从 ProjectInterface 配置直接构造该控制器，会形成独立运行入口，不符合最终 GUI 目标。

### 4.3 不采用：本地 PlayTools 兼容服务

实现 PlayTools 协议后可使用 `PlayCoverController`，但需要额外前台进程、端口管理、生命周期管理和协议维护。游戏本身不是 PlayCover 环境，该复杂度没有必要。

## 5. 总体架构

```text
MFAAvalonia / MaaPiCli
          |
          v
MaaFramework MacOSController
          |
          +-- ScreenCaptureKit（首选，首次成功则继续使用）
          |
          +-- CoreGraphicsRegion（失败后，本次连接内缓存为回退）
          |
          v
共享导航与安全动作层
          |
          v
17 个独立任务 pipeline / 复杂任务状态机
          |
          v
诊断、窗口恢复与逐任务验收资料
```

项目新增内容按职责组织：

```text
MJA/
├── native/
│   └── maafw-macos-fallback/
│       ├── patches/
│       ├── build.sh
│       └── README.md
├── vendor/
│   └── maafw/v5.12.2/macos-arm64/
│       └── libMaaMacOSControlUnit.dylib
├── assets/resource/
│   ├── pipeline/
│   │   ├── common/
│   │   └── daily/
│   └── image/
├── agent/
│   ├── actions/
│   ├── recognizers/
│   └── workflows/
├── tools/
│   ├── setup.py
│   └── verify_macos_controller.py
└── diagnostics/                 # 本地生成，不提交 Git
```

## 6. macOS 截图回退

### 6.1 后端选择

每次控制器连接从 `ScreenCaptureKit` 开始：

1. 首次截图成功，连接期间继续使用 ScreenCaptureKit。
2. `SCShareableContent`、目标窗口查找或截图请求失败时，记录具体错误并尝试 CoreGraphics 区域截图。
3. CoreGraphics 首次成功后，将当前连接的后端固定为 `CoreGraphicsRegion`，避免每帧重复打印 ScreenCaptureKit 错误。
4. 两种后端都失败时，返回控制器截图失败，不产生输入。

后端选择只在当前连接内缓存。下一次新连接仍先尝试 ScreenCaptureKit，以便系统或 MaaFramework 修复后自动恢复官方路径。

### 6.2 CoreGraphicsRegion 算法

CoreGraphics 回退执行以下步骤：

1. 以控制器创建时的窗口 ID 调用 `CGWindowListCopyWindowInfo`。
2. 验证窗口存在、位于当前用户会话、layer 为 0、alpha 非零且边界为合理横屏尺寸。
3. 读取窗口逻辑坐标和尺寸。
4. 以窗口矩形调用 `CGWindowListCreateImage`：
   - window option：`kCGWindowListOptionOnScreenOnly`
   - relative window：`kCGNullWindowID`
   - image option：`kCGWindowImageBoundsIgnoreFraming | kCGWindowImageNominalResolution`
5. 将返回图像通过确定的 CoreGraphics bitmap context 归一化为 BGRA，再转换为 OpenCV BGR。
6. 校验输出宽高与窗口逻辑尺寸一致、图像非空且步长有效。
7. 返回 `cv::Mat` 给原有 MaaFramework 控制器后处理流程。

该方法截取的是屏幕上可见的窗口区域，因此截图前置条件是游戏窗口处于前台、未最小化且未被其他窗口遮挡。现有 `WindowLifecycle` 负责启动、置前和固定窗口；执行期间用户不应切换窗口。

### 6.3 输入与坐标

回退图像使用 nominal resolution，图像尺寸与窗口逻辑尺寸一致，因此 MaaFramework 的截图坐标、现有窗口坐标映射和 `GlobalEvent` 输入继续使用同一尺度，不引入 Retina 2 倍坐标偏差。

现有 `MacOSForegroundClick` 保留，并扩展同一安全模型下的滑动和长按动作。每次输入前必须：

- 确认准备态窗口 ID 未变化。
- 将游戏置于前台。
- 确认当前识别结果或页面标记仍有效。
- 将识别坐标映射到当前窗口边界。
- 执行一次有上限的输入并等待后置状态。

### 6.4 构建与分发

修补版控制单元从 MaaFramework `v5.12.2` 的干净源码快照构建，不在本地参考仓库中直接修改。

仓库同时保存：

- 最小源码 patch。
- 可重复构建命令和依赖说明。
- 当前 macOS arm64 的修补版 dylib。
- 基础版本、构建输入和输出 SHA-256。
- MaaFramework 对应的许可证和来源说明。

`tools/setup.py` 先安装官方 `v5.12.2` 运行库，再核对官方基线，最后覆盖单个 `libMaaMacOSControlUnit.dylib`。版本或哈希不匹配时停止安装，不把修补库应用到未知 MaaFramework 版本。

### 6.5 权限与运行宿主

CoreGraphics 回退仍受 macOS TCC 屏幕录制权限约束，不是权限绕过。MFAAvalonia 实机运行使用 MFAAvalonia 的已授权宿主；CLI 验收从已授权的“终端”启动。直接从未授权的 tmux、编辑器或其他父进程启动时，权限检查失败并给出稳定错误，不继续创建任务。

显式安装命令负责调用系统原生屏幕录制和辅助功能授权请求，让用户只处理 macOS 自身的确认界面。正常任务运行只检查权限，不在无人值守执行过程中突然弹出授权窗口。

## 7. 任务目录与风险分级

迁移源以 `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily` 为业务真值。旧 `jianzhichuan_maa` 只作为模板、坐标和历史失败证据来源，不直接视为已验证实现。

| 顺序 | 任务 ID | 中文任务 | 风险级别 |
| ---: | --- | --- | --- |
| 1 | `MAIL_REWARD_DAILY` | 邮件奖励 | 普通 |
| 2 | `SHOP_FREE_GIFT_DAILY` | 商城每日免费礼包 | 受保护领取 |
| 3 | `WEEKLY_FREE_GIFT_MONDAY` | 周一免费礼包 | 受保护领取 |
| 4 | `TRIAL_SWORD_DAILY` | 试剑奖励与免费次数 | 受保护领取 |
| 5 | `FREE_APPRAISAL_DAILY` | 免费鉴宝 | 受保护领取 |
| 6 | `BUY_TEA_DAILY` | 购买茶叶 | 消耗型 |
| 7 | `COLLECTION_DEPLOYMENT_DAILY` | 采集部署领取 | 普通 |
| 8 | `HERO_DISPATCH_DAILY` | 侠客派遣 | 状态型 |
| 9 | `SHADOW_RUINS_DAILY` | 蜃影武墟 | 战斗型 |
| 10 | `SPEND_CONDENSATE_DAILY` | 消耗凝晶 | 消耗型 |
| 11 | `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | 武学研习与突破 | 消耗型、状态型 |
| 12 | `EAT_STAMINA_FOOD_DAILY` | 食用体力食物 | 消耗型 |
| 13 | `DUNGEON_SWEEP_DAILY` | 副本扫荡 | 消耗型 |
| 14 | `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | 剑林资源体力消耗 | 消耗型、战斗型 |
| 15 | `RING_CHALLENGE_DAILY` | 擂台挑战 | 消耗型、战斗型 |
| 16 | `DAILY_TASK_REWARD_CLAIM_DAILY` | 日常任务奖励领取 | 普通 |
| 17 | `BATTLE_PASS_REWARD_DAILY` | 战令奖励领取 | 受保护领取 |

## 8. Pipeline 与状态机设计

### 8.1 共享页面导航

以下页面识别和导航作为共享组件，不在 17 个任务中复制：

- 主界面
- 功能面板
- 邮件、商城、背包、日常、武学研习
- 画卷、偃武世界、云州
- 万用商店、采集部署、侠客派遣、蜃影武墟
- 试剑、鉴宝、副本、战令
- 剑林资源和擂台

共享导航节点必须同时识别父页面标记和目标入口。任务结束时只通过已识别的关闭、返回或主页控件恢复到已知页面，不使用 Escape 或猜测性空白点击。

### 8.2 识别策略

- 稳定图标、按钮和页面装饰优先使用 TemplateMatch。
- 按钮文字、进度、分数、剩余时间和资源类型使用 OCR。
- 色彩和局部几何只作为辅助条件，不单独授权有副作用的动作。
- 每个有副作用的动作都必须由同一帧中的页面标记和目标状态共同授权。
- 固定相对坐标只允许用于已识别页面上的稳定控件，并必须声明页面前置条件；禁止全局绝对坐标盲点。

### 8.3 任务状态机

简单任务由标准 MAA pipeline 编排。侠客派遣、蜃影武墟、武学研习、剑林资源和擂台等动态任务使用 Python Agent 中的确定性状态机，但仍遵循统一循环：

```text
截图 -> 识别允许状态集合 -> 选择唯一动作 -> 执行一次 -> 验证后置状态
```

每个状态声明：

- 允许的页面和视觉证据。
- 唯一动作及其资源副作用。
- 后置状态。
- 重试次数和总步骤上限。
- 已完成、暂不可用、安全阻止和失败分支。

不存在唯一安全动作时停止，而不是选择最可能的坐标。

### 8.4 独立任务与日常预设

17 个任务分别注册到 `assets/interface.json`，可在 MFAAvalonia 中单独运行和验收。全部单项通过后，再启用按旧稳定顺序执行的“剑之川日常”预设。

单项任务之间不依赖进程内隐藏状态。日常预设只复用已知父页面以减少往返，并为每个子任务保留独立结果。

## 9. 安全边界

### 9.1 真实付费硬停止

以下任一视觉或 OCR 信号出现时，当前任务和日常预设立即停止：

- `¥`、`￥` 或人民币价格。
- Apple Pay、购买、支付、充值、月卡或付费礼包。
- 需要系统账户、密码、生物识别或支付确认的弹窗。
- 无法确认货币类型的购买对话框。

停止后保存截图和识别证据，不点击确认或取消之外的未知区域；若安全关闭方式不唯一，则保持原屏幕并退出。

### 9.2 非付费资源消耗

已授权任务可消耗旧稳定工作流明确要求的非付费资源。每个任务必须定义单次运行上限，例如食物使用次数、购买次数、扫荡次数、战斗次数和派遣队伍数。

状态机不得通过“直到资源耗尽”的无界循环实现任务。达到上限但后置状态仍未满足时，任务失败并留存证据。

### 9.3 其他停止条件

- 登录或安全验证。
- 游戏更新、资源下载或维护提示。
- 未知页面持续超过任务超时。
- 窗口 ID、尺寸或前台状态异常。
- 识别结果存在多个冲突目标。

## 10. 结果模型、恢复与诊断

每个任务返回以下之一：

- `completed`：本次执行完成目标且后置状态已验证。
- `already_complete`：进入任务后确认今日已完成，未重复消耗资源。
- `not_eligible`：例如非周一运行周礼包任务。
- `blocked_safety`：触发付费、登录或未知安全边界。
- `failed`：截图、识别、输入、超时或后置验证失败。

`blocked_safety` 和 `failed` 默认终止聚合日常流程。`already_complete` 和符合计划的 `not_eligible` 可继续下一个任务。

每个任务使用独立诊断目录：

```text
diagnostics/<YYYY-MM-DD>/<任务 ID>/<run-id>/
├── result.json
├── agent.log
├── maafw.log
├── before.png
├── after.png
├── failure.png
└── action-trace.jsonl
```

`result.json` 记录控制器后端、窗口 ID、截图尺寸、任务状态、资源动作计数、节点耗时和稳定错误码。任务结束、失败或取消后继续使用现有幂等窗口恢复机制。

## 11. 分批实现顺序

### 批次 0：控制器与邮件回归

- 构建并安装截图回退。
- 连续只读截图稳定性测试。
- 重跑现有邮件菜单闭环，确认主界面、功能面板和邮件导航没有回归。

### 批次 1：普通和免费领取

- `MAIL_REWARD_DAILY`
- `SHOP_FREE_GIFT_DAILY`
- `WEEKLY_FREE_GIFT_MONDAY`
- `TRIAL_SWORD_DAILY`
- `FREE_APPRAISAL_DAILY`
- `COLLECTION_DEPLOYMENT_DAILY`
- `DAILY_TASK_REWARD_CLAIM_DAILY`
- `BATTLE_PASS_REWARD_DAILY`

### 批次 2：状态型和直接消耗

- `HERO_DISPATCH_DAILY`
- `BUY_TEA_DAILY`
- `SPEND_CONDENSATE_DAILY`
- `MARTIAL_STUDY_BREAKTHROUGH_DAILY`
- `EAT_STAMINA_FOOD_DAILY`
- `DUNGEON_SWEEP_DAILY`

### 批次 3：战斗和动态分支

- `SHADOW_RUINS_DAILY`
- `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`
- `RING_CHALLENGE_DAILY`

每个批次内按“实现一个、验证一个、再开始下一个”的顺序推进，不先批量生成未经实机验证的 pipeline。

## 12. 验证标准

### 12.1 控制器验证

- 修补库的版本和 SHA-256 与 manifest 一致。
- ScreenCaptureKit 成功时不进入回退。
- 当前游戏窗口上 ScreenCaptureKit 失败后只切换一次回退。
- 连续至少 50 帧截图成功，尺寸稳定、图像非空、没有 Retina 坐标漂移。
- 主界面到功能面板、邮件页再回主界面的真实点击路径通过。
- 窗口被遮挡、最小化或 ID 失效时安全失败。

### 12.2 每个任务的自动化验证

- pipeline 和 ProjectInterface schema 通过。
- 所有模板、OCR 模型和 Agent 入口存在。
- 单元测试覆盖正常、已完成、重试上限和安全阻止分支。
- 至少包含入口页、可执行状态、已完成状态和危险弹窗夹具。
- 在夹具上执行无输入识别测试，结果与预期一致。

### 12.3 每个任务的实机验证

每个任务独立满足：

1. 从当前 checkout 组装并启动，排除旧运行目录和旧进程。
2. 保存输入前的全屏证据和 MAA 控制器截图。
3. 通过真实 UI 输入执行完整用户路径。
4. 保存输入后的全屏证据和 MAA 控制器截图。
5. 通过页面状态、日常进度、按钮消失、剩余次数或奖励状态进行独立确认。
6. 在安全且不会重复消耗资源时立即重跑，验证 `already_complete` no-op。
7. 保存命令、日志、动作轨迹和结果文件，使验证可复现。

周一或活动条件限定任务在当前不可执行时保持 `not_eligible` 或 `live-pending`，不得用夹具测试冒充实机完成。任务只有在所需真实分支得到验证后才标记为 `live_verified`。

### 12.4 聚合日常验证

17 个单项任务全部达到要求后，运行一次完整“剑之川日常”预设，确认：

- 任务顺序正确。
- 已完成任务安全跳过。
- 共享页面复用不改变单项结果。
- 任一安全阻止或失败会终止后续输入。
- 结束后窗口和此前前台应用恢复。

## 13. 验收标准

以下条件全部满足后，本阶段完成：

1. MaaFramework macOS 控制器可在当前游戏窗口稳定截图。
2. MFAAvalonia 和 MaaPiCli 使用同一修补库和资源。
3. 原邮件闭环无回归。
4. 17 个任务均可单独显示、运行并产生结构化结果。
5. 17 个任务均通过自动化测试和规定的真实 UI 验收。
6. 消耗型任务不超过声明上限。
7. 所有真实付费入口均被硬停止规则覆盖。
8. 未知状态下不执行盲点或键盘操作。
9. 每个任务均有可复查的本地证据目录。
10. 聚合“剑之川日常”预设通过最终验收。

## 14. 不在本阶段范围内

- 后台或无前台窗口运行。
- Intel Mac、Windows、Android 模拟器或其他机器适配。
- 游戏账号登录、验证码或安全验证自动化。
- 绕过 Apple TCC 权限。
- PlayCover 注入或 PlayTools 常驻服务。
- 自动确认任何真实付费交易。
- 修改 MFAAvalonia 源码。
- 将修补库应用到 MaaFramework `v5.12.2` 之外的未知版本。

## 15. 参考

- 当前项目：`/Users/gaoguobin/project/MJA`
- MaaFramework：`/Users/gaoguobin/project/MaaFramework`
- 稳定业务工作流：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily`
- 旧 MAA 尝试：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa`
- 现有邮件闭环设计：`docs/superpowers/specs/2026-07-27-mja-macos-mail-smoke-test-design.md`
