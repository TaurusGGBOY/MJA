# MJA MFW 日常任务批次 C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **2026-08-05 target correction (authoritative):** 批次 C 的实机目标是本机 macOS/iOS 游戏窗口，通过 `MacOS` Controller + `ScreenCaptureKit` + `GlobalEvent` 验收；不是 Android 模拟器。Android fixture、ADB 命令和 Android live gate 不能作为当前 MFW 任务的验收证据。

**Goal:** 将蜃影遗迹、武学研习突破、副本扫荡和擂台挑战迁移为循环有界、战斗结果明确、危险状态可 Abort 且能安全同日重跑的独立 MFW Pipeline。

**Architecture:** 长流程完全由 Maa Pipeline 的页面识别、有限循环和新截图后置条件编排，不把战斗导航搬回 Python。窄 Agent 仍只执行受政策约束的当前帧输入和诊断；战斗/扫荡/突破所需资源不足由识别结果分流为正常不适用，未知状态显式 Abort。

**Tech Stack:** Maa Pipeline JSON、embedded GuardedInput、ProjectInterface v2、pytest graph/fixture assertions、MFW Android ADB live validation

## Global Constraints

- 开始本计划前，A+B 13 项在同一候选中的串行、同日重跑、资源审计和 Abort 隔离必须通过。
- 本批迁移顺序固定为 `SHADOW_RUINS_DAILY`、`MARTIAL_STUDY_BREAKTHROUGH_DAILY`、`DUNGEON_SWEEP_DAILY`、`RING_CHALLENGE_DAILY`。
- 战斗、扫荡、突破、确认和跳过均是副作用动作：发送后必须读取新截图，不允许 Maa 超时自动重放。
- 所有循环都有当前冻结政策中的明确最大次数；到达上限且终态未确认时记录稳定错误码并 Abort。
- 战斗失败弹窗只在识别到已知失败状态时关闭；不得把失败结果当 success，也不得无限重开战斗。
- 功能未开放、次数耗尽、票券不足、无活动卡或普通材料不足是可解释的 `not_eligible`/`already_complete`；识别冲突是 failed/Abort。
- `DUNGEON_SWEEP_DAILY.assign_sweep_ticket` 动作次数冻结为 100，资源总上限冻结为 `副本票: 20`；不能把两者错误合并成同一个数。
- `RING_CHALLENGE_DAILY` 只允许 `擂台券: 12`，扫荡最多一次，普通挑战/跳过各最多 12。
- 不使用 Python 中央 driver、aggregate、raw adb input、speedrun 或 MFW 队列业务重试。
- macOS 屏幕录制/辅助功能权限、真实窗口截图和当前坐标校准缺失时，任务只能停留在静态候选状态，不得伪造 fixture 或 live evidence。
- 现有未跟踪 `uv.lock` 不修改、不暂存、不提交。

---

## 批次 C 文件边界

| Canonical ID | Pipeline | 关键界限 |
| --- | --- | --- |
| `SHADOW_RUINS_DAILY` | `assets/resource/base/pipeline/daily/shadow_ruins_daily.json` | transfer 8, foreground 40, battle 12, failure dismiss 3 |
| `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | `assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json` | claim 3, study 9, breakthrough/confirm 3 |
| `DUNGEON_SWEEP_DAILY` | `assets/resource/base/pipeline/daily/dungeon_sweep_daily.json` | scroll policy 4, assign action 100, ticket resource 20, one sweep |
| `RING_CHALLENGE_DAILY` | `assets/resource/base/pipeline/daily/ring_challenge_daily.json` | fight 12, skip 12, sweep 1, ticket resource 12 |

Evidence sources are the same-basename files under `assets/resource_android/pipeline/daily/` and each task's dedicated file under `agent/workflows/definitions/`. Use them to preserve exact action IDs, page evidence, caps and postconditions; replace every central-driver delegation with Maa nodes and never import the legacy Python definition from the embedded Agent.

Before each task's live/test gate, manually show the recognized normal-ineligible state and then a supported off-route page, capturing the two missing fixture cases with these exact screenshot-only commands:

```bash
python3 -m tools.capture_mfw_fixture --task-id SHADOW_RUINS_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id SHADOW_RUINS_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id MARTIAL_STUDY_BREAKTHROUGH_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id MARTIAL_STUDY_BREAKTHROUGH_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id DUNGEON_SWEEP_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id DUNGEON_SWEEP_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id RING_CHALLENGE_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id RING_CHALLENGE_DAILY --case known_drift
```

Each live-gate command block is an ordered operator checklist. Run its concrete `mfw_install.py` line first, then pause, open the newly named output once, create and save the exact profile name shown with only the required task(s), close MFW, and only then run the following `mfw_profile.py` line. Never open or mutate `install/mfw-foundation-candidate`; it is the immutable release/runtime base. For `install/mfw-full-candidate`, create both full-preset and manual-all profiles before either direct run so both bind to exactly the same metadata.

### Task 1: 扩展长流程和战斗 Pipeline 契约

**Files:**
- Create: `tests/mfw/tasks/test_batch_c.py`
- Modify: `tests/mfw/task_contract.py`
- Modify: `tests/mfw/test_task_contract_helpers.py`
- Modify: `tests/test_mfw_safety.py`
- Modify: `tests/test_mfw_presets.py`

**Interfaces:**
- Consumes: `TaskContract`、`assert_no_side_effect_retry`、`TASK_POLICIES`。
- Produces: `assert_loop_bound`、`assert_terminal_after_loop`、`assert_battle_result_partition`、完整 17-ID preset contract。

- [ ] **Step 1: 写四个长流程契约测试**

```python
BATCH_C = [
    TaskContract("SHADOW_RUINS_DAILY", "shadow_ruins_daily.json"),
    TaskContract("MARTIAL_STUDY_BREAKTHROUGH_DAILY", "martial_study_breakthrough_daily.json"),
    TaskContract("DUNGEON_SWEEP_DAILY", "dungeon_sweep_daily.json"),
    TaskContract("RING_CHALLENGE_DAILY", "ring_challenge_daily.json"),
]


def test_batch_c_contracts():
    for contract in BATCH_C:
        assert_task_contract(contract)
        assert_fixture_matrix(
            contract.task_id,
            required={"entry", "actionable", "completed", "not_eligible", "known_drift", "danger"},
        )


def test_full_preset_has_start_then_all_17_once():
    assert preset_ids("日常-完整版") == ["GAME_START", *FINAL_CANONICAL_IDS]
    assert len(set(preset_ids("日常-完整版"))) == 18
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py tests/test_mfw_presets.py -q`

Expected: FAIL because four task declarations/Pipelines are absent and the full preset is incomplete.

- [ ] **Step 3: 实现终态分区和循环出口断言**

```python
def assert_terminal_after_loop(nodes, loop_node: str, maximum: int, exhausted_code: str) -> None:
    assert_loop_bound(nodes, loop_node, maximum)
    exhausted = nodes[f"{loop_node}_EXHAUSTED"]
    assert custom_param(exhausted, "error_code") == exhausted_code
    assert_reachable(nodes, exhausted["next"][0], "MJA_COMMON_ABORT")


def assert_battle_result_partition(nodes, prefix: str) -> None:
    assert f"{prefix}_VICTORY" in nodes
    assert f"{prefix}_DEFEAT" in nodes
    assert f"{prefix}_UNKNOWN_RESULT" in nodes
    assert_reachable(nodes, f"{prefix}_UNKNOWN_RESULT", "MJA_COMMON_ABORT")
```

Require every side-effect node to have retry count zero and a fresh-frame result branch. Add malformed tests for victory/defeat overlap, loop exhaustion returning success, and battle input without a failure branch.

- [ ] **Step 4: 运行辅助器测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/test_task_contract_helpers.py tests/test_mfw_safety.py -q`

Expected: PASS and malformed long-flow examples are rejected.

- [ ] **Step 5: 提交**

```bash
git add tests/mfw/task_contract.py tests/mfw/tasks/test_batch_c.py tests/mfw/test_task_contract_helpers.py tests/test_mfw_safety.py tests/test_mfw_presets.py
git commit -m "test: define bounded MFW combat task contracts"
```

### Task 2: 迁移 SHADOW_RUINS_DAILY

**Files:**
- Create: `assets/tasks/日常/SHADOW_RUINS_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/shadow_ruins_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_c.py`
- Modify: `tests/fixtures/SHADOW_RUINS_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/SHADOW_RUINS_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/SHADOW_RUINS_DAILY/known_drift.png`
- Create after live run: `verification/mfw/SHADOW_RUINS_DAILY.json`

**Interfaces:**
- Consumes: 公共启动、Shadow templates 和冻结政策。
- Produces: `MJA_SHADOW_RUINS_DAILY_START`; exact action IDs `open_painting_scroll`, `open_shadow`, `select_active_shadow_card`, `enter_shadow_stage`, `confirm_shadow_auto_route`, `dismiss_shadow_battle_result`, `dismiss_shadow_battle_failure`, `dismiss_shadow_reward_popup`, `confirm_shadow_completion`, `advance_shadow_foreground_triplet`, `transfer_shadow_stage`, `confirm_shadow_transfer`, `apply_shadow_recommended_team`, `use_shadow_recommended_team`, `close_shadow_recommended_team`, `move_shadow_foreground_left`, `move_shadow_foreground_center`, `move_shadow_foreground_right`, `battle`。

- [ ] **Step 1: 写蜃影状态机界限测试**

```python
def test_shadow_ruins_bounds_every_progress_loop():
    nodes = task_nodes("SHADOW_RUINS_DAILY")
    assert_loop_bound(nodes, "MJA_SHADOW_TRANSFER_LOOP", 8)
    assert_loop_bound(nodes, "MJA_SHADOW_FOREGROUND_LOOP", 40)
    assert_loop_bound(nodes, "MJA_SHADOW_BATTLE_LOOP", 12)
    assert_loop_bound(nodes, "MJA_SHADOW_FAILURE_DISMISS_LOOP", 3)
    assert_action_limit("SHADOW_RUINS_DAILY", "confirm_shadow_completion", 1)
    assert_battle_result_partition(nodes, "MJA_SHADOW_BATTLE_RESULT")
    assert_outcome(nodes, "MJA_SHADOW_NO_ACTIVE_CARD", "already_complete", "shadow.no_active_or_done")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k shadow -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现蜃影 Maa Pipeline**

```json
{"task":[{"name":"SHADOW_RUINS_DAILY","label":"蜃影遗迹","default_check":true,"group":["日常"],"entry":"MJA_SHADOW_RUINS_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/shadow_ruins_daily.json`; retain its existing Maa exploration recognitions, remove all central-driver delegation, and implement the bounded state machine below.

Navigate home → painting → Shadow. No active card or recognized completed card is `already_complete`. Select one unique active card, enter stage at most twice, confirm known auto-route prompt at most twice, then run an exploration state machine: known transfer ≤8, foreground triplet advancement ≤40 and battle ≤12. Recommended-team dialog uses apply/use/close each at most once. Victory closes recognized result/reward popups and resumes exploration; defeat closes only known failure at most 3 and records failed when no safe continuation exists; unknown result Aborts. Final completion confirmation occurs once and must produce done/no-active evidence before success.

- [ ] **Step 4: 运行自动化与单项实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k shadow -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-shadow-ruins-daily
python3 tools/mfw_profile.py run --install install/mfw-shadow-ruins-daily --profile-name live-SHADOW_RUINS_DAILY
```

Expected: fixture and all loop-exhaustion synthetic cases pass；live counts remain within policy，known defeat is not success，rerun no-active/already_complete. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/SHADOW_RUINS_DAILY.json assets/resource/base/pipeline/daily/shadow_ruins_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_c.py tests/fixtures/SHADOW_RUINS_DAILY verification/mfw/SHADOW_RUINS_DAILY.json
git commit -m "feat: migrate bounded Shadow Ruins flow to MFW"
```

### Task 3: 迁移 MARTIAL_STUDY_BREAKTHROUGH_DAILY

**Files:**
- Create: `assets/tasks/日常/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_c.py`
- Modify: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/known_drift.png`
- Create after live run: `verification/mfw/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json`

**Interfaces:**
- Consumes: martial page/card/slot/material templates。
- Produces: `MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_START`; exact action IDs `open_function_panel`, `open_martial_study`, `claim_success_card`, `close_reward_popup`, `close_martial`, `close_martial_page`, `open_martial_plus_slot_0`, `open_martial_plus_slot_1`, `open_martial_plus_slot_2`, `study_martial_slot`, `breakthrough_martial_slot`, `confirm_martial_breakthrough`。

- [ ] **Step 1: 写卡片、槽位和材料独立验证测试**

```python
def test_martial_claim_study_and_breakthrough_are_bounded():
    nodes = task_nodes("MARTIAL_STUDY_BREAKTHROUGH_DAILY")
    assert_loop_bound(nodes, "MJA_MARTIAL_CLAIM_LOOP", 3)
    assert_loop_bound(nodes, "MJA_MARTIAL_STUDY_LOOP", 9)
    assert_loop_bound(nodes, "MJA_MARTIAL_BREAKTHROUGH_LOOP", 3)
    assert_material_guard(nodes, "breakthrough_martial_slot")
    assert_material_guard(nodes, "confirm_martial_breakthrough")
    assert_outcome(nodes, "MJA_MARTIAL_ALL_SLOTS_FULL", "already_complete", "martial.slots_full")
    assert_abort_code(nodes, "MJA_MARTIAL_SLOT_AMBIGUOUS", "MARTIAL_SLOT_STATE_AMBIGUOUS")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k martial -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现武学 Pipeline**

```json
{"task":[{"name":"MARTIAL_STUDY_BREAKTHROUGH_DAILY","label":"武学研习突破","default_check":true,"group":["日常"],"entry":"MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/martial_study_breakthrough_daily.json`; retain its page/slot recognitions, remove central-driver delegation, and implement the bounded flow below.

Navigate panel → martial. Claim up to 3 unique success cards and close each recognized reward. Probe slots 0–2 explicitly; full slots before mutation is `already_complete`. Open an empty plus slot only when its index is unique, then perform study actions up to 9. A breakthrough is allowed only when material name, owned count and required count are independently recognized and owned ≥ required on the same frame; confirm up to 3 only while the same martial/slot context remains. Ordinary insufficient material returns `not_eligible`; no identifiable free slot, conflicting slot evidence, unknown material or missing postcondition Aborts.

- [ ] **Step 4: 运行自动化与单项实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k martial -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-martial-study-daily
python3 tools/mfw_profile.py run --install install/mfw-martial-study-daily --profile-name live-MARTIAL_STUDY_BREAKTHROUGH_DAILY
```

Expected: completed/full, insufficient-material, actionable and ambiguous fixtures partition correctly；live caps 3/9/3 and no breakthrough on unverified material. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_c.py tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY verification/mfw/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json
git commit -m "feat: migrate guarded martial study flow to MFW"
```

### Task 4: 迁移 DUNGEON_SWEEP_DAILY

**Files:**
- Create: `assets/tasks/日常/DUNGEON_SWEEP_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/dungeon_sweep_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_c.py`
- Modify: `tests/fixtures/DUNGEON_SWEEP_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/DUNGEON_SWEEP_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/DUNGEON_SWEEP_DAILY/known_drift.png`
- Create after live run: `verification/mfw/DUNGEON_SWEEP_DAILY.json`

**Interfaces:**
- Consumes: dungeon/Yanwangling/master-sweep templates and policy `副本票: 20`。
- Produces: `MJA_DUNGEON_SWEEP_DAILY_START`; exact action IDs `open_dungeon`, `scroll_dungeon_list`, `select_yanwangling`, `open_sweep_panel`, `select_yanwangling_in_panel`, `select_master_80`, `assign_sweep_ticket`, `start_yanwangling_master_sweep`, `confirm_yanwangling_master_sweep`, `dismiss_sweep_result`, `close_dungeon`。

- [ ] **Step 1: 写票券预算和一次扫荡测试**

```python
def test_dungeon_sweep_preserves_action_and_resource_limits_separately():
    nodes = task_nodes("DUNGEON_SWEEP_DAILY")
    assert_action_limit("DUNGEON_SWEEP_DAILY", "scroll_dungeon_list", 4)
    assert_action_limit("DUNGEON_SWEEP_DAILY", "assign_sweep_ticket", 100)
    assert_resource_guard(nodes, "assign_sweep_ticket", "副本票", 20)
    assert_action_limit("DUNGEON_SWEEP_DAILY", "start_yanwangling_master_sweep", 1)
    assert_no_side_effect_retry(nodes, "start_yanwangling_master_sweep")
    assert_outcome(nodes, "MJA_DUNGEON_NO_TICKET", "not_eligible", "dungeon.ticket_unavailable")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k dungeon -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现副本扫荡 Pipeline**

```json
{"task":[{"name":"DUNGEON_SWEEP_DAILY","label":"副本扫荡","default_check":true,"group":["日常"],"entry":"MJA_DUNGEON_SWEEP_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/dungeon_sweep_daily.json`; retain its Yanwangling/master recognitions, remove central-driver delegation, and implement the guarded flow below.

Navigate/open dungeon, scroll the list no more than the frozen action cap 4 (the expected normal route uses at most 2), select Yanwangling, open sweep panel, select Yanwangling and master-80. Ticket assignment may click the bounded increment control up to action cap 100 but the recognized assigned ticket count and cumulative resource amount must never exceed 20. No ticket or locked master level returns `not_eligible`. Start and confirm one sweep, dismiss one recognized result, and require sweep result/remaining-ticket change before `success`; unknown ticket OCR, >20 assignment, wrong dungeon/difficulty or result ambiguity Aborts.

- [ ] **Step 4: 运行自动化与单项实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k dungeon -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-dungeon-sweep-daily
python3 tools/mfw_profile.py run --install install/mfw-dungeon-sweep-daily --profile-name live-DUNGEON_SWEEP_DAILY
```

Expected: no-ticket is normal not_eligible；live one sweep maximum, assigned ticket ≤20, action increments ≤100, rerun does not replay completed sweep. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/DUNGEON_SWEEP_DAILY.json assets/resource/base/pipeline/daily/dungeon_sweep_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_c.py tests/fixtures/DUNGEON_SWEEP_DAILY verification/mfw/DUNGEON_SWEEP_DAILY.json
git commit -m "feat: migrate guarded dungeon sweep to MFW"
```

### Task 5: 迁移 RING_CHALLENGE_DAILY 并完成完整版预设

**Files:**
- Create: `assets/tasks/日常/RING_CHALLENGE_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/ring_challenge_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_c.py`
- Modify: `tests/test_mfw_presets.py`
- Modify: `tests/fixtures/RING_CHALLENGE_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/RING_CHALLENGE_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/RING_CHALLENGE_DAILY/known_drift.png`
- Create after live run: `verification/mfw/RING_CHALLENGE_DAILY.json`

**Interfaces:**
- Consumes: ring page/score/attempt/sweep templates and `擂台券: 12`。
- Produces: `MJA_RING_CHALLENGE_DAILY_START`; exact action IDs `open_function_panel`, `open_daily_tasks`, `open_ring_challenge`, `close_reward_popup`, `open_ring_attempt_mode`, `fight_ring_opponent`, `skip_ring_battle`, `sweep_ring`, `confirm_ring_sweep`, `dismiss_ring_result`, `close_ring_opponents`, `close_ring_page`; final full preset。

- [ ] **Step 1: 写擂台模式分流和最终预设测试**

```python
def test_ring_uses_one_sweep_for_master_or_5000_else_bounded_fights():
    nodes = task_nodes("RING_CHALLENGE_DAILY")
    assert_condition(nodes, "MJA_RING_SWEEP_ELIGIBLE", "master_mode_or_score_gte_5000")
    assert_resource_guard(nodes, "sweep_ring", "擂台券", 12)
    assert_action_limit("RING_CHALLENGE_DAILY", "sweep_ring", 1)
    assert_loop_bound(nodes, "MJA_RING_FIGHT_LOOP", 12)
    assert_action_limit("RING_CHALLENGE_DAILY", "skip_ring_battle", 12)
    assert_outcome(nodes, "MJA_RING_ATTEMPTS_EXHAUSTED", "already_complete", "ring.attempts_exhausted")
    assert_outcome(nodes, "MJA_RING_NOT_OPEN", "not_eligible", "ring.not_open")


def test_full_preset_is_exact():
    assert preset_ids("日常-完整版") == ["GAME_START", *FINAL_CANONICAL_IDS]
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py -k ring tests/test_mfw_presets.py -q`

Expected: FAIL because task/Pipeline and final full preset are incomplete.

- [ ] **Step 3: 实现擂台 Pipeline 和完整版预设**

```json
{"task":[{"name":"RING_CHALLENGE_DAILY","label":"擂台挑战","default_check":true,"group":["日常"],"entry":"MJA_RING_CHALLENGE_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/ring_challenge_daily.json`; retain its ring state recognitions, remove central-driver delegation, and implement the mode partition below.

Navigate panel → daily → ring. Recognized not-open is `not_eligible`; attempts exhausted/done is `already_complete`. If master mode or independently OCR-verified score ≥5000, open attempt mode and authorize one sweep only when ticket name/count are recognized and amount ≤12; confirm once and require result. Otherwise fight a unique opponent and skip known battle presentation in a max-12 loop; each result must decrement attempts or update score. Terminal attempts exhausted after mutation is `success`; unknown score/mode, duplicate opponent, unresolved result or loop exhaustion Aborts. Set full preset exactly to startup plus all 17 canonical IDs in the design order.

- [ ] **Step 4: 运行批次自动化和擂台实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_c.py tests/test_mfw_presets.py tests/test_mfw_pipeline_contract.py -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-ring-challenge-daily
python3 tools/mfw_profile.py run --install install/mfw-ring-challenge-daily --profile-name live-RING_CHALLENGE_DAILY
```

Expected: not-open/done/sweep/fight/danger fixtures partition correctly；live sweep ≤1 or fight/skip ≤12, ticket ≤12, rerun done/already_complete. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/RING_CHALLENGE_DAILY.json assets/resource/base/pipeline/daily/ring_challenge_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_c.py tests/test_mfw_presets.py tests/fixtures/RING_CHALLENGE_DAILY verification/mfw/RING_CHALLENGE_DAILY.json
git commit -m "feat: migrate ring challenge and complete full preset"
```

### Task 6: 执行 17 项完整版、手工全选和故障隔离验收

**Files:**
- Create after live run: `verification/mfw/full-preset.json`
- Create after live run: `verification/mfw/manual-all.json`
- Create after live run: `verification/mfw/batch-c-sequence.json`
- Create after live run: `verification/mfw/full-business-abort.json`
- Create after live run: `verification/mfw/full-infrastructure-stop.json`
- Modify: `tools/verify_mfw_evidence.py`
- Modify: `tests/test_mfw_evidence.py`

**Interfaces:**
- Consumes: 17 个单项 evidence、完整版 preset 和同一 build metadata。
- Produces: `verify_full_candidate(root)`，是生产切换计划的强制输入。

- [ ] **Step 1: 写重复任务、错误顺序和虚假通过拒绝测试**

```python
def test_full_candidate_rejects_duplicate_or_unexecuted_tasks(tmp_path):
    write_valid_full_candidate(tmp_path)
    append_task(tmp_path / "manual-all.json", "MAIL_REWARD_DAILY")
    with pytest.raises(ValueError, match="exactly once"):
        verify_full_candidate(tmp_path)
    remove_run_id(tmp_path / "SHADOW_RUINS_DAILY.json")
    with pytest.raises(ValueError, match="run_id"):
        verify_full_candidate(tmp_path)
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_evidence.py -q`

Expected: FAIL until full candidate checks are implemented.

- [ ] **Step 3: 实现最终证据检查器**

Require full-preset and manual-all to use identical candidate metadata and list `GAME_START` then the exact 17 canonical IDs once. Require every applicable task to be success/already_complete, every expected ineligible state to include a reason, an injected business Abort to be followed by a successful next task, and separate disconnected-controller run to stop before later tasks. Require first-run and same-day rerun action totals, resource totals and evidence paths. The full-preset run appends a fresh record for all 17 per-task evidence files using `install/mfw-full-candidate`; manual-all appends the same-day rerun record to those files, preserving both histories instead of overwriting the first run. Earlier per-task candidates are development evidence only and cannot satisfy the cutover verifier.

- [ ] **Step 4: 执行同一候选的两种全量入口和故障注入**

Treat the commands below as checkpoints, not one unattended script. After building `mfw-full-candidate`, open it and create `live-full-preset`, `live-manual-all`, and `live-full-infra-stop`; the last profile contains startup, mail, and shop. After deriving `mfw-full-failure-probe`, open only that derived output and create `live-full-business-abort` with business-failure followed by sentinel. Disconnect the configured Android device before the `live-full-infra-stop` run, confirm MFW stops before mail/shop, then restore the device. Never inject probe tasks into production assets or mark the disconnected run passed without its MFW/controller log.

```bash
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-full-candidate
python3 tools/mfw_profile.py run --install install/mfw-full-candidate --profile-name live-full-preset
python3 tools/mfw_profile.py run --install install/mfw-full-candidate --profile-name live-manual-all
python3 tools/mfw_probe_install.py --base install/mfw-full-candidate --output install/mfw-full-failure-probe
python3 tools/mfw_profile.py run --install install/mfw-full-failure-probe --profile-name live-full-business-abort
python3 tools/mfw_profile.py run --install install/mfw-full-candidate --profile-name live-full-infra-stop
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-all-tasks --require-full-preset --require-manual-all
```

Expected: GUI/配置中的手工全选不包含 `daily_all`；两种入口每个业务 ID 一次；17 个单项、full-preset 和 manual-all evidence 全部绑定 `mfw-full-candidate` 的同一 metadata/payload SHA；probe evidence 的 `base_metadata_sha256` 指向该完整候选；任务局部 Abort 继续；Controller 断开停止；第二轮不重复已完成副作用。

- [ ] **Step 5: 提交真实全量候选证据**

```bash
git add tools/verify_mfw_evidence.py tests/test_mfw_evidence.py verification/mfw/full-preset.json verification/mfw/manual-all.json verification/mfw/batch-c-sequence.json verification/mfw/full-business-abort.json verification/mfw/full-infrastructure-stop.json
git commit -m "test: validate full and manual-all MFW execution"
```

### Task 7: 冻结切换候选并运行全量自动化

**Files:**
- Create: `verification/mfw/candidate-summary.json`
- Modify: `docs/mfw-development.md`
- Create: `tests/test_mfw_candidate_summary.py`
- Modify: `tools/verify_mfw_evidence.py`

**Interfaces:**
- Consumes: `verify_full_candidate` 通过的 17 项候选。
- Produces: 切换计划引用的 candidate SHA、commit、MFW/Maa versions 和 evidence manifest。

- [ ] **Step 1: 写候选摘要一致性测试**

```python
def test_candidate_summary_matches_install_metadata():
    summary = load_json("verification/mfw/candidate-summary.json")
    metadata = load_json("install/mfw-full-candidate/build-metadata.json")
    assert summary["build_metadata_sha256"] == sha256_json(metadata)
    assert summary["mja_commit"] == metadata["mja_commit"]
    assert summary["automatic_tests"] == "passed"
    assert summary["android_full_preset"] == "passed"
    assert summary["android_manual_all"] == "passed"
```

- [ ] **Step 2: 运行测试确认摘要缺失**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_candidate_summary.py -q`

Expected: FAIL because `tests/test_mfw_candidate_summary.py` and summary do not exist; create the test above before rerunning.

- [ ] **Step 3: 从已验证证据生成摘要**

Add `tools/verify_mfw_evidence.py --write-summary verification/mfw/candidate-summary.json`; it may write summary only after all required checks pass and must embed evidence file SHA-256 values. It never converts missing/pending evidence to passed.

- [ ] **Step 4: 运行最终迁移候选门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest -q
uv run --no-project --with ruff ruff check .
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-all-tasks --require-full-preset --require-manual-all --write-summary verification/mfw/candidate-summary.json
git diff --check
```

Expected: all PASS；summary hashes match；正式 `assets/interface.json` 仍未修改。

- [ ] **Step 5: 提交候选冻结记录**

```bash
git add verification/mfw/candidate-summary.json docs/mfw-development.md tests/test_mfw_candidate_summary.py tools/verify_mfw_evidence.py
git commit -m "test: freeze validated MFW cutover candidate"
```

## 批次 C 完成门

- [ ] 四个长流程的所有循环上限、胜负分流、资源门禁、未知状态 Abort 自动化均通过。
- [ ] 四个任务完成主页、业务页、已完成/不适用、危险状态和同日重跑实机验收。
- [ ] 完整版和手工全选在同一 candidate 上各执行 17 个业务 ID 一次，没有 `daily_all`。
- [ ] 业务 Abort 继续下一项，Controller 断开停止队列，二者证据不混淆。
- [ ] 候选摘要由验证器生成并绑定 build/evidence SHA，满足后才允许执行生产切换。
