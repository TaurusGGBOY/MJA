# MJA Maa_bbb Display and Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align MJA with Maa_bbb's stable runtime contract—fixed 16:9 geometry, deterministic foreground lifecycle, and one consistent template/ROI coordinate system—while retaining the macOS-native controller required by the iOS-on-Mac game.

**Architecture:** Add one shared macOS display-contract module used by window preparation, click mapping, capture tooling, and install verification. Window preparation will attempt to resize the game to exactly 1280×720, then fail before controller creation if the window does not honor that contract; templates and pipeline ROIs will remain in the same 1280×720 coordinate system. The CLI and AgentServer will continue sharing the persisted window identity and will always restore the original window state.

**Tech Stack:** Python 3.14, PyObjC/AppKit/Quartz, MaaFramework v5.12.2, Pillow, pytest, Ruff, MFAAvalonia.

## Global Constraints

- The supported MJA display contract is exactly `1280×720` with a 16:9 aspect ratio.
- The game window must be prepared and verified before Maa creates a task controller.
- A resize/readback mismatch is a safe failure; the pipeline must never run against an uncalibrated geometry.
- Template image dimensions and TemplateMatch ROIs must be compatible with the same capture contract.
- macOS permissions remain explicit and are the only user-operated step.
- Window identity is validated by both `window_id` and `pid` before clicks or restoration.
- No standard absolute-coordinate click or unknown-screen recovery is introduced.

## Files and Responsibilities

- Create `agent/macos/display_contract.py` for the shared 1280×720 contract and validation errors.
- Modify `agent/errors.py` to expose a stable display-contract failure code.
- Modify `agent/macos/window_lifecycle.py` to enforce exact geometry after Accessibility resize and before task execution.
- Modify `agent/actions/macos_foreground_click.py` to validate the same contract before mapping a recognition box.
- Modify `tools/capture_templates.py` to capture only the canonical contract by default and stop projecting legacy coordinates into an incompatible frame.
- Modify `assets/resource/calibration.json` and `assets/resource/pipeline/mail_smoke_test.json` to restore the canonical 1280×720 resource contract.
- Restore the seven mail-smoke PNGs to their 1280×720 legacy-contract dimensions until a valid live UI capture is available.
- Modify `tools/verify_install.py` to reject template/ROI and calibration mismatches during installation verification.
- Extend `tests/test_window_lifecycle.py`, `tests/test_macos_foreground_click.py`, `tests/test_capture_templates.py`, and `tests/test_verify_install.py` for strict geometry and resource checks.
- Update `docs/testing/macos-mail-smoke-test.md` with the new preflight and failure meaning.

### Task 1: Add the shared display contract

**Files:**
- Create: `agent/macos/display_contract.py`
- Modify: `agent/errors.py`
- Test: `tests/test_display_contract.py`

**Interfaces:**
- Produces `MJA_DISPLAY_CONTRACT`, `DisplayContract`, `DisplayContractError`, `validate_window_size()`, and `validate_capture_size()`.
- `MJA_DISPLAY_CONTRACT.window_size == (1280, 720)` and `.capture_size == (1280, 720)`.

- [ ] Write tests for accepting 1280×720 and rejecting 1051×820, 923×720, zero, negative, and malformed sizes.
- [ ] Run `install/.venv/bin/python -m pytest -q tests/test_display_contract.py` and verify the new tests fail before implementation.
- [ ] Implement the immutable contract and strict size validators with actionable error messages.
- [ ] Add `DISPLAY_CONTRACT_MISMATCH` to `ErrorCode` and map contract failures to `MJAError` at lifecycle boundaries.
- [ ] Run the focused tests and Ruff.

### Task 2: Enforce geometry before controller creation

**Files:**
- Modify: `agent/macos/window_lifecycle.py`
- Test: `tests/test_window_lifecycle.py`

**Interfaces:**
- `WindowLifecycle.prepare()` must return a window whose bounds are exactly `(1280, 720)` or raise `MJAError(ErrorCode.DISPLAY_CONTRACT_MISMATCH, ...)`.
- `WindowLifecycle.restore()` keeps restoring the persisted original bounds and frontmost application.

- [ ] Add a test where the backend ignores the resize request and assert the new stable error code, pending restore state, and no prepared window.
- [ ] Add a test where the backend returns 1280×720 and assert activation, readback, and persistence order remain unchanged.
- [ ] Implement strict post-resize validation; remove the old behavior that accepted the original noncanonical bounds as a successful preparation.
- [ ] Run `install/.venv/bin/python -m pytest -q tests/test_window_lifecycle.py` and verify all lifecycle tests pass.

### Task 3: Align click mapping and capture tooling

**Files:**
- Modify: `agent/actions/macos_foreground_click.py`
- Modify: `tools/capture_templates.py`
- Test: `tests/test_macos_foreground_click.py`
- Test: `tests/test_capture_templates.py`

**Interfaces:**
- `map_box_center()` accepts only a capture size and window size matching `MJA_DISPLAY_CONTRACT`.
- `capture_profile()` writes crops in the same canonical coordinate system and does not silently scale a noncanonical live frame.

- [ ] Replace the observed 923×720 success test with a rejection test and add a canonical 1280×720 mapping test.
- [ ] Add a capture-tool test that rejects `OBSERVED_IOS_CALIBRATION` for the canonical profile instead of projecting its ROIs.
- [ ] Implement contract validation before any activation or `cliclick` invocation.
- [ ] Remove `_crops_for_calibration()`'s implicit x-only projection from the canonical capture path; keep explicit source-size validation.
- [ ] Run both focused test files and Ruff.

### Task 4: Restore and verify canonical resources

**Files:**
- Modify: `assets/resource/calibration.json`
- Modify: `assets/resource/pipeline/mail_smoke_test.json`
- Restore: `assets/resource/image/home/*.png`, `assets/resource/image/panel/*.png`, `assets/resource/image/mail/*.png`
- Modify: `tools/verify_install.py`
- Test: `tests/test_verify_install.py`

**Interfaces:**
- `verify_install()` reports a clear error when calibration is not 1280×720, a referenced template is larger than its ROI, or a ROI is outside 1280×720.

- [ ] Add a temporary-install test with a too-small ROI/template mismatch and assert the error names the pipeline node and image.
- [ ] Restore the seven tracked PNGs from the pre-alignment 1280×720 contract commit, set calibration profile to `true_1280_legacy_assets`, and restore all pipeline ROIs to 1280 coordinates.
- [ ] Implement static template/ROI validation using Pillow and the canonical calibration size.
- [ ] Run `install/.venv/bin/python -m pytest -q tests/test_verify_install.py` and `install/.venv/bin/python -m tools.verify_install install`.

### Task 5: Document and verify the operator workflow

**Files:**
- Modify: `docs/testing/macos-mail-smoke-test.md`
- Test: `tests/test_project_contract.py`

**Interfaces:**
- Documentation must state that a non-16:9 or non-1280×720 window is a preflight failure, not a reason to lower recognition thresholds.

- [ ] Add documentation for checking `agent.pretask`, the window bounds, and the display-contract error before running MaaPiCli.
- [ ] Add a project-contract assertion that the canonical calibration and pipeline are present.
- [ ] Run the complete test suite, Ruff, setup, install verification, and a read-only 50-frame controller probe.
- [ ] Run the CLI smoke task once and confirm it fails safely before any click when the current game window refuses the canonical resize.
- [ ] Commit the implementation, push a new branch, and open a PR against `main`.

## Final Verification Commands

```bash
install/.venv/bin/python -m pytest -q
install/.venv/bin/ruff check .
install/.venv/bin/python -m tools.setup --root .
install/.venv/bin/python -m tools.verify_install install
install/.venv/bin/python -m tools.verify_macos_controller --window-id <prepared-window-id> --frames 50 --evidence-root diagnostics/controller-probe/aligned
install/.venv/bin/python -m tools.run_cli --install-root install
```

## Acceptance Criteria

- The runtime never starts a task with a 1051×820 or 923×720 display contract.
- A refused Accessibility resize produces a stable, diagnosable preflight failure and leaves a recoverable restore snapshot.
- Every pipeline template and ROI is valid in one 1280×720 coordinate system.
- The controller probe still captures 50 nonempty frames when permissions and a valid window are available.
- Existing window restore and child-process state rehydration tests remain green.
- The new branch is pushed and its PR targets the already-merged `main`.
