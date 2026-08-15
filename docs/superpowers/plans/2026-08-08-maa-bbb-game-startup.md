# Maa_bbb 同构游戏启动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MJA 的 Android 游戏启动完全重构为 Maa_bbb 的画面驱动启动路由，消除启动即 `StopApp`、固定等待后误判、无条件 Back、未知页假失败和 `StopTask` 假成功；覆盖实机观测到的白屏、黑屏、标题页和加载页变体。

**Architecture:** `MJA_GAME_START` 成为 Maa_bbb 式父路由：先识别当前画面，已知临时状态通过 `[JumpBack]` 处理后回到父路由，黑屏只等待，主页视觉命中才结束成功，最后才用幂等 `StartApp` 作为未知画面的兜底。`StopApp` 从启动链彻底移出并成为独立、默认不勾选的关闭任务；每个日常任务继续通过 `[JumpBack]MJA_GAME_START` 复用同一启动能力。

**Tech Stack:** MaaFramework Pipeline v5、ProjectInterface v2、MFW macOS arm64、MaaFramework ADB Controller、JSON/JSONC 资源、Python 3.12、pytest、MJA MFW 安装与资源校验工具。

## Global Constraints

- Maa_bbb 忠实度基线固定为本地 `/Users/gaoguobin/project/Maa_bbb` 的 `main` 分支提交 `d45534a9deee7f1279cfb11ad2271c0e9b61185e`。
- 忠实复用 Maa_bbb 的启动控制流，不复制《崩坏 3》包名、坐标、模板、业务弹窗名称或 Win32 专用逻辑。
- 启动链不得包含 `StopApp`、`ClickKey`、Android Back、ESC、盲点点击、`MJA_GAME_BACK_*` 或未知页面 `StopTask`。
- 默认启动模式必须先识别当前页面；只有所有已知状态都未命中时，才执行 `StartApp`。
- `StartApp` 固定使用 `com.hanjiasongshu.dr22/.MainActivity`；独立关闭任务固定使用包名 `com.hanjiasongshu.dr22`。
- 黑屏必须通过纯黑画面识别进入 3000ms 无输入等待，再由 `[JumpBack]` 返回启动路由。
- 白屏是游戏启动期间的已知临时状态，必须通过全屏纯白 ColorMatch 进入 3000ms 无输入等待，再由 `[JumpBack]` 返回启动路由；不得在白屏期间反复 `StartApp`。
- 启动成功只能由新截图中的 `home/home_marker.png` 命中，并在同一成功节点通过现有 `RuntimeHealth` Controller 门禁。
- 已知公告、移动网络下载确认、更新进度、标题页、加载页、网络确认、资源更新确认、已知弹窗和已知页面必须各自识别后处理；处理完成后统一回到父路由。
- Maa_bbb 式未知状态行为固定为重新执行 `StartApp` 并回到父路由；不得恢复当前 `MJA_START_UNKNOWN_ABORT` 兜底。
- 为保持 Maa_bbb 忠实度，父启动路由不增加 Maa_bbb 基线中不存在的总超时、`max_hit`、退避或未知页失败出口；这项启动持久化语义覆盖旧 MJA 的 bounded-abort 启动设计，但不改变业务任务自身的有界动作要求。
- `RuntimeHealth` 保持窄 Controller 健康职责，不增加游戏导航、进程管理、任务排序或直接 ADB 输入。
- 游戏输入只能经过当前 MaaFramework ADB Controller；不得使用 `adb shell input` 或其他旁路输入。
- Android 模拟器必须以 `-gpu host` 运行；不得引入其他 GPU 模式、自动回退或有歧义的 host 表述。
- 不启动 Terminal.app；构建、验证和监控通过当前自动化会话执行。
- 本计划只修改游戏启动、独立关闭、相关任务声明、测试和验收证据；不修改任何日常业务动作、擂台策略、副本策略或资源预算。
- 当前工作树已有大量用户改动；每次只暂存本任务 Files 区列出的路径，不清理、不覆盖、不顺带提交其他改动。
- 实施计划正文禁止加入具体实现代码或测试代码；所有任务只给出文件、节点契约、操作、命令、预期结果和提交边界。

---

## Reference Behavior

实施前必须逐项对照以下 Maa_bbb 文件，不凭记忆改写：

| 参考文件 | 必须复用的行为 |
| --- | --- |
| `/Users/gaoguobin/project/Maa_bbb/assets/resource/base/pipeline/进入游戏/打开游戏.json` | 父启动路由、已知页面优先、普通成功节点、临时状态 `[JumpBack]`、黑屏等待、末尾 `StartApp` 和空任务兜底 |
| `/Users/gaoguobin/project/Maa_bbb/assets/resource/base/pipeline/进入游戏/停止游戏.json` | `StopApp` 与启动解耦，关闭成为独立任务 |
| `/Users/gaoguobin/project/Maa_bbb/assets/tasks/游戏启动.json` | 默认安全模式、可选极速启动模式、关闭任务默认不勾选、桌面 ESC 与 Android 资源隔离 |
| `/Users/gaoguobin/project/MaaFramework/docs/zh_cn/3.1-任务流水线协议.md` | `[JumpBack]` 返回父节点重新识别的 MaaFramework v5 语义 |

### MJA Node Fidelity Map

| Maa_bbb 职责 | MJA 节点 | 完成契约 |
| --- | --- | --- |
| `登录方式选择接口` | `MJA_GAME_START_ENTRY` | 零延迟进入统一启动路由，不管理业务队列 |
| `启动并进入游戏` | `MJA_GAME_START` | 默认 `DoNothing`，按固定顺序识别状态，临时节点均为 `[JumpBack]` |
| `成功进入游戏主菜单` | `MJA_GAME_READY` | 新截图主页模板命中并通过 `RuntimeHealth` 后正常结束 |
| `黑屏计数` | `MJA_START_BLACK_SCREEN_WAIT` | 纯黑识别、无输入、等待 3000ms、回父路由 |
| `白屏计数` | `MJA_START_WHITE_SCREEN_WAIT` | 纯白识别、无输入、等待 3000ms、回父路由 |
| `模拟器包名游戏启动` | `MJA_GAME_LAUNCH` | `StartApp` 后结束子链，由 `[JumpBack]` 回父路由 |
| `空任务` | `MJA_START_IDLE` | `DoNothing`，作为启动路由最后的无副作用占位节点 |
| `关闭游戏` | `MJA_GAME_STOP` | 只存在于独立关闭任务，使用纯包名执行 `StopApp` |

`MJA_GAME_START` 的 `next` 顺序固定如下，实施期间不得随意重排（当前为 14 项）：

1. `[JumpBack]MJA_START_ANNOUNCEMENT`
2. `[JumpBack]MJA_START_MOBILE_NETWORK_UPDATE`
3. `[JumpBack]MJA_START_UPDATE_PROGRESS`
4. `MJA_GAME_READY`
5. `[JumpBack]MJA_START_TITLE_OR_LOADING`
6. `[JumpBack]MJA_START_LOADING`
7. `[JumpBack]MJA_KNOWN_NETWORK_CONFIRM`
8. `[JumpBack]MJA_KNOWN_RESOURCE_UPDATE_CONFIRM`
9. `[JumpBack]MJA_KNOWN_POPUP_CLOSE`
10. `[JumpBack]MJA_KNOWN_PAGE_CLOSE`
11. `[JumpBack]MJA_START_BLACK_SCREEN_WAIT`
12. `[JumpBack]MJA_START_WHITE_SCREEN_WAIT`
13. `[JumpBack]MJA_GAME_LAUNCH`
14. `[JumpBack]MJA_START_IDLE`

这个顺序保证可处理状态优先于成功、成功优先于通用恢复、黑白屏等待优先于重新启动，且任何时候都不存在无条件 Back。

## File Structure

| Path | Change | Responsibility after this plan |
| --- | --- | --- |
| `assets/resource/base/pipeline/startup/game_start.json` | Rewrite | 唯一正式游戏启动路由及所有启动期状态节点 |
| `assets/resource/base/pipeline/startup/game_stop.json` | Create | 独立关闭游戏节点；启动链不再拥有 `StopApp` |
| `assets/resource/base/pipeline/common/known_popups.json` | Modify | 只保留可识别、可安全处理的公共弹窗节点；移除启动未知页假失败节点 |
| `assets/resource_android/pipeline/startup/game_start.json` | Delete | 删除未被正式 MFW interface 加载的重复启动定义，避免双源漂移 |
| `assets/tasks/游戏启动.json` | Modify | 声明启动任务、默认关闭的独立关闭任务和默认关闭的极速启动选项 |
| `tests/test_mfw_startup_pipeline.py` | Rewrite | 固定 Maa_bbb 同构启动顺序、动作边界、成功条件和禁用项 |
| `tests/test_mfw_interface.py` | Modify | 固定启动/关闭任务及极速模式在 ProjectInterface 中的声明契约 |
| `tests/test_android_resources.py` | Modify | 禁止 Android 旧资源树重新定义正式启动节点 |
| `tests/mfw/task_contract.py` | Modify | 固定所有业务任务通过 `[JumpBack]MJA_GAME_START` 复用公共启动路由 |
| `tests/fixtures/startup/manifest.json` | Modify | 描述主页、标题、弹窗、已知页、Launcher 和黑屏的预期路由 |
| `tests/fixtures/startup/launcher.png` | Create | 12:11 失败现场的 1280×720 Launcher 回归帧 |
| `tests/fixtures/startup/black_screen.png` | Create | 1280×720 纯黑启动等待回归帧 |
| `verification/mfw/live/game-startup-maa-bbb-20260808/report.md` | Create | 记录自动化、候选产物和 MFW 实机启动验收结果 |

不修改 `agent/custom/action/runtime_health.py`、任何 `assets/resource/base/pipeline/daily/*.json` 业务动作或任何旧 Python workflow；它们只作为回归边界参与验证。

---

### Task 1: Establish the Maa_bbb Startup Fidelity Contract

**Files:**

- Modify: `assets/resource/base/pipeline/startup/game_start.json:2`
- Modify: `tests/test_mfw_startup_pipeline.py:14`

**Interfaces:**

- Consumes: Maa_bbb `启动并进入游戏` 的父路由顺序、`[JumpBack]` 语义、黑屏等待和主页成功条件。
- Produces: 可运行的 Maa_bbb 父路由骨架，以及后续临时状态清理必须满足的节点名称、顺序和成功条件。

- [x] **Step 1: Replace the obsolete startup contract assertions.**

  删除对 `MJA_GAME_START = StopApp`、`MJA_GAME_LAUNCH` 固定后继链、`MJA_GAME_BACK_*` 和 `MJA_START_UNKNOWN_ABORT` 的正向期待。新增对 Reference Behavior 中 14 项精确顺序、所有临时节点 `[JumpBack]` 前缀、`MJA_GAME_READY` 非 JumpBack 成功出口、`MJA_GAME_LAUNCH` 末端兜底和 `MJA_START_IDLE` 无副作用占位的断言。

- [x] **Step 2: Add the visual-success and black-screen assertions.**

  固定 `MJA_GAME_READY` 只能使用 `home/home_marker.png` 的新截图识别并调用 `RuntimeHealth`；固定 `MJA_START_BLACK_SCREEN_WAIT` 使用纯黑 ColorMatch、无输入动作和 3000ms 等待；固定 `MJA_GAME_LAUNCH` 只执行目标组件的 `StartApp`。

- [x] **Step 3: Run the focused test and confirm red state.**

  Run: `python3 -m pytest -q tests/test_mfw_startup_pipeline.py`

  Expected: FAIL only because现有 Pipeline 仍以 `StopApp` 开始、路由顺序不符且缺失黑屏节点；不得出现测试导入或 JSON 解析错误。

- [x] **Step 4: Implement the parent-router skeleton.**

  在现有启动文件中建立 `MJA_GAME_START_ENTRY` 和默认 `DoNothing` 的 `MJA_GAME_START`，写入 Reference Behavior 的精确 14 项顺序；同时建立唯一 `MJA_GAME_READY`、`MJA_START_BLACK_SCREEN_WAIT`、`MJA_START_WHITE_SCREEN_WAIT`、`MJA_GAME_LAUNCH` 和 `MJA_START_IDLE`。旧线性临时节点和 Back 节点暂时保留为不可达定义，Task 2 再删除，避免在一个步骤中同时改写所有识别器。

- [x] **Step 5: Run the parent-router contract and confirm green state.**

  Run: `python3 -m pytest -q tests/test_mfw_startup_pipeline.py`

  Expected: PASS；父路由、主页成功门、黑屏等待和 StartApp 兜底均满足契约。测试此时不把不可达旧节点计入最终禁止动作扫描，该扫描由 Task 2 增加；旧 fixture 测试保持原样，Task 4 再迁移。

- [x] **Step 6: Commit the parent-router skeleton.**

  Stage only: `assets/resource/base/pipeline/startup/game_start.json`, `tests/test_mfw_startup_pipeline.py`。

  Commit message: `refactor: introduce maa_bbb startup router`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。

---

### Task 2: Convert Transient States to Maa_bbb JumpBack Leaf Handlers

**Files:**

- Modify: `assets/resource/base/pipeline/startup/game_start.json:2`
- Modify: `assets/resource/base/pipeline/common/known_popups.json:2`
- Test: `tests/test_mfw_startup_pipeline.py`

**Interfaces:**

- Consumes: Task 1 已通过测试的父路由骨架和 14 项 `next` 顺序。
- Produces: 全部临时状态叶节点、零不可达旧 Back 节点、零启动假失败节点和完整禁止动作契约。

- [x] **Step 1: Add leaf-handler and destructive-action tests.**

  固定公告、移动网络下载确认、更新进度、标题页、加载页、网络确认、资源更新确认、已知弹窗和已知页面均为无内部导航的叶节点。遍历整个正式启动文件，拒绝 `StopApp`、`StopTask`、`ClickKey`、`key: 4`、`MJA_GAME_BACK_*`、重复主页成功节点和 unknown-abort；启动文件中的点击只能属于带 TemplateMatch/OCR/ColorMatch 识别证据的已知状态节点。

- [x] **Step 2: Run the expanded startup test and confirm red state.**

  Run: `python3 -m pytest -q tests/test_mfw_startup_pipeline.py`

  Expected: FAIL only because Task 1 暂留的旧 Back/线性节点仍存在，且公共 known-popup 文件仍定义 startup abort；父路由骨架相关断言保持通过。

- [x] **Step 3: Convert every transient startup state into a leaf handler.**

  公告、移动网络下载确认、更新进度、标题页、加载页、网络确认、资源更新确认、已知弹窗和已知页面只负责识别并执行自己的安全动作。删除这些节点内部通向主页、下一个弹窗、自循环或 unknown-abort 的线性后继；动作结束后由父路由上的 `[JumpBack]` 统一重新截图和重新分类。

- [x] **Step 4: Make loading states non-destructive.**

  `MJA_START_LOADING` 和 `MJA_START_UPDATE_PROGRESS` 只执行 `DoNothing` 与各自等待，不点击、不返回、不启动应用。复核 Task 1 新增的 `MJA_START_BLACK_SCREEN_WAIT` 仍严格保持 Maa_bbb 的纯黑识别、80000 像素计数、connected 检查和 3000ms 等待行为。

- [x] **Step 5: Remove all obsolete recovery chains.**

  删除 `MJA_GAME_BACK_1..5`、`MJA_GAME_HOME_CHECK_1..5`、重复的 Android 主页成功节点、重复 popup/page startup wrapper，以及所有只为旧线性链服务的 `next` 和 `on_error`。保留 Task 1 的单一 `MJA_GAME_READY`，避免 Launcher OCR、缓存帧或普通文本被误报为启动成功。

- [x] **Step 6: Remove false startup abort nodes from the common popup file.**

  删除 `MJA_START_UNKNOWN_ABORT`、`MJA_START_LOGIN_ABORT` 和 `MJA_START_CLIENT_UPDATE_ABORT`。保留并校准 `MJA_KNOWN_POPUP_CLOSE`、`MJA_KNOWN_PAGE_CLOSE`、`MJA_KNOWN_NETWORK_CONFIRM`、`MJA_KNOWN_RESOURCE_UPDATE_CONFIRM`，确保每个动作均有明确识别证据且不自行串到旧主页/Back 链。

- [x] **Step 7: Run focused static verification.**

  Run: `python3 -m pytest -q tests/test_mfw_startup_pipeline.py tests/test_mfw_pipeline_contract.py`

  Expected: PASS；启动契约不再引用任何旧 Back 或 unknown-abort 节点，公共资源仍通过引用完整性和循环校验。

- [x] **Step 8: Commit the leaf-handler cleanup.**

  Stage only: `assets/resource/base/pipeline/startup/game_start.json`, `assets/resource/base/pipeline/common/known_popups.json`, `tests/test_mfw_startup_pipeline.py`。

  Commit message: `refactor: remove destructive startup recovery`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。

---

### Task 3: Separate Game Shutdown and Add Maa_bbb Safe/Fast Startup Modes

**Files:**

- Create: `assets/resource/base/pipeline/startup/game_stop.json`
- Modify: `assets/tasks/游戏启动.json:1`
- Modify: `tests/test_mfw_interface.py:95`
- Modify: `tests/test_mfw_startup_pipeline.py`

**Interfaces:**

- Consumes: Task 2 的 `MJA_GAME_START_ENTRY`、`MJA_GAME_START` 和 `MJA_GAME_LAUNCH`。
- Produces: `GAME_START` 默认安全模式、`MJA_START_FAST_MODE` 可选极速模式、`GAME_STOP` 独立关闭任务、`MJA_GAME_STOP` 关闭节点。

- [x] **Step 1: Write task-declaration tests for both GUI tasks.**

  固定 `GAME_START` 仍属于“启动”分组并改用 `MJA_GAME_START_ENTRY`；固定新增 `GAME_STOP` 标签为“退出/关闭游戏”、默认不勾选、入口为 `MJA_GAME_STOP`；固定两个正式日常预设只包含 `GAME_START`，绝不自动包含 `GAME_STOP`。

- [x] **Step 2: Write the fast-mode option contract.**

  固定 `GAME_START` 暴露 `MJA_START_FAST_MODE`。默认 case 必须是 `No`；`No` 仅保持父路由 `DoNothing`；`Yes` 才在进入父路由前立即执行同一目标组件的 `StartApp`。选项只适用于 Android Controller，不增加 ESC、Back 或 Win32 分支。

- [x] **Step 3: Run the interface tests and confirm red state.**

  Run: `python3 -m pytest -q tests/test_mfw_interface.py tests/test_mfw_startup_pipeline.py`

  Expected: FAIL only because `GAME_STOP`、`MJA_GAME_STOP` 和 `MJA_START_FAST_MODE` 尚未声明，且 `GAME_START` 尚未指向新 entry。

- [x] **Step 4: Add the independent close Pipeline.**

  新建独立关闭文件，只定义 `MJA_GAME_STOP`；它使用 `StopApp` 和纯包名 `com.hanjiasongshu.dr22`，无启动节点引用、无后继导航、无输入动作。确认 `StopApp` 在整个正式资源树中只存在于该文件。

- [x] **Step 5: Update the ProjectInterface task file.**

  调整 `GAME_START` 入口并挂载极速选项；增加默认不勾选的 `GAME_STOP`；增加 option 定义及两种 pipeline override。不得更改正式预设顺序、其他任务默认选择或业务任务声明。

- [x] **Step 6: Run the task and interface contract suite.**

  Run: `python3 -m pytest -q tests/test_mfw_interface.py tests/test_mfw_presets.py tests/test_mfw_startup_pipeline.py`

  Expected: PASS；GUI 声明恰好包含一个启动任务和一个默认关闭的关闭任务，预设中的启动任务仍位于第一位。

- [x] **Step 7: Commit the startup-mode and shutdown separation.**

  Stage only: `assets/resource/base/pipeline/startup/game_stop.json`, `assets/tasks/游戏启动.json`, `tests/test_mfw_interface.py`, `tests/test_mfw_startup_pipeline.py`。

  Commit message: `feat: separate game shutdown from startup`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。

---

### Task 4: Remove the Duplicate Android Startup Source and Add Regression Frames

**Files:**

- Delete: `assets/resource_android/pipeline/startup/game_start.json`
- Modify: `tests/test_android_resources.py:495`
- Modify: `tests/fixtures/startup/manifest.json:1`
- Create: `tests/fixtures/startup/launcher.png`
- Create: `tests/fixtures/startup/black_screen.png`
- Test: `tests/test_mfw_startup_pipeline.py`

**Interfaces:**

- Consumes: Task 2 的唯一正式启动节点集合和 fixture case 契约。
- Produces: `assets/resource/base/pipeline/startup/` 作为唯一启动真源，Launcher 与黑屏两类历史回归证据。

- [x] **Step 1: Add a single-source resource assertion.**

  扩展 Android 资源测试，拒绝 `assets/resource_android` 中再次定义 `MJA_GAME_START_ENTRY`、`MJA_GAME_START`、`MJA_GAME_READY`、`MJA_GAME_LAUNCH` 或任何 `MJA_START_*` 正式启动节点。测试同时确认正式 MFW interface 仍只加载 `./resource/base`。

- [x] **Step 2: Run the single-source test and confirm red state.**

  Run: `python3 -m pytest -q tests/test_android_resources.py tests/test_mfw_interface.py`

  Expected: FAIL because `assets/resource_android/pipeline/startup/game_start.json` 仍重复定义启动节点。

- [x] **Step 3: Preserve the historical Launcher regression frame.**

  将 `install/mfw-android-candidate/debug/on_error/2026.08.08-12.11.32.424_MJA_MAIL_REWARD_DAILY_START.png` 复制为 `tests/fixtures/startup/launcher.png`，保持原始 1280×720 像素和 PNG 内容，不裁切、不重采样、不覆盖源证据。

- [x] **Step 4: Create the canonical black-screen regression frame.**

  创建严格 1280×720、每个 RGB 通道均为 0 的 PNG，保存为 `tests/fixtures/startup/black_screen.png`。验证图像尺寸、颜色范围和无透明通道后再写入 fixture manifest。

- [x] **Step 5: Remove the duplicate startup file and finalize the manifest.**

  删除 Android 旧资源中的重复启动定义。将 manifest 固定为 `schema_version: 2`，每个 case 只使用 `image` 和 `expected_first_node` 两个字段：Launcher 指向 `MJA_GAME_LAUNCH`，black-screen 指向 `MJA_START_BLACK_SCREEN_WAIT`，主页指向 `MJA_GAME_READY`，标题、弹窗和已知页面分别指向自己的 JumpBack 叶节点。同步重写 `tests/test_mfw_startup_pipeline.py` 的 fixture 测试，删除旧 `unknown -> MJA_COMMON_ABORT` 终态集合，并检查每个 manifest 图像真实存在且为合法 PNG。

- [x] **Step 6: Run fixture and resource tests.**

  Run: `python3 -m pytest -q tests/test_mfw_startup_pipeline.py tests/test_android_resources.py tests/test_mfw_interface.py`

  Expected: PASS；不存在启动节点双源，两个新增 fixture 均为 1280×720，Launcher 不再被解释为失败终点，黑屏不再触发输入。

- [x] **Step 7: Commit resource consolidation and fixtures.**

  Stage only: `assets/resource_android/pipeline/startup/game_start.json`, `tests/test_android_resources.py`, `tests/fixtures/startup/manifest.json`, `tests/fixtures/startup/launcher.png`, `tests/fixtures/startup/black_screen.png`。

  Commit message: `test: lock startup launcher and black screen recovery`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。

---

### Task 5: Guarantee Standalone and Manual-All Tasks Reuse the Same Startup Router

**Files:**

- Modify: `tests/mfw/task_contract.py:365`
- Modify: `tests/test_mfw_presets.py:1`
- Modify: `tests/test_mfw_startup_pipeline.py`

**Interfaces:**

- Consumes: `GAME_START` 独立任务入口和所有业务 Pipeline 已存在的 `MJA_GAME_START` 可达性。
- Produces: 单独勾选任务、手工全选、简化预设和完整预设共用同一启动语义的自动化保证。

- [x] **Step 1: Strengthen the shared-startup reachability contract.**

  对全部 canonical 业务任务断言：任务入口能够到达 `MJA_GAME_START`；业务 Pipeline 对该节点的引用必须携带 `[JumpBack]`；除 `assets/resource/base/pipeline/startup/` 外任何正式 Pipeline 都不得执行 `StartApp` 或 `StopApp`。

- [x] **Step 2: Strengthen preset and manual-all ordering assertions.**

  固定简化版和完整版中 `GAME_START` 只出现一次且位于第一位；`GAME_STOP` 不属于任何自动预设；手工全选声明中不存在 aggregate/daily_all，也不存在第二套启动入口。

- [x] **Step 3: Run the focused task-contract suite.**

  Run: `python3 -m pytest -q tests/mfw tests/test_mfw_presets.py tests/test_mfw_interface.py tests/test_mfw_startup_pipeline.py`

  Expected: PASS；每个业务任务单独运行时均能通过 JumpBack 进入统一启动路由，完整预设和手工全选不会重复启动或绕过启动路由。

- [x] **Step 4: Run the resource graph validator.**

  Run: `python3 tools/check_mfw_resources.py assets/resource/base`

  Expected: PASS；所有节点引用存在，除明确的 Maa_bbb JumpBack 父路由行为外不存在普通无界图循环，正式资源不包含禁止控制面。

- [x] **Step 5: Commit the cross-task startup contract.**

  Stage only: `tests/mfw/task_contract.py`, `tests/test_mfw_presets.py`, `tests/test_mfw_startup_pipeline.py`。

  Commit message: `test: require shared startup recovery for every task`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。

---

### Task 6: Build and Validate a Fresh MFW Candidate

**Files:**

- Modify: `tests/test_mfw_install.py:1`
- Create: `verification/mfw/live/game-startup-maa-bbb-20260808/report.md`
- Generated, never stage: `install/mfw-game-startup-maa-bbb-20260808/`

**Interfaces:**

- Consumes: 当前提交中的 ProjectInterface、tasks、正式 base resource、embedded Agent 和不可变 `install/mfw-foundation-candidate` runtime。
- Produces: 一个全新、可验证、未复用旧项目 payload 的 MFW 候选目录和自动化验收记录。

- [x] **Step 1: Add install-payload assertions.**

  固定派生候选中只存在重构后的 `resource/base/pipeline/startup/game_start.json` 和独立 `game_stop.json`；不得出现 `MJA_GAME_BACK_*`、启动期 `StopApp`、unknown-abort 或 `resource_android/pipeline/startup/game_start.json`；安装后的任务声明必须包含 `GAME_START` 和默认关闭的 `GAME_STOP`。

- [x] **Step 2: Run install tests before assembly.**

  Run: `python3 -m pytest -q tests/test_mfw_install.py tests/test_mfw_interface.py tests/test_mfw_startup_pipeline.py`

  Expected: PASS；安装器测试证明当前源码 payload 会完整替换候选中的旧项目文件。

- [x] **Step 3: Run the full static MFW suite.**

  Run: `uv run --no-project --with-requirements requirements.txt --with pytest --with ruff pytest tests/mfw tests/test_mfw_agent.py tests/test_mfw_interface.py tests/test_mfw_pipeline_contract.py tests/test_mfw_startup_pipeline.py tests/test_mfw_presets.py tests/test_mfw_install.py tests/test_android_resources.py -q`

  Expected: PASS with zero skipped startup-contract tests and zero unexpected warnings.

- [x] **Step 4: Run formatting and repository checks.**

  Run: `uv run --no-project --with ruff ruff check agent/custom tools/mfw_install.py tools/check_mfw_resources.py tests/mfw tests/test_mfw_*.py tests/test_android_resources.py`

  Expected: PASS.

  Run: `git diff --check`

  Expected: no output.

- [x] **Step 5: Assemble a new candidate from the immutable base.**

  Run: `python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-game-startup-maa-bbb-20260808`

  Expected: 新目录创建成功；不覆盖任何现有候选；build metadata 记录当前 MJA commit、既有 MFW release 和 MaaFramework runtime。

- [x] **Step 6: Verify candidate integrity and runtime resource loading.**

  Run: `python3 tools/mfw_install.py --verify-candidate install/mfw-game-startup-maa-bbb-20260808`

  Expected: PASS.

  Run: `python3 tools/load_mfw_resource.py install/mfw-game-startup-maa-bbb-20260808`

  Expected: 输出 MaaFramework version，资源 bundle 加载成功，无缺失节点、重复节点或 embedded Agent 错误。

- [x] **Step 7: Record automated results without claiming live success.**

  在报告中记录 commit、工作树相关路径、候选 metadata digest、全部命令和真实结果。此时 Android 实机章节保持“未执行”，不得提前写成通过。

- [x] **Step 8: Commit install assertions and the initial report.**

  Stage only: `tests/test_mfw_install.py`, `verification/mfw/live/game-startup-maa-bbb-20260808/report.md`。

  Commit message: `test: verify maa_bbb startup candidate payload`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。

---

### Task 7: Perform Android/MFW Live Startup Acceptance

**Files:**

- Modify: `verification/mfw/live/game-startup-maa-bbb-20260808/report.md`
- Evidence, never stage unless repository policy changes: `install/mfw-game-startup-maa-bbb-20260808/debug/`

**Interfaces:**

- Consumes: Task 6 验证通过的候选、`mja-api35-apis` AVD、MFW Android ADB Controller、默认安全启动模式和手工全选任务配置。
- Produces: 冷启动、热启动、黑屏等待、单任务复用和手工全选的真实日志证据。

- [x] **Step 1: Verify runtime preconditions without game input.**

  确认当前 QEMU 命令包含 `-gpu host` 和 `-memory 4096`；确认 `emulator-5556` 已连接；确认 MFW 绑定 Android ADB Controller；确认没有项目启动的 Terminal.app。任何一项不满足都先修复运行环境，不开始游戏输入。

- [x] **Step 2: Open only the fresh candidate.**

  保持 QEMU 的 `-gpu host`，通过系统图形入口直接打开 `install/mfw-game-startup-maa-bbb-20260808` 中的 MFW；不开启旧候选、不添加终端包装器、不启动外部 supervisor。创建独立 profile `MJA-game-startup-maa-bbb-20260808`，选择 Android Controller 和 MJA resource。

- [x] **Step 3: Validate an already-running home screen.**

  让游戏停留主页，只勾选 `GAME_START`，极速模式保持 `No`，点击运行。预期 `MJA_GAME_READY` 首轮命中，任务成功；日志中没有 `StopApp`、`StartApp`、`ClickKey`、keycode 4 或 Launcher 切换。

- [x] **Step 4: Validate Launcher-to-game recovery.**

  使用独立 `GAME_STOP` 任务关闭游戏，确认回到 Launcher；随后只运行 `GAME_START`。预期父路由先识别不到游戏状态，命中 `MJA_GAME_LAUNCH`，执行一次或多次幂等 `StartApp`，每次子链结束后 JumpBack，最终 `MJA_GAME_READY` 成功。全过程不得出现 Back、ESC、无条件点击或 unknown-abort。

- [x] **Step 5: Validate black-screen waiting.**

  在一次真实冷启动出现黑屏时保存 Maa Controller 全帧和对应日志。预期命中 `MJA_START_BLACK_SCREEN_WAIT`，连续 3000ms 不产生输入，然后回到父路由重新识别；不得在游戏窗口刚获得焦点时执行任何返回键。

- [x] **Step 6: Validate title/loading/update transitions.**

  在可观察到的标题页、加载页、公告、移动网络下载确认或更新进度中逐项保存实际出现的状态。每个状态只能命中对应识别节点并执行对应安全动作，随后 JumpBack；未实际出现的状态在报告中标记“本次未触发”，不得伪造通过。

- [ ] **Step 7: Validate a standalone daily task.**

  关闭游戏后只勾选 `DUNGEON_SWEEP_DAILY`，不额外勾选 `GAME_START`。点击运行并只观察启动阶段。预期该任务通过 `[JumpBack]MJA_GAME_START` 启动并进入主页，再返回自己的开始层；确认启动链成功后暂停，不继续评估或修改副本业务逻辑。

- [ ] **Step 8: Validate manual-all startup ordering.**

  在 MFW 图形界面手工勾选全部正式任务并确认 `GAME_START` 排在第一。点击运行，监控到 `GAME_START` 以主页视觉证据成功结束且第一个业务任务开始。确认没有 `daily_all`、没有第二次独立启动任务、没有 Launcher 假成功；随后暂停队列，本计划不验收其他业务任务结果。

- [x] **Step 9: Check OOM and process-death evidence for the acceptance window.**

  对本次时间窗只读检查 Android events、ApplicationExitInfo、kernel log 和 MFW log。预期没有游戏 `am_proc_died`、`am_kill`、`LOW_MEMORY`、OOM killer、ANR 或 crash；记录游戏 PID、PSS/RSS、模拟器可用内存和 swap，区分容量观察与启动成败。

- [x] **Step 10: Check the exact forbidden-log set.**

  在候选 debug 日志中搜索 `MJA_GAME_BACK_`、`ClickKey`、`keycode 4`、`MJA_START_UNKNOWN_ABORT`、启动期 `StopApp` 和 `Tasker.Task.Succeeded` 早于主页识别的情况。预期全部为零命中；独立 `GAME_STOP` 的 `StopApp` 必须只出现在 Step 4 的关闭任务时间窗。

- [x] **Step 11: Finalize the live report.**

  报告逐项写入时间、profile、候选 metadata、起始画面、命中节点序列、动作序列、最终画面、任务状态、内存观察和证据路径。任何未触发状态保持“未触发”，任何失败保留原始证据并停止发布候选。

- [x] **Step 12: Commit the verified report.**

  Stage only: `verification/mfw/live/game-startup-maa-bbb-20260808/report.md`。

  Commit message: `docs: record maa_bbb startup live acceptance`

  本次按用户要求保留在当前工作树，未创建新的 Git commit。Step 7、Step 8 的业务队列实机验收不属于本次只保证启动链的范围，保持未勾选，不伪造通过。

---

## Implementation Status

Task 1–6 以及 Task 7 的运行环境、热启动、独立关闭后冷启动、黑屏/白屏等待、标题/加载态、内存/进程和禁止日志检查已经完成。最终候选为 `install/mfw-game-startup-maa-bbb-20260808-final-r4`，正式入口 `tools/launch_mfw.zsh` 已指向该候选。

最终候选在 MFW embedded agent loader 完成其确定性 decorator 改写后，重新执行了候选校验并通过；`tools/mfw_install.py` 会按该运行时改写规则规范化比较 embedded agent 源文件，因此不会把 MFW 的正常加载行为误判为候选损坏。r4 还完成了 `GAME_START + MAIL_REWARD_DAILY` 的 pair 验收；启动树的不可变树哈希与冷启动已验收候选保持一致。

Task 7 Step 7（关闭后只运行 `DUNGEON_SWEEP_DAILY`）和 Step 8（手工全选业务队列）本次没有执行，因此不能把“启动链已通过”扩大解释为“所有业务任务已通过”。它们由并发任务修复计划的逐任务验收负责。

## Final Verification Gate

按顺序执行，前一步失败就停止，不运行后面的实机步骤：

1. `python3 -m pytest -q tests/test_mfw_startup_pipeline.py tests/test_mfw_interface.py tests/test_mfw_presets.py tests/test_android_resources.py tests/test_mfw_install.py`
2. `python3 -m pytest -q tests/mfw`
3. `python3 tools/check_mfw_resources.py assets/resource/base`
4. `uv run --no-project --with-requirements requirements.txt --with pytest --with ruff pytest -q`
5. `uv run --no-project --with ruff ruff check agent tools tests`
6. `git diff --check`
7. `python3 tools/mfw_install.py --verify-candidate install/mfw-game-startup-maa-bbb-20260808-final-r4`
8. `python3 tools/load_mfw_resource.py install/mfw-game-startup-maa-bbb-20260808-final-r4`
9. 完成 Task 7 的冷启动、热启动、黑屏和白屏验收；单任务业务与手工全选仍以并发任务修复计划的 live acceptance 为准。

最终完成必须同时满足：

- 正式启动资源只有一个真源。
- `GAME_START` 默认先识别当前画面，不停止已有游戏。
- Launcher 只触发 `StartApp`，不触发失败终点。
- 黑屏只触发 3000ms 等待，不产生输入。
- 所有已知临时状态处理后通过 `[JumpBack]` 回父路由。
- 主页模板新截图命中并通过 `RuntimeHealth` 后才报告成功。
- 启动子图零 `StopApp`、零 `StopTask`、零 Back、零 ESC、零 `ClickKey`。
- `GAME_STOP` 独立、默认不勾选且不在任何预设中。
- 单独运行任一业务任务和手工全选均复用同一启动路由。
- 组装候选、资源加载、自动化测试和已实际触发的实机状态全部有真实证据。

## Self-Review Traceability

| Requirement | Covered by |
| --- | --- |
| 完全采用 Maa_bbb 父启动路由 | Reference Behavior、Task 1、Task 2 |
| 不再冷启动即杀进程 | Global Constraints、Task 1、Task 3、Task 7 Step 3 |
| 不再连续 Back 退出游戏 | Task 2 Steps 1 and 5、Task 7 Step 10 |
| 黑屏只等待 | Task 1 Steps 2 and 4、Task 2 Step 4、Task 7 Step 5 |
| 主页视觉成功门 | Task 1 Steps 2 and 4、Task 7 Steps 3–4 |
| 未知 Launcher 重新 StartApp | Task 1 Step 4、Task 4 Step 5、Task 7 Step 4 |
| StopApp 独立关闭任务 | Task 3 |
| GUI 单任务、预设、手工全选一致 | Task 5、Task 7 Steps 7–8 |
| 无启动假失败和 StopTask 假成功 | Task 2 Steps 1 and 6、Task 7 Step 10 |
| GPU host、ADB Controller、无 Terminal | Global Constraints、Task 7 Steps 1–2 |
| 不触碰其他业务任务 | Global Constraints、Task 5、Task 7 Step 7 |
| 自动化、组装、资源加载、实机证据 | Tasks 6–7、Final Verification Gate |
