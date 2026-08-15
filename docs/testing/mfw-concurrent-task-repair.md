# MFW 批量任务修复操作规约

本文是 MJA 在同一台 Android 模拟器上批量修复 MFW 任务时的操作协议。代码分析和离线测试可以并行；ADB、MFW、截图、启动/停止游戏和任何会改变模拟器状态的操作直接在当前执行环境中完成。启动真实 MFW 前确认没有第二个 runner 正在运行。

## 基线与隔离

1. 先从用户批准的干净提交创建一个独立 worktree 和分支；每个业务任务一个 worker，不允许多个 worker 直接写同一个工作区。
2. 每次尝试都从当前源代码构建不可变候选包，使用唯一输出目录；候选包一旦开始实机运行就不再编辑。
3. 游戏启动已经单独通过 Maa_bbb 同构启动门禁。并发修复只允许复用 `GAME_START`，不得在业务任务中复制启动、停止或返回逻辑。

## 离线阶段

worker 只修改自己拥有的 pipeline、workflow、策略和测试文件。先运行该任务的 focused contract tests，再运行相关 Android/MFW 静态测试；通过后打包候选。日志分析、代码修改、测试和构建均在当前执行环境中完成。

## 实机验收阶段

先创建新鲜验收 ticket：

```bash
ticket=$(install/.venv/bin/python tools/mfw_live_acceptance.py begin \
  --candidate "$CANDIDATE" --owner "$WORKER" --task "$TASK_ID")
```

随后从候选目录直接运行 MFW：

```bash
(
  cd "$CANDIDATE"
  ./MFW
)
```

MFW 中只能勾选 `GAME_START + 指定任务`；不得把其他业务任务、`GAME_STOP` 或未声明的辅助任务混入本次验收。运行结束后继续执行：

```bash
install/.venv/bin/python tools/mfw_live_acceptance.py finish \
  --ticket "$ticket" \
  --record "verification/mfw/repair/$TASK_ID.json"
```

只有 `finish` 返回 0，并且同时拥有 GUI 的精确任务顺序、MaaFramework 的新鲜 native terminal、该任务的新鲜 `result.json` 和可解释的业务后置条件，worker 才能交付。

## 失败路由

- exact task order mismatch：先修正 MFW 勾选状态并重新创建 ticket，不修改代码。
- native `Failed`：只修复该任务拥有的识别、动作或终止路由，并增加 focused regression assertion。
- 业务结果为 `running`：补齐所有可达终止分支的 outcome recorder，不能把超时当成功。
- 业务结果为 `failed`：根据该次结果的 `postcondition`、`error_code`、最新错误图像、`gui.log.slice` 和 `maafw.log.slice` 定位真实失败状态。
- native 成功但业务失败：业务结果优先；修复错误的 wrapper success。
- `not_eligible`：只有任务策略明确允许当前日期、资源或资格状态时才可接受，并且 native task 也必须成功。
- stale result：旧结果不参与验收；修改后重新打包、创建新 ticket、重新运行。

## 正式任务矩阵

每一行表示一个可独立验收的业务任务；第一项永远是公共启动任务。单任务验收只用于首轮高风险诊断；发现失败后必须冻结“首个失败任务 + 首个失败后的未执行任务”并整批复跑，禁止逐任务修复/复跑。

| Worker | MFW pair |
| --- | --- |
| mail | `GAME_START + MAIL_REWARD_DAILY` |
| shop | `GAME_START + SHOP_FREE_GIFT_DAILY` |
| tea | `GAME_START + BUY_TEA_DAILY` |
| appraisal | `GAME_START + FREE_APPRAISAL_DAILY` |
| trial | `GAME_START + TRIAL_SWORD_DAILY` |
| dispatch | `GAME_START + HERO_DISPATCH_DAILY` |
| collection | `GAME_START + COLLECTION_DEPLOYMENT_DAILY` |
| weekly-gift | `GAME_START + WEEKLY_FREE_GIFT_MONDAY` |
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

## 完成与集成

worker 先提交实现和离线测试，再提交对应的 passing acceptance summary；两者一起交给 integrator。integrator 逐个复核 pair 的 fresh evidence 后，按正式矩阵集成，不接收只有 `Tasker.Task.Succeeded` 的 worker。

最终集成必须从干净源代码构建一个候选，确认 GPU 使用 `-gpu host`，先用只读选择器扫描当天结果，再创建只包含 `GAME_START + pending_tasks` 的批量 ticket。首个失败由 native Tasker 停止，下一批只带失败任务和未执行任务；已经有 fresh success 证据的任务不得重复运行。选择器和 ticket 示例：

```bash
selection=$(install/.venv/bin/python tools/mfw_task_selection.py \
  --candidate "$CANDIDATE" --date "$MJA_OPERATION_DATE" \
  --result-root "$MJA_RESULT_ROOT")
printf '%s\n' "$selection" > "$CANDIDATE/debug/selection.json"
ticket=$(install/.venv/bin/python tools/mfw_live_acceptance.py begin \
  --candidate "$CANDIDATE" --owner integrator \
  --selection "$CANDIDATE/debug/selection.json")
(
  cd "$CANDIDATE"
  ./MFW
)
install/.venv/bin/python tools/mfw_live_acceptance.py finish \
  --ticket "$ticket" --record verification/mfw/repair/batch.json
```

如果 native stop 形成部分批次，`finish` 的非零结果是预期的停止证据；修复完成后必须重建不可变候选并整批复跑失败+未执行集合。当天正式 import 的 22 个业务任务全部有 fresh 业务后置条件和 native 终态后，才能报告 full 范围收敛。
