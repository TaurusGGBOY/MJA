# MJA Maa_bbb 游戏启动实机验收

日期：2026-08-08（Asia/Shanghai）  
候选：`install/mfw-game-startup-maa-bbb-20260808-final-r4`  
源代码提交记录：`5815ae03df72c1bce68ec8c08a6ee59a2656db02`

## 结论

最终候选已在 MFW 图形界面中完成启动链实机验收。r3 的同一不可变启动树完成了未知/白屏/黑屏到主页的冷启动，r4 在当前模拟器状态下再次通过 `GAME_START`，并与邮件任务完成 pair 验收；MFW 均记录任务完成，原生 MaaFramework 记录 `Tasker.Task.Succeeded`。

本次没有发现游戏因内存不足、OOM、ANR 或进程崩溃导致的启动失败。MFW 的 embedded agent loader 会把 `AgentServer.custom_action` 按其运行时约定改写为 `resource.custom_action`；候选校验器已对这一确定性改写做规范化处理，实机运行后再次校验通过。

## 候选与静态校验

候选 metadata：

- `payload_sha256`: `5cfa412465277353ffadddb9d90be174ed136ab310b31064676768a2ebc13c5f`
- `immutable_tree_sha256`: `5ce41097c69ffc3a96fece8f89bb7659b88808f6ddbf4cd1e46697bd831a7231`
- MFW：`v4.8.23`
- MaaFramework：`v5.12.3`

已通过：

- 启动、接口、预设、Android 资源和候选安装测试：`49 passed`
- Android 锁、运行器、日常运行和 live acceptance 回归：`45 passed`
- MFW 任务契约：`56 passed`
- `python3 tools/check_mfw_resources.py assets/resource/base`：1264 个节点，0 个错误
- `install/.venv/bin/python tools/mfw_install.py --verify-candidate install/mfw-game-startup-maa-bbb-20260808-final-r4`：通过
- `install/.venv/bin/python tools/load_mfw_resource.py install/mfw-game-startup-maa-bbb-20260808-final-r4`：MaaFramework v5.12.3，加载通过
- `git diff --check`：无输出

启动资源覆盖实机观测到的 `点击开始游戏！`、`点击开始游戏!`、`进入游戏`、`正在连接服务器`、`正在加载配置表`、`穿梭入世中` 等变体；白屏和纯黑画面均为无输入等待叶节点。

## MFW 图形界面验收

- 18:09:38：MFW 只执行 `GAME_START`，使用入口 `MJA_GAME_START_ENTRY`。
- 18:09:40：`MJA_GAME_LAUNCH` 以 `StartApp` 启动 `com.hanjiasongshu.dr22/.MainActivity`。
- 18:09:45：命中 `MJA_START_WHITE_SCREEN_WAIT`，全屏 ColorMatch 计数 `917820`，执行 `DoNothing` 等待。
- 18:09:55：命中纯黑 `MJA_START_BLACK_SCREEN_WAIT`，计数 `892341`，执行无输入等待。
- 18:10:03：OCR 命中 `点击开始游戏！`，标题节点点击成功。
- 18:10:14：OCR 命中 `正在连接服务器`；18:10:16 再命中 `穿梭入世中`，加载节点等待成功。
- 18:10:31：`MJA_GAME_READY` 命中 `home/home_marker.png`，分数 `0.845520`，随后 `RuntimeHealth` 返回 `true`。
- 18:10:32：`MJA_GAME_START_ENTRY` 的 `Tasker.Task.Succeeded` 到达，MFW 记录“所有任务都已完成”。

完整原始日志保留在候选的 `debug/maafw.log` 和 `debug/gui.log`；冷启动对应窗口为 18:09:30–18:10:32，r4 pair 对应窗口为 18:36:56–18:37:12。

## r4 业务 pair 验收

- ticket：`debug/acceptance/MAIL_REWARD_DAILY/20260808T103623757251Z/ticket.json`
- 任务顺序严格为 `GAME_START` → `MAIL_REWARD_DAILY`，没有夹入其他任务。
- `GAME_START` 在 18:37:04 完成；邮件任务在 18:37:06 启动并于 18:37:12 完成。
- acceptance 结果为 `passed`；邮件状态为 `already_complete`，后置条件为 `mail.empty`。
- 结果摘要：`verification/mfw/repair/MAIL_REWARD_DAILY-FINAL-R4.json`。

r4 相比 r3 只加入了邮件任务在“功能面板已打开”时的入口分支；启动树的 `immutable_tree_sha256` 保持不变，因此冷启动证据仍直接覆盖正式 r4 的启动资源。

## 模拟器和内存证据

本次实际 QEMU 命令包含 `-gpu host`、`-memory 4096` 和 `-port 5556`。AVD 配置同时为 `hw.gpu.enabled=yes`、`hw.gpu.mode=host`、`hw.ramSize=4096M`，未使用 software、auto、SwiftShader 或其他 GPU 回退。

冷启动结束后的只读内存检查：游戏 PSS 约 `1,319,221 KB`，RSS 约 `1,505,976 KB`，Swap 为 `0 KB`；设备保持 `device` 状态。验收时间窗没有 `am_proc_died`、`am_kill`、`LOW_MEMORY`、`OutOfMemory`、ANR 或 `FATAL EXCEPTION`。

历史失败现场的 `SIGKILL` 没有配套 lmkd/low-memory/OOM 证据；宿主日志中的 `Failed to find ColorBuffer` 属于图形/模拟器侧风险观察，不能据此判定为内存不足。本项目继续固定使用 `-gpu host`。

## 禁止项检查

针对最终候选本次启动窗口的 MAA 日志检查结果：

- `MJA_GAME_BACK_`：0
- `MJA_START_UNKNOWN_ABORT`：0
- `ClickKey`：0
- `keycode 4`：0
- 启动链 `StopApp`：0
- `GAME_STOP` 的 `StopApp`：不属于本次 `GAME_START` 运行

本报告只确认启动链。未在最终候选上逐项 fresh 验收的业务任务，仍由并发任务修复计划管理，不在此报告中宣称通过。
