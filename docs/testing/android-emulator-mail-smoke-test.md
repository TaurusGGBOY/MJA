# Android 模拟器邮件闭环测试

## 一键运行

已完成登录和首次授权后，运行：

```bash
./tools/android_run.sh --task mail_smoke_test
```

脚本会自动检查 SDK、启动 `mja-api35-apis` AVD、确认已验证安装包中的官方游戏包
`com.hanjiasongshu.dr22`，并在 ADB 就绪后将隔离 userdebug AVD 设置为配置中的
`selinux_mode=permissive`，再检查 userdata 空间、网络、前台包名和截图尺寸。默认保留模拟器和登录状态；加入 `--stop`
才会在结束时关闭模拟器。Google Play 安装路径已禁用。

## 用户唯一介入点

如果游戏显示登录页，终端会输出：

```text
请完成游戏账号登录，完成后无需点击继续
```

用户只需完成游戏登录。MJA 不读取、保存或填写账号、密码、验证码，也不会点击支付或购买控件。登录完成后，脚本通过前台包名和非登录 UI 连续三次确认，然后自动继续。

## 运行前检查

```bash
./install/.venv/bin/python -m tools.android_setup --check
./install/.venv/bin/python -m tools.android_device
```

第二条命令必须报告唯一 serial、设备已启动、userdata 空间充足、网络可达、游戏在前台且截图尺寸为 `1280x720`。任一条件不满足时会以明确的 `MJAError` 失败，不执行任何游戏点击。

## 模板捕获

模板必须来自已登录、已稳定的 Android 画面：

```bash
./install/.venv/bin/python -m tools.capture_android_templates home
./install/.venv/bin/python -m tools.capture_android_templates panel
./install/.venv/bin/python -m tools.capture_android_templates mail
```

捕获命令只截图和裁剪。本项目当前的三个模板组均来自已登录 Android 的
`1280x720` 实时画面，契约状态为 `live_capture_verified`；禁止把 macOS/iOS
背景帧或旧资源复制为 Android 模板。

## 证据

运行日志、最后一帧和结构化状态位于 `diagnostics/android/`。提交验收记录时只保留 AVD 名称、SDK 组件、serial、分辨率、包名、时间和结果，不记录账号信息。
