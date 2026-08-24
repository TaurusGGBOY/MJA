# MFW 批量任务修复操作规约

本文规定同一 Android 模拟器上的 MFW 任务如何并行分析、串行执行和验收。代码分析、离线测试和构建可以并行；同一 serial 的 MFW、ADB、截图和游戏状态操作必须由 `tools/mfw_simulator_lock.py` lease 串行化。启动真实 MFW 前确认没有第二个 active runner。

## 基线与隔离

1. 从批准的干净提交创建独立 worktree 和分支；每个正式业务任务一个 worker，不允许多个 worker 写同一工作区。
2. 每次尝试都从当前源代码构建唯一、不可变的候选包；候选开始实机运行后不再编辑。
3. 每个 worker 只运行自己的 `GAME_START + 一个业务任务`。不要把多个业务任务、`GAME_STOP` 或未声明辅助任务混入 pair。

## 离线阶段

worker 先运行本任务 focused contract tests、资源检查和相关 Android/MFW 静态测试，再打包候选。启动前自动补齐精确 pair profile：

```bash
install/.venv/bin/python tools/mfw_profile.py ensure-pair-profiles \
  --install "$CANDIDATE"
python3 tools/check_mfw_resources.py "$CANDIDATE/resource/base" --task-entry-gate
```

profile 修复只写候选配置，不启动 MFW、ADB、模拟器或 Controller。模拟器启动命令必须保留 `-gpu host`。

## 实机验收阶段

普通 worker 在启动 MFW 前必须取得覆盖 `GAME_START + 业务任务 + native teardown` 的 simulator lease。等待 lease 时不得启动 MFW、Controller、ADB 或截图。

先创建新鲜 ticket，并在启动前声明该业务任务的期望原生终态：

```bash
ticket=$(install/.venv/bin/python tools/mfw_live_acceptance.py begin \
  --candidate "$CANDIDATE" \
  --owner "$WORKER" \
  --selected-task "$TASK_ID" \
  --expect-terminal "$TASK_ID=Succeeded")
```

然后从候选目录直接运行 MFW，精确勾选 `GAME_START + 指定任务`。完成后执行：

```bash
install/.venv/bin/python tools/mfw_live_acceptance.py finish \
  --ticket "$ticket" \
  --record "verification/mfw/20260820-native-status/$TASK_ID.json"
```

只有 `finish` 返回 0 且新鲜 MFW 原生终态匹配启动前声明，worker 才能交付。Tasker 事件、日志、截图、节点轨迹和后置条件只作为诊断材料；不再要求或读取平行结果文件。

预期失败的探针显式使用 `--expect-terminal TASK_ID=Failed`。普通业务 `Failed` 不阻止后续选中任务；`GAME_START=Failed` 才是停止队列的全局前置条件。手动停止保留 MaaFramework 默认语义。

## 失败路由

- pair 顺序不匹配：修正 MFW 选择并重新创建 ticket，不修改代码。
- native `Failed`：只修复该任务拥有的识别、动作、显式 `FailTask` 或终止路由，并增加 focused regression assertion。
- 终态仍为 `Pending` 或 `Running`：先判断任务是否仍在执行、是否超时或是否有 runner/lease 问题；不能把未结束的运行报告为成功或失败。
- 原生成功但画面观测异常：保留诊断材料，检查 pipeline 的成功边界；不得另造业务状态覆盖原生 `Succeeded`。
- `on_error`：只保留有明确前置、次数上限和无危险副作用重放的任务内恢复；否则删除该路由。

## 正式任务矩阵

每一行都是一个独立 pair；第一项永远是该 worker 自己的启动任务。`WEEKLY_FREE_GIFT_DAILY` 每天可运行，不能按星期过滤。

| Worker | MFW pair |
| --- | --- |
| mail | `GAME_START + MAIL_REWARD_DAILY` |
| shop | `GAME_START + SHOP_FREE_GIFT_DAILY` |
| tea | `GAME_START + BUY_TEA_DAILY` |
| appraisal | `GAME_START + FREE_APPRAISAL_DAILY` |
| trial | `GAME_START + TRIAL_SWORD_DAILY` |
| dispatch | `GAME_START + HERO_DISPATCH_DAILY` |
| collection | `GAME_START + COLLECTION_DEPLOYMENT_DAILY` |
| weekly-gift | `GAME_START + WEEKLY_FREE_GIFT_DAILY` |
| shadow-ruins | `GAME_START + SHADOW_RUINS_DAILY` |
| condensate | `GAME_START + SPEND_CONDENSATE_DAILY` |
| martial-study | `GAME_START + MARTIAL_STUDY_BREAKTHROUGH_DAILY` |
| stamina-food | `GAME_START + EAT_STAMINA_FOOD_DAILY` |
| equipment | `GAME_START + EQUIPMENT_DECOMPOSE_DAILY` |
| dungeon | `GAME_START + DUNGEON_SWEEP_DAILY` |
| jianlin | `GAME_START + JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` |
| ring | `GAME_START + RING_CHALLENGE_DAILY` |
| break-array | `GAME_START + BREAK_ARRAY_MARTIAL_DAILY` |
| guild-activity | `GAME_START + GUILD_ACTIVITY_CHALLENGE_DAILY` |
| guild-affairs | `GAME_START + GUILD_AFFAIRS_DAILY` |
| guild-donation | `GAME_START + GUILD_DONATION_DAILY` |
| daily-rewards | `GAME_START + DAILY_TASK_REWARD_CLAIM_DAILY` |
| battle-pass | `GAME_START + BATTLE_PASS_REWARD_DAILY` |

## 集成

worker 先提交 pipeline 与离线测试，再提交对应的原生终态验收记录；integrator 按正式矩阵逐项复核。不能仅凭单个 `Tasker.Task.Succeeded` 事件报告完成，也不能用未运行任务的记录补齐矩阵。

全量集成从干净源代码构建不可变候选，冻结 pair 选择范围，确认普通业务失败不会影响后续队列，并确认 `GAME_START` 失败能停止队列。所有 worker 安全释放 lease 后才报告整批结果。
