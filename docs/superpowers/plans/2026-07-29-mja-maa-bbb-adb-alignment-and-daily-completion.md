# MJA Maa_bbb ADB Alignment and Daily Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align MJA's Android input path with Maa_bbb's single MAA `Adb` controller model, remove all non-MAA input side channels, and obtain emulator evidence for every remaining Jianzhichuan daily task.

**Status (2026-07-30):** The 17 daily task implementations, pipelines, policies, and automated tests are present. The formal live-verification gate remains open: all 17 records under `verification/tasks/` are still `live_pending`. The latest static/runtime checks pass: `486 passed, 5 skipped`, Ruff clean, install verification clean, and `git diff --check` clean. No commit or push has been performed.

**Architecture:** Recognition, screenshots, and task actions continue through the MAA tasker's Android `Adb` controller, exactly as in Maa_bbb. MaaFramework receives its normal ADB input-method bitmask and automatically selects the first supported ADB-backed implementation for the emulator; MJA does not launch or address MaaTouch/Minitouch separately. The workflow adapter retains bounded current-frame coordinates, but removes its direct `subprocess` ADB side channel and sends every action through the same controller.

**Tech Stack:** Python 3.12, pytest, Ruff, MaaFramework v5.12.2 C++/C API, MaaPiCli, Android SDK ADB, AVD `mja-api35-apis`, package `com.hanjiasongshu.dr22`.

## Global Constraints

- Live Android game input must use only the standard MAA `Adb` controller and its automatic ADB-backed input selection.
- Do not separately launch MaaTouch/Minitouch, use Computer Use, Win32 input, macOS mouse injection, AppleScript, or add a second direct-input path.
- Do not wipe emulator data, uninstall the game, download the game from Google Play, or clear login state.
- The user intervenes only for login or SMS verification; ordinary Android permissions may be accepted automatically.
- `MJA_DISABLE_SAFETY=1` remains required for the already approved stored-凝晶 actions; real-money, recharge, and unknown-resource prompts remain stop conditions.
- Preserve all existing worktree changes and edit only files in this plan.
- A task is not reported successful without a fresh `install/debug/runs/android/<run>/result.json` and matching `install/debug/runs/daily/<run>/result.json`.

---

## File Structure

- `native/maafw-android-cli/patches/0001-plain-adb-defaults.patch`: keeps plain ADB configs usable and restores Maa_bbb-compatible automatic ADB input selection while retaining portable ADB screenshot defaults.
- `agent/workflows/maa_android.py`: maps recognized current-frame targets to generic MAA controller actions; contains no `subprocess` input side channel.
- `tests/test_android_native_patch_bundle.py`: verifies the native patch selects the normal MaaFramework ADB default mask and does not introduce a non-ADB controller.
- `tests/test_maa_android_workflow.py`: verifies special bounded taps and swipes still call the MAA controller.
- `install/MaaPiCli`, `install/libMaaAdbControlUnit.dylib`, `install/runtime/maafw/bin/libMaaAdbControlUnit.dylib`: rebuilt runtime artifacts consumed by the emulator run.
- `install/agent/workflows/maa_android.py`: assembled copy of the verified source adapter.
- `install/debug/runs/android/**/result.json`, `install/debug/runs/daily/**/result.json`: immutable per-run acceptance evidence.

### Task 1: Lock the Single-Controller Contract with Tests

**Files:**
- Modify: `tests/test_android_native_patch_bundle.py`
- Modify: `tests/test_maa_android_workflow.py`

**Interfaces:**
- Consumes: `MaaAndroidWorkflowDriver.execute(intent)` and MaaFramework's ADB controller defaults.
- Produces: regression tests proving special navigation actions call `controller.post_click` / `controller.post_swipe` and the adapter has no direct input side channel.

- [x] **Step 1: Change the native patch assertion to the exact backend**

```python
assert "adb_param.input = MaaAdbInputMethod_Default;" in patch
assert "MaaAdbInputMethod_AdbShell" not in patch
```

- [x] **Step 2: Extend the fake controller with swipe recording**

```python
def post_swipe(self, x1, y1, x2, y2, duration):
    self.swipes.append((x1, y1, x2, y2, duration))
    return Job(None)
```

- [x] **Step 3: Replace `_adb_tap` monkeypatch expectations with controller-call assertions**

```python
driver.execute(ActionIntent("open_yanwu_currency_purchase", "page", "target"))
assert context.tasker.controller.clicks == [(1095, 42)]
```

- [x] **Step 4: Add a no-side-channel source assertion**

```python
source = Path("agent/workflows/maa_android.py").read_text(encoding="utf-8")
assert '"shell", "input"' not in source
assert "subprocess.run" not in source
```

- [ ] **Step 5: Run the focused tests and confirm they fail before implementation**

Run:

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_android_native_patch_bundle.py \
  tests/test_maa_android_workflow.py \
  tests/test_workflow_input.py
```

Expected: failures identify `MaaAdbInputMethod_Default`, `_adb_tap` / `_adb_swipe`, or missing fake-controller swipe support.

### Task 2: Route Every Workflow Action Through the Maa_bbb-Style MAA ADB Controller

**Files:**
- Modify: `agent/workflows/maa_android.py`
- Modify: `native/maafw-android-cli/patches/0001-plain-adb-defaults.patch`

**Interfaces:**
- Consumes: `AndroidWorkflowDriver.click(box, frame_size=...)` and `AndroidWorkflowDriver.swipe(start_box, end_box, duration_ms=..., frame_size=...)`.
- Produces: `MaaAndroidWorkflowDriver` with one controller path and a patched MaaPiCli that uses MaaFramework's normal automatic ADB input mask.

- [x] **Step 1: Replace direct ADB tap helpers with the generic controller gesture**

```python
def _controller_tap(self, box: tuple[int, int, int, int]) -> None:
    self.gestures.click(box, frame_size=(1280, 720))
```

- [x] **Step 2: Replace direct ADB swipe helpers with the generic controller gesture**

```python
def _controller_swipe(
    self,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    duration_ms: int,
) -> None:
    self.gestures.swipe(
        (*start, 1, 1),
        (*end, 1, 1),
        duration_ms=duration_ms,
        frame_size=(1280, 720),
    )
```

- [x] **Step 3: Update every special action branch and boundary cleanup call site**

All former `_adb_tap(...)` calls become `_controller_tap(...)`; the dungeon list's `_adb_swipe(...)` call becomes `_controller_swipe(...)`. Remove the direct-input helper implementation and the unused `subprocess` import. Keep current-frame recognition, finite action caps, approved-resource checks, and settle windows unchanged.

- [x] **Step 4: Keep MaaFramework's automatic ADB input selection**

```cpp
if (adb_param.input == MaaAdbInputMethod_None) {
    adb_param.input = MaaAdbInputMethod_Default;
}
```

Keep the existing `config = "{}"` and portable ADB screenshot fallback. The patch must not create a Win32, Computer Use, macOS, or separately launched touch controller; the default ADB bitmask is intentionally passed to MaaFramework so it can choose the supported ADB-backed implementation like Maa_bbb.

- [x] **Step 5: Run the focused tests**

Run the Task 1 pytest command.

Expected: all focused tests pass.

- [ ] **Step 6: Commit the source-level controller alignment**

```bash
git add -- agent/workflows/maa_android.py \
  native/maafw-android-cli/patches/0001-plain-adb-defaults.patch \
  tests/test_android_native_patch_bundle.py \
  tests/test_maa_android_workflow.py
git commit -m "fix: unify android input on the adb controller"
```

Only perform this scoped commit after tests pass; do not stage unrelated dirty files.

### Task 3: Rebuild, Assemble, and Verify the Runtime

**Files:**
- Replace through the build script: `install/MaaPiCli`
- Replace through the build script: `install/libMaaAdbControlUnit.dylib`
- Replace through the build script: `install/runtime/maafw/bin/libMaaAdbControlUnit.dylib`
- Sync from source: `install/agent/workflows/maa_android.py`

**Interfaces:**
- Consumes: pinned MaaFramework tag `v5.12.2`, commit `f625a60edeccd4549f9a71c0f74628d827ade8fb`, official MaaFramework binary directory, and the patch from Task 2.
- Produces: an attested macOS arm64 MaaPiCli and Android control-unit library used by `tools/android_run.sh`.

- [ ] **Step 1: Obtain an exact clean upstream checkout in a temporary directory**

```bash
git clone --branch v5.12.2 --depth 1 \
  https://github.com/MaaXYZ/MaaFramework.git \
  /tmp/mja-maafw-v5.12.2
git -C /tmp/mja-maafw-v5.12.2 rev-parse HEAD
```

Expected commit: `f625a60edeccd4549f9a71c0f74628d827ade8fb`.

- [ ] **Step 2: Build and atomically install the patched CLI and ADB library**

```bash
native/maafw-android-cli/build.sh \
  --source /tmp/mja-maafw-v5.12.2 \
  --official-bin install/runtime/maafw/bin \
  --output install
```

Expected: `built and attested .../install/MaaPiCli` and a new `install/MaaPiCli.android.manifest.json` matching the current patch digest.

- [ ] **Step 3: Synchronize the Python adapter into the assembled runtime**

```bash
rsync -a agent/workflows/maa_android.py install/agent/workflows/maa_android.py
```

- [x] **Step 4: Run static and assembled-install verification**

```bash
./install/.venv/bin/python -m pytest -q
./install/.venv/bin/python -m ruff check agent tools tests
./install/.venv/bin/python -m tools.verify_install install
git diff --check
```

Expected: all tests, Ruff, assembled-install verification, and whitespace checks pass.

- [ ] **Step 5: Confirm the runtime log uses the standard MAA ADB controller**

Run a non-consumptive already-complete workflow and inspect only the newly appended `maafw.log` segment. It must show an `AdbControlUnit` controller and MAA controller post actions; no Computer Use, Win32, macOS, or direct adapter `subprocess` input may appear. The selected ADB-backed implementation may be MaaTouch/Minitouch when MaaFramework's automatic probe finds it, as it does in the Maa_bbb model.

### Task 4: Calibrate the Yanwu Selector with Maa_bbb-Style ADB Gestures

**Files:**
- Modify only if calibration proves necessary: `agent/workflows/maa_android.py`
- Modify corresponding tests: `tests/test_maa_android_workflow.py`
- Sync after any fix: `install/agent/workflows/maa_android.py`

**Interfaces:**
- Consumes: recognized `painting_scroll.page`, bounded Yanwu row `(100, 130, 200, 75)`, and the single MaaFramework ADB controller.
- Produces: a verified transition from 云州 painting scroll to the distinct 偃武 page before any currency action is authorized.

- [ ] **Step 1: Capture the current painting-scroll frame through ADB/MAA without input**

Save the frame under `install/debug/manual/` and verify it is 1280x720.

- [ ] **Step 2: Try a normal controller click at the bounded Yanwu row center**

Expected state delta: the regional page changes and the distinct 偃武 map marker is recognized.

- [ ] **Step 3: If normal click does not transition, try one bounded MAA-controller long press**

Use the same row center with 300 ms, then 600 ms through `controller.post_long_press` / the adapter gesture wrapper. Each attempt must be followed by a fresh MAA ADB screenshot; do not click a currency control until the 偃武 page marker is present.

- [ ] **Step 4: Encode only the first verified gesture**

If a long press is required, change the `select_yanwu_world` branch to `self.gestures.long_press(...)`, add a unit assertion for its duration, rerun focused tests, and resync the assembled adapter.

### Task 5: Complete and Verify Condensate Spending

**Files:**
- Evidence only: `install/debug/runs/android/**/result.json`
- Evidence only: `install/debug/runs/daily/**/result.json`
- Failure evidence when applicable: `install/debug/runs/daily/**/{before,after}.png`

**Interfaces:**
- Consumes: the verified Yanwu transition from Task 4 and approved `MJA_DISABLE_SAFETY=1` stored-凝晶 policy.
- Produces: fresh `SPEND_CONDENSATE_DAILY` success evidence without page fabrication.

- [ ] **Step 1: Run the task**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task spend_condensate_daily
```

- [ ] **Step 2: Verify the result contract**

The Android wrapper result must be `succeeded`; the daily result must be `completed` or `already_complete`; the action trace must show the Yanwu transition before its currency purchase and the Yunzhou transition before its purchase.

- [ ] **Step 3: On failure, use the saved before/after frames and new log segment**

Fix only the failed recognition or bounded controller gesture, add a regression test, resync, and rerun the same task until it succeeds or encounters a genuine login/recharge/unknown-resource stop condition.

### Task 6: Verify Every Remaining Daily Task in Dependency Order

**Files:**
- Modify only when a reproducible task defect is found: relevant `agent/workflows/definitions/*.py`, `agent/workflows/maa_android.py`, resource pipeline JSON/image, and matching tests.
- Evidence: fresh Android and daily result JSON for each task.

**Interfaces:**
- Consumes: the single MaaFramework ADB controller and prior successful task state.
- Produces: one fresh terminal result for every remaining task, with battle pass last.

- [ ] **Step 1: Run martial study breakthrough**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task martial_study_breakthrough_daily
```

- [ ] **Step 2: Run stamina food**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task eat_stamina_food_daily
```

- [ ] **Step 3: Reverify dungeon sweep after the controller change**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task dungeon_sweep_daily
```

- [ ] **Step 4: Run Jianlin condensate stamina spending**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task jianlin_resource_condensate_stamina_daily
```

- [ ] **Step 5: Reverify ring challenge after the controller change**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task ring_challenge_daily
```

- [ ] **Step 6: Claim all newly available daily rewards**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task daily_task_reward_claim_daily
```

- [ ] **Step 7: Run battle pass last**

```bash
MJA_DISABLE_SAFETY=1 ./tools/android_run.sh --task battle_pass_reward_daily
```

For every step, inspect the newest wrapper and daily `result.json`. If a task fails, preserve its frames/logs, add the smallest regression test and fix, rerun unit/static verification, resync the assembled files, and rerun that same task before continuing. Login or SMS verification is the only expected user handoff.

### Task 7: Final Acceptance and Evidence Matrix

**Files:**
- Modify: this plan's checkboxes
- Read: all fresh `install/debug/runs/android/**/result.json`
- Read: all fresh `install/debug/runs/daily/**/result.json`

**Interfaces:**
- Consumes: Tasks 1-6 results.
- Produces: a final status matrix that distinguishes `completed`, `already_complete`, `failed`, and genuine blockers.

- [x] **Step 1: Rerun the complete automated verification suite**

```bash
./install/.venv/bin/python -m pytest -q
./install/.venv/bin/python -m ruff check agent tools tests
./install/.venv/bin/python -m tools.verify_install install
git diff --check
```

- [ ] **Step 2: Verify input-path evidence**

Confirm the current patch uses `MaaAdbInputMethod_Default`, `agent/workflows/maa_android.py` contains no direct `subprocess` input, and the new Maa log segment contains only the MAA Android controller path.

- [ ] **Step 3: Build the final table**

Include task ID, fresh status, Android result path, daily result path, and any non-success reason. Do not claim all tasks run successfully unless every listed task has fresh success evidence.
