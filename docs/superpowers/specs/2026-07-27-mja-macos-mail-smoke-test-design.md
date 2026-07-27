# MJA macOS 邮件菜单闭环设计

## 1. 目标

本阶段交付一个可重复验证的最小闭环：用户在 MFAAvalonia 中启动任务后，MJA 自动启动或激活本机已登录的《对决！剑之川》iOS App，识别主界面，打开邮件界面但不领取任何内容，关闭邮件界面，并再次确认回到主界面。

该闭环用于验证 ProjectInterface、macOS 窗口控制、MaaFramework 识别、前台点击、Python Agent、日志和窗口恢复是否能在当前 Apple Silicon Mac 上协同工作。它不是日常任务迁移版本。

## 2. 已确认的约束

- 目标系统：当前 Apple Silicon Mac，macOS 27.0（26A5388g）。
- 游戏路径：`/Applications/对决！剑之川.app`。
- 游戏账号已登录；首版不处理账号登录。
- 自动化前台运行，执行期间用户不操作鼠标和键盘。
- 游戏内容区统一调整为 `1280×720`，任务结束后恢复原状态。
- 从 MFAAvalonia 启动并验收；MaaPiCli 使用同一资源进行诊断。
- 任务只打开和关闭邮件界面，严禁点击领取按钮或改变游戏资源。
- 识别失败后安全停止，不进行猜测性点击或通用弹窗恢复。
- 实机验收要求连续运行三次全部成功。
- 首版只保证当前机器，不发布 Intel Mac 或通用安装包。

## 3. 技术基线

项目固定以下运行基线，不跟随 `latest`：

- MaaFramework `v5.12.2`
- MFAAvalonia `v2.13.0-beta.5` 的 `osx-arm64` 发布包
- Python 3 项目内虚拟环境 `.venv`
- `cliclick`：当前机器路径 `/opt/homebrew/bin/cliclick`

选择 MFAAvalonia 预发布版是因为稳定版 `v2.12.2` 尚未包含本设计需要的完整 MacOS 控制器和 PI `pretask` 支持，而 `v2.13.0-beta.5` 已包含这些能力并提供 Apple Silicon 构建。

官方 MaaFramework `v5.12.2` 负责窗口截图、图像识别、任务调度和 Agent 通信。它的标准 `GlobalEvent` 点击对本游戏的临时包装进程不够可靠，因此首版不修改或 fork MaaFramework，而是在 Python Agent 中实现独立的游戏前台点击适配器。

## 4. 总体架构

MJA 保持为标准 MaaFramework ProjectInterface V2 项目：

```text
MJA/
├── assets/
│   ├── interface.json
│   └── resource/
│       ├── pipeline/
│       │   └── mail_smoke_test.json
│       └── image/
│           ├── home/
│           └── mail/
├── agent/
│   ├── main.py
│   ├── actions/
│   │   └── macos_foreground_click.py
│   ├── macos/
│   │   ├── permissions.py
│   │   ├── window_lifecycle.py
│   │   └── window_state.py
│   └── sinks/
│       └── restore_window.py
├── tools/
│   ├── setup.py
│   ├── configure_mfa.py
│   ├── run_cli.py
│   └── verify_install.py
├── tests/
├── requirements.lock
└── runtime-manifest.json
```

### 4.1 ProjectInterface

`assets/interface.json` 使用 PI V2，声明：

- 项目标识 `MJA`
- 一个 `MacOS` 控制器
- `ScreenCaptureKit` 截图
- `GlobalEvent` 输入配置，用于满足控制器初始化；业务 pipeline 不使用标准 `Click` 动作
- `display_short_side: 720`
- 一个默认任务“邮件菜单闭环测试”
- 一个 macOS `pretask`，调用 `.venv/bin/python3` 执行权限和窗口准备
- Python Agent 子进程入口 `agent/main.py`

MFAAvalonia 实例启动设置固定为：

- 程序：`/usr/bin/open`
- 参数：`-a "对决！剑之川"`
- 启动等待：60 秒
- 自动检测目标窗口：开启

`tools/configure_mfa.py` 负责生成或验证这些设置。若需要修改已有 MFAAvalonia 配置，工具先创建带时间戳的备份，再进行最小字段更新；无法安全定位配置时只输出人工配置步骤，不猜测写入位置。

本地组装后的运行根目录固定为：

```text
install/
├── MFAAvalonia.app/
├── MaaPiCli
├── interface.json
├── resource/
├── agent/
├── runtimes/
└── .venv/
```

`interface.json` 中 Agent 和 `pretask` 的解释器路径均相对于该运行根目录解析为 `.venv/bin/python3`。源码目录不直接作为 GUI 运行目录。

### 4.2 macOS 前置准备

PI `pretask` 在控制器创建前完成以下工作：

1. 使用系统 API 检查屏幕录制权限和辅助功能权限。
2. 查找游戏进程和标题匹配的窗口。
3. 原子写入原始窗口位置、尺寸、窗口 ID、进程 ID 和此前前台应用。
4. 将游戏窗口置前。
5. 使用 Accessibility API 将游戏内容区调整为 `1280×720`。
6. 重新读取窗口状态，确认尺寸调整成功后退出。

前置准备失败时返回非零退出码，MFAAvalonia 不创建任务控制器，也不执行 pipeline。

### 4.3 图像识别 pipeline

pipeline 只承担状态识别和流程编排：

```text
识别主界面
    ↓
匹配邮件入口模板
    ↓
调用 MacOSForegroundClick
    ↓
识别邮件界面固定特征
    ↓
匹配邮件关闭/返回模板
    ↓
调用 MacOSForegroundClick
    ↓
再次识别主界面
```

主界面、邮件入口、邮件界面和关闭按钮均使用从当前游戏实机截图裁剪的模板。ROI 仅覆盖对应 UI 区域。pipeline 中禁止出现邮件领取按钮的模板、ROI 或坐标。

### 4.4 前台点击适配器

`MacOSForegroundClick` 是 Maa Agent 自定义动作。它接收 MaaFramework 识别结果中的目标框，执行以下步骤：

1. 读取当前窗口边界和控制器截图分辨率。
2. 取目标框中心点，并按截图尺寸与窗口边界的比例映射到全局屏幕坐标。
3. 使用 `System Events` 将目标进程切换为前台，并等待 150 毫秒。
4. 记录当前鼠标位置。
5. 调用固定路径下的 `cliclick` 完成一次完整点击。
6. 恢复原鼠标位置。
7. 将命令退出状态和映射坐标写入 Agent 日志。

点击适配器不接受 pipeline 提供的任意绝对屏幕坐标；它只接受当前识别节点返回的目标框。这样可防止识别失败后仍执行猜测性点击。

### 4.5 窗口恢复

Agent 注册 tasker sink，监听任务成功、失败和取消事件。任一终态到达时，恢复原窗口尺寸、位置和此前前台应用。

窗口恢复必须幂等：同一状态文件重复恢复不会造成额外移动。若进程异常退出，下一次 `pretask` 发现遗留状态文件时先尝试恢复旧状态，再开始新任务。恢复失败记录独立警告，但不覆盖任务本身的失败原因。

## 5. 运行数据流

1. 用户在 MFAAvalonia 中点击“开始”。
2. MFAAvalonia 通过 `/usr/bin/open` 启动或激活游戏，并等待发现窗口。
3. PI `pretask` 检查权限、保存窗口状态、置前并调整窗口。
4. MFAAvalonia 使用窗口 ID 创建 MacOS 控制器。
5. MaaFramework 加载 `1280×720` 基准资源并连接 Python Agent。
6. pipeline 识别主界面并打开邮件界面。
7. pipeline 确认邮件界面后点击关闭按钮。
8. pipeline 再次识别主界面，成功后结束。
9. Agent sink 恢复窗口和此前前台应用。

若游戏已经运行，`open -a` 仅负责激活。若游戏冷启动后未在 60 秒内出现窗口，任务在控制器创建前失败。

MaaPiCli 诊断由 `tools/run_cli.py` 包装。包装器先执行与 GUI 相同的应用启动、权限检查和窗口准备，再启动 MaaPiCli；无论 MaaPiCli 成功、失败还是被中断，包装器都在 `finally` 中恢复窗口。MaaPiCli 仍加载组装目录中的同一份 `interface.json`、资源、Agent 和任务入口。

## 6. 超时与安全策略

- 游戏窗口发现：60 秒
- 初始主界面识别：30 秒
- 邮件界面确认：10 秒
- 返回主界面确认：10 秒

首版不处理登录、公告、更新、下载、活动弹窗或未知页面。任一识别节点超时后立即失败，不按返回键、不点击空白区域、不尝试关闭未知弹窗。

业务 pipeline 只允许两个有输入副作用的节点：邮件入口点击和邮件关闭点击。两者都必须使用 `MacOSForegroundClick`，且必须依赖当前节点成功识别出的目标框。

## 7. 错误模型与诊断

稳定错误码如下：

- `PERMISSION_SCREEN_CAPTURE`
- `PERMISSION_ACCESSIBILITY`
- `APP_LAUNCH_TIMEOUT`
- `WINDOW_NOT_FOUND`
- `WINDOW_RESIZE_FAILED`
- `CONTROLLER_CONNECT_FAILED`
- `HOME_RECOGNITION_TIMEOUT`
- `MAIL_OPEN_TIMEOUT`
- `HOME_RETURN_TIMEOUT`
- `WINDOW_RESTORE_FAILED`

每次运行创建独立诊断目录：

```text
debug/runs/<时间戳>/
├── run.json
├── agent.log
├── maafw.log
├── last-screen.png
└── failure-screen.png
```

`run.json` 记录组件版本、窗口 ID、进程 ID、截图分辨率、节点时间线、耗时和稳定错误码。它不记录账号凭据。日志和截图只保存在本机，并由 `.gitignore` 排除。

失败截图在以下情况保存：权限通过但控制器连接失败、主界面超时、邮件界面超时、返回主界面超时。权限检查失败或窗口不存在时没有可用截图，只记录结构化诊断。

## 8. 安装与依赖

`tools/setup.py` 可重复执行，并完成：

1. 在 `install/.venv` 创建或复用虚拟环境。
2. 安装 `requirements.lock` 中固定版本的 Python 依赖。
3. 按 `runtime-manifest.json` 下载 MaaFramework `v5.12.2` macOS arm64 运行库。
4. 下载 MFAAvalonia `v2.13.0-beta.5` 的 `osx-arm64` 发布包。
5. 对下载文件执行 SHA-256 校验。
6. 检查 `/opt/homebrew/bin/cliclick` 可执行。
7. 将 MFAAvalonia、MaaPiCli、资源、Agent 和运行库组装到本地 `install/` 目录。
8. 重写组装后 `interface.json` 的相对运行路径，并运行 `verify_install.py`。

`runtime-manifest.json` 保存精确版本、下载 URL、目标文件名和 SHA-256。下载内容、`.venv`、`install/`、日志和实机截图不提交 Git。

首版不自动安装 Homebrew 或 `cliclick`。缺少 `cliclick` 时，安装检查失败并给出明确命令和原因。

## 9. 测试设计

### 9.1 配置测试

- `interface.json` 可被 PI V2 解析。
- 任务入口存在。
- pipeline 引用的模板文件全部存在。
- pipeline 不包含标准 `Click`、`StartApp`、邮件领取模板或领取坐标。
- 所有输入节点都使用 `MacOSForegroundClick` 且依赖识别框。

### 9.2 单元测试

- 权限状态到错误码的映射。
- 窗口状态原子保存和读取。
- 截图坐标到屏幕坐标的比例映射。
- `1280×720` 内容区调整计算。
- 遗留状态恢复。
- 窗口恢复幂等性。
- `cliclick` 不存在或返回非零时的失败传播。

### 9.3 Agent 测试

- 成功事件触发一次恢复。
- 失败事件触发一次恢复。
- 取消事件触发一次恢复。
- 多个终态通知不会重复破坏窗口状态。
- 点击前未提供识别框时拒绝执行。

### 9.4 实机验收

1. 游戏关闭状态下，从 MFAAvalonia 启动任务并完成闭环。
2. 游戏已运行状态下，再次执行并完成闭环。
3. 连续运行三次，三次均最终识别到主界面。
4. 人为替换为无效主界面模板，确认任务安全失败、不产生点击、保存诊断并恢复窗口。
5. 运行中取消任务，确认窗口和前台应用恢复。
6. 使用 `tools/run_cli.py` 包装 MaaPiCli，加载同一 `interface.json` 和任务入口完成诊断运行，并确认异常时仍恢复窗口。

## 10. 验收标准

以下条件必须全部满足：

1. `setup.py` 可重复执行且不破坏已有环境。
2. MFAAvalonia 显示 MJA 和“邮件菜单闭环测试”。
3. 游戏未运行时可自动启动，已运行时可自动激活。
4. 游戏内容区调整为 `1280×720`。
5. 能识别主界面、打开邮件、确认邮件界面、关闭邮件并重新确认主界面。
6. 连续三次实机运行全部成功。
7. 成功、失败和取消后均恢复原窗口状态。
8. 识别失败时不执行猜测性点击，并生成完整诊断资料。
9. CLI 包装器可使用同一资源完成诊断运行，并提供与 GUI 一致的窗口准备和恢复保障。
10. Git 仓库不包含环境、运行库、日志或实机截图。

## 11. 明确不在首版范围内

- 账号登录
- 公告、更新、资源下载和未知弹窗处理
- 邮件领取
- 后台控制
- 任意窗口尺寸和分辨率适配
- 其他日常、周常或战斗任务
- Intel Mac 或其他机器分发
- 修改或 fork MaaFramework
- 修改或 fork MFAAvalonia
- 自动安装 Homebrew 或系统级工具

## 12. 后续演进边界

首版通过后，后续任务继续复用同一 ProjectInterface、窗口生命周期、错误模型和诊断目录。新增业务只应增加独立 pipeline 与模板，不应绕过点击适配器或扩大通用恢复动作。

若未来 MaaFramework 官方 macOS 输入能够稳定控制本游戏，只替换 `MacOSForegroundClick` 适配器实现；pipeline 节点名称和安全约束保持不变。

## 13. 参考实现

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)
- [MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia)
- [Maa_bbb](https://github.com/miaojiuqing/Maa_bbb)
- 本地既有工作流：`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily`
- 本地 MaaFramework：`/Users/gaoguobin/project/MaaFramework`
