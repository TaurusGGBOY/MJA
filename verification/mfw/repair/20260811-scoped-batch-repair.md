# 2026-08-11 MFW 指定任务批量修复

## 本轮上下文

- 日期：2026-08-11（周二，Asia/Shanghai）
- 范围模式：`explicit`
- 用户原始清单：剑林；副本扫荡；帮会活动；帮会事务；帮派捐献；虾仁好像也没吃
- 任务映射：`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`；`DUNGEON_SWEEP_DAILY`；`GUILD_ACTIVITY_CHALLENGE_DAILY`；`GUILD_AFFAIRS_DAILY`；`GUILD_DONATION_DAILY`；`EAT_STAMINA_FOOD_DAILY`
- 候选：`install/mfw-android-all-20260811-r82`
- 候选 `payload_sha256`：`00137a96904494923177d51b5b2a12a5432f27d7d7c3252f69a8e800d2dbb49c`
- 候选 `immutable_tree_sha256`：`5ce41097c69ffc3a96fece8f89bb7659b88808f6ddbf4cd1e46697bd831a7231`
- MFW 配置：`c_mfw_scoped_20260811_r1`
- Android 序列号：`emulator-5556`
- 诊断文档：本文件

## 首轮范围

按候选 `interface.json` 原始顺序，首轮严格选择：

1. `GAME_START`
2. `EAT_STAMINA_FOOD_DAILY`
3. `DUNGEON_SWEEP_DAILY`
4. `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`
5. `GUILD_ACTIVITY_CHALLENGE_DAILY`
6. `GUILD_AFFAIRS_DAILY`
7. `GUILD_DONATION_DAILY`

未选择、不是本轮失败的任务：`MAIL_REWARD_DAILY`、`SHOP_FREE_GIFT_DAILY`、`BUY_TEA_DAILY`、`FREE_APPRAISAL_DAILY`、`TRIAL_SWORD_DAILY`、`HERO_DISPATCH_DAILY`、`COLLECTION_DEPLOYMENT_DAILY`、`WEEKLY_FREE_GIFT_MONDAY`、`SHADOW_RUINS_DAILY`、`SPEND_CONDENSATE_DAILY`、`MARTIAL_STUDY_BREAKTHROUGH_DAILY`、`RING_CHALLENGE_DAILY`、`BREAK_ARRAY_MARTIAL_DAILY`、`DAILY_TASK_REWARD_CLAIM_DAILY`、`BATTLE_PASS_REWARD_DAILY`。

## 批量循环

### 第 1 轮：首轮基线

- 验收票据：`install/mfw-android-all-20260811-r82/debug/acceptance/ALL/20260811T120203835354Z/ticket.json`
- `expected_tasks`：`GAME_START`、`EAT_STAMINA_FOOD_DAILY`、`DUNGEON_SWEEP_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`、`GUILD_ACTIVITY_CHALLENGE_DAILY`、`GUILD_AFFAIRS_DAILY`、`GUILD_DONATION_DAILY`
- 结果：共享运行时阻断；MFW 未进入 `GAME_START`，GUI 初始化因 `multi_config.json` 引用缺失配置文件而停滞
- `finish`：失败，`exact task order mismatch`，期望 7 个任务，实际执行序列为空
- fresh 业务结果：无；没有任务产生 `result.json`
- 证据归档：`verification/mfw/repair/20260811-r1-shared-runtime-debug/debug`
- 失败集合 `F(0)`：全部 6 个用户指定业务任务因共享运行时未执行而冻结，下一轮仍以同一整批 `GAME_START + F(0)` 复跑

### 第 2 轮准备：共享运行时修复

- 修复：将候选 `config/multi_config.json` 的配置列表收敛为实际存在的 `c_mfw_scoped_20260811_r1`
- 候选 payload 未修改；修复仅作用于可变 MFW 配置状态
- 第 2 轮验收票据：`install/mfw-android-all-20260811-r82/debug/acceptance/ALL/20260811T120541790864Z/ticket.json`
- 第 2 轮：整批复跑 `GAME_START + F(0)`，结果待运行

后续各轮在本文件追加：候选哈希、配置 ID、排除集合、每任务 fresh 结果/证据、批量 `finish` 退出码、失败原因、修复 commit、下一轮完整失败集合及最终全量回归票据。
