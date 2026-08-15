# MJA 共享状态收敛与任务可靠性专项整治 Implementation Plan

> 执行要求：按任务顺序逐项落地、逐项验证、逐项提交；在用户未明确授权前，不使用 superpowers 类执行技能。

**目标：** 在保留 MJA 严格成功证据、首错停止和新鲜结果校验的前提下，引入 Maa_bbb 式的共享状态收敛能力，使每个业务任务都能从主页、任务中间页、已知弹窗、残留页面、启动页和有限异常状态恢复，而不再由每个任务重复维护一套脆弱的启动与回退分支。

**架构：** 将当前“GAME_START 启动成功后，各任务各自处理现场”的结构改为四层：运行时健康层、共享状态收敛层、业务任务层、统一结束边界层。共享状态收敛层只负责识别当前位置并把流程送到主页、当前任务可续跑页面或明确失败终点；业务任务只负责业务动作和业务后置条件；统一结束边界负责在业务证据已封存后回到主页并提交最终结果。

**技术栈：** MaaFramework 资源管线、MFW PyQt6、Android 模拟器、项目 Python 自定义动作与事件汇、模板匹配、OCR、颜色识别、pytest、现有候选包安装和真实 MFW 验收工具。

---

## 一、不可退让的整治边界

- 不采用 Maa_bbb 的空识别无限兜底；所有等待、返回、重启和重拉起都必须有单次调用预算。
- 不降低成功标准。最终成功仍要求本轮新鲜业务结果、任务专属后置条件、原生终态和验收工具通过。
- 不允许把 `Tasker.Task.Succeeded` 单独当成业务成功。
- 不允许为提高通过率而加入无条件点击、全屏点击、付费确认点击或未知页面盲点。
- 业务任务开始标记每轮只建立一次；共享收敛和重试不得重复建立业务运行记录。
- 已经完成业务动作但尚未回到主页时，必须续做结束收敛，不能再次执行消费、领取、挑战或分解动作。
- 继续保持第一处原生失败立即停止批次，后续任务不得在同轮继续启动。
- 真实验收只允许一个 MFW runner；不增加外部 watchdog、第二套调度器或额外串行控制层。
- Android 模拟器必须保持 host GPU，实际 QEMU 参数必须包含 `-gpu host`，不得切换到软件或自动后端。
- 项目不得启动或控制 Terminal.app；命令只在当前执行环境中运行。
- 不重写已经稳定的业务判定，只把重复的公共入口、恢复和结束逻辑上收。

## 二、统一状态与恢复策略

共享收敛按以下优先级判断，前一类命中后不得继续执行后一类动作：

| 优先级 | 状态类别 | 处理原则 | 成功出口 |
|---|---|---|---|
| 1 | 付费、账号、权限及其他危险页面 | 不点击，立即留证并失败 | 无 |
| 2 | 当前任务已封存业务结果、等待结束 | 只执行回主页，不再重做业务 | 统一结束边界 |
| 3 | 当前任务可续跑页面 | 直接交还任务自己的续跑节点 | 当前任务 |
| 4 | 已知安全弹窗 | 精确关闭后重新识别 | 重新进入共享收敛 |
| 5 | 游戏主页 | 交给当前任务的主页入口 | 当前任务 |
| 6 | 其他任务或历史运行残留页 | 通过已验证的关闭、返回或主页动作退出 | 重新进入共享收敛 |
| 7 | 启动、公告、更新、网络重试和登录过渡页 | 使用对应精确处理并等待稳定 | 重新进入共享收敛 |
| 8 | Launcher、进程缺失或游戏表面失效 | 进行有预算的拉起或表面重启 | 重新进入共享收敛 |
| 9 | 黑屏、白屏、加载和动画过渡 | 先等待多帧确认，持续异常时执行一次运行时恢复 | 重新进入共享收敛 |
| 10 | 未知页面 | 连续采样、保存诊断证据、禁止点击并明确失败 | 无 |

每次共享收敛调用使用独立预算，不继承此前任务节点累计命中次数。整轮最长一百二十秒；同类安全弹窗最多处理两次；返回主页类动作最多三次；游戏表面重启最多一次；初始拉起后最多再拉起一次；加载类状态累计等待不超过三十秒；未知页面连续十秒仍无法归类时失败。预算耗尽必须进入带状态分类、最后画面和动作轨迹的明确失败终点。

## 三、目标文件结构

### 新增文件

- `docs/architecture/mfw-state-convergence.md`：状态分类、优先级、预算、恢复动作和安全边界的唯一设计真源。
- `agent/custom/support/convergence.py`：单次收敛会话、预算和状态迁移数据模型。
- `agent/custom/action/convergence_lifecycle.py`：开始收敛、消费预算、记录迁移和结束收敛的动作入口。
- `assets/resource/base/pipeline/common/state_convergence.json`：共享状态识别与恢复路由。
- `assets/resource/base/pipeline/common/home_boundary.json`：业务完成后的统一主页收敛边界。
- `tests/mfw/test_state_convergence_contract.py`：状态优先级和动作策略契约。
- `tests/mfw/test_recovery_budget_contract.py`：单次调用预算和耗尽行为契约。
- `tests/mfw/test_task_entry_convergence_contract.py`：全部任务入口一致性契约。
- `tests/mfw/test_home_boundary_contract.py`：两阶段成功和防止重复业务动作的契约。
- `tests/mfw/fixtures/convergence/manifest.json`：状态样本清单、期望分类和期望动作。

### 重点修改文件

- `assets/resource/base/pipeline/startup/game_start.json`：保留启动职责，将通用现场清理交给共享收敛。
- `assets/resource/base/pipeline/common/known_popups.json`：只保留确认安全的弹窗动作，并纳入统一优先级。
- `assets/resource/base/pipeline/common/home_recovery.json`：收敛为主页识别和安全返回能力，供两个公共边界复用。
- `assets/resource/base/pipeline/common/terminal.json`：补充预算耗尽、未知状态、危险页面和结束边界失败终点。
- `agent/custom/action/task_lifecycle.py`：增加业务结果封存状态，区分业务已完成与整轮最终成功。
- `agent/custom/action/restart_game.py`：接入单次收敛预算并输出恢复原因和恢复结果。
- `agent/custom/sink/task_flow.py`：继续保持首错停止，并把共享收敛失败纳入同一失败传播路径。
- `agent/custom/support/diagnostics.py`：记录状态序列、识别证据、动作、预算余额和最终失败分类。
- `agent/custom/support/state.py`：持久化当前任务、当前阶段和待结束状态，避免恢复后重做业务动作。
- `tools/check_mfw_resources.py`：增加公共入口、公共结束边界和禁止重复恢复分支的静态检查。
- `tools/mfw_live_acceptance.py`：保持新鲜结果和原生终态校验，并展示共享收敛轨迹摘要。
- `tools/mfw_task_selection.py`：保持状态感知选择，不重复选择本日已有合格新鲜成功证据的任务。
- `tools/mfw_install.py`：把新增公共资源和测试契约纳入候选包完整性校验。

## 四、实施任务

### Task 1：冻结状态分类、恢复矩阵和成功语义

**文件：**

- 新增 `docs/architecture/mfw-state-convergence.md`
- 新增 `tests/mfw/test_state_convergence_contract.py`
- 新增 `tests/mfw/fixtures/convergence/manifest.json`
- 修改 `tests/mfw/task_contract.py`

**步骤：**

1. 汇总现有 GAME_START、公共弹窗、主页恢复和二十二个业务任务中的重复状态，去重后形成唯一状态目录。
2. 为每种状态明确识别证据、互斥条件、优先级、安全动作、重入出口、预算和失败分类；危险页面一律没有自动点击动作。
3. 把历史失败画面按“可续跑、可安全恢复、运行时异常、未知失败”重新归档，并登记到样本清单。
4. 先建立会失败的契约测试，证明当前资源中存在重复入口、优先级冲突和无统一预算的问题。
5. 完成设计文档评审，确认状态矩阵中没有未决项、隐式兜底或无限等待。
6. 提交本任务，提交主题聚焦“冻结共享状态收敛契约”。

### Task 2：建立单次收敛会话、预算与诊断轨迹

**文件：**

- 新增 `agent/custom/support/convergence.py`
- 新增 `agent/custom/action/convergence_lifecycle.py`
- 新增 `tests/mfw/test_recovery_budget_contract.py`
- 修改 `agent/custom/support/diagnostics.py`
- 修改 `agent/custom/support/state.py`
- 修改 `agent/custom/action/restart_game.py`
- 修改 `tests/test_diagnostics.py`
- 修改 `tests/test_restart_game_action.py`

**步骤：**

1. 先为预算隔离、预算消费、预算耗尽、状态迁移记录和重启次数上限建立失败测试。
2. 建立独立于业务运行记录的收敛会话；同一业务任务可多次进入收敛，但每次有独立预算和唯一轨迹标识。
3. 让每次状态判断记录观察时间、状态类别、证据来源、选择动作、动作结果和剩余预算。
4. 让表面重启和重新拉起在动作前检查预算，动作后重新进入状态识别，不直接宣布恢复成功。
5. 验证恢复过程不会重复建立业务任务、不会覆盖已封存业务结果，也不会把旧运行证据带入新轮次。
6. 运行相关单元测试和失败传播测试，确认预算耗尽产生可读且唯一的失败原因。
7. 提交本任务，提交主题聚焦“增加有界恢复会话和诊断轨迹”。

### Task 3：落地共享状态收敛管线

**文件：**

- 新增 `assets/resource/base/pipeline/common/state_convergence.json`
- 修改 `assets/resource/base/pipeline/startup/game_start.json`
- 修改 `assets/resource/base/pipeline/common/known_popups.json`
- 修改 `assets/resource/base/pipeline/common/home_recovery.json`
- 修改 `assets/resource/base/pipeline/common/terminal.json`
- 修改 `tests/test_mfw_startup_pipeline.py`
- 修改 `tests/test_game_start_r9_network_retry_roi.py`
- 修改 `tests/test_game_start_r10_stale_victory_recovery.py`
- 修改 `tests/test_game_start_r13_shadow_exploration_recovery.py`
- 修改 `tests/test_game_start_r14_shadow_multilayer_recovery.py`
- 修改 `tests/test_game_start_r15_sigkill_relaunch.py`
- 修改 `tests/test_game_start_r16_chest_reward_stale_recovery.py`
- 修改 `tests/test_game_start_r17_persistent_black_recovery.py`

**步骤：**

1. 先补齐共享路由测试，覆盖主页、当前任务页、安全弹窗、残留胜利页、网络重试、Launcher、进程被终止、短暂黑屏和持续黑屏。
2. 将 GAME_START 收窄为“确保游戏进程和画面可观察”，不再承担所有业务残留页面的专用恢复。
3. 将通用弹窗、残留页、启动过渡页、主页和运行时异常接入统一优先级路由。
4. 对黑屏先多帧确认；只在持续异常时消费一次表面重启预算，恢复后必须重新识别真实页面。
5. 对未知页面连续采样十秒；期间只截图和记录，不执行点击，最终进入明确失败终点。
6. 运行启动与历史回归测试，确认旧有可恢复场景仍然通过，未知场景不会被误判为成功。
7. 提交本任务，提交主题聚焦“引入共享状态收敛管线”。

### Task 4：建立两阶段成功和统一主页结束边界

**文件：**

- 新增 `assets/resource/base/pipeline/common/home_boundary.json`
- 新增 `tests/mfw/test_home_boundary_contract.py`
- 修改 `agent/custom/action/task_lifecycle.py`
- 修改 `agent/custom/support/state.py`
- 修改 `assets/resource/base/pipeline/common/home_recovery.json`
- 修改 `assets/resource/base/pipeline/common/terminal.json`
- 修改 `tests/test_mfw_failure_contract.py`
- 修改 `tests/test_mfw_first_failure_stops_batch.py`

**步骤：**

1. 先建立失败测试，复现“业务已完成但回主页失败后再次进入任务并重复业务动作”的风险。
2. 将结果生命周期拆成业务证据已封存、主页收敛中、最终成功三个阶段。
3. 业务任务一旦取得专属后置条件，立即封存业务证据；此后任何恢复只能进入主页结束边界。
4. 主页结束边界只允许安全关闭、返回、主页识别和有预算的运行时恢复，不允许调用业务动作节点。
5. 只有业务证据有效且主页证据有效时才写入最终成功；结束边界失败仍输出失败，但保留“业务已完成”的诊断事实。
6. 验证第一处结束边界失败会停止整批，且不会产生第二个业务运行记录或伪造成功结果。
7. 提交本任务，提交主题聚焦“两阶段提交任务成功”。

### Task 5：统一所有任务入口并增加静态门禁

**文件：**

- 新增 `tests/mfw/test_task_entry_convergence_contract.py`
- 修改 `tools/check_mfw_resources.py`
- 修改 `tests/mfw/tasks/test_batch_a_native_pipelines.py`
- 修改 `tests/mfw/tasks/test_batch_b_native_pipelines.py`
- 修改 `tests/mfw/tasks/test_batch_c_native_pipelines.py`
- 修改全部 `assets/resource/base/pipeline/daily` 下的任务资源文件

**步骤：**

1. 先建立全量任务入口契约，要求每个任务只能建立一次业务运行记录，并同时具备当前任务页续跑、主页入口和共享收敛入口。
2. 禁止任务文件继续复制 GAME_START、网络弹窗、Launcher、黑屏和其他任务残留页的通用恢复分支。
3. 明确入口顺序：危险状态保护优先，其次是已封存业务结果、当前任务续跑页、主页入口，最后才进入共享收敛。
4. 在资源检查工具中加入门禁，发现重复通用恢复、无主页入口、无续跑入口、无统一结束边界或未知兜底时直接失败。
5. 先只调整结构引用，不修改任务专属业务识别和业务动作，降低迁移变量数量。
6. 运行资源完整性、批次原生管线和任务入口契约测试，确认二十二个任务全部满足同一入口规范。
7. 提交本任务，提交主题聚焦“统一业务任务入口契约”。

### Task 6：迁移第一批低风险领取与轻导航任务

**文件：**

- 修改 `assets/resource/base/pipeline/daily/mail_reward_daily.json`
- 修改 `assets/resource/base/pipeline/daily/shop_free_gift_daily.json`
- 修改 `assets/resource/base/pipeline/daily/buy_tea_daily.json`
- 修改 `assets/resource/base/pipeline/daily/free_appraisal_daily.json`
- 修改 `assets/resource/base/pipeline/daily/trial_sword_daily.json`
- 修改 `assets/resource/base/pipeline/daily/hero_dispatch_daily.json`
- 修改 `assets/resource/base/pipeline/daily/collection_deployment_daily.json`
- 修改对应 `tests/mfw/tasks` 下的现有专项测试

**步骤：**

1. 为每个任务补齐三种入口测试：从主页进入、从本任务中间页续跑、从已知残留页经共享收敛进入。
2. 把通用弹窗、启动恢复和主页回退移出任务文件，仅保留任务专属页面判断、业务动作和业务后置条件。
3. 将业务后置条件接入两阶段成功；封存后统一进入主页结束边界。
4. 对已完成页面继续执行任务现有策略，不把“看起来不可操作”泛化成成功；需要实际领取或实际业务变化的任务继续保持严格标准。
5. 完成离线测试后，构建一次候选包，使用同一批次连续验收，出现首错立即停止并冻结现场，不进行单任务边改边跑。
6. 该批全部产生本轮新鲜合格结果且验收工具通过后，提交本任务，提交主题聚焦“迁移低风险任务到共享收敛”。

### Task 7：迁移第二批资源、背包与消耗任务

**文件：**

- 修改 `assets/resource/base/pipeline/daily/spend_condensate_daily.json`
- 修改 `assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json`
- 修改 `assets/resource/base/pipeline/daily/eat_stamina_food_daily.json`
- 修改 `assets/resource/base/pipeline/daily/equipment_decompose_daily.json`
- 修改 `assets/resource/base/pipeline/daily/dungeon_sweep_daily.json`
- 修改对应 `tests/mfw/tasks` 下的现有专项测试

**步骤：**

1. 为资源不足、材料详情、背包列表、确认弹窗、任务中间页和业务完成页建立明确状态样本。
2. 将跨任务通用恢复迁出，只保留本任务业务路径和消费前安全检查。
3. 对会消耗资源的动作保持动作前条件、动作后变化和最终业务后置条件三重校验。
4. 验证表面重启或重新拉起后，已封存消费结果不会导致二次消费。
5. 通过该批离线测试后，按批次进行真实 MFW 验收；首错现场必须包含共享收敛轨迹和业务阶段。
6. 该批全部取得新鲜合格结果后提交，提交主题聚焦“迁移资源消耗任务到共享收敛”。

### Task 8：迁移第三批战斗与长流程任务

**文件：**

- 修改 `assets/resource/base/pipeline/daily/shadow_ruins_daily.json`
- 修改 `assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`
- 修改 `assets/resource/base/pipeline/daily/ring_challenge_daily.json`
- 修改 `assets/resource/base/pipeline/daily/break_array_martial_daily.json`
- 修改 `assets/resource/base/pipeline/daily/guild_activity_challenge_daily.json`
- 修改对应 `tests/mfw/tasks` 下的现有专项测试

**步骤：**

1. 保留各任务现有的战斗等待、胜利多层弹窗、宝箱领取、计时区域和严格业务后置条件。
2. 将战斗中的短暂黑屏与运行时持续黑屏分开；前者只等待，后者才允许消费一次表面重启预算。
3. 为战斗进行中、胜利页、奖励弹窗、探索页、任务主页和游戏主页建立互斥优先级，避免多识别器同时命中。
4. 验证重拉起后能从当前任务可续跑页面继续，无法续跑时才回主页重新进入，并且不重复已经封存的领取动作。
5. 用历史专项测试覆盖影之遗迹多层胜利、最终主页边界、宝箱弹窗、计时区域、黑屏恢复，以及剑林运行时恢复。
6. 离线测试全部通过后按整批真实验收，不因单个任务成功日志而跳过新鲜结果和原生终态检查。
7. 该批全部取得新鲜合格结果后提交，提交主题聚焦“迁移战斗长流程到共享收敛”。

### Task 9：迁移第四批公会、奖励与周常任务

**文件：**

- 修改 `assets/resource/base/pipeline/daily/guild_affairs_daily.json`
- 修改 `assets/resource/base/pipeline/daily/guild_donation_daily.json`
- 修改 `assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json`
- 修改 `assets/resource/base/pipeline/daily/battle_pass_reward_daily.json`
- 修改 `assets/resource/base/pipeline/daily/weekly_free_gift_monday.json`
- 修改对应 `tests/mfw/tasks` 下的现有专项测试

**步骤：**

1. 对公会主页、公会子页、奖励红点、领取完成态、捐赠确认和周一资格分别建立专属后置条件。
2. 公会内部页面只作为业务页面处理，不再同时承担全局恢复职责。
3. 奖励任务必须证明本轮有任务专属成功信号；仅仅回到主页不能构成成功。
4. 周常任务继续受星期和资格约束，非周一不伪造成功；真实周一验收单独留出日期窗口。
5. 完成离线测试后，先验收四个日常任务；到周一再把周常纳入同一候选包完成最终资格验收。
6. 该批全部满足对应日期策略后提交，提交主题聚焦“迁移公会奖励和周常任务到共享收敛”。

### Task 10：候选包、全量批次验收与旧恢复分支清理

**文件：**

- 修改 `tools/mfw_install.py`
- 修改 `tools/mfw_live_acceptance.py`
- 修改 `tools/mfw_task_selection.py`
- 修改 `tests/test_mfw_install.py`
- 修改 `tests/test_mfw_live_acceptance.py`
- 修改 `tests/test_mfw_task_selection.py`
- 修改 `tests/test_mfw_android_preflight.py`
- 修改 `docs/testing/mfw-concurrent-task-repair.md`
- 修改 `docs/mfw-development.md`

**步骤：**

1. 把共享收敛资源、两阶段结束边界、状态样本清单和入口契约纳入候选包完整性检查。
2. 在真实运行前检查单 runner、Android 目标、host GPU、截图新鲜度、候选包校验和当天任务选择结果。
3. 依次执行冷启动、主页启动、任务中间页续跑、已知弹窗、历史残留页、进程被终止和持续黑屏恢复验收。
4. 运行状态感知全批次，只选择当天仍缺少合格新鲜成功证据的任务；第一处失败立即停止并保留现场。
5. 每个任务都必须具备新鲜结果、允许的最终状态、任务专属后置条件、原生终态和对应截图证据；最终验收工具返回成功才算整治完成。
6. 全量通过后删除任务文件中已经被共享层取代的重复恢复节点和过期专项补丁，但保留历史回归测试。
7. 更新开发和验收文档，明确今后新增状态只能先进入统一状态目录，不得直接复制到多个任务。
8. 运行完整离线回归、资源检查、候选安装检查和最终真实批次验收。
9. 提交最终整治结果，提交主题聚焦“完成共享状态收敛全量切换”。

## 五、每轮失败后的固定处理方式

整治期间不再采用“看到一个失败画面，就在当前任务追加一个识别器”的方式。每轮失败统一执行以下流程：

1. 先判断失败属于业务逻辑、共享状态识别、恢复动作、运行时健康、结束边界还是验收证据。
2. 如果是新状态，先加入统一状态目录和样本清单，再决定它属于安全恢复还是明确失败。
3. 如果是已知状态误识别，修正互斥条件和优先级，同时对所有任务生效。
4. 如果是预算不足，只在有完整轨迹证明动作有效但时间不足时调整；不得用增大超时掩盖无效循环。
5. 如果业务已经完成，修复只能发生在结束边界，禁止重新执行业务动作。
6. 修复完成后先跑状态矩阵和对应批次离线测试，再重新构建候选包并从失败批次继续验收。

## 六、完成定义

只有同时满足以下条件，才能宣布专项整治完成并继续后续 MFW 任务：

- 二十二个任务全部使用同一共享状态收敛入口和统一主页结束边界。
- 任务文件中不再复制 GAME_START、Launcher、网络弹窗、黑屏和跨任务残留页的通用恢复逻辑。
- 所有恢复都有单次调用预算，未知状态不会点击，也不会无限等待。
- 业务结果封存后，任何重试都不会重复消费、领取、挑战、分解或捐赠。
- 历史 GAME_START 与任务专项回归全部通过。
- 候选包完整性、资源图、任务选择、首错停止和验收契约全部通过。
- Android 模拟器实际运行保持 host GPU，真实 MFW 运行期间只有一个 runner。
- 所有当日可执行任务都取得本轮新鲜合格结果；周常在合法日期窗口取得合格结果。
- 最终 `mfw_live_acceptance.py finish` 返回成功，并且没有依赖旧结果、仅日志成功或人工口头判断。

## 七、执行顺序和回滚边界

- Task 1 至 Task 5 是公共基础，必须完成后才能迁移任何业务批次。
- Task 6 至 Task 9 每批独立提交、独立构建、独立验收；某批失败不允许继续下一批。
- 每次只回滚当前任务的提交，不回滚用户已有修改，也不清理与本计划无关的脏工作区。
- 公共基础一旦进入真实候选包，不允许新旧入口混用；尚未迁移的任务通过兼容适配层进入共享收敛。
- Task 10 完成后，旧重复恢复节点才能删除；在此之前它们只允许被隔离，不允许破坏历史可回退能力。
