## 背景

- 本项目为《对决剑之川》游戏的MAAFramework特化版
- 参考MaaFramework: /Users/gaoguobin/project/MaaFramework
- 优秀改造案例参考：/Users/gaoguobin/project/Maa_bbb
- 参考剑之川的maa workflow：/Users/gaoguobin/project/computer-use/tools/maa，这个maa暂时不能完美运行
- 参考剑之川的原始workflow：/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily，这个之前基本可以完美运行
- 参考后续需要能正常显示在这个GUI上：https://github.com/SweetSmellFox/MFAAvalonia
- 本项目后续主要是运行在MAC： System Version: macOS 27.0 (26A5388g)
- 本项目控制的游戏也是先适配运行在本机MAC上的IOS版本
- 对决剑之川在本机上已经安装好了：/Applications/对决！剑之川.app
- 我没有明确要求使用superpowers的skill时禁止使用

## Android 模拟器 GPU 运行约束

- Android 模拟器的 GPU 后端只能使用 host：启动参数必须是 `-gpu host`，AVD 配置必须保持 `hw.gpu.enabled=yes` 和 `hw.gpu.mode=host`。
- 禁止改用 auto、software、SwiftShader 或其他 GPU 后端。当前 macOS 环境下不用 host 可能导致画面卡顿、卡死、闪退，进而让游戏和日常任务运行失败。
- 修改模拟器启动、AVD 配置或运行脚本后，必须检查实际 QEMU 命令行仍包含 `-gpu host`，并确认没有注入会覆盖 GPU 后端的环境变量。

## macOS Terminal 使用约束

- 项目入口、运行脚本和自动化代码禁止自行启动或控制 `Terminal.app`（包括 AppleScript `tell application "Terminal"`、`open -a Terminal` 等方式）。
- 项目命令必须在调用方已有的执行环境中运行；需要用户查看日志时输出日志路径或使用当前执行会话，不得为了执行项目而新开 Terminal 窗口。

## Android 模拟器并发修复约束

- 每个正式 MFW 业务任务使用一个独立 sub-agent/worktree；禁止多个 sub-agent 直接修改同一个工作区。
- 真实模拟器操作直接在当前执行环境中进行；MFW、ADB、截图、启动或停止游戏使用项目现有命令，不再添加额外串行层。
- 分析日志、修改代码、跑离线测试和打包候选均在当前执行环境中完成；启动真实 MFW 前确认没有第二个 runner 正在运行。
- 单任务验收必须在 MFW 中只勾选 `GAME_START + 指定任务`，并以 `tools/mfw_live_acceptance.py finish` 返回 0 为完成条件。
- `Tasker.Task.Succeeded` 不能单独作为成功证据；对应的新鲜 `result.json` 必须为 `success`、`already_complete` 或策略允许的 `not_eligible`。
- sub-agent 不得在真实运行失败、结果仍为 `running`、证据来自旧运行或尚未完成 MFW 验收时报告任务完成。


## Migration History
- 2026-08-08: Project migrated from `/Users/gaoguobin/project/MJA` to `/Volumes/my_disk/project/MJA`.
- Canonical project path: `/Volumes/my_disk/project/MJA`.
- Keep agent instructions in `AGENTS.md`; `CLAUDE.md` is a symlink to it.

## tips

- 用户如果需要查看pipeline，可以使用MaaPipelineEditor(MPE)

