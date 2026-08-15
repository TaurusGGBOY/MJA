# MJA

《对决！剑之川》MaaFramework 自动化项目。

当前正式入口是 macOS 上运行的 Android 模拟器 + MFW。任务只使用 ADB Android Controller；不会启动 `/Applications/对决！剑之川.app` 这个 macOS 原生 App。

```bash
./tools/launch_mfw.zsh
```

启动脚本会使用固定的 `mja-api35-apis` AVD 和 `emulator-5556`，模拟器必须以 `-gpu host` 启动。任务在 MFW GUI 中选择；旧 `MFAAvalonia` macOS 项目和 `/Applications/对决！剑之川.app` 不属于当前运行入口。

旧的 macOS 游戏入口已移除；Android 任务只能使用上面的 MFW/ADB 入口。

首次准备 Android 环境时，会安装 SDK、创建 AVD，并通过 `adb install -r` 侧载 `artifacts/jianzhichuan.apk`。不登录 Google Play，也不从 Google Play 下载游戏；只在游戏账号登录时需要人工介入，登录完成后流程自动继续。详细说明见 [Android 模拟器测试](docs/testing/android-emulator-mail-smoke-test.md)。

该游戏的 Android 15 原生热更模块需要 AVD 使用 `selinux_mode=permissive`；MJA 会在 ADB 就绪后自动执行并验证这一设置。它只针对本项目的隔离 userdebug 模拟器，不应套用到真实设备。

## MFW 运行候选

MFW 候选使用 ProjectInterface v2、独立 Maa Pipeline 和 embedded Agent；游戏启动由 Android 任务负责，不依赖 macOS 原生 App。

```bash
python3 tools/check_mfw_resources.py install/mfw-game-startup-maa-bbb-20260808-final-r3/resource/base
```

候选运行入口固定为 `tools/launch_mfw.zsh`，它会检查 ADB/AVD 就绪状态后启动 MFW。
