# 2026-08-09 MFW Android 全量运行记录

## 目标与验收口径

- 运行环境：macOS 上的 Android 模拟器 `mja-api35-apis`，固定序列号 `emulator-5556`。
- 最新待实跑候选包：`install/mfw-android-all-20260809-r22`；payload SHA-256 为 `1383033eb2c8dcb54b5dd976dab6bd30a9ee5996021ce918aac6f9df9ce4da6a`，完整树 SHA-256 为 `5ce41097c69ffc3a96fece8f89bb7659b88808f6ddbf4cd1e46697bd831a7231`，构建后候选校验通过。每个正式任务使用全新空 `debug`，结束后整目录归档。
- 最终全量配置：`今天全部任务（除周一限定）`，包含 `GAME_START` 和 20 个非周一业务任务。
- 2026-08-09 是星期日；按本轮要求，`WEEKLY_FREE_GIFT_MONDAY` 不进入最终队列，也不以 `not_eligible` 代替“排除”。
- 真实模拟器操作全部直接在当前执行环境中进行。
- 成功证据以新鲜 `result.json` 和 `tools/mfw_live_acceptance.py finish` 为准，不能只看 `Tasker.Task.Succeeded`。

## 环境预检

- 模拟器已启动，ADB 状态为 `device`，`sys.boot_completed=1`。
- 实际 QEMU 命令行包含 `-gpu host`；渲染器为 Android Emulator OpenGL ES Translator (Apple M4)。
- AVD 保持 `hw.gpu.enabled=yes`、`hw.gpu.mode=host`。
- MFW Controller 与 Resource 分别只有 `android`、`mja_android`；未使用 macOS 控制器或原生游戏 App。
- 候选包 `tools.mfw_install --verify-candidate` 校验通过。

## 问题 1：旧候选包完整性失效

现象：旧 MFW 候选包在启动前校验时报 `candidate payload hash mismatch`，且缺少近期修复标记。

原因：旧候选包来自迁移前路径，项目 payload 已变化，不能再作为当前源码的可验证候选包。

解决方案：从已知 MFW 运行时重新派生 `install/mfw-android-all-20260809-r1`，写入当前 Android-only payload；新候选的 payload SHA-256 为 `33c4da941dd545127448c34fca12b411b2e026127e5284b8c6f20dca1c3ee6fa`，完整树 SHA-256 为 `5ce41097c69ffc3a96fece8f89bb7659b88808f6ddbf4cd1e46697bd831a7231`。

## 问题 2：MFW 界面自动化无法抓屏

现象：Computer Use 能发现正在运行的 `com.gaoguobin.MFAAvaloniaJianzhichuan`，但读取窗口状态返回 `Computer Use server error -10005: The screen capture failed`。

原因：Computer Use 服务当前没有可用的 macOS 屏幕录制捕获权限；这是桌面验证通道问题，不是 MFW 或模拟器问题。

解决方案：本轮使用 MFW 官方 `--config-id=<id> --direct-run` 执行已保存的 `日常-完整版`。该入口与在 MFW 中选择配置后点击开始使用相同任务流。后续若要恢复桌面点击验证，需要在 macOS 隐私设置中为 Computer Use/ChatGPT 授予屏幕录制权限，并建立新会话复测。

## 问题 3：保存的配置缺少 ADB 子配置

现象：首次 direct-run 在任何业务任务开始前停止，`gui.log` 报 `ADB路径为空，请在控制器中配置ADB路径`。

原因：保存的 `Controller.task_option` 只有 `controller_type: android`，没有 MFW 实际读取的 `android.adb_path` 与 `android.address`。

解决方案：在完整/简化配置中补齐：

```json
{
  "controller_type": "android",
  "android": {
    "adb_path": "/Volumes/my_disk/project/MJA/install/android-sdk/platform-tools/adb",
    "address": "emulator-5556",
    "emulator_path": "",
    "emulator_params": "",
    "wait_time": 30,
    "config": {}
  }
}
```

复测结果：MFW 成功连接 `emulator-5556`，创建 1280×720 MaaFramework ADB 控制器并开始 `GAME_START`。

## 问题 4：GAME_START 在登录奖励页重复启动 App

现象：游戏标题页被正确识别并进入加载；登录完成后画面 OCR 稳定识别到 `点击空白处关闭`（现场框约 `[570, 660, 138, 26]`）。现有启动路由没有处理该提示页，随后 `MJA_GAME_LAUNCH` 的 DirectHit 每约 12 秒执行一次 `StartApp`，`GAME_START` 无法结束，也没有生成新鲜结果文件。

原因：启动路由只有基于关闭图标模板的 `MJA_KNOWN_POPUP_CLOSE`，没有“点击空白处关闭”这种全屏奖励页的 OCR 叶处理器；无条件的 App 启动兜底位于其后，因此未知提示页会触发重复重启。

解决方案：已在 `MJA_GAME_LAUNCH` 前加入仅匹配稳定 OCR 文案 `点击空白处关闭` 的 Click + JumpBack 叶处理器，并补充 bounded-cycle 与路由测试；定向测试共 32 项通过。修复已打入 `install/mfw-android-all-20260809-r2`。首次定向实跑尚未到达该节点，被下述 MFW 监控控制器取图争用阻断，因此仍需新的真实验收票据证明。

## 问题 5：MFW 自动监控与业务 Tasker 并发取图时卡死

现象：r2 定向配置只勾选 `GAME_START + MAIL_REWARD_DAILY`。业务 Tasker 于 `12:16:10` 完成 `MJA_GAME_START_ENTRY` 的首个节点后，在第二次取图处停止推进；主任务取图子进程变为 `<defunct>`。同一时刻 MFW 自动启动第二个 ADB 监控控制器，并以 30 FPS 持续执行 `screencap | gzip -1`。直到 `12:18:30`，业务线程仍无任何新节点事件，`gui.log` 也停止更新。

原因：当前 MFW 在主任务设备就绪后无条件启动独立预览监控；监控与业务控制器并发连接并高频访问同一个 `emulator-5556`。本次两条取图链路在启动窗口重叠，业务控制器未收到截图完成事件。

解决方案：将候选包的可变 MFW 配置 `monitor_capture_fps` 从 30 降为 1，并关闭 `monitor_recognition_roi_enabled`，减少预览控制器对 ADB 与 CPU 的压力。新票据复跑时业务 Tasker 正常越过第二次取图点，并持续执行节点；该运行没有再复现取图僵死。最终全量运行继续沿用此配置。

## 问题 6：关闭登录奖励后停在月签到页

现象：r2 降频复跑中，`MJA_KNOWN_CLICK_BLANK_TO_CLOSE` 于 `12:21:46` 以约 0.9998 的 OCR 置信度命中，随后成功点击并关闭奖励明细。下一层画面是“八月·签到”月签到页，右上角有红色关闭 X；现有 `MJA_KNOWN_POPUP_CLOSE` 与 `MJA_KNOWN_PAGE_CLOSE` 均未命中。启动路由因而再次落入 `MJA_GAME_LAUNCH`，每轮执行 `StartApp`，无法完成 `GAME_START`。

原因：月签到页使用独立版式，关闭按钮约位于 `[1048, 125, 60, 50]`，不在通用弹窗关闭模板的 `[1180, 10, 70, 70]` ROI 内；启动路由也没有以“八月·签到/已签到/累计签到”为页面锚点的专用叶节点。

解决方案：新增 `MJA_KNOWN_MONTHLY_SIGNIN_CLOSE`，同时要求月份签到标题正则与“累计签到”命中，再点击右上角安全区域 `[1052, 144, 32, 32]`；节点以有界 JumpBack 叶处理器放在主页识别之前。离线测试 32 项和 1284 个资源节点校验通过。r3 实跑于 `12:33:19` 同时命中“八月·签到/累计签到”，并在 `(1075,167)` 点击成功。现场截图：`debug/live-captures/2026-08-09-monthly-signin.png`。

## 问题 7：主页模板现场分数低于启动阈值

现象：月签到页关闭后已经进入实际主页，`MJA_GAME_READY` 连续多轮对 `home/home_marker.png` 得到完全稳定的 `0.767864`，但当前阈值为 `0.80`，因此主页被判定失败并落入 `MJA_GAME_LAUNCH`。现场截图显示顶部“副本/画卷/圆形图标”与模板一致，同时游戏世界画面存在大面积洋红/黑色纹理异常。

原因：当前 host-GPU 模拟器帧中的色彩/纹理与采集模板有明显差异，导致结构一致的主页标记得分略低于静态阈值；这不是页面导航失败。项目约束禁止切换到 software/SwiftShader，因此不能用更换 GPU 后端规避。

解决方案：将 base MFW 资源中所有现存的 31 个 `home/home_marker.png` + `[1040,0,240,110]` 主页探针统一校准为 `0.75`，低于现场稳定分数 `0.767864`，并新增全局契约测试保证以后新增引用也保持一致。主工作区比独立 worktree 多 5 个后加入的帮会任务探针，集成时已一并校准；最终相关测试 33 项通过，1284 个资源节点零错误。修复进入 `install/mfw-android-all-20260809-r4`。同一 AVD 随后以 canonical SDK 和 `-gpu host` 无快照重启，重启后紫黑纹理消失。r4 定向 MFW 于 `12:57:49` 完成 `GAME_START`，随后 `MAIL_REWARD_DAILY` 生成新鲜 `already_complete`/`mail.empty` 结果；正式 `finish` 返回 0。

## 问题 8：模拟器重启进程需要脱离一次性执行会话

现象：第一次用普通后台子进程重启模拟器时，ADB 已就绪、QEMU 命令也已验证包含 `-gpu host`，但外层执行会话结束后 QEMU 随进程组退出。两次尝试用 `launchctl submit` 托管 Android emulator 前端和 QEMU，进程都停在 GUI 初始化前且没有建立 ADB。首次 tmux 启动又被项目启动脚本的 `pgrep` 误判为“已有同 AVD”，因为外层诊断命令本身包含匹配文本。

原因：一次性命令执行器会清理同一进程组；Android emulator 的 macOS GUI 前端又不能在本轮 launchd 守护上下文中正常初始化。项目启动脚本采用 `pgrep -f`，会匹配包含 QEMU 参数的外层诊断命令行。

解决方案：创建后台 tmux 会话，并由该会话直接执行 canonical SDK 的 `emulator` 二进制与固定参数，避免启动脚本的自匹配；等待 `sys.boot_completed=1` 后核验实际 QEMU。最终进程为 `/Volumes/my_disk/project/MJA/install/android-sdk/emulator/qemu/darwin-aarch64/qemu-system-aarch64 ... -gpu host ... -port 5556`，tmux 会话在外层执行会话结束后保持在线。重启后截图为 `debug/live-captures/2026-08-09-home-after-host-restart.png`。

## 非阻塞日志

- MFW 全局快捷键监听线程在 macOS 报 `Must be run as administrator`，但不影响 direct-run、ADB 连接或 MaaFramework 任务执行。
- MFW 未配置 GitHub 更新地址，启动时显示更新检查失败；本地候选包仍继续执行，不是任务失败。

## 问题 9：r4 首次全量运行的跨任务状态污染与结果生命周期不闭合

现象：r4 全量配置确认 26 项全部勾选（`PreTask + Controller + Resource + GAME_START + 21 个业务任务 + Post-Action`），运行时间 `12:59:47–13:07:35`。`GAME_START` 与邮件任务先成功；商城进入“周期福利”后，游戏在 `13:00:29` 掉到 Android launcher，`MJA_SHOP_BENEFITS_PAGE_PROBE` 最终触发 error-handling loop。此后购买茶叶至破阵前的任务大多在 launcher 上超时。破阵自定义动作重新拉起了游戏，后续帮会任务恢复执行；帮会捐献写出成功后却停留在捐献弹窗，最后两个奖励任务又被该页面连锁阻断。

原因：至少包含三类独立根因：

1. 多数任务 root 只有页面候选列表，全部识别失败时没有有界 `GAME_START` 恢复，应用不在前台时直接 Tasker failed。
2. `BeginTask` 先写 `running`，但原生 Tasker failed 分支没有统一调用 `RecordTaskOutcome`，所以 14 个新鲜结果停在 `running`；`BREAK_ARRAY_MARTIAL_DAILY` 甚至没有生成结果。
3. 成功任务没有统一归位约束；帮会捐献业务后置条件成立，但结束时未关闭捐献弹窗，污染后续任务。

证据汇总：本轮 20 个业务 `result.json` 中，邮件为 `already_complete`，帮会捐献为 `success`；副本、剑林、帮会活动、帮会事务为显式 `failed`；其余 14 个为 `running`；破阵无结果。全量 `finish` 正确返回 1，首个错误为 `SHOP_FREE_GIFT_DAILY: native terminal events=['Failed']`。失败截图保存在 `install/mfw-android-all-20260809-r4/debug/on_error/`，全量结束现场为 `debug/live-captures/2026-08-09-after-full-r4.png`。

解决方案：按正式业务任务分别使用独立 sub-agent/worktree 修复并做 `GAME_START + 指定任务` 定向 MFW 验收；首先处理商城有界恢复、购买茶 launcher 恢复、破阵资源契约和帮会捐献归位。完成定向验收后再跑新的全量票据，避免把前序页面污染误判为后序任务自身缺陷。

## 问题 10：r5 单任务验收配置没有注册

现象：r5 中已经生成商店、买茶、破阵和帮会捐献的 pair 配置文件，但 MFW 用 `--config-id` 启动时无法切换到这些配置。

原因：配置文件存在于 `config/configs/`，但 ID 没有加入 `config/multi_config.json` 的 `config_list`；MFW 不会仅凭文件存在自动注册配置。

解决方案：把 4 个 pair ID 注册到 `multi_config.json`，并在 r7 继续沿用。后续新增的副本、剑林、帮会活动和帮会事务 pair 配置也同时注册，且逐一核对只有 `GAME_START + 指定业务任务` 被勾选。

## 问题 11：商店已到“周期福利”却没有进入领取分支

现象：r5 的 `SHOP_FREE_GIFT_DAILY` 已稳定进入“周期福利”页，OCR 同时看到“周期福利”和“免费领取”，但任务仍走到 `SHOP_RUNTIME_RECOVERY_EXHAUSTED`。

原因：`MJA_SHOP_BENEFITS_PAGE_PROBE.next` 只有 `MJA_SHOP_STATUS_PROBE`。该子节点识别失败时，MaaFramework 回到父节点的 `on_error`，不会执行子节点自己的 `on_error`，所以 `MJA_SHOP_CLAIM_GATE` 从未获得机会。

解决方案：把领取 gate 作为同级候选加入 benefits page 的 `next`：`[MJA_SHOP_STATUS_PROBE, MJA_SHOP_CLAIM_GATE]`，并补充资源路由测试。r7 正式验收通过，结果为 `success / shop.daily_free_gift_claimed`；`GAME_START` 和商店任务的原生终态均恰好一次 `Succeeded`。随后买茶 r7 正式验收也通过，结果为 `success / tea.inventory_decremented`。

## 问题 12：MFW 日志轮转后验收工具从 EOF 之后读取

现象：商店业务已成功且新鲜结果正确，但首次 `finish` 报 `GAME_START native terminal events=[]`。

原因：候选包继承了旧 debug 日志，票据保存的 `maafw.log` offset 约 17.4 MB；MFW 启动时把日志轮转/截断到约 2 MB，验收工具仍从旧 offset seek，得到空后缀。

解决方案：`tools/mfw_live_acceptance.py` 在读取日志后缀前检查当前文件大小；若小于票据 offset，则从 0 读取。已加入日志截断回归测试，共 9 项验收工具测试通过；同一张真实商店票据复核返回 0。

## 问题 13：破阵自定义动作失败时无结果且外层假成功

现象：r7 pair 中 `GAME_START` 成功；`BreakArrayMartialDailyAction` 在正常主页运行约 13 秒后返回 false，没有生成新鲜 `result.json`。入口节点的 `on_error` 又跳回 `MJA_GAME_START`，最终外层发出 `Tasker.Task.Succeeded`。正式 `finish` 正确拒绝，报 `BREAK_ARRAY_MARTIAL_DAILY: no fresh result`。

原因：MFW 上下文没有 `context.diagnostics`，进程也没有 `MJA_DEBUG_DIR`，自定义动作退化为没有 `write_task_result` 的 `SimpleNamespace`；同时入口没有使用已存在的 `BeginTask/diagnostics_for` 生命周期，错误路由还把业务失败转换成了启动成功。

解决方案：在独立 break-array worktree 中把动作接入 active `TaskDiagnostics`，让成功、失败和异常都写出新鲜业务结果；入口改成 `BeginTask -> 自定义动作`，失败进入真实 abort，禁止 `[JumpBack]MJA_GAME_START` 制造绿色假象。离线修复已完成，仍需打入新候选并做正式 pair 实跑。

## 问题 14：帮会捐献退出按钮阈值过高，污染下一任务

现象：r7 的帮会捐献 pair 业务结果为 `already_complete / guild.donation.remaining_9_of_10`，正式 `finish` 返回 0，但任务结束后仍停在“帮会捐献”弹窗。随后副本 pair 的前置 `GAME_START` 只剩 `GAME_START` 一个实际任务事件，并在该页面上反复执行 `StartApp`；副本本体没有启动，`finish` 报任务顺序只有 `('GAME_START',)`。现场截图为 `/tmp/mja-dungeon-block-20260809.png`。

原因：捐献页右上角 X 的 ColorMatch 被分成 4 个连通块，现场计数为 23、57、73、21，而识别器要求单个连通块 `count=180`，所以 guarded close 没有执行；legacy close 也不适配 Android 版页面。随后 `MJA_GUILD_DONATION_EXIT_CLEANUP_STOP` 仍允许任务成功结束。`GAME_START` 又没有该业务弹窗的专用关闭叶，造成跨任务污染。

解决方案：需要降低/重构 Android 捐献 X 的稳定识别门槛，并把“业务成功”与“已回到主页”一起作为终态约束；修复后重新验收帮会捐献和副本。当前这两项不能因先前的绿色 MFW 提示而计为最终完成。

## 问题 15：破阵接入统一生命周期后，诊断接口签名不兼容

现象：r11 的破阵恢复运行从“没有结果”改进为能生成新鲜失败结果，但自定义动作只运行约 3 秒，没有点击“开始挑战”。`activity.page` 和 `break_array.page` 在同一现场帧均识别成功，随后结果为 `failed / break_array.postcondition_missing / WORKFLOW_DRIVER_FAILED`，`action-trace.jsonl` 为空。

原因：`BreakArrayMartialDailyAction` 把 active `TaskDiagnostics` 直接传给通用 `run_workflow`。引擎在首个 transition 前调用 `record_action(intent, authorization, frame_id)`，而 `TaskDiagnostics.record_action` 的接口是 `record_action(action_id, details=None)`；这个 `TypeError` 被引擎捕获并归一为 `WORKFLOW_DRIVER_FAILED`。因此识图没有失败，动作记录适配层先失败了。

解决方案：由独立 break-array worktree 增加通用引擎诊断协议与 MFW task diagnostics 之间的兼容适配，并补真实调用签名的回归测试；修复进入新候选后重新执行 `GAME_START + BREAK_ARRAY_MARTIAL_DAILY` 正式验收。失败现场为 `/tmp/mja-donation-recovery-r11.png`，MFW on-error 图为 `install/mfw-android-all-20260809-r11/debug/on_error/2026.08.09-14.27.28.594_MJA_BREAK_ARRAY_MARTIAL_DAILY_EXECUTE.png`。

## 问题 16：捐献弹窗关闭后仍有一层帮会主页

现象：r11 正式 `GAME_START + GUILD_DONATION_DAILY` 从冷启动进入捐献页，Android X 识别稳定命中（ColorMatch `count=286`），`GuardedInput` 成功点击 `(1004,125)`。弹窗关闭后实际停在“浮生城/帮会大厅”帮会主页；流程只轮询游戏主页模板，最终写出新鲜 `failed / home.ready / GUILD_DONATION_HOME_RETURN_FAILED`，正式 `finish` 返回 1。

原因：前一轮修复只覆盖“关闭捐献弹窗”这一层，把弹窗下方的帮会主页误当成了游戏主界面；帮会主页右上角仍有独立关闭 X，需要第二个有页面证据约束的归位动作。

解决方案：由独立 donation worktree 复用帮会活动/帮会事务已经校准的帮会主页证据，关闭帮会主页后再要求真正的 `home_marker` 才能写成功或已完成；未知页继续 fail closed。当前现场截图为 `/tmp/mja-donation-after-close-r11.png`，失败结果在 `install/mfw-android-all-20260809-r11/debug/mfw-105553136190088/GUILD_DONATION_DAILY/result.json`。

## 问题 17：手工生成配置把 64 位输入枚举写成了浮点近似值

现象：r11 新增的副本、剑林、帮会活动、帮会事务和全量配置在 MFW 连接控制器前失败，日志报 `384 is not a valid MaaAdbScreencapMethodEnum`，任务顺序为空。

原因：配置中的无符号 64 位截图/输入位掩码被中间 JSON 处理按 IEEE-754 数值近似成 `18446744073709552000`。MFW 转回底层枚举后模 2^64 得到无效值 `384`，而不是候选中已验证的负掩码 `-57/-9`。

解决方案：把相关配置精确恢复为 `screencap_methods=18446744073709551559`、`input_methods=18446744073709551607`；MFW 启动日志随后显示 `-57/-9`，控制器连接和正式业务任务均能开始。后续生成配置必须保留整数字面量精度，不能经过 JavaScript Number 或浮点序列化。

## 问题 18：副本扫荡面板 OCR 稳定少识别一个字

现象：r11 正式副本任务已经打开扫荡分配面板，右侧“燕王秘陵”卡片和“开始扫荡”按钮肉眼可见；OCR 多帧稳定输出 `开始扫`（约 0.83–0.87），但 `MJA_DUNGEON_OPEN_SWEEP` 等待 20 秒后写出 `failed / dungeon.state_known / DUNGEON_POSTCONDITION_MISSING`。

原因：`dungeon.sweep.panel` 只接受完整文案 `开始扫荡`；同时旧的 `dungeon.yanwangling.title` 是详情页 ROI，不能证明当前分配面板中的目标卡片。

解决方案：面板改为同帧组合识别：精确按钮候选 `开始扫荡|开始扫` 加面板专用的“燕王秘陵”卡片 ROI；选择动作也绑定新卡片锚点，未放宽为泛化“开始”。base/Android 资源和契约测试已同步，仍需新候选正式验收。失败票据为 `install/mfw-android-all-20260809-r11/debug/acceptance/DUNGEON_SWEEP_DAILY/20260809T063637546190Z/ticket.json`。

## 问题 19：剑林未完成分支藏在候选节点的 on_error 中

现象：r11 正式剑林任务进入“日常任务”页，OCR 正确识别 `消耗10000凝晶。/ 0/1W`、`消耗120体力。/ 0/120` 和 `战胜一次剑林的首领。`；`jianlin.daily.done` 正确不命中，但任务没有前往剑林，8 秒后写出 `JIANLIN_POSTCONDITION_MISSING`。

原因：父节点 `MJA_JIANLIN_DAILY_PAGE_PROBE.next` 只列“已完成”候选，未完成路线放在该候选自己的 `on_error`。MFW 对 `next` 执行候选识别；候选识别失败不会执行该候选的 `on_error`，因此未完成路线不可达。

解决方案：父节点把“已完成”和“存在未完成目标行”列为按特异性排序的 sibling candidates；已完成候选自身异常改为统一失败，保持 fail closed。相关测试已明确固化 MFW next-list 语义，仍需新候选正式验收。失败票据为 `install/mfw-android-all-20260809-r11/debug/acceptance/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/20260809T063848047543Z/ticket.json`。

## 问题 20：帮会活动页面仍使用旧标题

现象：r11 正式帮会活动任务成功进入征讨页，现场标题为“幻境征讨”，今日剩余次数 `2/2`、挑战按钮可见；OCR 输出 `幻境征讨`，但 `guild.activity.page` 只等待“帮会活动”，20 秒后写出 `GUILD_POSTCONDITION_MISSING`。

原因：入口“帮会活动”和进入后的页面标题被当成了同一文案；实际入口仍是“帮会活动”，目标页面已经显示“幻境征讨”。

解决方案：保留入口识别“帮会活动”，将页面标题精确改为“幻境征讨”；挑战、状态判断和关闭继续要求征讨上下文，关闭动作同时绑定标题、上下文和 X，避免仅凭标题误点。离线资源和安全契约已通过，仍需新候选正式验收。失败票据为 `install/mfw-android-all-20260809-r11/debug/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T064240375286Z/ticket.json`。

## 问题 21：帮会事务领奖成功后被奖励遮罩挡住后置验证

现象：r11 正式帮会事务任务已经完成领取，现场显示“恭喜获得”奖励遮罩和多项奖励；底层事务列表仍在，但流程立即检查底层 paid/start/done 状态，所有分支均因遮罩阻挡而超时，结果为 `GUILD_AFFAIRS_POSTCONDITION_MISSING`。

原因：领奖动作后缺少结果弹层归一化步骤；后置探针都要求可见的 `guild.affairs.daily.affairs.page`，在奖励层关闭前必然失败。

解决方案：已增加精确的奖励结果识别、单次受控关闭及关闭后的事务状态复核；未知页面继续失败关闭。r13 实跑中 `dismiss_guild_affairs_reward` 已获授权并成功关闭奖励层，证明本问题已修复；关闭后暴露出的连续多笔待领奖状态另记为问题 28。原失败票据为 `install/mfw-android-all-20260809-r11/debug/acceptance/GUILD_AFFAIRS_DAILY/20260809T064447288151Z/ticket.json`。

## 问题 22：候选包继承旧 debug 后，运行中再次轮转导致验收缺事件

现象：r12 在 `begin` 后启动 MFW，运行期间 `maafw.log` 发生轮转；票据记录的目标日志与最终保留文件不再是同一段内容。业务结果存在，但 `finish` 无法同时找到本轮 `GAME_START` 与业务任务的完整原生终态。

原因：候选包复制时继承了上一候选的大体积 `debug`，只在 `finish` 处理“文件变短”不足以覆盖运行中重命名轮转；本轮开头的事件可能进入历史文件，结尾事件进入新文件。

解决方案：每个候选正式验收前使用全新的空 `debug`；每个实跑批次结束后按任务归档整个 debug，再创建空目录，确保一张票据只对应一组不会跨代继承的日志。r13 已按 `inherited-debug`、`through-jianlin`、`guild-activity`、`guild-affairs` 分批归档。

## 问题 23：破阵页面边界依赖固定标题，实机动态次数无法成立

现象：破阵流程能进入页面，但旧边界把静态标题/剩余次数写得过于固定；实机页面显示动态 `9/9` 等次数时，页面或开始按钮组合可能无法建立可靠证据。

原因：页面边界没有把左侧已选中的“破阵演武”、合法动态剩余次数和右侧精确“开始挑战”分开建模，容易因样式标题或计数变化误判。

解决方案：页面改为同帧组合“左侧选中项 + 合法 x/y 剩余次数”，并验证剩余数不大于总数；开始按钮使用紧 ROI 精确匹配“开始挑战”，动作继续要求完整页面边界且最多挑战 3 次。离线契约已通过，待新候选正式单任务验收。

## 问题 24：帮会捐献退出还存在第三层功能面板

现象：关闭捐献弹窗和帮会主页后，现场仍可能停在主页功能面板；若任务直接成功结束，会继续污染下一个业务任务。

原因：归位流程只建模了捐献弹窗与帮会主页两层，未把最外层功能面板纳入成功后置条件。

解决方案：成功与 already-complete 路线统一执行三层归位：关闭捐献弹窗、关闭帮会主页、验证功能面板边界后受控点击面板 X，最后必须命中真实游戏主页。新增 `close_function_panel` 单次安全 cap，离线测试通过，待正式复验。

## 问题 25：副本选中相邻“大师80”且加号无法被 OCR 识别

现象：r13 在燕王秘陵扫荡面板中，`dungeon.master.80` 的宽 ROI 先命中左侧黑刹教卡片的“大师80级”，点击 `(595,416)` 后打开了错误的奖励预览；同时票据加号使用 OCR `+`，现场 OCR 只返回“解锁扫荡”和数量，没有识别图形加号。

原因：大师难度探针横跨多张卡片，未绑定燕王秘陵卡片；加号是无文本语义的图标，不适合依赖 OCR。

解决方案：大师 ROI 收紧到燕王秘陵卡片 `[900,370,210,100]` 并接受实机 `大师80级`；票据加号改为 `[1228,400,40,40]` 的窄区域连通 ColorMatch，现场连通块 81 像素，高于 40 的保守阈值。base/Android 资源已同步，聚焦测试与资源校验通过，待正式复验。

## 问题 26：剑林前往动作误点顶部公告，空白模板又制造页面假阳性

现象：r13 日常页中，打开剑林动作点击了顶部公告“各位大侠可前往剑林·对弈中参与”附近，而不是底部“战胜一次剑林的首领”同一行的“前往”；随后 `jianlin_page.png` 在日常页多个位置都给出 1.0 分，错误地证明已进入剑林。

原因：目标 OCR 在全页搜索泛化“前往/剑林”，没有建立任务行与同排按钮的 sibling 关系；现有 `jianlin_page.png` 是空白/无辨识度模板，不能作为页面边界。

解决方案：入口已绑定到“战胜一次剑林的首领”任务行和同排右侧精确“前往”，不再把顶部公告当成目标；空白 `jianlin_page.png` 已从运行时页面证明中移除，改用“养成/资源”标题、倍率栏和次数栏的同帧组合边界。base、Android 资源及契约测试已同步，未知页继续失败关闭，待新候选正式复验。

## 问题 27：帮会活动上下文文案与右侧 ROI 不符合实机

现象：r13 已进入“幻境征讨”，现场显示状态“讨伐中”、`今日剩余征讨次数：2/2` 和右下挑战按钮；旧 context 期望“征讨”，ROI 只到 x=1100，把右侧次数文本截成“今日剩”，最终 `GUILD_POSTCONDITION_MISSING`。

原因：页面状态的实机 OCR 文案是“讨伐中”；次数与挑战控件位于屏幕右缘，旧 ROI 同时过宽、又没有覆盖完整文本和按钮。

解决方案：context 接受“讨伐中/今日剩余征讨次数”并延伸至 x=1280；次数 ROI 收紧到右下角 `[980,540,300,100]`，挑战按钮收紧到 `[940,580,340,110]`。页面标题“幻境征讨”仍作为同帧边界，所有变更已通过任务、安全和资源校验，待正式复验。

## 问题 28：帮会事务领取一笔后首行仍是另一笔待领取

现象：r13 成功打开帮会事务、领取首行并关闭奖励层；回到列表后首行仍显示“事务完成/领取奖励”，第二、第三行也可领取，第四行才是“开始事务”。现有流程却只检查首行 start/done，最终写出 `GUILD_AFFAIRS_POSTCONDITION_MISSING`。

原因：事务完成项会在领取后刷新/重排，且可能同时积累多笔奖励；单次领取后直接进入首行开始/完成判断不符合真实列表生命周期。

解决方案：独立修复分支已实现有页面边界和弹层证据的有限领奖循环，每次领取后都关闭弹层并重新探测首行；领取次数与关闭次数上限均为事务存储上限 6，第 7 次由策略拒绝，且没有任何付费“刷新事务”点击路径。全部可领奖项清空后才安全开始可用事务，或以可靠进行中/无操作状态结束。主工作区聚焦回归 96 项通过，最新 base 资源 1361 个节点零错误，待 r16 正式单任务验收。

## 问题 29：破阵“开始挑战”在实机被拆成上下两个 OCR 框

现象：r14 页面边界已经稳定命中左侧“破阵演武”和右下 `剩余挑战次数：9/9`；但按钮 OCR 分别返回上行“开始” `[1091,547,94,49]` 和下行“挑战” `[1089,586,96,49]`，旧候选 `开始挑战|开始 挑战` 无法匹配，动作轨迹止于 `open_break_array`，结果为 `WORKFLOW_POSTCONDITION_MISSING`。

原因：按钮采用上下两行排版，MaaFramework OCR 不会自动把两个独立框拼接成一个文本；继续要求单框完整短语必然失败。

解决方案：按钮已改成紧 ROI 内同帧的精确 `^开始$` 与 `^挑战$` 组合，并通过 `box_index: 0` 明确选择按钮内部点击框；完整破阵页面边界保持不变，没有退化为全屏泛化文本。主工作区相关资源与安全回归 56 项通过，待新候选正式单任务验收。失败证据归档于 `install/mfw-android-all-20260809-r14-debug-break-r1`。

## 问题 30：副本“大师80”文字会打开奖励预览，票券又没有文字标签

现象：r14 窄 ROI 正确命中燕王秘陵的“大师80级”，但点击该文字打开中央“燕王秘陵(大师) / 概率获得以下奖励”弹窗；它不是难度选择控件。与此同时，大师行右侧加号已稳定 ColorMatch 为 `[1240,411,15,15]`、81 像素，但分配条件仍等待不存在的“副本票”文字。现场底部实际只有票券图标和数字 `2`，数字约在 x=862、y=550，旧余额 ROI 从 x=900 开始也会漏掉。

原因：把难度说明文本误当成可选控件；并根据语义名称臆造了“副本票”OCR 标签，而实机 UI 只显示图标与数值。

解决方案：有害的 `select_master_80` 点击已移除；现在由燕王卡片、大师行、目标加号、票券图标和正余额同帧证明后直接点击大师行加号。余额 ROI 已收紧为 `[840,520,90,70]`，覆盖实机数字位置；资源身份只有在显式 opt-in 时可由精确票券模板证明，默认任务仍强制 OCR 资源标签，资源消耗仍由策略预算计数。已知奖励预览增加了精确且单次的关闭恢复路径。主工作区相关模型、管线、Android 资源、安全与 Agent 回归 94 项通过，base 资源 1371 个节点零错误，待新候选正式单任务验收。失败证据归档于 `install/mfw-android-all-20260809-r14-debug-dungeon-r1`。

## 问题 31：帮会活动挑战后直接进入“世界首领”编队页

现象：r14 的“幻境征讨/讨伐中/2/2/挑战”入口均成功，动作轨迹已执行 `challenge_guild_activity`。点击后直接进入“世界首领”编队页：左上“世界首领”、右侧“首领战斗”、右下竖排橙色“开始”。旧流程既未命中确认页，也未命中 `征讨准备|战前准备|队伍配置`；`MJA_GUILD_CHALLENGE_LOOP` 超时后 on_error 回到自身，触发原生 `error handling loop detected`，业务结果停在 `running`。

原因：真实页面转换与旧状态机假设不同；编队页识别文本和开始按钮版式均未建模，且错误路由缺少统一 `RecordTaskOutcome` 生命周期收口。

解决方案：已增加“世界首领 + 首领战斗”的同帧编队边界和右下安全开始按钮，保留可选确认页作为 sibling；错误自环已移除，所有未知转换/结果/退出分支先写入新鲜 failed 结果，再让原生任务失败，不能留下 running。合入时保留了主线较新的 Maa 上下文诊断绑定逻辑；聚焦回归 46 项通过，base 资源 1364 个节点零错误，待新候选正式单任务验收。失败证据归档于 `install/mfw-android-all-20260809-r14-debug-guild-activity-r1`。

## 问题 32：破阵开始按钮后还有一次消耗次数确认

现象：r17 已稳定命中破阵页面、两行“开始/挑战”按钮，并成功记录 `start_break_array_challenge`；随后弹出中央“提示”，正文为“开始挑战将消耗1次挑战次数并进入准备界面，请阁主搭配适合的出战阵容。”，左下“取消”、右下“确认”。旧流程没有确认节点，等待后置条件超时并写出 `WORKFLOW_POSTCONDITION_MISSING`。

原因：前一轮只修复了按钮的两行 OCR 排版，状态机仍假设点击开始后会直接进入准备界面；真实流程还有一次明确、可安全证明的消耗次数确认。

解决方案：已增加竖排“提示”标题、消耗 1 次挑战次数正文、准备界面正文与右下“确认”的同帧边界；每次开始只允许一次有界确认，确认次数必须与开始次数严格配对。确认后必须证明进入可靠准备界面，或挑战次数从 `N/9` 精确降至 `N-1/9`；重复确认、次数不变和未知页继续失败关闭。base/Android 新增节点保持同步，相关聚焦回归已纳入主线，待新候选正式复验。失败证据归档于 `install/mfw-android-all-20260809-r17-debug-break-r1`。

## 问题 33：副本票券图标模板阈值高于现场稳定分数

现象：r17 已进入燕王秘陵扫荡面板；燕王卡片 OCR 0.998759、大师 80 行 OCR 0.977952、目标加号 ColorMatch 93 像素均命中。只有 `dungeon.ticket.icon` 在精确 ROI `[770,510,95,75]` 内的模板分数反复为 0.652958–0.662200，低于现有 0.72 阈值，导致大师行同帧门失败，没有执行 `assign_sweep_ticket`。

原因：票券模板裁剪和实机渲染存在稳定差异，首次按经验设置的 0.72 没有覆盖真实分数；其余页面、难度和加号证明均正常。

解决方案：精确票券 ROI 的模板阈值已从 0.72 校准为 0.64，仍保留燕王卡片、大师行、目标加号、票券图标和正余额全部同帧安全条件；没有删除资源身份门或扩大到全屏。base/Android 资源与契约测试已同步，聚焦回归 8 项通过，base 资源 1371 个节点零错误，待新候选正式复验。失败证据归档于 `install/mfw-android-all-20260809-r17-debug-dungeon-r1`。

## 问题 34：世界首领“开始”是竖排按钮，OCR 输出不稳定

现象：r17 的“世界首领”页面标题得分 0.999991，“首领战斗”得分 0.992818，同帧页面边界稳定命中；右下紧 ROI `[1110,555,130,130]` 中的竖排“开始”却被 OCR 为 `·丽始`（0.677355），不符合现有 `开始|印始`，因而没有执行开始战斗。

原因：竖排装饰字形和按钮背景会让 OCR 把两个字及装饰点合并成不稳定文本；枚举单个错字变体不可持续。

解决方案：右下按钮已改为“世界首领 + 首领战斗”同帧页面边界下的紧 ROI ColorMatch；橙色范围 `[200,80,20]`—`[255,170,90]`、连通面积下限 5000，现场最大按钮连通块为 7384 像素，点击框仍由 `box_index/target_index=1` 绑定到该控件，不再依赖枚举 OCR 错字。聚焦回归 23 项通过，base 资源 1371 个节点零错误。r17 的新失败生命周期也已验证有效：先写出 `GUILD_CHALLENGE_TRANSITION_UNKNOWN`，再让原生任务明确 Failed，没有残留 running。待新候选正式复验；失败证据归档于 `install/mfw-android-all-20260809-r17-debug-guild-activity-r1`。

## 问题 35：帮会事务启动成功后，后置 OCR 区域仍在左半边

现象：r17 连续领取并关闭三笔事务奖励后，安全点击了第一行“开始事务”。现场第一行已变为“事务进行中 03:59:42”，但任务仍写出 `failed / GUILD_AFFAIRS_POSTCONDITION_MISSING`；正式验收器返回 1，没有把 MFW 外层“所有任务都已完成”当作业务成功。

原因：`guild.affairs.daily.first_row.no_action` 的 OCR ROI 是 `[80,150,820,150]`，只覆盖第一行左侧内容；实机“事务进行中”位于右侧操作区约 x=1060，当前探针不可能看到这个后置状态。

解决方案：`no_action` OCR 已收紧并移动到第一行右侧状态区 `[1040,95,180,70]`，完整覆盖现场识别框 `[1062,113,106,23]`，且在第二行 y=217 前结束。Android MFW 已由契约测试确认直接加载 canonical base pipeline，无需创建无效 override；页面边界、受控点击和付费/刷新防护均未改动。待新候选正式复验；失败证据归档于 `install/mfw-android-all-20260809-r17-debug-guild-affairs-r1`。

## 问题 36：破阵确认后先进入无文字黑色过渡帧

现象：r18 已成功执行 `start_break_array_challenge` 和单次 `confirm_break_array_challenge`；确认约 3 秒后仍是黑色场景切换画面，只显示顶部滚动传闻和右下 UID。流程反复尝试此前推测的“战术谱/怒气上限”准备页与 `8/9` 返回页，均未命中，最终写出 `WORKFLOW_POSTCONDITION_MISSING`。

原因：确认后的真实首个状态是无可交互控件的加载过渡，不是立即可见的准备页；确认 transition 的后置条件没有接受这个短暂但可安全等待的 task-local 状态，轮询窗口也因此在约 3 秒内耗尽。

解决方案：黑屏过渡已建模为任务内三要素同帧边界：中央纯黑连通区域（现场 420000 像素，阈值 400000）、顶部浅色传闻字形（3527，阈值 3000）和右下 UID 灰色字形（499，阈值 350）。确认动作允许它作为后置状态；过渡期间只执行有上限的 `InputKind.NONE` 轮询，绝不点击，并最终要求准备、战斗或结算等已知状态。挑战与确认仍严格一对一且最多三次，未知页继续失败关闭。聚焦回归已合入主线，待新候选正式复验。失败证据归档于 `install/mfw-android-all-20260809-r18-debug-break-r1`。

## 问题 37：副本扫荡结果标题竖排，OCR 只读到奖励物品

现象：r18 已成功分配燕王秘陵大师票券、开始扫荡并确认；结果页显示中央白色奖励横幅、左侧竖排橙色“恭喜获得”和底部横排“点击空白处关闭”。现有 `dungeon.result` OCR 连续 20 秒只读到奖励格中的“80级/600”等文本，未命中竖排标题，最终写出 `DUNGEON_POSTCONDITION_MISSING`。

原因：把竖排装饰标题当作普通横排 OCR 文案；ROI 内虽然包含奖励页，但 OCR 不会把四个竖排字可靠拼成“恭喜获得”。

解决方案：结果页改为同帧组合：浅色奖励面板连通块（现场 135795 像素，阈值 90000）、左侧橙色竖牌（13002，阈值 8000）和底部精确横排 OCR“点击空白处关闭”；扫荡前页面在两个视觉 ROI 中只有 138/0 像素。只有完整边界成立才允许一次受控关闭，关闭后仍要求返回副本页且票券耗尽；票券身份、资源预算和动作上限没有放宽。r19 正式 `GAME_START + DUNGEON_SWEEP_DAILY` 已产生新鲜 `success / dungeon.reward_popup_seen_and_ticket_count_zero`，原生终态成功，`acceptance.json` 为 `passed`。失败证据归档于 `install/mfw-android-all-20260809-r18-debug-dungeon-r1`，通过证据归档于 `install/mfw-android-all-20260809-r19-debug-dungeon-r1`。

## 问题 38：帮会活动开始后，状态机没有“战斗进行中”分支

现象：r18 已成功进入世界首领并执行 `start_guild_challenge`；现场随后是约 01:46 的自动战斗，顶部有“14级 镇门铁腿”与血条，右上显示“自动中/暂停”，右下显示“自动中…”。但开始节点只等待危险、验证、胜利或失败结果，20 秒内战斗尚未结束，因而超时并写出 `GUILD_POSTCONDITION_MISSING`；原生终态正确为 `Failed`。

原因：把点击开始后的下一帧假设为结算页，漏掉持续数分钟的正常战斗状态，也没有为无输入等待结果设置独立有界时限。

解决方案：已用计时、Boss 等级、顶部“自动中”、右上“暂停”和底部“自动中”五个紧 ROI 建立同帧战斗边界。开始动作先接受该状态；战斗节点本身为 `DoNothing`，其 next-list 识别窗口扩展为 180 秒，只等待危险、验证、胜利或失败结果，不执行点击。窗口超时或未知页面继续写新鲜 failed 结果并原生失败。聚焦回归与 1410 节点资源校验已通过，待新候选正式复验。失败证据归档于 `install/mfw-android-all-20260809-r18-debug-guild-activity-r1`。

## 问题 39：帮会事务业务成功后，关闭按钮模板阻断原生成功

现象：r18 已正确识别第一行右侧“事务进行中”，新鲜结果为 `success / guild.affairs.daily.first_row.no_action`；但成功节点随后尝试关闭事务页时，`home/modal_close.png` 在右上精确 ROI 的现场分数只有 0.563087，低于 0.78，最终 native terminal 为 `Failed`，正式验收器据此拒绝通过。

原因：业务成功与退出清理是两个阶段；关闭 X 的实机样式与通用模板差异较大，而同一帮会页面在捐献和活动任务中已经用右上角紧 ROI ColorMatch 稳定识别。把通用模板继续用于事务页，会让真实业务成功被清理步骤否决。

解决方案：独立 worktree 已把关闭证据改为“事务页面边界 + 右上关闭 ColorMatch”同帧，参数复用已实跑验证的帮会关闭控件：RGB `[0,0,0]`—`[125,125,125]`、ROI `[1180,0,100,100]`、连通面积下限 180。归档截图在该 ROI 内的最大连通暗色区域为 8962 像素；关闭动作显式 `max_hit=1`，策略 cap 也保持 1。关闭后仍须命中帮会页，任何清理异常转入 native abort，而已经写入的业务 `success` 不被篡改。Android MFW 直接加载 base，没有新增重复 override。独立修复 commit 为 `edaa3fb62f4dd9753b63e705b0af163b2f27c51c`；聚焦回归 27 项通过、base 资源 1290 节点零错误，合入主线后四任务联合回归 75 项通过、base 资源 1410 节点零错误。r19 正式 `GAME_START + GUILD_AFFAIRS_DAILY` 已产生新鲜 `success / guild.affairs.daily.first_row.no_action`，右上关闭实测命中 8962，原生终态成功，`acceptance.json` 为 `passed`。失败证据归档于 `install/mfw-android-all-20260809-r18-debug-guild-affairs-r1`，通过证据归档于 `install/mfw-android-all-20260809-r19-debug-guild-affairs-r1`。

## 问题 40：破阵黑屏后是编队页，宽泛“战斗”把它误判成战斗中

现象：r19 已证明黑屏过渡识别和无输入等待生效；随后进入真实编队页，现场有“阵容”“首领战斗”“战时长：02:00”“战术谱/战斗设置”和右下竖排“开战”。现有 `break_array.prepare_page` 因臆测的“怒气上限/开始”不命中，`break_array.battle` 却因宽泛候选“战斗”命中“首领战斗”，流程连续执行 12 次 `wait_break_array_battle`，从未点击开战，最终新鲜结果为 `failed / break_array.postcondition_missing`。

原因：黑屏后的真实业务状态是需要一次明确输入的阵容编队页，不是战斗进行中；战斗识别又用了可命中页面标题的泛化文本，导致状态机把可操作页归到只读等待分支。

解决方案：独立 break worktree 已按归档 OCR 建立“阵容 + 首领战斗 + 战时长：02:00 + 战术谱”的紧 ROI 同帧边界；“战时长”严格使用现场原文，不枚举错字。右下橙色竖排按钮由 ColorMatch 授权：ROI `[1100,550,150,145]`、RGB `[200,65,0]—[255,170,70]`、阈值 4500，归档截图命中 5630 像素，包围盒 `[1111,560,126,125]`。workflow 新增一次有边界的 `start_break_array_battle`；开始挑战、确认、开战严格一对一且总上限均为 3，开战后只接受已知加载、真实战斗或结果，真实战斗仍只读等待，未知页失败关闭；宽泛“战斗”已删除。修复 commit 为 `d7845c1daec1c4c66f2f29cf0e8b385afc1629fc`；失败证据归档于 `install/mfw-android-all-20260809-r19-debug-break-r1`。

## 问题 41：帮会活动战败标题在组合 OCR 中被裁掉末字

现象：r19 已稳定进入“世界首领”自动战斗，战斗期间只做无输入等待；约三分钟后真实结算页显示“战斗失败”。同一帧的全图 batch OCR 能识别完整 `战斗失败`，框为 `[742,97,504,149]`，但 `guild.result.page` 在组合探针中重裁成约 `[742,100,388,146]` 后只返回 `战斗失`。胜利和失败探针都未命中，最终写出新鲜 `failed / guild.challenge_result_known / GUILD_RESULT_UNKNOWN`。

原因：通用结果页 OCR 同时承担页面边界和胜负判定，其 ROI/重识别框会裁掉大号标题的最右字符；完整标题明明已存在于同帧 OCR 缓存，却被二次裁切破坏。它不是战斗等待超时，也不是未知页面。

解决方案：独立 guild-activity worktree 已把结果标题统一到完整覆盖现场大字框的紧 ROI `[700,70,580,210]`，胜利和失败分别只接受精确 `^战斗胜利$` / `^战斗失败$`，不枚举 `战斗失`。战败还必须与紧 ROI `[840,390,340,90]` 内的精确“可以通过以下途径提升”同帧成立，形成独立 `guild.result.defeat.page`；未知结果继续失败关闭。命中已知战败后直接记录真实 `failed / GUILD_RESULT_DEFEAT / guild.challenge_result_known` 并原生失败，不关闭结果页继续挑战，也不伪装成功；战斗期间仍只无输入等待。修复 commits 为 `9b26ad31bb6ec9a65bd0b0aa7d6b5f9a4e56c5b2`、`22d9503f01ea4d789671976d69394f1785901458`。两项修复合入主工作区后 focused 测试 `88 passed`、base 资源 1414 节点零错误、全量测试 `1075 passed, 5 skipped`。失败证据归档于 `install/mfw-android-all-20260809-r19-debug-guild-activity-r1`。

## 问题 42：未验收任务批量 dry-run 暴露 START next-list 系统性不可达

现象：r19 选择 `GAME_START` 加 11 个此前未正式覆盖的业务任务运行。`FREE_APPRAISAL_DAILY`、`TRIAL_SWORD_DAILY`、`HERO_DISPATCH_DAILY`、`COLLECTION_DEPLOYMENT_DAILY`、`SPEND_CONDENSATE_DAILY`、`MARTIAL_STUDY_BREAKTHROUGH_DAILY`、`EAT_STAMINA_FOOD_DAILY`、`RING_CHALLENGE_DAILY`、`DAILY_TASK_REWARD_CLAIM_DAILY`、`BATTLE_PASS_REWARD_DAILY` 均失败；`SHADOW_RUINS_DAILY` 的 MFW 外层没有打印 Failed，但新鲜结果仍为 `failed / SHADOW_POSTCONDITION_MISSING`。除蜃影外，多数 `result.json` 留在 `running`，动作轨迹为空。

原因：多项任务的 START `next` 只列一个“恢复弹窗”候选，把正常主页路线放在该候选的 `on_error`。MFW 的 next-list 只识别候选；候选识别失败不会执行候选自己的 `on_error`，父 START 因而反复识别同一个不可能成立的恢复页，直到外层超时或永久等待。这与问题 19 的剑林 sibling 不可达属于同一框架语义。

解决方案：每个任务必须把恢复弹窗、业务页和主页入口写成 START 的同级 sibling candidates，按特异性排序；不能依赖未命中候选的 `on_error` 导航。所有未知页和入口超时必须先 `RecordTaskOutcome(failed)` 再 native Failed，禁止遗留 `running`。免费鉴宝提交 `a24f535950b783e922c29e773a8bddb89f80076e`、试剑提交 `c587123e08c3a1cf15606b8c49484ad68da5be5c`、侠客派遣提交 `c1fb5ad8edd9b3faa43ba6048be68018149981f7`、藏品布阵提交 `71bd4e488a078d40f883c4a8dca85d6a74d06aba`、武学研习提交 `4b65998e03e6504fd7983519d52c710d2ea2e9e5` 已按该模式完成离线修复。藏品与武学研习合入后主线全量测试为 `1101 passed, 5 skipped`；帮会退出修复同步后 base 资源为 `1436` 个节点零错误。这些任务仍须新候选逐项 MFW 实机验收。批量证据归档于 `install/mfw-android-all-20260809-r19-debug-unverified-r1`。

## 问题 43：主页功能面板模板被红点覆盖，部分任务还会无界等待

现象：r20 独立运行心法研习与擂台时，`martial.home` / `ring.home` 在 `[1040,0,240,110]` 的模板分数稳定约 `0.82`—`0.83`，高于 0.75，证明已经在主页；但 `home/panel_open.png` 在带红点的圆形功能按钮上只有约 `0.458`，低于任务阈值 0.72。两项任务持续停在 `MJA_*_HOME_PROBE`，动作轨迹为空、结果永久 `running`、native terminal events 为空。心法研习运行约三分钟、擂台约一分钟后由监控方保留日志并停止。

原因：旧模板采集自无红点状态，当前右上按钮有红色通知标记；更严重的是父节点没有有效的有界失败出口，识别失败以 1 秒频率无限重试。

解决方案：入口改为对红点稳定的窄 ROI 视觉目标，并与主页边界同帧组合；入口 `GuardedInput` 与策略 cap 均为 1。START/主页探测必须有界，失败先写结构化终态再 native abort。免费鉴宝已覆盖同类按钮；武学研习提交 `4b65998e03e6504fd7983519d52c710d2ea2e9e5` 进一步把入口改为 r20 实测的 `[1170,10,60,60]` 金色 ColorMatch。擂台提交 `337b9ca45b991534f0b64b8e45a56846e0bd5b43` 已修正功能面板右上入口 ROI，增加擂台页、日常页、功能面板和主页四种有限起始 sibling，移除 0.458 错误候选自循环，并修复资源索引越界；所有副作用同时受 pipeline `max_hit` 与策略 cap 约束。两项仍待新候选正式验收。证据归档于 `install/mfw-android-all-20260809-r20-debug-martial-study-r1`、`install/mfw-android-all-20260809-r20-debug-ring-r1`。

## 问题 44：蜃影任务点击“画卷”后实际进入普通副本页

现象：r19 独立运行蜃影武墟时，`open_painting_scroll` 获授权并执行；下一页的完整 OCR 标题是“副本”，列表为“贼寇山洞/楚家庄/风雪神道/沙匪营地/玄阙地宫·表”，并非预期“画卷/蜃影武墟/偃武世界”。流程在 `MJA_SHADOW_PAINTING_PAGE` 写出 `failed / shadow.state_known / SHADOW_POSTCONDITION_MISSING`。

原因：当前主页“画卷”图标或点击目标实际落到普通副本入口，现有任务把旧版/推测的画卷页面当成当前产品页面；后续 `shadow.entry` 在实机页不存在。

解决方案：从当前 UI 重新确认蜃影武墟的真实入口和页面层级，只用可证明的同帧页面/目标边界更新导航；若当前账号或版本没有该功能，应返回策略允许的明确不可执行状态，不能在普通副本页继续点击。证据归档于 `install/mfw-android-all-20260809-r19-debug-shadow-r1`。

## 问题 45：r20 破阵仍在准备页选择只读战斗等待

现象：r20 已识别黑屏并进入真实准备页；现场明确显示“阵容、首领战斗、战时长：02:00、战术谱、战斗设置、开战”。动作轨迹却是 `confirm_break_array_challenge -> wait_break_array_battle`，仍缺少 `start_break_array_battle`，约一分钟后写出 `WORKFLOW_POSTCONDITION_MISSING`。

原因：上轮已补准备页资源，但 custom workflow 的 runtime snapshot 映射或 `decide` 优先级仍把该帧判到 battle 等待分支；只修 pipeline recognizer 不能改变实际 custom action 的决策。

解决方案：提交 `3a8ea09` 已修正 custom engine 的 post-action snapshot：下一状态不能继续复用动作前 recognizer；确认后和点击开战后分别最多进行 30 次、每秒一次的有限截图轮询，黑色 Unity 转场不产生任何输入。错误的“确认转场 → wait”决策已删除，严格顺序固定为 `confirm -> start_break_array_battle -> wait_break_array_battle`；wait 仅在开战计数一一配对且真实 loading/battle 边界成立时允许。r20 准备页 fixture 为 `prepare=true/start=true/battle=false`，r21 黑转场 fixture 三者均为 false。修复合入主线后的交叉聚焦回归 `84 passed`、base 资源 `1436` 节点零错误，待新候选正式验收。证据归档于 `install/mfw-android-all-20260809-r20-debug-break-r1`；r21 票据已归档到 `install/mfw-android-all-20260809-r21-debug-break-r2/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T102905420030Z/ticket.json`。

## 问题 46：剩余未验收任务的干净单任务结果

现象与原因：r19/r20 在每次 force-stop 后只运行 `GAME_START + 指定任务`，确认以下均不是前序页面污染：侠客派遣只识别 `MJA_HERO_RESUME_REWARD_PROBE`；藏品布阵只识别 `MJA_COLLECTION_RESUME_REWARD_PROBE`；消耗凝晶只识别 `MJA_CONDENSATE_RESUME_YANWU_REWARD_PROBE`；食用体力食物只识别 `MJA_FOOD_RESUME_REPLACE_PROBE`；日常奖励只识别 `MJA_DAILY_RESUME_REWARD_PROBE`；战令只识别 `MJA_BP_RESUME_REWARD_PROBE`。这些候选在正常主页必然失败，其 `on_error` 不可达，最终 native Failed 且多数结果仍为 `running`。藏品布阵提交 `71bd4e48`、消耗凝晶提交 `ffd2bac`、食用体力食物提交 `571a6ea` 已完成离线修复并合入；日常奖励提交 `ebaeadfdb1b48cdc55672b02bdbf26b9015daa6d` 已补齐奖励弹层、日常页、功能面板与主页的有限 START sibling，并确保未知状态先 fresh failed 再 native Failed；侠客派遣入口第二层问题另见问题 50；战令仍待处理。

解决方案：统一采用问题 42 的 START sibling 和真实终态模式，但每项任务仍需保留自己的页面边界、副作用 cap、资源预算及最终后置条件，并分别通过 `GAME_START + 单任务` 的 fresh MFW 验收。证据归档：`install/mfw-android-all-20260809-r19-debug-hero-r1`、`install/mfw-android-all-20260809-r19-debug-collection-r1`、`install/mfw-android-all-20260809-r20-debug-condensate-r1`、`install/mfw-android-all-20260809-r20-debug-food-r1`、`install/mfw-android-all-20260809-r20-debug-daily-reward-r1`、`install/mfw-android-all-20260809-r20-debug-battle-pass-r1`。

## 问题 47：帮会活动次数为零后只退出到功能面板

现象：r20 第二次帮会活动实跑无需再次战斗，页面已证明今日次数为 0，并依次授权 `exit_guild_activity`、`exit_guild_home`。退出后现场是最外层功能面板，能看到“活动/商城/日常/武学研习/帮会”等图标；流程却立即要求世界主页模板，最终写出 `failed / guild.home_restored / GUILD_HOME_RETURN_FAILED`。

原因：already-complete 清理只建模了征讨页与帮会主页两层，漏掉从帮会主页返回后仍打开的功能面板；这与问题 24 的捐献三层归位相同。

解决方案：复用已正式验收的捐献清理模式，在“功能面板边界 + 面板关闭控件”同帧成立时执行一次有 cap 的 `close_function_panel`，然后才验证真正的 `home_marker` 并记录 already-complete；成功挑战的共用退出链也采用相同三层归位。未知页继续失败关闭。独立 `guild-activity-r20-zero-exit-20260809` worktree 已提交 `504f4a69ce01f6e5d47700272a9354c8b3d59bd7`；r20 截图量化为 panel marker `0.8166`、panel close `0.2460`、home marker `0.0227`。r22 正式运行已产生 fresh `already_complete / guild.remaining_conquest_0_of_2`，动作链完整执行 `exit_guild_activity -> exit_guild_home -> close_function_panel`，native terminal 为 Succeeded，`mfw_live_acceptance.py finish` 返回 0。通过证据归档于 `install/mfw-android-all-20260809-r22-debug-guild-activity-r1/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T113322437604Z/acceptance.json`；此前失败证据为 `install/mfw-android-all-20260809-r20-debug-guild-activity-r2`。

## 问题 48：免费鉴宝真实入口在主世界顶部，不在功能面板

现象：r21 正式运行 `GAME_START + FREE_APPRAISAL_DAILY` 后，唯一动作是 `open_function_panel`。主世界全图 OCR 已在顶部识别“鉴宝” `[938,58,35,14]`，但打开后的功能面板只有“活动/商城/日常/武学研习/秘宝/帮会/签到/天书/载具”，不存在“鉴宝”。`MJA_APPRAISAL_OPEN_APPRAISAL` 连续无法命中，任务写出 fresh `failed / APPRAISAL_POSTCONDITION_MISSING`；MFW 外层为 Succeeded，但验收器正确返回 1。

原因：上一轮只修复了 START sibling 与红点入口，却错误假设“鉴宝”位于功能面板；“秘宝”是另一项功能，不能当作鉴宝入口。

解决方案：提交 `9828e82942358925fecc5d760e156362d3a587d8` 已把正常路线改为主世界边界与顶部紧 ROI 的精确 `^鉴宝$` 同帧直达；若从已打开功能面板恢复，只允许一次 `close_function_panel`，验证主世界后再点击鉴宝。`秘宝` 只作为面板边界，不会成为点击目标；所有输入 cap 为 1，且不存在付费鉴宝路径。修复合入后的交叉聚焦回归 `84 passed`、base 资源 `1436` 节点零错误，待新候选正式验收。证据归档于 `install/mfw-android-all-20260809-r21-debug-free-r1`，票据为其中 `acceptance/FREE_APPRAISAL_DAILY/20260809T103946390160Z/ticket.json`。

## 问题 49：试剑进入“挂机收益”后漏掉当前收益可领取状态

现象：r21 正式运行试剑时已执行 `open_trial_sword`，并进入真实“挂机收益”页；同帧 OCR 为“挂机收益” `[30,267,107,27]`、“当前收益” `[31,462,106,25]`、底部精确“领取” `[180,632,58,34]`。现有页面探针只接受“已领取/已获得”，8 秒后写出 fresh `failed / TRIAL_POSTCONDITION_MISSING`，native terminal 为 Failed。

原因：可领取状态没有作为 `MJA_TRIAL_PAGE_PROBE` 的 sibling；页面明明可安全领取免费挂机收益，却被误判为未知。

解决方案：提交 `4d44bed105c6e1e51803a61bed84de2fc86b1478` 已增加“挂机收益 + 当前收益 + 紧 ROI 精确领取”的同帧分支，`GuardedInput` 与策略领取 cap 均为 1；领取后必须识别奖励弹层或已领取状态，有限关闭并验证安全退出，不会泛化到右侧免费控件或任何付费确认。修复合入主线后的聚焦回归 `3 passed`、base 资源 `1437` 节点零错误，待新候选正式验收。证据归档于 `install/mfw-android-all-20260809-r21-debug-trial-r1`，票据为其中 `acceptance/TRIAL_SWORD_DAILY/20260809T104213824285Z/ticket.json`。

## 问题 50：画卷页显示繁体“俠客派遣”，未命中后又形成自环

现象：r21 侠客派遣已执行 `open_painting_scroll` 并进入真实画卷页；全图 OCR 同帧识别“画卷/偃武世界/云州/采集部署/蜃影武墟”，派遣入口却是繁体 `俠客派遣` `[1006,648,86,28]`。现有精确简体目标未命中，随后 `MJA_HERO_PAINTING_PROBE` 的错误路由回到自身，MFW 报 `error handling loop detected`，fresh result 再次遗留 `running`。

原因：入口没有覆盖实机稳定繁体字形，且 `PAINTING_PROBE` 的失败拓扑违反了“失败先落盘再 native Failed”的约束。

解决方案：提交 `07c38a744a92e11056e42b05819b85eca55940e6` 已在紧 ROI 内精确接受简体/繁体“侠客派遣/俠客派遣”，并要求“画卷 + 偃武世界”双边界同帧成立；派遣 ROI 与相邻“蜃影武墟”框不相交。原 `PAINTING_PROBE` 自环和回跳 `GAME_START` 已删除，所有未知状态直接进入 fresh failed 后 native Failed。修复合入主线后的 HERO 聚焦回归 `12 passed`、base 资源 `1438` 节点零错误，待新候选正式验收。证据归档于 `install/mfw-android-all-20260809-r21-debug-hero-r1`，票据为其中 `acceptance/HERO_DISPATCH_DAILY/20260809T104405633587Z/ticket.json`。

## 问题 51：武学研习选槽后进入详情页，材料不足状态未建模

现象：r21 武学研习已依次执行 `open_function_panel`、`open_martial_study`、`open_martial_plus_slot_0`。随后真实画面是角色武学详情“剑川之主/生死符/突破”，材料显示 `60/1200` 与 `2/80`，显然不足；流程仍要求顶部“武学研习”，最终 fresh `failed / MARTIAL_SLOT_STATE_AMBIGUOUS`。MFW 外层仍为 Succeeded，验收器正确返回 1。

原因：选择空槽后的详情页是独立页面边界，旧流程把它当作仍在武学研习列表；材料不足判断因此永远不可达。

解决方案：提交 `c18ab5e89715354d93e388c7e477659fc5178e9c` 已为“剑川之主/生死符/重数/重置”建立紧详情页边界，并由自定义识别器同帧解析两项材料比例。任一必需材料不足时不允许点击“突破”，只执行有界关闭并记录策略允许的 `not_eligible / martial.material_insufficient`；只有所有 `owned >= required` 才能授权有 cap 的突破。聚焦回归 `37 passed`、扩展相关回归 `312 passed`、资源校验 `1205` 节点零错误，待新候选正式验收。证据归档于 `install/mfw-android-all-20260809-r21-debug-martial-r1`，票据为其中 `acceptance/MARTIAL_STUDY_BREAKTHROUGH_DAILY/20260809T104603789790Z/ticket.json`。

## 问题 52：免费鉴宝已产出结果，但结果页没有业务后置分支

现象：r22 已按主世界顶部精确入口执行 `open_appraisal -> claim_free_appraisal_once`。失败截图明确显示中央物品 `x5`、顶部传闻“传世高手【掠月影】飞鸿仙子已经出现在…”和右上关闭按钮；底部只剩“鉴宝一次/鉴宝十次”付费按钮。免费动作已经真实成功，但任务仍写出 fresh `failed / APPRAISAL_POSTCONDITION_MISSING`。

原因：入口问题已经解决，第二层缺陷是结果页只识别通用奖励文案，没有覆盖本次鉴宝专用的传闻结果页；流程因此不能安全关闭结果，也不能验证免费按钮已经消失。底部付费按钮绝不能作为恢复目标。

解决方案：独立 FREE worktree 已提交 `eac8dc7a5d2a153e6483f189208a3b5dedbf3a94`。新分支要求中央数量、底部“鉴宝一次”和“鉴宝十次”三个锚点同帧成立，并只点击与两枚付费按钮完全不相交的左侧暗幕安全区来关闭结果；关闭后精确验证免费次数已用后的“鉴宝一次”状态，再有界返回主页。所有输入 cap 为 1，未知状态仍失败关闭。补丁已按文件哈希无损同步到主工作区，FREE r21/r22 聚焦回归 `10 passed`，当前 base 资源 `1472` 个节点零错误，待下一候选正式验收。证据归档于 `install/mfw-android-all-20260809-r22-debug-free-r1`，票据为其中 `acceptance/FREE_APPRAISAL_DAILY/20260809T110457739611Z/ticket.json`。

## 问题 53：试剑全部领取后，实机完成态是“0 + 敬请期待”

现象：r22 已完成 `open_trial_sword -> claim_trial_sword_reward -> close_reward_popup -> claim_free_trial -> confirm_free_trial -> close_reward_popup`。最终试剑页同帧显示“挂机收益/当前收益”，第一项资源数量为 `0`，右侧免费区域变成“敬请期待”；旧 `trial.free_used` 仍只搜索“挂机时长/已使用/已完成”，最终 fresh `failed / TRIAL_POSTCONDITION_MISSING`。

原因：普通收益与免费次数的输入链均成功，遗漏的是今天账号上的真实终态文案。继续等待“已使用/已完成”不可能命中，也不得因为底部仍绘制无资源的“领取”按钮而再次点击。

解决方案：在严格试剑页边界下，以“敬请期待”和当前收益关键数量为 0 的同帧证据建立完成分支；普通收益与免费动作各保持 cap 1，完成后不得再次输入。修复正在原 TRIAL 独立 worktree 中进行。证据归档于 `install/mfw-android-all-20260809-r22-debug-trial-r1`，票据为其中 `acceptance/TRIAL_SWORD_DAILY/20260809T111257556279Z/ticket.json`。

## 问题 54：侠客派遣入口成功后，9/9 全部派遣中的等待态未建模

现象：r22 已稳定执行 `open_painting_scroll -> open_hero_dispatch` 并进入真实“侠客派遣”页。现场左侧显示 `任务: 9/9`、`已完成: 0`，九个派遣槽位均已有任务且尚未完成；右侧“尚未选择派遣任务”只是当前没有选中列表行，不代表仍有空闲派遣容量。现有领取 gate 只接受可领取任务，因而写出 fresh `failed / HERO_POSTCONDITION_MISSING`。

原因：繁体入口和画卷边界已修复，新的缺口在页内状态机：它只覆盖可领取任务，没有把“9/9 已全部派遣、0 已完成”的正常等待态建模成今日无需继续输入的明确终态。

解决方案：必须在“侠客派遣 + 任务 9/9 + 已完成 0 + 九槽已占用”的严格同帧边界下记录 `already_complete`/等待中，并直接安全退出，不得再次选择、派遣或领取；可领取分支仍需优先，未知页仍 fresh failed + native Failed。修复正在原 HERO 独立 worktree 中进行。证据归档于 `install/mfw-android-all-20260809-r22-debug-hero-r1`；该归档中的正式运行票据为 `acceptance/HERO_DISPATCH_DAILY/20260809T111556403782Z/ticket.json`。

## 问题 55：破阵已进入战斗并获胜，但胜利大字被窄 ROI 裁断

现象：r22 首次完整执行了 `open_break_array_activity -> open_break_array -> start_break_array_challenge -> confirm_break_array_challenge -> start_break_array_battle`，随后无输入等待约两分钟并到达明确“战斗胜利”结算画面。全幅/较宽 OCR 多次返回精确“战斗胜利”且得分约 0.999，但 `break_array.result` 在旧 ROI 中返回“战斗胜禾”，`break_array.success` 只返回“战斗胜”，最终 fresh `failed / WORKFLOW_POSTCONDITION_MISSING`。

原因：确认、黑屏过渡、准备页、开战和战斗等待链已经全部修复；新的唯一缺口是结算页超大装饰标题宽度超出结果与成功探针的裁剪范围。状态机因此看见真实胜利却无法分区。

解决方案：使用该 r22 结算截图校准能完整包围巨大“战斗胜利”的紧结果 ROI，并要求精确胜利文本与结算页视觉边界同帧成立；只有明确胜利才允许有 cap 的结算关闭和后续次数/完成态验证，不能把 OCR 半词或战斗中画面当成功。本次 `mfw_live_acceptance.py finish` 已按预期返回 1，修复仍待独立 BREAK worktree 代理槽位。证据归档于 `install/mfw-android-all-20260809-r22-debug-break-r1`，票据为其中 `acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T111908133393Z/ticket.json`。

## 问题 56：采集页已有“一键收获”，但领取分支挂在不可达的子节点错误路由

现象：r22 已完成 `open_painting_scroll -> select_yanwu_world -> open_collection_deployment`，并进入真实“采集部署”页。`MJA_COLLECTION_POST_OPEN_PAGE_PROBE` 已以 0.977 分精确命中标题；现场右下角有“一键收获”，矿石行另有一个“未部署”槽位。流程只探测“已采集/已收获”，约 15 秒后写出 fresh `failed / COLLECTION_POSTCONDITION_MISSING`，正式 `finish` 返回 1。

原因：`MJA_COLLECTION_POST_OPEN_PAGE_PROBE.next` 只有 `MJA_COLLECTION_INITIAL_HARVESTED`。该子节点未命中时，MaaFramework 回到父节点失败处理，不会继续执行子节点自己的 `on_error: MJA_COLLECTION_CLAIM`，所以明明存在的“一键收获”从未成为 sibling 候选；这与早期商店领取 gate 的不可达缺陷相同。

解决方案：把严格页面边界下的“一键收获”作为与“已收获”并列且次优先的有限 sibling；只有精确按钮同帧成立才允许一次领取，随后验证奖励/已收获状态。现场还有一个明确“未部署”槽位，修复时需根据任务契约决定是否在收获闭环后执行一次有 cap 的安全部署；不能把领取成功直接等同于部署完成。未知页面仍 fresh failed + native Failed。证据归档于 `install/mfw-android-all-20260809-r22-debug-collection-r1`，票据为其中 `acceptance/COLLECTION_DEPLOYMENT_DAILY/20260809T112542647107Z/ticket.json`。

## 问题 57：消耗凝晶打开功能面板后，“日常”入口 ROI 未覆盖实机按钮

现象：r22 消耗凝晶在正常主页执行 `open_function_panel`，面板模板先以 0.876 命中，随后面板页边界仍以 0.814 命中；实机截图也明确显示右上第二枚按钮“日常”。但 `condensate.daily.entry` 在当前 ROI 内持续返回空 OCR，8 秒后 fresh `failed / CONDENSATE_POSTCONDITION_MISSING`，正式验收器返回 1。

原因：START sibling 和功能面板本身已工作，失败点是“日常”目标的 ROI/版式仍不覆盖实机按钮文字；等待过程中面板模板分数又被顶部传闻滚动降到约 0.47，但这不是入口初始识别失败的根因。

解决方案：用 r22 截图校准“日常”按钮紧 ROI，并与同帧功能面板边界绑定；点击后继续要求日常页及凝晶任务的明确页面状态，所有资源消耗与输入 cap 不放宽。未知状态仍 fresh failed + native Failed。证据归档于 `install/mfw-android-all-20260809-r22-debug-condensate-r1`，票据为其中 `acceptance/SPEND_CONDENSATE_DAILY/20260809T112851158420Z/ticket.json`。

## 问题 58：体力食物已打开资源背包，但页面边界仍按旧版名称判断

现象：r22 体力食物从主页执行 `open_resource_page` 后稳定进入真实资源背包。现场左侧标题为“资源”，顶部标签为“全部/可使用”，右侧显示选中物品“极品精粹/物品/当前拥有 190”；现有 `MJA_FOOD_BAG_PAGE_PROBE` 没有接受这个页面，fresh `failed / FOOD_POSTCONDITION_MISSING`，正式验收器返回 1。

原因：主页入口与有界 START sibling 已生效，新的缺口是页内页面契约仍依赖旧版“行囊/背包/食物”等推测文案，没有建模当前“资源 + 全部/可使用”布局，也未安全导航到可使用类目。

解决方案：以“资源 + 全部 + 可使用”的同帧精确边界确认页面，只允许有 cap 地切换“可使用”标签，再在明确体力食品身份、数量和使用确认下执行任务；不能点击当前“极品精粹”等非食品材料。资源预算、动作 cap 和未知 fresh failed + native Failed 保持不变。证据归档于 `install/mfw-android-all-20260809-r22-debug-food-r1`，票据为其中 `acceptance/EAT_STAMINA_FOOD_DAILY/20260809T113123597712Z/ticket.json`。

## 证据路径

- GUI 日志：`install/mfw-android-all-20260809-r1/debug/gui.log`
- MaaFramework 日志：`install/mfw-android-all-20260809-r1/debug/maafw.log`
- 第二轮票据（在 GAME_START 缺陷处中止）：`install/mfw-android-all-20260809-r1/debug/acceptance/ALL/20260809T040339155059Z/ticket.json`
- r2 第一次定向票据（MFW 自动监控取图争用，失败）：`install/mfw-android-all-20260809-r2/debug/acceptance/MAIL_REWARD_DAILY/20260809T041451499653Z/ticket.json`
- r2 第二次定向票据（新弹窗节点已生效，停在月签到页，失败）：`install/mfw-android-all-20260809-r2/debug/acceptance/MAIL_REWARD_DAILY/20260809T042123975158Z/ticket.json`
- r3 空启动票据（MFW 首次冷启动较慢，在任务开始前被终止）：`install/mfw-android-all-20260809-r3/debug/acceptance/MAIL_REWARD_DAILY/20260809T043130180971Z/ticket.json`
- r3 定向票据（月签到关闭成功，主页模板阈值阻断）：`install/mfw-android-all-20260809-r3/debug/acceptance/MAIL_REWARD_DAILY/20260809T043248214540Z/ticket.json`
- r4 定向验收（`GAME_START + MAIL_REWARD_DAILY`，通过）：`install/mfw-android-all-20260809-r4/debug/acceptance/MAIL_REWARD_DAILY/20260809T045540225954Z/acceptance.json`
- r4 首次全量票据（商城失败并产生跨任务污染，失败）：`install/mfw-android-all-20260809-r4/debug/acceptance/ALL/20260809T045933883573Z/ticket.json`
- r7 商店正式验收（通过）：`install/mfw-android-all-20260809-r7/debug/acceptance/SHOP_FREE_GIFT_DAILY/20260809T054229696533Z/acceptance.json`
- r7 买茶正式验收（通过）：`install/mfw-android-all-20260809-r7/debug/acceptance/BUY_TEA_DAILY/20260809T054656938704Z/acceptance.json`
- r7 破阵正式票据（无新鲜结果，失败）：`install/mfw-android-all-20260809-r7/debug/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T054945910989Z/ticket.json`
- r7 帮会捐献正式验收（业务结果通过，但退出污染待复验）：`install/mfw-android-all-20260809-r7/debug/acceptance/GUILD_DONATION_DAILY/20260809T055556391879Z/acceptance.json`
- r7 副本正式票据（前置 GAME_START 被捐献页阻断，失败）：`install/mfw-android-all-20260809-r7/debug/acceptance/DUNGEON_SWEEP_DAILY/20260809T055826069324Z/ticket.json`
- r11 破阵恢复结果（识图成功但诊断接口异常，失败）：`install/mfw-android-all-20260809-r11/debug/mfw-105553180116216/BREAK_ARRAY_MARTIAL_DAILY/result.json`
- r11 帮会捐献正式票据（关闭弹窗后停在帮会主页，失败）：`install/mfw-android-all-20260809-r11/debug/acceptance/GUILD_DONATION_DAILY/20260809T063216429197Z/ticket.json`
- r11 副本扫荡正式票据（扫荡面板 OCR 文案不兼容，失败）：`install/mfw-android-all-20260809-r11/debug/acceptance/DUNGEON_SWEEP_DAILY/20260809T063637546190Z/ticket.json`
- r11 剑林正式票据（未完成 sibling 分支不可达，失败）：`install/mfw-android-all-20260809-r11/debug/acceptance/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/20260809T063848047543Z/ticket.json`
- r11 帮会活动正式票据（页面旧标题不匹配，失败）：`install/mfw-android-all-20260809-r11/debug/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T064240375286Z/ticket.json`
- r11 帮会事务正式票据（领奖遮罩未关闭，失败）：`install/mfw-android-all-20260809-r11/debug/acceptance/GUILD_AFFAIRS_DAILY/20260809T064447288151Z/ticket.json`
- r13 副本正式票据（误选相邻大师卡片，失败）：`install/mfw-android-all-20260809-r13-debug-through-jianlin/acceptance/DUNGEON_SWEEP_DAILY/20260809T070724978419Z/ticket.json`
- r13 剑林正式票据（误点顶部公告且页面模板假阳性，失败）：`install/mfw-android-all-20260809-r13-debug-through-jianlin/acceptance/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/20260809T071055019898Z/ticket.json`
- r13 帮会活动正式票据（右侧上下文被截断，失败）：`install/mfw-android-all-20260809-r13-debug-guild-activity/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T071839000619Z/ticket.json`
- r13 帮会事务正式票据（连续待领奖状态未建模，失败）：`install/mfw-android-all-20260809-r13-debug-guild-affairs/acceptance/GUILD_AFFAIRS_DAILY/20260809T072140304412Z/ticket.json`
- r14 破阵正式票据（上下两行开始按钮未组合，失败）：`install/mfw-android-all-20260809-r14-debug-break-r1/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T074437870508Z/ticket.json`
- r14 帮会捐献正式验收（三层归位通过）：`install/mfw-android-all-20260809-r14-debug-donation/acceptance/GUILD_DONATION_DAILY/20260809T074712942033Z/acceptance.json`
- r14 副本正式票据（难度文字打开奖励预览，失败）：`install/mfw-android-all-20260809-r14-debug-dungeon-r1/acceptance/DUNGEON_SWEEP_DAILY/20260809T074849964629Z/ticket.json`
- r14 剑林正式验收（通过）：`install/mfw-android-all-20260809-r14-debug-jianlin/acceptance/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/20260809T075111751152Z/acceptance.json`
- r14 帮会活动正式票据（世界首领编队页未建模，失败）：`install/mfw-android-all-20260809-r14-debug-guild-activity-r1/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T075246658188Z/ticket.json`
- r17 破阵正式票据（消耗次数确认弹窗未建模，失败）：`install/mfw-android-all-20260809-r17-debug-break-r1/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T082408286317Z/ticket.json`
- r17 副本正式票据（票券模板阈值过高，失败）：`install/mfw-android-all-20260809-r17-debug-dungeon-r1/acceptance/DUNGEON_SWEEP_DAILY/20260809T082753318039Z/ticket.json`
- r17 帮会活动正式票据（世界首领竖排开始 OCR 不稳定，失败）：`install/mfw-android-all-20260809-r17-debug-guild-activity-r1/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T083100044969Z/ticket.json`
- r17 帮会事务正式票据（事务已启动但右侧后置状态不在 OCR ROI，失败）：`install/mfw-android-all-20260809-r17-debug-guild-affairs-r1/acceptance/GUILD_AFFAIRS_DAILY/20260809T083329540468Z/ticket.json`
- r18 破阵正式票据（确认后黑色过渡帧未建模，失败）：`install/mfw-android-all-20260809-r18-debug-break-r1/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T084809942302Z/ticket.json`
- r18 副本正式票据（竖排结果标题无法被横排 OCR 识别，失败）：`install/mfw-android-all-20260809-r18-debug-dungeon-r1/acceptance/DUNGEON_SWEEP_DAILY/20260809T085122704149Z/ticket.json`
- r18 帮会活动正式票据（缺少战斗进行中无输入等待分支，失败）：`install/mfw-android-all-20260809-r18-debug-guild-activity-r1/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T085443041980Z/ticket.json`
- r18 帮会事务正式票据（业务结果成功但关闭清理原生失败）：`install/mfw-android-all-20260809-r18-debug-guild-affairs-r1/acceptance/GUILD_AFFAIRS_DAILY/20260809T085808933363Z/ticket.json`
- r19 破阵正式票据（黑屏后编队页被误判为战斗中，失败）：`install/mfw-android-all-20260809-r19-debug-break-r1/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T091609014871Z/ticket.json`
- r19 副本正式验收（扫荡结果识别、单次关闭和票券耗尽验证通过）：`install/mfw-android-all-20260809-r19-debug-dungeon-r1/acceptance/DUNGEON_SWEEP_DAILY/20260809T092221969735Z/acceptance.json`
- r19 帮会活动正式票据（战败标题被裁成“战斗失”，结果分区失败）：`install/mfw-android-all-20260809-r19-debug-guild-activity-r1/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T092442138243Z/ticket.json`
- r19 帮会事务正式验收（业务成功且页面关闭清理通过）：`install/mfw-android-all-20260809-r19-debug-guild-affairs-r1/acceptance/GUILD_AFFAIRS_DAILY/20260809T092955325207Z/acceptance.json`
- r19 未验收任务批量 dry-run（11 项，失败清单）：`install/mfw-android-all-20260809-r19-debug-unverified-r1/acceptance/ALL/20260809T093340215641Z/ticket.json`
- r20 破阵正式票据（准备页仍被 runtime 决策成战斗等待，失败）：`install/mfw-android-all-20260809-r20-debug-break-r1/acceptance/BREAK_ARRAY_MARTIAL_DAILY/20260809T095410115911Z/ticket.json`
- r20 心法研习正式票据（红点面板模板失效并无界等待，失败）：`install/mfw-android-all-20260809-r20-debug-martial-study-r1/acceptance/MARTIAL_STUDY_BREAKTHROUGH_DAILY/20260809T100041574087Z/ticket.json`
- r20 擂台正式票据（红点面板模板失效并无界等待，失败）：`install/mfw-android-all-20260809-r20-debug-ring-r1/acceptance/RING_CHALLENGE_DAILY/20260809T100611271692Z/ticket.json`
- r20 帮会活动正式票据（次数为零但只退出到功能面板，失败）：`install/mfw-android-all-20260809-r20-debug-guild-activity-r2/acceptance/GUILD_ACTIVITY_CHALLENGE_DAILY/20260809T101635757314Z/ticket.json`
- r20 Android-only 候选元数据（已实跑）：`install/mfw-android-all-20260809-r20/build-metadata.json`

本记录将在后续全量运行和逐任务修复中继续更新。
