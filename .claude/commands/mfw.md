---
description: 运行并批量修复对决！剑之川 MFW 任务（遵循 mfw-batch-repair-jianzhichuan skill）
---

先完整阅读 `.claude/skills/mfw-batch-repair-jianzhichuan/SKILL.md`，然后严格按其中的契约执行：

- 用户明确列出任务 → `explicit` 模式，只跑 `GAME_START` + 这些任务，绝不扩展到未列出的业务任务或自动全量回归；
- 用户未列出任务 → `full` 模式，先调用只读选择器 `tools/mfw_task_selection.py` 筛选当天 date-eligible 的 `pending_tasks`，首批只跑 `GAME_START + pending_tasks`。

随后按 skill 定义的循环进行：

`确定授权范围 → 运行到首个失败即停 → 冻结 F(n) → systematic-debugging 定位根因 → 批量修复 → 整批复跑 F(n) → 在授权范围内收敛`

严格遵守所有安全与验收边界（仅 Android 模拟器、单 runner、`mfw_android_preflight.py` 预检门禁、截图桥、禁止 fix-one/rerun-one、禁止 `Tasker.Task.Succeeded` 单独作为成功证据等）。
