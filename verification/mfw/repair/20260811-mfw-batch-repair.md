# MFW 剑之川批量修复诊断（2026-08-11）

## 本轮上下文

- 日期：2026-08-11，星期二（Asia/Shanghai）
- 项目：`/Volumes/my_disk/project/MJA`
- 候选：`install/mfw-android-all-20260811-r1`
- 候选 payload SHA-256：`c7b8679ccb7e242353c911794bc32cccf146a3dc07fed1eb5f7d231aa955e1de`
- 候选不可变运行时树 SHA-256：`5ce41097c69ffc3a96fece8f89bb7659b88808f6ddbf4cd1e46697bd831a7231`
- 候选校验：`tools/mfw_install.py --verify-candidate` 通过；资源校验通过（1522 个 Pipeline 节点）
- MFW 配置：`c_all_except_monday_20260809_r10`
- Android：AVD `mja-api35-apis`，序列号 `emulator-5556`
- QEMU：PID 68852，命令包含 `-gpu host`，未发现 `-no-window`
- 批量验收文档：本文件

## 当天选择集合

按 `interface.json` 原始顺序，MFW 配置应恰好运行：

`GAME_START`、`MAIL_REWARD_DAILY`、`SHOP_FREE_GIFT_DAILY`、`BUY_TEA_DAILY`、`FREE_APPRAISAL_DAILY`、`TRIAL_SWORD_DAILY`、`HERO_DISPATCH_DAILY`、`COLLECTION_DEPLOYMENT_DAILY`、`SHADOW_RUINS_DAILY`、`SPEND_CONDENSATE_DAILY`、`MARTIAL_STUDY_BREAKTHROUGH_DAILY`、`EAT_STAMINA_FOOD_DAILY`、`DUNGEON_SWEEP_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`、`RING_CHALLENGE_DAILY`、`BREAK_ARRAY_MARTIAL_DAILY`、`GUILD_ACTIVITY_CHALLENGE_DAILY`、`GUILD_AFFAIRS_DAILY`、`GUILD_DONATION_DAILY`、`DAILY_TASK_REWARD_CLAIM_DAILY`、`BATTLE_PASS_REWARD_DAILY`。

排除：`WEEKLY_FREE_GIFT_MONDAY`（非周一）。不运行 `GAME_STOP`。

## 运行时前置证据

- ADB：`emulator-5556` 为 `device`，`sys.boot_completed=1`。
- 显示：`Physical size: 1280x720`。
- GPU：实际 QEMU 命令包含 `-gpu host`。
- 游戏包：`com.hanjiasongshu.dr22` 已安装。
- 初始前台：`com.google.android.apps.nexuslauncher`；由本轮唯一的 `GAME_START` 任务负责进入游戏，未手工启动游戏。
- SELinux：由项目 Android 运行时门禁从 `Enforcing` 切换并验证为 `permissive`。
- phantom-process monitor：`false`。
- 内存：`MemAvailable=2474905600`，`SwapFree=2839752704`。
- userdata 可用空间：`6162108416` 字节。

## 轮次记录

### 第 1 轮：全量基线（共享启动故障，中止）

- 选择集合：上述 21 项（`GAME_START` + 20 个业务任务）
- 排除集合：`WEEKLY_FREE_GIFT_MONDAY`
- MFW 配置：`c_all_except_monday_20260809_r10`
- 验收 owner：`mja-batch-20260811-baseline`
- 验收 ticket：`verification/mfw/repair/20260811-baseline-debug/acceptance/ALL/20260811T012343961823Z/ticket.json`
- MFW 运行命令：在 `install/mfw-android-all-20260811-r1` 目录直接执行 `./MFW --config-id c_all_except_monday_20260809_r10 --direct-run`。
- MFW 运行窗口：约 `09:24:55`–`09:30:34`（Asia/Shanghai）；通过 PTY `Ctrl-C` 安全终止，模拟器未停止。
- 归档证据：`verification/mfw/repair/20260811-baseline-debug/`；启动后截图：`verification/mfw/repair/20260811-baseline-screen.png`。
- 验收 finish：退出码 `1`；报错为 GUI 实际任务顺序只有 `('GAME_START',)`，未进入 20 个业务任务，故不是可单独归因到业务任务的失败集合。
- 失败集合 `F(1)`：共享启动故障 `GAME_START`（业务任务均被启动前置阻塞，不把它们伪记为独立失败）。
- 修复状态：已冻结证据，启动层修复在独立 worktree `MJA-worktrees/mfw-batch-startup-20260811-r1` 中处理。

#### 共享启动故障证据

- `MJA_KNOWN_MONTHLY_SIGNIN_CLOSE` 在 `09:25:32.351` 识别弹窗并报告 `Click` 成功，但实际触点为 `[1063,172]`；配置目标矩形为 `[1052,144,32,32]`，触点落在图标下缘，弹窗仍然可见。
- 随后 `MJA_GAME_READY` 在多个循环中稳定得到模板分数 `0.587117`，低于阈值 `0.75`；`MJA_GAME_IN_GAME_READY` 同样失败。
- 因而无条件的 `MJA_GAME_LAUNCH` 反复执行 `StartApp com.hanjiasongshu.dr22/.MainActivity`，没有 `Tasker.Task.Succeeded/Failed` 终态，也没有任何本轮新鲜业务 `result.json`。
- 终止前截图显示月签到弹窗仍覆盖在游戏界面上；QEMU 仍为 PID `68852`，命令含 `-gpu host`。

### 第 2 轮：共享启动修复复验（通过）

- 候选：`install/mfw-android-all-20260811-r2`
- 候选 payload SHA-256：`c7d78c6f572d713560b94b5c74729d59422ce6be8c9474049ff678736138b298`
- 候选不可变运行时树 SHA-256：`5ce41097c69ffc3a96fece8f89bb7659b88808f6ddbf4cd1e46697bd831a7231`
- 离线校验：候选校验通过；资源校验通过（1522 个 Pipeline 节点）。
- 修复内容：`MJA_KNOWN_MONTHLY_SIGNIN_CLOSE.target` 从 `[1052,144,32,32]` 收紧为 `[1060,152,16,16]`，并同步 `tests/test_mfw_startup_pipeline.py` 契约。
- MFW 配置：`c_mfw_batch_game_start_20260811_r2`，实际勾选 `GAME_START`（另含框架必需的 PreTask/Controller/Resource/Post-Action）。
- 验收 ticket：`verification/mfw/repair/20260811-startup-repair-debug/acceptance/ALL/20260811T014018069818Z/ticket.json`
- 验收记录：`verification/mfw/repair/20260811-startup-repair-debug/acceptance/ALL/20260811T014018069818Z/acceptance.json`，`tools/mfw_live_acceptance.py finish` 退出码 `0`。
- 实时证据：关闭点击实际触点 `[1067,158]`；关闭后 `MJA_GAME_READY` 分数 `0.810306`（阈值 `0.75`）；`Tasker.Task.Succeeded` 出现，未再执行 `MJA_GAME_LAUNCH` 重试循环。
- 归档证据：`verification/mfw/repair/20260811-startup-repair-debug/`。候选 `debug/` 已清空，准备全量回归。

### 第 3 轮：直接串行全量回归（共享恢复阻塞，归档）

- 运行约束：只保留一个直接启动的 MFW runner，串行执行。
- 候选：`install/mfw-android-all-20260811-r2`
- 验收 ticket：`install/mfw-android-all-20260811-r2/debug/acceptance/ALL/20260811T014627289440Z/ticket.json`
- MFW 命令：候选目录内直接执行 `./MFW --config-id c_all_except_monday_20260809_r10 --direct-run`。
- 运行结果：安全停止并归档；`mfw_live_acceptance finish` 退出码 `1`，实际顺序到 `MARTIAL_STUDY_BREAKTHROUGH_DAILY`，后续任务未开始，不能把后续未运行任务伪记为失败。
- 归档证据：`verification/mfw/repair/20260811-final-full-no-lock-interrupted-debug/`。
- 已通过：`GAME_START`、`MAIL_REWARD_DAILY (already_complete)`、`SHOP_FREE_GIFT_DAILY (already_complete)`。
- 新鲜失败结果：
  - `BUY_TEA_DAILY`：`TEA_POSTCONDITION_MISSING`
  - `FREE_APPRAISAL_DAILY`：`APPRAISAL_POSTCONDITION_MISSING`
  - `TRIAL_SWORD_DAILY`：`TRIAL_POSTCONDITION_MISSING`
  - `HERO_DISPATCH_DAILY`：`HERO_POSTCONDITION_MISSING`
  - `COLLECTION_DEPLOYMENT_DAILY`：`COLLECTION_POSTCONDITION_MISSING`
  - `SHADOW_RUINS_DAILY`：`SHADOW_PAINTING_ENTRY_UNKNOWN`
  - `SPEND_CONDENSATE_DAILY`：`CONDENSATE_POSTCONDITION_MISSING`
- 共享阻塞：`MARTIAL_STUDY_BREAKTHROUGH_DAILY` 的 `result.json` 在停止时仍为 `running`；日志中统一 `MJA_GAME_LAUNCH` 约每 7 秒重复一次（共 29 次），当前 OCR 处于商城页面。将其与“首页恢复循环”一起处理。
- 冻结失败集合：上述 7 个业务任务 + 共享恢复阻塞 `MARTIAL_STUDY_BREAKTHROUGH_DAILY`；未运行的后续任务暂不计入失败集合。
