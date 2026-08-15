# MJA macOS 邮件菜单闭环验收

## 前置条件

- Apple Silicon Mac，目标应用为 `/Applications/对决！剑之川.app`。
- 在“系统设置 → 隐私与安全性”中为当前终端/运行 Python 的应用开启“屏幕录制”和“辅助功能”。
- 游戏账号已登录，执行期间用户不操作鼠标和键盘。
- 游戏不领取邮件、不购买、不消耗任何资源。

## 自动检查

```bash
install/.venv/bin/python -m tools.setup --root .
install/.venv/bin/python -m tools.verify_install install
install/.venv/bin/ruff check agent tools tests
install/.venv/bin/python -m pytest -q
```

预期：安装验证、Ruff 和测试全部成功。运行前置检查必须先把游戏窗口调整并验证为 `1280×720`；如果 macOS Accessibility 拒绝调整，任务必须以 `DISPLAY_CONTRACT_MISMATCH` 安全失败，不能降低阈值或使用 `923×720` 背景画面继续运行。

## 模板采集

先执行窗口前置检查：

```bash
install/.venv/bin/python -m agent.pretask
osascript -e 'tell application "System Events" to tell process "ProductName" to tell window 1 to get {position, size}'
MJA_WINDOW_ID=$(install/.venv/bin/python -c 'import json; print(json.load(open(".mja-state/window.json"))["snapshot"]["window_id"])')
install/.venv/bin/python -m tools.capture_templates capture home --window-id "$MJA_WINDOW_ID"
```

只有窗口尺寸验证为 `1280×720` 后才允许采集模板。模板采集工具默认拒绝非 canonical calibration；`capture_screen` 可以单独用于诊断非标准帧，但诊断帧不能写入业务 PNG。

手动打开功能面板后执行：

```bash
install/.venv/bin/python -m tools.capture_templates capture panel --window-id "$MJA_WINDOW_ID"
```

手动打开邮件页面但不选择邮件、不点击领取后执行：

```bash
install/.venv/bin/python -m tools.capture_templates capture mail --window-id "$MJA_WINDOW_ID"
```

检查并确认 7 个 PNG 不包含“全部领取”、奖励弹窗或其他资源变更入口，然后关闭邮件和功能面板。

## CLI 验收

```bash
install/.venv/bin/python -m tools.run_cli --install-root install
```

每次运行必须记录：`debug/runs/<run>/run.json`、窗口原始边界、原前台应用、四次点击事件、最终 `MJA_ConfirmHome` 节点和恢复后的边界。失败、异常或 Ctrl-C 后都必须确认窗口恢复。

## MFAAvalonia 验收

启动 `install/MFAAvalonia`，加载 `install/interface.json`，确认 GUI 显示“邮件菜单闭环测试”。执行以下矩阵：

1. 游戏关闭时冷启动一次。
2. 游戏已运行且位于主界面时热启动一次。
3. 连续执行三次并记录三个成功的 `run.json` 路径。
4. 用临时错误模板替换 `install/resource/image/home/home_marker.png`，确认 `HOME_RECOGNITION_TIMEOUT`、零点击、失败截图和窗口恢复；随后重新运行 setup 还原安装目录。
5. 在初始识别等待期间 Ctrl-C，确认零猜测点击且窗口恢复。

成功标准：每次成功运行最终识别主界面，恰好 4 次 `MacOSForegroundClick`，没有领取/奖励点击，且任务结束后窗口尺寸与前台应用回到运行前状态。任一次失败都将“三次连续成功”计数归零。
