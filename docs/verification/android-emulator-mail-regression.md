# Android 模拟器回归记录

## 验收结果（2026-07-28）

本记录对应当前默认 AVD `mja-api35-apis`，不使用 Google Play。所有账号、手机号、验证码和 UID 均未写入记录。

- AVD：`mja-api35-apis`
- serial：`emulator-5556`
- system image：`system-images;android-35;google_apis;arm64-v8a`
- 分辨率：`1280x720`
- SDK：`35`
- locale：`zh-Hans-CN`
- 游戏包：`com.hanjiasongshu.dr22`
- 游戏版本：`1.5.3`
- userdata 可用空间：`6687524 KiB`（运行前超过 1GB 门槛）
- 连续截图：`valid_frames=50/50`
- 证据帧：`diagnostics/android/20260728-1907/frames/`
- 邮件闭环：主界面 → 面板 → 邮件 → 面板 → 主界面
- 任务结果：`Tasker.Task.Succeeded`
- runner 结果：`succeeded`
- 结构化结果：`install/debug/runs/android/20260728T191825578628/result.json`
- 安全性：未执行领取、购买、支付或其他非目标输入

## 运行前检查

```bash
./install/.venv/bin/python -m tools.android_setup --check
./install/.venv/bin/python -m tools.android_device
```

运行器在启动 MaaPiCli 前检查 userdata 空间、网络探测、游戏前台包名和截图尺寸；任一条件失败都会以明确的 `MJAError` 停止，不执行游戏点击。

## 重跑命令

```bash
./tools/android_run.sh --task mail_smoke_test
```

除账号登录或系统授权页外无需介入。默认保留模拟器和登录状态；需要结束模拟器时追加 `--stop`。
