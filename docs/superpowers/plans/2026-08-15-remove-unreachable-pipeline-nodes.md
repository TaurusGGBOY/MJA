# Unreachable Pipeline Node Cleanup Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with an explicit review checkpoint after each task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove pipeline nodes and obsolete branches that cannot be reached from any declared task entry, while preserving every reachable action, recognition component, normal terminal, and failure terminal.

**Architecture:** Treat every task `entry` in `assets/tasks` as a graph root. Resolve transitions through `next` and `on_error`, and resolve composite-recognition dependencies through their nested recognition references. The audit found 1,289 reachable nodes and 36 unreachable nodes across 28 base pipeline files; cleanup is limited to those 36 nodes in five files.

**Tech Stack:** MaaFramework JSON pipelines, Python standard-library audit, `jq`, existing MFW resource validator, and offline tests only.

## Global Constraints

- Do not run a real MFW pipeline, emulator, game, ADB task, or MPE execution.
- Preserve all nodes reachable from declared task entries, including normal success terminals and failure/abort terminals.
- Preserve the existing `启动-游戏启动` homepage route, the 20-second timeout, and prior removal of the obsolete 影页面 nodes.
- Do not modify the pre-existing user change in `AGENTS.md`.
- Use the base resource under `assets/resource/base`; do not alter archived Android compatibility resources unless a direct production reference requires it.

---

### Task 1: Reconfirm the dead-node inventory

**Files:**
- Read: `assets/tasks/**/*.json`
- Read: `assets/resource/base/pipeline/**/*.json`
- Read: `assets/interface.json`

- [ ] Recompute roots from every declared task entry, including `GAME_START`, `GAME_STOP`, active daily tasks, and the declared retired task resource.
- [ ] Traverse `next`, `on_error`, and composite recognition dependencies, normalizing `[JumpBack]` targets.
- [ ] Confirm the inventory remains 36 unreachable nodes: 30 unreachable leaf nodes and 6 unreachable branch containers.
- [ ] Confirm no reachable node references any candidate for deletion.

### Task 2: Remove unreachable shared pipeline branches

**Files:**
- Modify: `assets/resource/base/pipeline/common/home_recovery.json`
- Modify: `assets/resource/base/pipeline/common/known_popups.json`
- Modify: `tools/check_mfw_resources.py`

- [ ] Remove the unreachable home-recovery branch and its recognition-only descendants: `公共-主页恢复`, `公共-主页恢复-弹窗`, `公共-主页恢复-未知-中止`, `公共-游戏主页-标题`, `公共-游戏主页-位置`, `公共-游戏主页-地图-页面`, `公共-游戏地图-世界`, `公共-游戏地图-区域`, and `公共-游戏地图-就绪`.
- [ ] Remove the unreachable known-popup branches and their recognition-only descendants: the reward-popup branch, safety-announcement branch, battle-result branches, monthly-sign-in branch, network-confirm branch, hero-dispatch-close branch, resource-update-confirm branch, cross-map-prompt branch, and unused generic-page-close branch.
- [ ] Keep all shared popup and home nodes that have an incoming path from a task entry.
- [ ] Remove the validator's stale convergence alias for the deleted `公共-主页恢复` node.

### Task 3: Remove unreachable task-local leaf nodes

**Files:**
- Modify: `assets/resource/base/pipeline/daily/break_array_martial_daily.json`
- Modify: `assets/resource/base/pipeline/daily/guild_affairs_daily.json`
- Modify: `assets/resource/base/pipeline/daily/mail_reward_daily.json`

- [ ] Remove the unreferenced break-array modal-close, breakthrough-modal-close, and breakthrough-loading markers.
- [ ] Remove the unreferenced guild-affairs home-page marker.
- [ ] Remove the unreferenced mail-panel-close marker.
- [ ] Do not remove any task entry, action node, recognition dependency, success outcome, or failure outcome that remains reachable.

### Task 4: Validate the cleaned resource graph

**Files:**
- Read: `assets/resource/base/pipeline/**/*.json`
- Read: `assets/tasks/**/*.json`

- [ ] Parse every modified JSON file successfully.
- [ ] Run the existing MFW resource validator against `assets/resource/base` and confirm there are no missing transition targets or unbounded-cycle regressions caused by the cleanup.
- [ ] Re-run the reachability audit and confirm no unreachable nodes remain in the production base resource under the declared task-entry model.
- [ ] Run `git diff --check`.
- [ ] Do not start a real pipeline; report any unavailable Python test dependency separately from the static validation result.
