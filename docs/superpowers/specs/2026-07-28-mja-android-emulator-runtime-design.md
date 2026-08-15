# MJA Android 模拟器运行方案设计

## 目标

把 MJA 的运行目标从当前 macOS/iOS 兼容窗口切换为 Android 模拟器，通过 Android Studio AVD 和 ADB 提供稳定的截图、点击、应用启动与状态检查能力。用户只在 Android/游戏账号登录时介入，登录完成后，模拟器启动、游戏安装检查、任务运行、证据保存和结果校验全部自动完成。

现有 macOS 控制器和资源保留，作为回滚路径；新的 Android 控制器成为默认验证路径，不删除或覆盖旧实现。

## 方案选择

采用 Android Studio AVD，使用 ARM64 系统镜像，固定模拟器显示为横向 1280×720。MaaFramework 通过 `Adb` 控制器连接本机 ADB serial，使用设备截图和 ADB 输入，不依赖 macOS 窗口尺寸、屏幕录制权限或前台窗口焦点。游戏只通过官方/可信来源 APK 侧载，不登录 Google Play，也不使用 Google Play 下载。

不采用 MuMu/蓝叠作为第一实现：它们可能更适合某些游戏兼容性场景，但在 macOS 上的命令行生命周期、ADB 端口和版本管理更依赖厂商实现；如果 Android Studio AVD 无法运行目标游戏，再以兼容性证据为依据增加第二种后端。

## 运行边界

### 自动化部分

- 安装并校验 Android SDK command-line tools、platform-tools 和 emulator。
- 创建或复用固定名称的 AVD，配置 ARM64、横屏、1280×720 和硬件加速。
- 启动模拟器，等待 `sys.boot_completed=1`，解锁并等待 ADB 稳定。
- 检查游戏包；通过配置的 APK 路径执行 `adb install -r`，未配置或找不到 APK 时明确失败。
- 启动游戏、等待登录完成、读取登录状态、执行 MJA pipeline、保存截图和结构化诊断。
- 任务结束后按配置保留或关闭模拟器。

### 用户介入边界

自动化在检测到 Google 账号、游戏账号、验证码或系统授权页面时暂停，并明确输出“请完成登录”。检测到目标游戏进入已登录主界面后自动继续。除此之外不要求用户点击安装、启动或选择任务。

### 不安全行为

- 不自动填写或保存账号密码、短信验证码或支付信息。
- 不点击充值、购买、Apple/Google Pay 或其他消费确认。
- 游戏安装来源只允许显式配置的 APK；不打开 Play Store，不从未知第三方站点下载 APK。
- ADB serial、包名、分辨率和截图尺寸不匹配时安全失败，不执行业务点击。

## 组件设计

### 1. Android 环境引导器

新增 `tools/android_env.py`，提供可测试的命令封装和幂等流程：

- `AndroidSdk.ensure()`：解析项目配置，安装缺失 SDK 组件并记录版本。
- `AndroidAvd.ensure()`：创建固定 AVD，重复运行不修改已存在的用户设置。
- `AndroidAvd.start()` / `stop()`：启动、等待、停止模拟器。
- `AdbDevice.wait_ready()`：确认 serial 唯一、设备在线、系统完成启动、截图尺寸符合契约。
- `GameInstaller.ensure_installed()`：检查已安装包或侧载 APK；缺少 APK 时返回稳定的安装失败错误。
- `LoginGate.wait_until_ready()`：只负责等待登录，不处理凭证。

所有外部命令均通过注入的 runner 执行，测试使用 fake runner；真实运行使用项目本地 SDK 的 `adb` 和 `emulator`。

### 2. ADB 控制器配置

更新 `assets/interface.json`，新增一个 `Adb` controller，并把 Android 资源和任务绑定到该 controller。配置从 `config/android.json` 读取：

```json
{
  "avd_name": "mja-api35",
  "serial": "emulator-5554",
  "package_name": "",
  "display_size": [1280, 720],
  "apk_path": "",
  "keep_running": true
}
```

`package_name` 在首次 Play Store 安装时由显式配置或安装结果确定，不能通过模糊包名直接运行未知应用。游戏名称、包名和 APK 路径集中在配置中，不散落在 Python、pipeline 和文档里。

### 3. Android 资源和 pipeline

新增 Android 专用资源目录，重新从模拟器真实画面捕获模板。模板、ROI 和校准文件全部使用设备截图坐标；1280×720 是硬契约。当前 macOS/iOS 的旧 PNG 不直接复制到 Android 资源目录，避免把背景帧或错误比例带入新运行时。

邮件闭环仍然只打开和关闭邮件菜单，不领取邮件、奖励或任何付费内容。只有经过真实模拟器截图和识别验证的节点才允许进入默认任务。

### 4. 一键入口

新增 `tools/android_run.py` 和包装脚本 `tools/android_run.sh`：

```text
ensure SDK → ensure AVD → start → wait ADB → ensure game → wait login → run MAA task → verify evidence → stop/keep
```

所有阶段输出稳定错误码，并把命令、serial、AVD、分辨率、包名和登录等待事件写入 `diagnostics/android/`。失败时保留最后一帧和 ADB 日志。

## 状态和错误处理

状态机固定为：`SDK_READY`、`AVD_READY`、`DEVICE_READY`、`GAME_READY`、`LOGIN_REQUIRED`、`LOGIN_READY`、`TASK_RUNNING`、`SUCCEEDED`、`FAILED`。

- SDK/AVD/ADB 错误：不启动业务 pipeline。
- 多设备或 serial 不一致：停止并要求明确设备，不自动猜测。
- 分辨率不等于 1280×720：停止并记录 `DISPLAY_CONTRACT_MISMATCH`。
- 游戏未安装：执行配置的安装路径；安装失败不进入任务。
- 登录未完成：停在 `LOGIN_REQUIRED`，只等待，不输入凭证，不超时误判成功。
- 模板识别失败：保存截图和节点信息，立即失败并恢复模拟器生命周期。
- 任何异常或中断：关闭 MAA agent，保留证据，并按 `keep_running` 决定是否停止模拟器。

## 验证标准

1. 新机器或清理后的项目可通过一条命令完成 SDK/AVD 安装和配置。
2. 重复执行不会重复创建 AVD、重复安装 SDK 或破坏用户登录状态。
3. 设备始终以唯一 ADB serial 连接，连续 50 帧截图非空且尺寸为 1280×720。
4. 未登录时流程只暂停在登录门，不会误执行游戏点击。
5. 登录完成后无需人工点击即可启动并完成邮件菜单闭环。
6. MFAAvalonia 能显示 Android 控制器和对应任务。
7. 自动化测试覆盖 SDK 命令构造、AVD 配置、ADB readiness、安装分支、登录门、分辨率校验、失败恢复和一键入口。
8. 真实验收记录包含模拟器版本、设备 serial、游戏包名、截图尺寸、任务结果和证据路径。
