# Android daily workflows（已退役）

旧的 Android daily workflow runner、聚合结果和独立验收入口已经退役。本文仅保留迁移提示，不再定义任务状态、验收命令或结果文件格式。

当前支持面是 MFW：每次验收精确选择 `GAME_START + 一个业务任务`，在启动前用 `--expect-terminal TASK_ID=Succeeded|Failed` 声明期望的 MFW 原生终态，运行后用 `tools/mfw_live_acceptance.py finish` 核对新鲜原生终态。

请参阅：

- [MFW 开发与验收](../mfw-development.md)
- [MFW 批量任务修复操作规约](mfw-concurrent-task-repair.md)

模拟器仍必须使用 `-gpu host`，AVD 必须保持 `hw.gpu.enabled=yes` 和 `hw.gpu.mode=host`。历史 Android 验收材料保留在原目录中，不能修改或重新解释为当前验收结果。
