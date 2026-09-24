# 崩溃取证与汇编追踪

正式入口 `tools/launch_mfw.zsh` 默认启动本地诊断观察器。它不定义任务结果：
任务仍以 MaaFramework 的原生终态为准，画面异常也不触发新的自动恢复。

## 证据位置与生命周期

- 设置 `MJA_ACCEPTANCE_TICKET` 可明确绑定本轮 `ticket.json`。
- 未指定时，选择同一候选最近一小时内、尚无 `acceptance.json` 的票据。
- 找不到可关联票据时，写到候选的 `debug/observability/`。
- 每次启动使用独立 `launch-*` 子目录，避免重试覆盖现场。
- `MJA_CRASH_OBSERVE=0` 关闭观察器；`MJA_ANDROID_SDK_ROOT` 覆盖 SDK 根目录。
- `MJA_EMULATOR_CRASH_DIR` 指向本机 Crashpad 数据库目录；未设置时搜索系统临时
  目录下的 Android 模拟器数据。不会更改崩溃报告上传设置。

目录位于已忽略的运行输出中。含截图、游戏日志、进程信息和可能的账号信息，
仅供本地诊断；发布前另行脱敏。每轮 Android 日志最多五份，每份约 8 MiB。
不同轮次的完整证据不自动删除，由使用者在调查结束后清理。

## 收集什么

| 文件/事件 | 意义 |
| --- | --- |
| `android.log*` | 持续读取 crash/main/system logcat，epoch 时间；断线重连有独立事件 |
| `events.jsonl` | UTC、宿主 monotonic、观察进程 PID、原生 task/node/action ID 和恢复请求 |
| `game-version.txt`、`device-properties.txt`、`guest-clock.txt` | 游戏版本、Android 属性及客体时钟；元数据命令完成时另记宿主时间 |
| `binary-*-uuid.txt` | 实际候选及模拟器 Mach-O UUID；工具缺失会记录错误 |
| `mfw-console.log` | MFW stdout/stderr，包括可见的 Python 异常栈 |
| `capture-*` | 进程 PID、crash logcat、Android exit-info、截图、tombstone 清单/归档 |
| `host-reports/` | 新的本地 `.ips` / `.dmp`，最多复制 8 份、128 MiB；扫描有时间上限 |
| `frame-*`、`image_measurement` | 已缓存的 Maa 画面及洋红像素比例；不判定业务成功或渲染根因 |

游戏进程消失和 logcat fatal 触发异步取证，同一观察器最多有一个在途取证进程。
每五秒探测游戏进程，ADB 错误记录为未知，不把断线当作游戏崩溃。
新启动的模拟器由一个轻量监督进程等待，保留真实子进程退出码及负信号值。
复用既有模拟器时无法获取其父进程拥有的 `wait` 结果；这一情况下不能声称已知退出信号。
MFW 自身记录 shell wait 值，不能仅凭 `128+N` 排除程序主动返回该值的可能。

`RestartGameSurface` 在恢复前同步取证，所有 ADB 命令共享六秒预算、单条最多一秒。
随后记录 `game_recovery_requested`，再按原流程停止/重启。
主动停止的记录表示请求意图，不冒充 Android 已成功执行停止。
启动器切换隐藏模拟器、预运行 force-stop 也会先留下取证记录。
读不到 tombstone 时保留错误，不执行 root、重启 adbd 或提权。
超时输出可能是部分文件，尤其 `tombstones.tar`，必须结合命令退出事件检查。

## 如何判断因果

1. 查原生 task/node/action ID，确定故障发生在哪个动作附近。
2. 对照 `game_recovery_requested`，区分主动恢复与观察到的进程消失。
3. 查 Android exit-info、fatal 记录、tombstone 和宿主进程退出事件。
4. 对比客体时钟与宿主采集时间，处理时钟偏移；不能混用两侧 monotonic 值。
5. 缺少原始转储时只报告现象和候选原因，不把历史故障或静态代码当作本轮崩溃证据。

## 生成报告和反汇编

```sh
.venv/bin/python tools/mfw_crash_report.py "$EVIDENCE_DIR"

# LLDB 可读取的 core/minidump：提取线程栈、寄存器和当前 PC 附近指令。
.venv/bin/python tools/mfw_crash_report.py "$EVIDENCE_DIR" \
  --binary "$EXACT_BINARY" --core "$CORE_FILE"

# Android 文本 tombstone / macOS .ips 不能直接当成 core。
# 先以 Build ID/UUID 匹配二进制，并将模块偏移换算为该映像的链接地址。
.venv/bin/python tools/mfw_crash_report.py "$EVIDENCE_DIR" \
  --binary "$EXACT_BINARY" --address 0x1234
```

最后一种明确标注 STATIC；`0x1234` 只是用法示例，不是本轮故障地址。
报告工具不会自动证明转储与二进制相匹配，也不会下载符号。
保留本轮安装候选和对应符号，避免下一次升级后仅剩无法映射的偏移。
LLDB 不可用或不支持该转储格式时，报告会明确记录缺口。

## 验证边界

聚焦测试覆盖：共享超时预算、权限不足、票据与重试隔离、独立子进程退出信号、
持续日志轮转、观察器退出后的子进程清理、缺失转储报告和画面测量。
现有启动与恢复测试验证原生执行行为保持一致。
这些测试不证明真实设备能提供 tombstone 或宿主崩溃转储；需要下一次真实运行确认权限和产物。
