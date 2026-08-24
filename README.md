# MJA

《对决！剑之川》MaaFramework 自动化项目，当前运行入口是 macOS 上的 Android 模拟器 + MFW。任务只使用 ADB Android Controller，不依赖 macOS 原生 App。

```bash
./tools/launch_mfw.zsh
```

启动脚本默认使用 `mja-api35-apis` AVD 和 `emulator-5556`，模拟器必须以 `-gpu host` 启动。任务在 MFW GUI 中选择或通过已保存的 profile 运行；旧的 macOS 原生入口不属于当前运行入口。

Android 任务只能使用上面的 MFW/ADB 入口。

首次准备 Android 环境时，会安装 SDK、创建 AVD，并通过 `adb install -r` 侧载 `artifacts/jianzhichuan.apk`。不登录 Google Play，也不从 Google Play 下载游戏；只在游戏账号登录时需要人工介入，登录完成后流程自动继续。详细说明见 [Android 模拟器测试](docs/testing/android-emulator-mail-smoke-test.md)。

该游戏的 Android 15 原生热更模块需要 AVD 使用 `selinux_mode=permissive`；MJA 会在 ADB 就绪后自动执行并验证这一设置。它只针对本项目的隔离 userdebug 模拟器，不应套用到真实设备。

## 许可证

本项目代码和原创资源按 [Apache License 2.0](LICENSE) 发布。MaaFramework、MFAAvalonia、OCR 模型、游戏素材和其他第三方内容仍受各自许可证或服务条款约束，分发前请分别核对其许可。

## MFW 任务状态

MFW 原生 `Invalid`、`Pending`、`Running`、`Succeeded`、`Failed` 是唯一状态模型。业务已完成和本次执行成功都表现为 `Succeeded`；其他业务失败表现为 `Failed`。普通业务任务失败不阻止后续选中任务，只有 `GAME_START` 失败才停止队列。

运行前必须显式声明每个被验收任务的期望终态，运行后只以新鲜的原生终态事件判定结果。日志、截图和节点轨迹只用于排查，不是第二套结果判据；周礼包 `WEEKLY_FREE_GIFT_DAILY` 每天可运行，已领取时仍是 `Succeeded`。

## MFW 运行候选

MFW 候选使用 ProjectInterface v2、独立 Maa Pipeline 和 embedded Agent；游戏启动由 Android 任务负责，不依赖 macOS 原生 App。

```bash
python3 tools/check_mfw_resources.py install/mfw-native-status-20260820/resource/base --task-entry-gate
```

候选运行入口固定为 `tools/launch_mfw.zsh`，它会检查 ADB/AVD 就绪状态后启动 MFW。
