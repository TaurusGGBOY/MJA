# GAME_START 启动恢复时序与任务规则整合实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or **superpowers:executing-plans** to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先把 `GAME_START` 改成一条可解释、可复验的启动链路：只有确实无法继续时才重启 APP；重启后按固定等待和点击顺序进入游戏，最后才判断主页。随后把此前已经确认的任务成功/已完成规则一并落地，并保持失败只记录、不在运行中擅自修复。

**Architecture:** 用 MFW Pipeline 的线性节点表达固定时序，只保留“主页已在前台”与“执行一次重启启动流程”这两个必要分支。Launcher 视为启动过程中的中间状态，不是失败。主页最终只由右上角 `画卷/画券` 的 OCR 作为 `GAME_READY` 依据；所有旧的多层页面门禁、递归重启和恢复耗尽分支从 `GAME_START` 主路由移除。

**Tech Stack:** MAA/MFW Pipeline JSON、现有 `RestartGameSurface` 与 `StartApp` 动作、OCR、pytest、MFW 资源静态检查和单任务 live acceptance。

## Global Constraints

- 本次计划阶段只写计划，不修改业务代码、不启动游戏、不执行真实任务。
- 实施顺序固定为 `GAME_START` → `GAME_START` 单任务验收 → 其余任务规则；在 `GAME_START` 通过前不启动批量任务。
- 保留当前工作区已有改动，实施时只修改本计划列出的文件；不得用回滚或覆盖方式清理用户改动。
- 不新增哈希、颜色背景门禁、复杂状态机、无明确事故目标的 threshold 或重复重启限制。必要的单次动作超时只用于避免永久挂起，不作为业务判断条件。
- 失败时只产生一条一眼可读的失败记录，包含失败阶段、直接现象、根因分类、最后截图/日志路径；不在同一轮自动改代码或自动重跑同一任务。
- Android 模拟器继续使用 `-gpu host`，不改 GPU 后端，不通过新开 Terminal 执行项目。

## 1. 先固定 GAME_START 的行为契约与测试样本

**涉及文件：**

- `assets/resource/base/pipeline/startup/game_start.json`
- `assets/resource/base/pipeline/common/home_recovery.json`
- `assets/resource/base/pipeline/common/terminal.json`
- `tests/test_mfw_startup_pipeline.py`
- `tests/test_game_start_r15_sigkill_relaunch.py`
- `tests/fixtures/startup/manifest.json`
- `tests/fixtures/startup/launcher.png`

- [ ] 记录当前候选 `install/mfw-unified-repair-20260814-r36` 的启动图和现有脏工作区状态，确认基线不包含本次实施产生的文件。
- [ ] 把启动验收写成固定时序测试，测试关注节点顺序和等待值，不依赖真实等待：

  | 顺序 | 行为 | 允许的判断 |
  |---|---|---|
  | 0 | 先看应用是否已经是主页 | 只认右上角 `画卷/画券`；已是主页则直接成功 |
  | 1 | 确实不是主页时执行一次 APP 重启 | Launcher 是中间状态，不记失败 |
  | 2 | 如果重启后停在 Launcher，执行一次 `StartApp` 游戏切回 | 不递归重启，不进入旧的恢复耗尽循环 |
  | 3 | 应用切回后等待 20 秒 | 等待期间不做页面门禁和提前失败判断 |
  | 4 | OCR 识别并点击 `开始游戏`（实际文案可能带“点击”前缀） | 只要求按钮文字出现并点击 |
  | 5 | 等待 5 秒 | 不插入其他页面探测 |
  | 6 | OCR 识别并点击 `进入游戏` | 只要求按钮文字出现并点击 |
  | 7 | 等待 30 秒 | 30 秒结束前不判断主页 |
  | 8 | 判断是否到达主页 | 只认右上角 `画卷/画券` |

- [ ] 删除/改写当前 R15 测试中“禁止 Launcher handoff”的旧断言，改为验证 Launcher 可继续进入游戏、`StartApp` 最多经过一次、启动流程不存在自身递归。
- [ ] 在启动 fixture 清单中补齐三类可复验画面：Launcher、包含 `开始游戏` 的启动页、包含 `进入游戏` 的二次页；继续复用现有 `launcher.png`，新增样本放在 `tests/fixtures/startup/`。
- [ ] 增加失败阶段断言，至少能区分“未找到开始游戏”“未找到进入游戏”“30 秒后仍未到主页”“Launcher handoff 未进入 APP”，禁止只报告“未识别到主页”。

## 2. 按契约重写 GAME_START 主路由

**涉及文件：**

- `assets/resource/base/pipeline/startup/game_start.json`
- `assets/resource/base/pipeline/common/home_recovery.json`
- `assets/resource/base/pipeline/common/terminal.json`
- `agent/custom/action/restart_game.py`（仅核对接口，不改变其为 stop/start 的单一职责）

- [ ] 保留主页短路：如果启动入口已经能通过右上角 `画卷/画券` OCR 判断为主页，直接进入 `GAME_READY`，不重启 APP。
- [ ] 把非主页情况统一导向一次受控重启。重启动作完成后，若画面仍是 Launcher，调用现有 `MJA_GAME_LAUNCH`/`StartApp` 完成一次游戏切回；Launcher 本身不触发失败。
- [ ] 以“应用切回后”为 20 秒计时起点，加入明确的 20 秒等待节点；移除等待期间的旧页面识别、弹窗门禁和提前 `GAME_READY` 判断。
- [ ] 20 秒结束后，只通过 OCR 找到并点击 `开始游戏`；点击后固定等待 5 秒，再只通过 OCR 找到并点击 `进入游戏`。
- [ ] 第二次点击后固定等待 30 秒；30 秒结束前不做主页判定，不根据加载动画、黑屏、旧页面、推荐页等中间状态提前失败。
- [ ] 最终 `GAME_READY` 只保留右上角 `画卷/画券` OCR。删除此前额外的主页条件、颜色背景识别和不相关的面板条件。
- [ ] 从 `GAME_START` 主路由移除旧的 stale chest、persistent black、跨地图弹窗等花式恢复分支；这些状态不再触发隐式重启链。需要报告时直接给出最后画面和阶段化失败原因。
- [ ] 移除 `MJA_GAME_START`、`MJA_GAME_LAUNCH` 和恢复节点之间的自循环，以及把一次启动失败自动扩展成多轮重启的路径。保留终端失败记录能力，但不把 `recovery_exhausted` 当作正常流程门禁。
- [ ] 不修改 `RestartGameSurface` 的 stop/start 语义；20 秒、5 秒、30 秒都由 Pipeline 节点表达，避免把业务时序藏进 Python 状态机。

## 3. GAME_START 静态检查与真实验收

**涉及文件/产物：**

- `install/mfw-unified-repair-20260814-r36/resource/base/pipeline/...`（由资源构建流程生成，不手工与源文件分叉）
- `tests/test_mfw_startup_pipeline.py`
- `tests/test_game_start_r15_sigkill_relaunch.py`
- `tests/fixtures/startup/manifest.json`

- [ ] 运行启动相关 pytest，确认时序、Launcher 中间态、唯一主页 OCR、无递归/无旧门禁全部通过。
- [ ] 用 `tools/check_mfw_resources.py` 检查源资源树和候选资源树；检查结果不得出现 JSON、引用、入口或 Pipeline 图错误。
- [ ] 重新生成候选安装目录，确认源资源与安装资源中的 `GAME_START`、`GAME_READY` 和共享终端节点一致。
- [ ] 在 MFW 中只勾选 `GAME_START` 做 live acceptance；不能把 `Tasker.Task.Succeeded` 单独当作证据，必须以本轮新鲜 `result.json` 为成功依据。
- [ ] 从 live 日志确认真实顺序为：重启/切回 APP → 20 秒 → 点击开始游戏 → 5 秒 → 点击进入游戏 → 30 秒 → 主页 OCR；记录每个阶段的截图和时间戳。
- [ ] 如果验收失败，只输出阶段化根因，不在本轮继续改动；`GAME_START` 通过后再进入后续任务。

## 4. 合并此前已经确认的任务规则

这一阶段必须在 `GAME_START` 验收通过后进行，并保持每个业务任务独立验证。涉及的资源目录为 `assets/resource/base/pipeline/daily/`，需要同步对应的 Android 资源和现有安装候选；测试沿用各任务已有的 workflow/MFW 测试文件。

- [ ] **试剑：** 当左下角出现 `领取` 且右侧为 `80` 时记为 `already_complete`，不再继续点击领取。
- [ ] **一键收获：** 点击后等待奖励弹窗最多 5 秒；弹窗出现即成功，5 秒内没有弹窗按用户规则记为 `already_complete`，不再追加数量或库存验证。
- [ ] **扫荡：** 只使用覆盖实际按钮区域的 OCR；删除 ColorMatch/白像素计数回退，避免把普通白色 UI 当成扫荡按钮。
- [ ] **免费鉴宝：** 识别到 `鉴宝一次` 即记为 `already_complete`；执行购买/领取后以结果弹窗作为成功依据，不验证剩余次数或库存。
- [ ] **体力消耗：** 体力已满或已使用 5 次即成功；不再要求额外验证数量减少。
- [ ] **SPEND_CONDENSATE_DAILY：** 不再把点击 `画卷` 后的地图页当成预期功能侧面板；移除 `名帖/商城` 的错误初始页面契约，依据实际 OCR 入口重新定义正确的购买页面和结果弹窗成功条件，并为该入口保留一张新鲜 fixture。
- [ ] **EAT_STAMINA_FOOD_DAILY：** 删除资源入口的白像素 ColorMatch；改用实际可见的 `资源` 语义 OCR/模板进入背包，再验证进入资源页后执行消耗。
- [ ] **邮件：** 删除空邮件/再次验证邮件为空的步骤；`删除已读` 存在但没有 `全部领取` 时记为 `already_complete`；有 `全部领取` 才点击并以领取结果判定成功。当前批次未执行邮件时必须明确报告“未运行/未复验”，不能沿用旧结果冒充成功。
- [ ] **派遣类任务：** 第一行任务已经进入计时即算成功；不额外因为遮挡弹窗或数量变化判失败。
- [ ] **主页识别：** 所有任务共用的 `GAME_READY` 只认右上角 `画卷/画券` OCR，删除其它两个附加条件。

## 5. 恢复批处理的失败记录和人工决策边界

**涉及文件：**

- `/Users/gaoguobin/.codex/skills/mfw-batch-repair-jianzhichuan/SKILL.md`
- `tools/mfw_live_acceptance.py` 相关的批次记录和结果文件
- 各任务现有结果目录与统一失败汇总文档

- [ ] 明确批次顺序：每个选中的任务最多先运行一次；某个任务失败或未完成时，记录直接现象和根因，然后通过下一任务的 `GAME_START` 继续，不在运行中修复代码。
- [ ] 将失败分成“启动阶段失败”“入口/页面契约失败”“点击后结果未出现”“业务前置条件导致 already_complete”“未运行/无新鲜证据”五类，汇总中必须能一眼看出类别和证据路径。
- [ ] 所有选中任务跑完一次后，统一输出失败文档并暂停等待用户决策；只有用户给出修改决策后，才实施修复并重跑失败/未完成任务。
- [ ] 删除 skill 中任何“发现失败后自动修复、自动继续修复后任务、自动扩展重试”的表述；保留“继续跑完本轮、汇总、等待人工决策、修复后重跑”的循环。
- [ ] 对未被选中或被跳过的任务单独列为“未运行”，不能混入成功或失败统计。

## 6. 最终验收标准

- [ ] `GAME_START` 在 Launcher、启动页、二次进入页和已在主页四种场景下均有明确路径；Launcher 不再直接导致失败。
- [ ] 真实运行日志中固定出现 20 秒、5 秒、30 秒三个等待阶段，且主页判断只发生在最后 30 秒之后。
- [ ] 启动流程没有颜色背景依赖、Python 状态机、额外主页门禁、递归重启或无依据的恢复耗尽失败。
- [ ] 每个已修改任务都有对应的成功、`already_complete`、失败根因和未运行测试覆盖；邮件不会再被静默遗漏。
- [ ] 先完成 `GAME_START` 单任务 live acceptance，再按独立 worktree/runner 逐个验收业务任务；不在多个 runner 中并发操作同一个模拟器。
- [ ] 最终批次报告只在所有选定任务都运行过一次后生成；报告完成后停止，等待用户统一决策。
