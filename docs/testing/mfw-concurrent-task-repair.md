# MFW 批量任务修复操作规约

本文是 MJA 在同一台 Android 模拟器上执行 MFW 任务时的操作协议。代码分析和离线测试可以并行；每个真实业务任务由独立 execution subagent 负责，普通任务并发派发，但同一 serial 的 MFW/ADB/截图/游戏状态操作必须由 `tools/mfw_simulator_lock.py` lease 串行化。启动真实 MFW 前确认没有第二个 active native runner。

## 基线与隔离

1. 先从用户批准的干净提交创建一个独立 worktree 和分支；每个业务任务一个 worker，不允许多个 worker 直接写同一个工作区。
2. 每次尝试都从当前源代码构建不可变候选包，使用唯一输出目录；候选包一旦开始实机运行就不再编辑。
3. 游戏启动已经单独通过 Maa_bbb 同构启动门禁。每个 execution worker 都必须运行自己的 `GAME_START + 一个业务任务`；不得把多个业务任务放进同一 profile。

## 离线阶段

worker 只修改自己拥有的 pipeline、workflow、策略和测试文件。先运行该任务的 focused contract tests，再运行相关 Android/MFW 静态测试；通过后打包候选。日志分析、代码修改、测试和构建均在当前执行环境中完成。
候选构建和每次启动前都自动执行一次离线 profile 修复：

```bash
install/.venv/bin/python tools/mfw_profile.py ensure-pair-profiles \
  --install "$CANDIDATE"
```

该命令会为每个 active、非退休任务自动生成并注册唯一的
`GAME_START + 一个业务任务` profile；它不启动 MFW、ADB、模拟器或 Controller。
因此正常启动不再因为遗漏某个 pair profile 而停下来询问用户。

## 实机验收阶段

普通 worker 在启动 MFW 前必须取得覆盖 `GAME_START + 业务任务 + native teardown`
的 simulator lease；等待 lease 时不得启动 MFW、Maa Controller、ADB 或截图。
锁持有期间每 60 秒由本地 lock manager probe owner；明确 idle/release 或
owner 已死且有匹配 teardown evidence 才能释放/回收；无响应一律 `LOCK_BLOCKED`。
lease helper 只管资源，不调度任务、不判定业务成功、不注入输入。

先创建新鲜验收 ticket：

```bash
ticket=$(install/.venv/bin/python tools/mfw_live_acceptance.py begin \
  --candidate "$CANDIDATE" --owner "$WORKER" --task "$TASK_ID")
```

随后从候选目录直接运行 MFW（必须在上述 lease 内）：

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

只有 `finish` 返回 0，并且同时拥有 GUI 精确顺序、MaaFramework 新鲜 native
terminal、该任务新鲜 `result.json`、任务后置条件、Tasker/Controller teardown
和 released/safely-reclaimed lease，worker 才能交付。

## 失败路由

- exact task order mismatch：先修正 MFW 勾选状态并重新创建 ticket，不修改代码。
- native `Failed`：只修复该任务拥有的识别、动作或终止路由，并增加 focused regression assertion。
- 业务结果为 `running`：补齐所有可达终止分支的 outcome recorder，不能把超时当成功。
- 业务结果为 `failed`：根据该次结果的 `postcondition`、`error_code`、最新错误图像、`gui.log.slice` 和 `maafw.log.slice` 定位真实失败状态。
- native 成功但业务失败：业务结果优先；修复错误的 wrapper success。
- `not_eligible`：只有任务策略明确允许当前日期、资源或资格状态时才可接受，并且 native task 也必须成功。
- stale result：旧结果不参与验收；修改后重新打包、创建新 ticket、重新运行。

## 正式任务矩阵

每一行表示一个独立 worker；第一项永远是该 worker 自己的启动任务。普通
worker 可并发派发，业务失败只影响当前 worker，不创建 suffix continuation，
不把未运行任务伪造成失败。

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

worker 先提交实现和离线测试，再提交对应的 acceptance summary；两者一起交给
integrator。integrator 逐个复核 fresh evidence 后，按正式矩阵集成，不接收只有
`Tasker.Task.Succeeded` 的 worker。

最终集成从干净源代码构建不可变候选，自动检查 GPU 使用 `-gpu host`，用只读选择器
冻结范围并派发普通 worker；这些都是无交互机器检查，不向用户重复确认。普通 worker 全部 settled 且安全释放 lease 后，才按
`DAILY_TASK_REWARD_CLAIM_DAILY -> BATTLE_PASS_REWARD_DAILY` 串行创建两个后置
worker；每个后置 worker 也自带 `GAME_START` 和独立 lease。

```bash
selection=$(install/.venv/bin/python tools/mfw_task_selection.py \
  --candidate "$CANDIDATE" --date "$MJA_OPERATION_DATE" \
  --result-root "$MJA_RESULT_ROOT")
printf '%s\n' "$selection" > "$CANDIDATE/debug/selection.json"
# 每个 worker 另外创建自己的 pair ticket；全局 selection 只作为范围快照。
ticket=$(install/.venv/bin/python tools/mfw_live_acceptance.py begin \
  --candidate "$CANDIDATE" --owner "$WORKER_ID" \
  --selected-task "$TASK_ID" --profile-name "$PROFILE_NAME")
install/.venv/bin/python tools/mfw_profile.py run \
  --install "$CANDIDATE" --profile-name "$PROFILE_NAME" \
  --expected-task GAME_START --expected-task "$TASK_ID"
install/.venv/bin/python tools/mfw_live_acceptance.py finish \
  --ticket "$ticket" --record "verification/mfw/repair/$TASK_ID.json"
```

当天正式 import 的 22 个业务任务只有在各自 fresh 业务后置条件、native 终态、
teardown 和 lease evidence 都齐全后，才能报告 full 范围收敛；失败/阻塞任务须
先汇报，等待 post-report 修复或复跑授权，不自动重跑。
