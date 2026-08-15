# 《对决！剑之川》Android 日常确定性聚合设计

日期：2026-08-01  
状态：方案 1 已确认，待实现  
范围：MJA Android 日常聚合执行、任务边界、已确认失败项修复与验收

## 1. 目标与不可变约束

目标是让 `daily_all` 在明天可以一次性完成当天全部日常任务；任务之间不能因为前一项留下的异常页面而产生级联假失败。任务业务步骤不重试，运行结果必须能够区分“任务本身失败”和“后续任务没有被安全执行”。

必须满足以下约束：

- 所有游戏输入继续通过 MaaFramework 的 Android ADB Controller；不使用 Computer Use、macOS 点击或裸 `adb shell input`。
- 启动阶段可以使用现有 `AdbDevice.start_app`、`LoginGate` 和运行时健康检查；不自动输入账号、验证码、支付或未知弹窗。
- 不清除游戏数据、不卸载、不重置模拟器；模拟器保持开启。
- 不为失败任务增加业务重跑、盲点点击或无限等待。
- 失败时保留诊断证据；但聚合器不能把失败画面直接交给后续任务继续执行。
- `completed` 与 `already_complete` 都是可接受的任务成功状态；`failed`、运行时异常和剩余任务都不能出现在最终全量验收结果中。

## 2. 现状证据与根因

最近一次结果见 `install/debug/runs/daily/aggregate-latest.json`，共 16 项：

- `TRIAL_SWORD_DAILY`、`HERO_DISPATCH_DAILY`：`completed`。
- `BUY_TEA_DAILY`：`already_complete`。
- 其余 13 项：`failed`。

根因分为两层：

### 2.1 聚合边界根因

`AggregateScheduler.run()` 当前会在普通任务失败后继续循环。`AggregateDailyWorkflowAction._runner()` 在下一个任务前调用 `can_resume_task()`，识别不到失败画面时调用 `return_to_home()`；但 `MaaAndroidWorkflowDriver.return_to_home()` 只处理已识别的游戏页面。当前画面一旦是 Android Launcher，既没有游戏页面标记，也没有安全的游戏内关闭控件，因此恢复失败，后续任务仍被执行。

启动脚本只在整个聚合开始前执行一次 `start_app`、登录门禁和 `require_runtime_health`。任务之间没有“前置条件已经满足”的硬门禁。最近结果中后续任务的 Launcher 截图属于同一类级联问题，不应被当作六个独立业务缺陷。

### 2.2 已确认的业务根因

- `MAIL_REWARD_DAILY`：奖励/签到弹窗阻断功能面板后置条件。
- `SHOP_FREE_GIFT_DAILY`：截图已显示“已领取”，但 `claimed` 后置识别未命中。
- `FREE_APPRAISAL_DAILY`：奖励弹窗关闭后仍停在鉴宝页，没有完成主页边界。
- `COLLECTION_DEPLOYMENT_DAILY`：奖励弹窗关闭后仍停在画卷地图，没有完成主页边界。
- `SHADOW_RUINS_DAILY`：第二次战斗后的奖励弹窗未关闭，后续前进动作被阻断。
- `SPEND_CONDENSATE_DAILY`：出现 `no current-frame recognition box for yanwu_world_tab`，说明动作使用了当前帧之外的识别框。
- `MARTIAL_STUDY_BREAKTHROUGH_DAILY`：功能面板已经打开，但 `panel` 识别模板未命中。
- `EAT_STAMINA_FOOD_DAILY`、`DUNGEON_SWEEP_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`、`RING_CHALLENGE_DAILY`、`DAILY_TASK_REWARD_CLAIM_DAILY`、`BATTLE_PASS_REWARD_DAILY`：主要由 Launcher 级联失败造成；在边界修复后重新验证，若仍失败再按新的证据处理。

## 3. 总体架构

采用“运行门禁 + 单次任务执行 + 成功后归一化”的结构。

### 3.1 运行门禁

聚合开始时由 Android 运行环境门禁完成一次确定性检查：设备可用、游戏包已安装、游戏在前台、登录状态已就绪、存储/网络/截图能力正常，并且 Maa 首帧能识别为游戏主页。门禁复用现有 `AdbDevice` 和 `LoginGate` 能力，通过依赖注入或运行上下文提供给聚合动作；不在 workflow 中另造输入通道。

任务边界只做状态验证，不在失败后重跑任务。若游戏不在前台或当前画面不是受支持的游戏边界，聚合应停止并留下 `ANDROID_GAME_NOT_FOREGROUND` 或边界诊断，而不是继续执行后续任务。

### 3.2 任务执行与边界

每个任务严格执行一次：

1. 验证开始前的游戏前台和已知主页边界。
2. 调用现有 workflow engine，保持每个动作的新帧识别、授权和动作上限。
3. 只有 `completed` 或 `already_complete` 才允许进入成功清场。
4. 通过已识别的游戏内页面/关闭控件回到主页。
5. 在新截图上再次验证主页，并记录独立的 `after` 证据。

任务自身的业务后置条件仍保留在 `TaskResult`；“任务完成后已回到主页”作为独立的任务边界条件记录，不能用任务内部页面识别替代。

### 3.3 聚合控制

聚合器改为失败即停：

- 任务失败、边界清场失败、运行门禁失败或运行时异常都会停止后续调度。
- 已完成任务的 checkpoint 和诊断仍然写入。
- `remaining_task_ids` 必须准确列出尚未安全执行的任务。
- 不再产生“聚合表面上执行完 16 项、实际后 6 项全在 Launcher 上盲跑”的结果。

如需再次执行，使用新的明确运行请求；那是新的验收轮次，不是本次任务内部的隐式重试。

## 4. 组件与职责

### 4.1 `AggregateDailyWorkflowAction`

- 在创建 Maa driver 时注入 Android 运行时门禁能力。
- 在聚合开始前执行一次运行门禁。
- 在每个任务开始前执行只读边界验证。
- 将任务结果、边界结果和诊断生命周期交给 scheduler/diagnostics。
- 保留现有窗口准备逻辑，不新增 macOS 输入路径。

### 4.2 `MaaAndroidWorkflowDriver`

- 继续独占游戏画面捕获、Maa 识别和 ADB Controller 输入。
- 将 Launcher/非游戏前台识别为不可恢复边界，不对未知画面猜测点击。
- `return_to_home()` 成功必须以主页新帧识别为准；失败返回明确结果。
- 扩展已知的安全清场序列：邮件奖励弹窗、商城/鉴宝/武学/背包/副本/画卷/派遣/蜃影/日常与战令奖励页面。
- 所有新动作仍使用当前帧授权的识别框或固定的、已有页面标记授权的安全 ROI。

### 4.3 `AggregateScheduler`

- 保持工作流目录顺序和周一过滤逻辑。
- 任务返回非成功状态时立即生成 checkpoint 并停止。
- 保持 `KeyboardInterrupt` 与运行时异常的现有诊断语义。
- 为“任务失败后停止”增加覆盖测试，更新原先验证“继续执行任务失败”的测试预期。

### 4.4 Android 运行时适配层

复用 `AdbDevice.foreground_package()`、`start_app()`、`require_runtime_health()` 和 `LoginGate.wait_until_ready()`。真实运行使用 Android 环境变量与当前 `AndroidConfig`/SDK 路径创建适配器；单元测试使用 fake adapter 验证前台、登录和边界分支。适配器不负责游戏业务输入，不绕过 Maa Controller。

## 5. 已确认业务修复方向

这些修复必须以当前帧证据和后置条件为准，不通过放宽安全阈值解决：

- 邮件：将奖励结果弹窗的识别、关闭和功能面板/主页边界串成完整状态；弹窗存在时不能误判功能面板已就绪。
- 商城免费礼包：增加“已领取/售罄/领取结果”的稳定后置证据，允许已领取状态返回 `already_complete`，不把截图已领取判为失败。
- 鉴宝与采集：奖励关闭后继续执行已识别的页面关闭序列，并要求主页新帧；不能只关闭奖励层就报告成功。
- 蜃影：每次战斗结果和奖励弹窗分别关闭并验证探索页，再允许前进；未识别奖励层时停止。
- 偃武凝晶：所有动作使用当前识别帧的 `yanwu_world_tab`/页面证据；识别框不存在时返回清晰失败，不复用旧框。
- 武学突破：补齐功能面板的稳定识别资源/回退证据，等待页面完成渲染后再判断成功卡片；没有成功卡片时不报告完成。
- 其余 Launcher 级联任务：先由新的边界控制隔离；只有在真实重跑中仍出现独立失败时，依据新的诊断逐项修复。

## 6. 错误处理与安全策略

错误分为三类：

1. `TaskResult.FAILED`：任务业务后置条件或动作验证失败。记录任务前后帧、动作轨迹和错误码，停止聚合。
2. 边界失败：任务成功但不能安全回主页，或任务开始前不是受支持的游戏边界。记录边界截图，停止聚合，不猜测点击。
3. 运行时失败：设备、网络、存储、登录或 Maa Controller 异常。沿用现有 runtime error 语义，停止聚合。

不自动处理登录、验证码、支付和未知弹窗；这些情况只能保留现场并向运行报告暴露。失败后不调用业务 workflow 第二次，也不把失败画面交给下一个任务。

## 7. 测试与验收

### 7.1 自动化测试

- Android 运行门禁：前台正确、Launcher、登录提示、网络/存储失败、截图失败。
- 聚合 scheduler：成功任务继续；第一个失败任务停止；`remaining_task_ids` 与 checkpoint 正确。
- 任务边界：成功后清场成功变为 `home`；清场失败变为边界错误；失败任务保留现场。
- Maa driver：Launcher 不盲点；所有新增清场分支需要页面标记和关闭标记双重授权。
- 业务 workflow：邮件、商城、鉴宝、采集、蜃影、偃武、武学的 fixture/动作/后置条件覆盖。

### 7.2 Android 实机验收顺序

先执行静态测试和单任务 live smoke，再执行完整 `daily_all`。对最近一次失败的任务，按原聚合顺序重新执行：

1. `MAIL_REWARD_DAILY`
2. `SHOP_FREE_GIFT_DAILY`
3. `FREE_APPRAISAL_DAILY`
4. `COLLECTION_DEPLOYMENT_DAILY`
5. `SHADOW_RUINS_DAILY`
6. `SPEND_CONDENSATE_DAILY`
7. `MARTIAL_STUDY_BREAKTHROUGH_DAILY`
8. `EAT_STAMINA_FOOD_DAILY`
9. `DUNGEON_SWEEP_DAILY`
10. `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`
11. `RING_CHALLENGE_DAILY`
12. `DAILY_TASK_REWARD_CLAIM_DAILY`
13. `BATTLE_PASS_REWARD_DAILY`

每项都必须有成功或已完成结果和边界 `after` 证据；若某项失败，停止这一验收轮次并修复该项，不跳过后续任务冒充全量通过。最后执行一次全量聚合，验收条件为：

- 聚合状态为 `completed`；
- 所有选中任务均为 `completed` 或 `already_complete`；
- `remaining_task_ids` 为空；
- 没有 `WORKFLOW_POSTCONDITION_MISSING`、`WORKFLOW_DRIVER_FAILED`、边界失败或 Launcher 截图；
- 每个任务都有独立结果和主页边界证据。

## 8. 不在本次范围内

- 重写所有 workflow 为一个大状态机。
- 为失败任务增加自动重试或无限轮询。
- 自动登录、验证码、支付、购买确认或未知弹窗处理。
- 清理模拟器数据、改变游戏账号状态或修改 GUI 展示层。

