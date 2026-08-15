# MFW 剑之川批量修复记录（2026-08-11）

## 本轮上下文

- 日期：2026-08-11，星期二（排除 `WEEKLY_FREE_GIFT_MONDAY`）
- 初始候选：`/Volumes/my_disk/project/MJA/install/mfw-android-all-20260811-r81`
- 初始候选元数据：`install/mfw-android-all-20260811-r81/build-metadata.json`
- 全量配置：`c_all_except_monday_20260809_r10`
- Android 序列号：`emulator-5556`
- 运行所有者：`mfw-batch-repair-20260811-main`
- 任务验收工具：`tools/mfw_live_acceptance.py`
- 运行方式：从候选目录直接启动 MFW；同一时间只保留一个真实 runner。
- 既有 r81 调试证据归档：`verification/mfw/repair/20260811-r81-preexisting-debug/`
- 模拟器检查：`emulator-5556=device`，`sys.boot_completed=1`，QEMU 实际命令含 `-gpu host`，`hw.gpu.enabled=yes`、`hw.gpu.mode=host`

## 当前显式范围轮

- 用户原始范围：剑林、副本扫荡、帮会活动、帮会事务、帮派捐献、虾仁（按食用体力食物处理）
- 选择模式：`explicit`
- 首轮候选：`install/mfw-android-all-20260811-r82`
- 首轮配置：`c_mfw_scoped_20260811_r1`
- 首轮选择：`GAME_START` 加 `EAT_STAMINA_FOOD_DAILY`、`DUNGEON_SWEEP_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`、`GUILD_ACTIVITY_CHALLENGE_DAILY`、`GUILD_AFFAIRS_DAILY`、`GUILD_DONATION_DAILY`
- 首轮省略：其它所有业务任务及周一限定任务

## 历史全量尝试（已中断）

`GAME_START`，随后按 `interface.json` 原始顺序运行除 `WEEKLY_FREE_GIFT_MONDAY` 外的全部业务任务。

该尝试使用 r81 全量配置，已在用户修改首轮范围规则后中断；其部分日志仅作诊断，不作为验收证据：`verification/mfw/repair/20260811-r81-interrupted-full-debug/`。

## 当前轮次

### 基线轮 F(0)

- 候选：`install/mfw-android-all-20260811-r82`
- 配置：`c_mfw_scoped_20260811_r1`
- 批量验收票据：`install/mfw-android-all-20260811-r82/debug/acceptance/ALL/20260811T114739346952Z/ticket.json`
- 票据期望顺序：`GAME_START`、`EAT_STAMINA_FOOD_DAILY`、`DUNGEON_SWEEP_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`、`GUILD_ACTIVITY_CHALLENGE_DAILY`、`GUILD_AFFAIRS_DAILY`、`GUILD_DONATION_DAILY`
- 结果：待填写
- 失败集合：待填写

### 修复批次 1

- 失败集合：待填写
- worktree/commit：待填写
- 聚焦测试与资源校验：待填写
- 新候选：待填写

### 复跑轮 F(1)

- 复跑集合：待填写
- 批量验收票据：待填写
- 结果：待填写

### 最终全量回归

- 候选：待填写
- 批量验收票据：待填写
- `finish` 退出码：待填写
- 结果：待填写
