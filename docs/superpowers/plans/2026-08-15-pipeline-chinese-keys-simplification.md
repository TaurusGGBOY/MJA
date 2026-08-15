# Pipeline 中文节点键与流程精简实施计划

目标：把正式 pipeline 的节点键统一为清晰的中文名称，并在不运行真实游戏流程的前提下，逐个精简主干流程、保留必要防御和明确失败边界。

架构：以 assets/resource/base/pipeline 作为唯一正式 pipeline 源。公共导航、启动流程和日常业务分别保持现有边界；节点改名时同步维护所有引用，流程精简只在所属 pipeline 内完成，跨 pipeline 的公共能力继续复用。

技术范围：Maa/MFW Pipeline JSON、现有任务入口、静态资源校验、离线单元测试和 Git 独立提交。

全局约束：

- 不启动游戏、模拟器、ADB、MFW runner，也不执行真实 pipeline。
- 每个 pipeline 的修改由独立 sub-agent 在独立 worktree 中完成，并由该 sub-agent 直接提交。
- 保留主干进入、必要页面识别、必要副作用限制、成功或已完成判断、明确失败终点和正常回主页边界。
- 删除重复探测、不可达节点、重复开关页、无业务价值的重复复核、无依据的恢复分支和无界循环。
- 不修改任务标识、动作标识、模板文件路径、Maa 协议字段和项目既有安全限制，除非它们只是被改名节点的引用。
- 保留用户已有的 AGENTS.md 工作区修改，不把它混入本次提交。

## 文件范围

公共 pipeline：

- assets/resource/base/pipeline/common/home_boundary.json
- assets/resource/base/pipeline/common/home_recovery.json
- assets/resource/base/pipeline/common/known_popups.json
- assets/resource/base/pipeline/common/terminal.json

启动 pipeline：

- assets/resource/base/pipeline/startup/game_start.json
- assets/resource/base/pipeline/startup/game_stop.json

日常 pipeline：

- assets/resource/base/pipeline/daily/battle_pass_reward_daily.json
- assets/resource/base/pipeline/daily/break_array_martial_daily.json
- assets/resource/base/pipeline/daily/buy_tea_daily.json
- assets/resource/base/pipeline/daily/collection_deployment_daily.json
- assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json
- assets/resource/base/pipeline/daily/dungeon_sweep_daily.json
- assets/resource/base/pipeline/daily/eat_stamina_food_daily.json
- assets/resource/base/pipeline/daily/equipment_decompose_daily.json
- assets/resource/base/pipeline/daily/free_appraisal_daily.json
- assets/resource/base/pipeline/daily/guild_activity_challenge_daily.json
- assets/resource/base/pipeline/daily/guild_affairs_daily.json
- assets/resource/base/pipeline/daily/guild_donation_daily.json
- assets/resource/base/pipeline/daily/hero_dispatch_daily.json
- assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json
- assets/resource/base/pipeline/daily/mail_reward_daily.json
- assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json
- assets/resource/base/pipeline/daily/ring_challenge_daily.json
- assets/resource/base/pipeline/daily/shadow_ruins_daily.json
- assets/resource/base/pipeline/daily/shop_free_gift_daily.json
- assets/resource/base/pipeline/daily/spend_condensate_daily.json
- assets/resource/base/pipeline/daily/trial_sword_daily.json
- assets/resource/base/pipeline/daily/weekly_free_gift_monday.json

同步检查范围：assets/tasks、tests 中直接读取节点名称的静态契约、tools/check_mfw_resources.py 和其他只负责解析或校验 pipeline 节点的代码。只有节点引用需要同步时才修改这些文件。

## 执行任务

### 任务一：建立节点和引用清单

- [x] 记录 28 个正式 pipeline 的顶层节点、每个节点的前进引用和错误引用。
- [x] 区分公共节点、启动节点、业务节点和仅供识别的资源节点，确认哪些名称跨文件复用。
- [x] 以现有静态测试和资源校验为基线，明确改名后必须保持的入口、终点、引用完整性和安全限制。

### 任务二：迁移公共节点名称

- [x] 由独立 sub-agent 处理四个公共 pipeline，并将公共节点键改为中文。
- [x] 同步公共节点在启动和日常 pipeline 中的引用，以及任务入口和静态契约中的引用。
- [x] 保留公共恢复、弹窗关闭、停止、失败记录和终止语义，不因改名删除必要边界。
- [x] sub-agent 完成离线检查后直接提交，并记录提交标识。

### 任务三：迁移并精简启动流程

- [x] 由独立 sub-agent 处理 game_start 和 game_stop。
- [x] 保留已验证的启动主干、必要的启动失败终点、一次性重启边界和主页成功判断。
- [x] 删除重复等待、重复启动、不可达恢复分支和把中间状态误判为失败的冗余路径；不改变停止游戏的独立职责。
- [x] 同步启动任务入口和启动静态测试中的节点引用。
- [x] sub-agent 完成离线检查后直接提交，并记录提交标识。

### 任务四：逐个迁移并精简日常流程

- [x] 为 22 个日常 pipeline 分别分配独立 sub-agent/worktree，写入范围只覆盖对应 pipeline 及其明确的任务入口引用。
- [x] 每个 pipeline 将本地节点键改为中文，并同步本文件内的前进、错误、跳转和识别组合引用。
- [x] 每个 pipeline 只保留一条可读的主干和必要的正常防御：入口确认、动作授权、结果确认、已完成分支、有限重试、失败记录和回主页。
- [x] 删除重复探测、无效自循环、重复打开或关闭同一页面、只为猜测未知画面的分支，以及已经由公共 pipeline 覆盖的重复恢复流程。
- [x] 对会产生点击、领取、购买、战斗、分解或其他副作用的节点保留一次性限制、目标证据和结果确认；不删除付费或资源消耗门禁。
- [x] 对每个 pipeline 先做静态图检查，再由 sub-agent 直接提交；禁止以真实运行结果作为本轮完成条件。

### 任务五：同步静态契约并做离线验收

- [x] 更新本次改名直接影响的静态测试、任务入口和资源校验逻辑，使它们验证中文节点名称和相同的流程语义。
- [x] 验证所有 pipeline 都能解析为合法 JSON，所有前进、错误和跳转引用都能解析到现有节点或合法外部节点。
- [x] 验证正式 pipeline 的顶层节点键不再使用英文标识；识别资源键、任务标识、动作标识、路径和协议字段按全局约束保留。
- [x] 验证每个入口都有成功、已完成或明确失败出口；副作用节点具有限制；流程没有无界循环和明显不可达主干。
- [x] 只运行本地静态检查、资源校验和离线测试，不启动真实 pipeline。
- [x] 检查所有 sub-agent 提交已经集成，保持每个独立提交，不改动用户已有的 AGENTS.md 修改。

## 完成标准

- 28 个正式 pipeline 的节点键均为中文且引用无悬空。
- 每个 pipeline 都保留可读的主干流程和必要防御，删除经静态分析确认的冗余流程。
- 离线 JSON、引用、资源和本次改动相关的聚焦测试检查通过；仓库中仍有一批针对已删除历史分支的旧回归测试，未将其伪装成通过；真实游戏流程留给用户后续手动验证。
- Git 历史包含各 sub-agent 的独立提交，工作区未纳入 AGENTS.md 的既有修改。
