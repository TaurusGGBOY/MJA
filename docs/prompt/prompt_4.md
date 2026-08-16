  请接手当前 MJA 项目的 MFW 全量批量验收/修复覆盖工
  作，不要从头重跑。

  项目目录：
  /Volumes/my_disk/project/MJA

  必须使用：
  $mfw-batch-repair-jianzhichuan
  如需分析失败根因，使用 systematic-debugging 思路。

  当前目标：
  完成 2026-08-16 当天所有 active、date-eligible 日
  常任务的 fresh MFW 覆盖，记录真实失败根因、证据和
  runner 生命周期。当前只是覆盖和诊断，暂时不要修改
  daily pipeline；必须等最终失败报告后用户明确授权才
  能修复。

  重要约束：

  - 只使用候选：
    /Volumes/my_disk/project/MJA/install/mfw-batch-
    20260816-full-startup-optional-r1
  - 不运行真实 pipeline、真实游戏流程以外的额外自动
  化；不要使用 watchdog。
  - 同时只能有一个 native MFW runner。
  - 发现旧 runner 时，按“最新 runner 优先”处理：只核
  对并终止旧 shell/profile/MFW 精确 PID 链，不要杀
  emulator、ADB 或无关进程。
  - 当前批次必须先确认 native teardown，再释放 stale
  wrapper。
  - 每批都要 exact profile verify + Android
  preflight 后才能启动。
  - 每个失败批次只让 native 任务流自行停止；不要靠外
  部杀进程制造失败。
  - 不要重复执行已经有本轮 fresh 结果的任务。
  - 不要把失败/Abort 改成成功。
  - 不要修改 common/terminal.json、common/
  home_boundary.json、任何 daily pipeline、startup/
  game_start.json。
  - 当前工作区已有用户改动，不能回滚：
    assets/resource/base/pipeline/startup/
    game_start.json
    tests/test_mfw_startup_pipeline.py
  - 不要使用 git reset、checkout -- 等破坏性操作。

  当前轮目录：
  /Volumes/my_disk/project/MJA/verification/mfw/
  repair/20260816-full-r4

  候选信息：
  - MJA commit：
  91560d6722d99665fa5aaca2c5b0cbd1655238d3
  - 主线检查点：0180d18
  - candidate payload sha256：

    2a0d4ef107cb9ce8f37cd34978341ca76201d2dfeed7c2ae
    2c6d75753a0ea404

  全量选择的 20 个业务任务：

  MAIL_REWARD_DAILY
  SHOP_FREE_GIFT_DAILY
  BUY_TEA_DAILY
  FREE_APPRAISAL_DAILY
  TRIAL_SWORD_DAILY
  HERO_DISPATCH_DAILY
  COLLECTION_DEPLOYMENT_DAILY
  SHADOW_RUINS_DAILY
  SPEND_CONDENSATE_DAILY
  MARTIAL_STUDY_BREAKTHROUGH_DAILY
  EAT_STAMINA_FOOD_DAILY
  EQUIPMENT_DECOMPOSE_DAILY
  DUNGEON_SWEEP_DAILY
  JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY
  RING_CHALLENGE_DAILY
  GUILD_ACTIVITY_CHALLENGE_DAILY
  GUILD_AFFAIRS_DAILY
  GUILD_DONATION_DAILY
  DAILY_TASK_REWARD_CLAIM_DAILY
  BATTLE_PASS_REWARD_DAILY

  WEEKLY_FREE_GIFT_MONDAY 因为今天是周日而省略。
  BREAK_ARRAY_MARTIAL_DAILY 已退休。

  截至目前的 fresh 覆盖结果：

  - 成功：
    MAIL_REWARD_DAILY
    EAT_STAMINA_FOOD_DAILY
  - 失败：
    SHOP_FREE_GIFT_DAILY
    BUY_TEA_DAILY
    FREE_APPRAISAL_DAILY
    TRIAL_SWORD_DAILY
    HERO_DISPATCH_DAILY
    COLLECTION_DEPLOYMENT_DAILY
    SHADOW_RUINS_DAILY
    SPEND_CONDENSATE_DAILY
    MARTIAL_STUDY_BREAKTHROUGH_DAILY
    EQUIPMENT_DECOMPOSE_DAILY
    DUNGEON_SWEEP_DAILY
  - 尚未尝试：
    JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY
    RING_CHALLENGE_DAILY
    GUILD_ACTIVITY_CHALLENGE_DAILY
    GUILD_AFFAIRS_DAILY
    GUILD_DONATION_DAILY
    DAILY_TASK_REWARD_CLAIM_DAILY
    BATTLE_PASS_REWARD_DAILY

  GAME_START 在当前 r4 各批次均已成功；不要把之前 r3
  的 GAME_START 问题混入本轮失败结论。

  已完成的 continuation 批次：

  - 首批：MAIL 成功，SHOP 失败
  - continuation1：BUY_TEA 失败
  - continuation2：FREE_APPRAISAL 失败
  - continuation3：TRIAL_SWORD 失败
  - continuation4：HERO_DISPATCH 失败
  - continuation5：COLLECTION_DEPLOYMENT 失败
  - continuation6：SHADOW_RUINS 失败
  - continuation7：SPEND_CONDENSATE 失败
  - continuation8：MARTIAL_STUDY_BREAKTHROUGH 失败
  - continuation9：EAT 成功，然后
  EQUIPMENT_DECOMPOSE 失败
  - continuation10：DUNGEON_SWEEP 失败
  - continuation11：当前正在/刚开始执行 JIANLIN，尚
  未得到最终结果

  当前已知 cont11 runner：
  - shell PID：81268
  - profile PID：81274
  - MFW PID：81276
  - profile：
    每日 MFW 剑之川 full 20260816 r4 continuation11
  - 日志：
    verification/mfw/repair/20260816-full-r4/mfw-
    profile-cont11.log
  - ticket：
    /Volumes/my_disk/project/MJA/install/mfw-batch-
    20260816-full-startup-optional-r1/debug/
    acceptance/BATCH/20260815T194645668969Z/
    ticket.json
  - preflight：
    verification/mfw/repair/20260816-full-r4/
    continuation11-preflight.json
  - 生命周期：
    verification/mfw/repair/20260816-full-r4/runner-
    lifecycle.json

  我在等待 cont11 时被用户中断了。接手后的第一步：

  1. 检查 PID 81268/81274/81276 是否仍存在。
  2. 查看 cont11 profile 日志和候选 native 日志：
     /Volumes/my_disk/project/MJA/install/mfw-batch-
     20260816-full-startup-optional-r1/debug/
     maafw.log
  3. 如果 JIANLIN 仍在 native 执行且没有 teardown，
  不要启动新 runner，继续等待/观察。
  4. 如果已经出现完整 native teardown：
     - 读取 fresh result.json 和截图/动作证据；
     - 调用 mfw_live_acceptance.py finish
     --partial；
     - 更新 runner-lifecycle.json；
     - 只对已核对的 81268、81274、81276 精确发送
     SIGTERM，并验证全部消失；
     - 再生成 continuation12，只包含尚未尝试的后缀任
     务。
  5. 不要重复 JIANLIN，也不要重复任何已有 fresh 结果
  任务。

  已知明确根因证据：

  SPEND_CONDENSATE_DAILY：
  native 日志出现：
  error handling loop detected [node.name=消耗凝结
  体-主页-探测]
  随后任务返回 False，native 正常 StopTask/
  teardown。
  这是目前唯一已经从 native 日志明确确认到具体节点的
  根因。

  其他失败任务不能只写“Tasker 返回 False”。必须从对
  应 fresh result.json、GUI 日志、native 日志、截图
  和动作证据继续追到：
  - 失败节点；
  - 预期状态；
  - 实际状态；
  - 上游为什么没有进入/识别错误；
  - 最终终止动作和错误码/后置条件。
  如果证据不足，明确写 diagnostic_status=blocked，不
  要猜原因。

  继续方式：

  - 每个 continuation 配置放在候选的 config/configs/
  下，当前已有 cont1 到 cont11。
  - multi_config.json 当前应指向 cont11；生成新
  continuation 时更新为新 config id。
  - selection 文件放在当前轮目录。
  - 每批任务顺序必须严格是 GAME_START + 剩余任务原始
  顺序。
  - 每批启动前运行：
    .venv/bin/python tools/mfw_profile.py verify ...
    .venv/bin/python tools/mfw_android_preflight.py
    --output ...
  - 使用 mfw_live_acceptance.py begin/finish 管理
  ticket。
  - 直到 20 个业务任务全部有 fresh 结果，或触发
  GAME_START 无进展门禁，才结束覆盖。

  最终必须生成/完善：
  verification/mfw/repair/20260816-full-r4/
  failure_ledger.json

  最终报告必须以：
  【失败原因】
  开头，并包含：

  - 每个任务的成功/失败/未运行状态；
  - 每个失败的根因，而不是表象；
  - 失败节点、预期/实际状态、终止动作、错误码/后置条
  件；
  - batch、ticket、acceptance、result.json、日志和截
  图证据路径；
  - runner lifecycle 以及每次旧 runner 的精确终止记
  录；
  - GAME_START、ADB、GPU preflight 结果；
  - 未解决问题和 diagnostic_status=blocked 项；
  - 运行过的离线校验和 pytest。

  最后执行：
  python3 tools/check_mfw_resources.py assets/
  resource/base

  可运行相关离线 pytest，但不要运行真实 pipeline，也
  不要在本次覆盖结束后自动修改 pipeline。完成报告后，直接进行修复。

直到进行两轮修复之后 失败的任务还是没有减少 就停止
