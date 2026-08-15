# Android Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已验证的 Android 邮件闭环升级为可重复运行、可诊断、不会因 userdata 空间不足而隐式失败的模拟器运行底座。

**Architecture:** 保留当前 TapTap + ADB + MaaPiCli + Android 资源流水线，在旁边建立一个不含 Google Play 的大容量 `google_apis` AVD。运行器在启动任务前检查设备、存储、前台包名和截图能力；MaaPiCli 的 Android 默认截图/输入配置通过可复现补丁进入安装流程，而不是依赖本机手工编译产物。

**Tech Stack:** Python 3.14、pytest、ruff、Android SDK 35、ADB、Android Emulator、MaaFramework v5.12.2、MaaPiCli、TapTap、PNG 模板匹配。

## Global Constraints

- 游戏包固定为 `com.hanjiasongshu.dr22`，目标分辨率固定为 `1280x720`，系统语言固定为 `zh-CN`。
- 禁止 Google Play 下载游戏，游戏来源固定为 TapTap 官方安装渠道或已验证安装包。
- 用户只在游戏账号登录、短信验证码、系统授权页介入；其他普通权限、弹窗和启动流程自动处理。
- `mail_smoke_test` 只查看邮件，不领取邮件奖励、不购买、不支付、不执行其他游戏操作。
- 不清除游戏包、TapTap 数据或登录状态；更换 AVD 时允许用户只重新完成一次登录。
- 任何存储不足、截图尺寸错误、前台包名错误或资源缺失必须明确失败，不得继续盲点。

---

### Task 1: 建立不含 Google Play 的大容量 AVD

**Files:**
- Modify: `config/android.json`
- Modify: `agent/android/config.py`
- Modify: `agent/android/sdk.py`
- Modify: `agent/android/avd.py`
- Test: `tests/test_android_config.py`
- Test: `tests/test_android_sdk.py`
- Test: `tests/test_android_avd.py`

**Interfaces:**
- Produces `AndroidConfig.system_image_package: str` and `AndroidConfig.data_partition_size_gb: int`.
- `AndroidAvd.ensure()` must create/configure the requested AVD without `-wipe-data` unless the caller explicitly passes `wipe_data=True`.

- [x] **Step 1: 写失败测试**，要求默认配置使用 `system-images;android-35;google_apis;arm64-v8a`、AVD 数据盘至少 `12G`，并保留 `1280x720` 显示契约。

```python
def test_android_config_uses_non_play_store_large_avd():
    config = AndroidConfig.load()
    assert config.system_image_package == "system-images;android-35;google_apis;arm64-v8a"
    assert config.data_partition_size_gb >= 12
```

- [x] **Step 2: 实现配置驱动的 SDK/AVD 参数**：将 `agent/android/sdk.py` 的 `REQUIRED_PACKAGES` 改为由 `AndroidConfig.system_image_package` 生成；`AndroidAvd.ensure()` 在创建前写入 `disk.dataPartition.size=12G`，并在已有 AVD 不匹配时报告明确错误，不自动抹除数据。

- [x] **Step 3: 添加 AVD 测试**，断言 `avdmanager create avd` 使用 `google_apis` 包，配置文件包含 `disk.dataPartition.size=12G`，默认启动命令不含 `-wipe-data`。

- [x] **Step 4: 运行配置和 AVD 测试**。

```bash
./install/.venv/bin/python -m pytest -q tests/test_android_config.py tests/test_android_sdk.py tests/test_android_avd.py
```

- [x] **Step 5: 创建新 AVD 并人工介入一次登录**：创建新的默认 AVD，安装已从 TapTap 官方渠道取得并校验的游戏 APK；登录页只人工介入一次，之后自动执行。旧的 `mja-api35` 已删除。

- [x] **Step 6: 验证磁盘容量和安装来源**：确认新 AVD 的 userdata 可用空间超过 1GB、`pm path com.hanjiasongshu.dr22` 成功、安装包来自 `artifacts/jianzhichuan.apk`（TapTap 官方渠道取得），且没有 Google Play 下载动作。

### Task 2: 增加运行前存储和设备健康检查

**Files:**
- Modify: `agent/android/adb.py`
- Modify: `agent/android/avd.py`
- Modify: `tools/android_run.py`
- Modify: `agent/errors.py`
- Test: `tests/test_android_adb.py`
- Test: `tests/test_android_run.py`
- Test: `tests/test_android_acceptance_contract.py`

**Interfaces:**
- Produces `AdbDevice.storage_free_bytes() -> int`.
- Produces `AdbDevice.require_runtime_health(min_free_bytes: int = 1_073_741_824) -> None`.
- `AndroidRun.run()` calls the health check after `device.wait_ready()` and before starting MaaPiCli.

- [x] **Step 1: 写失败测试**，覆盖 userdata 可用空间、外网探测失败、非游戏前台包、非 `1280x720` 截图四种错误，并要求返回明确的 `MJAError` 错误码。

- [x] **Step 2: 实现只读健康检查**：使用 `df -Pk /data/user/0` 解析可用字节；使用 `ping`/ADB 网络状态作为诊断信息；复用现有 `foreground_package()` 和 `screencap()`，不执行点击。

- [x] **Step 3: 在 `AndroidRun.run()` 中接入检查**，失败时保存一份脱敏诊断，关闭 MaaPiCli 子进程，并保持现有模拟器清理策略。

- [x] **Step 4: 运行聚焦测试和真实检查**。

```bash
./install/.venv/bin/python -m pytest -q tests/test_android_adb.py tests/test_android_run.py tests/test_android_acceptance_contract.py
./install/.venv/bin/python -m tools.android_device
```

### Task 3: 把 MaaPiCli Android 修复纳入可复现构建

**Files:**
- Create: `native/maafw-android-cli/patches/0001-plain-adb-defaults.patch`
- Create: `native/maafw-android-cli/build.sh`
- Create: `native/maafw-android-cli/README.md`
- Modify: `tools/setup.py`
- Modify: `tests/test_native_patch_bundle.py`
- Modify: `tests/test_setup.py`

**Interfaces:**
- Produces `native/maafw-android-cli/build.sh --source <clean-v5.12.2-source> --official-bin <official-bin> --output <install-root>`.
- The patched `Runner::run()` supplies `{}` when plain ADB has no toolkit JSON and selects `MaaAdbScreencapMethod_Default` / `MaaAdbInputMethod_Default` when toolkit reconfiguration returns `None`.

- [x] **Step 1: 写补丁校验测试**，要求补丁只匹配 MaaFramework v5.12.2、固定上游 commit、干净临时 clone，并拒绝修改 `/Users/gaoguobin/project/MaaFramework` 参考 checkout。

- [x] **Step 2: 添加可复现构建脚本**：仿照 `native/maafw-macos-fallback/build.sh`，在临时 clone 中应用补丁，只构建 `MaaPiCli`，通过 Mach-O 检查和 SHA-256 校验后原子替换安装目录二进制。

- [x] **Step 3: 让 `tools/setup.py` 在组装安装目录时调用该构建/校验路径**；安装目录只保留生成结果，不把 `build/`、`debug/` 或参考仓库内容纳入 Git。

- [x] **Step 4: 验证 plain ADB 控制器能够初始化、截图并发送输入**。

```bash
./install/.venv/bin/python -m pytest -q tests/test_native_patch_bundle.py tests/test_setup.py
./install/.venv/bin/python tools/verify_install.py install
```

### Task 4: 修复 Android runner 的任务失败传播和证据记录

**Files:**
- Modify: `tools/android_run.py`
- Modify: `agent/diagnostics.py`
- Modify: `install/agent/main.py` through the project source copied by `tools/setup.py`
- Test: `tests/test_android_run.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Produces `AndroidRun._task_failed(debug_dir: Path) -> bool`.
- `AndroidRun.run()` returns non-zero when MaaPiCli exits zero but `maafw.log` contains `Tasker.Task.Failed`.
- Produces a redacted result record containing AVD, serial, package, display size, task name, timestamps, and status only.

- [x] **Step 1: 写失败测试**，模拟 MaaPiCli 返回 `0` 但日志出现 `Tasker.Task.Failed`，要求 runner 返回 `3`；模拟成功事件要求返回 `0`。

- [x] **Step 2: 实现共享失败判定和结果记录**，不写账号、手机号、验证码、UID、token 或完整游戏日志到结构化记录。

- [x] **Step 3: 测试 `finally` 行为**：成功、任务失败、子进程异常、登录超时四条路径都关闭子进程并按 `keep_running` 决定是否停止模拟器。

- [x] **Step 4: 运行完整测试和静态检查**。

```bash
./install/.venv/bin/python -m pytest -q
./install/.venv/bin/python -m ruff check .
git diff --check
```

### Task 5: 在新 AVD 上重做 Android 资源和端到端验收

**Files:**
- Modify: `assets/resource_android/calibration.json`
- Replace: `assets/resource_android/image/home/*.png`
- Replace: `assets/resource_android/image/panel/*.png`
- Replace: `assets/resource_android/image/mail/*.png`
- Modify: `docs/testing/android-emulator-mail-smoke-test.md`
- Modify: `docs/verification/android-emulator-mail-regression.md`
- Test: `tests/test_android_resources.py`
- Test: `tests/test_project_contract.py`

**Interfaces:**
- `tools.capture_android_templates` continues to produce exactly the seven templates required by `mail_smoke_test`.
- `mail_smoke_test` must end with `Tasker.Task.Succeeded` and must not emit claim/purchase/payment input.

- [x] **Step 1: 在新 AVD 登录后采集 home、panel、mail 三组模板**，每组均从当前真实 `1280x720` frame 生成，禁止复制旧环境模板。

- [x] **Step 2: 运行资源校验**，要求七张图片存在、尺寸不超过 ROI、校准状态为 `live_capture_verified`。

- [x] **Step 3: 连续采集 50 帧并运行邮件闭环**：主界面 → 面板 → 邮件 → 面板 → 主界面；只查看邮件，不点击领取。

- [x] **Step 4: 保存脱敏验收记录**，记录 `valid_frames=50/50`、任务结果、证据目录和存储余量，不记录账号信息。

- [x] **Step 5: 运行最终验收命令**。

```bash
./install/.venv/bin/python tools/verify_install.py install
./tools/android_run.sh --task mail_smoke_test
```

### 后续独立计划：日常任务扩展

Android 邮件闭环稳定后，再单独建立日常任务计划，按“只读识别 → 无消耗任务 → 非付费资源任务 → 明确人工授权任务”的顺序实现。每个任务都必须拥有独立模板、状态机、资源安全策略、失败回滚和真实模拟器验收；不把多个日常任务与本次运行底座改造混在一个提交中。
