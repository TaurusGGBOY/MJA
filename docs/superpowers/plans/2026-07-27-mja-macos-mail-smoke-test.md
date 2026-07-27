# MJA macOS Mail Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible ProjectInterface V2 project that MFAAvalonia can use to launch/activate the local game, open and close the mail page without claiming anything, positively verify the return to the home UI, and restore the original macOS window state.

**Architecture:** Keep MaaFramework and MFAAvalonia as pinned downloaded runtimes. Project-owned Python modules perform permission checks, macOS window lifecycle management, diagnostics, and the custom `MacOSForegroundClick` Maa Agent action. ProjectInterface and pipeline JSON remain declarative and contain exactly four input-producing nodes—open panel, open mail, close mail, close panel—each gated by successful template recognition.

**Tech Stack:** Python 3.14.6, MaaFw 5.12.2, PyObjC 12.2.1, Pillow 12.1.1, pytest 9.1.1, Ruff 0.16.0, MaaFramework 5.12.2 macOS arm64, MFAAvalonia 2.13.0-beta.5 osx-arm64, `/opt/homebrew/bin/cliclick` 5.1.

**Global Constraints:** Run attended and foreground-only on the current Apple Silicon Mac. Never click a claim/reward control, never use guessed coordinates, never recover unknown screens, never modify either upstream project, and never commit downloaded runtimes, virtual environments, live screenshots, logs, state files, or MFA user configuration. Every task follows red-green-refactor and ends with the named focused test plus the full test suite. The approved design's “two input nodes” count is corrected here to four because verified game navigation requires opening and closing the enclosing function panel to return to the main UI.

**Approved Specification:** `docs/superpowers/specs/2026-07-27-mja-macos-mail-smoke-test-design.md`

## Planned File Structure

```text
MJA/
├── pyproject.toml                         # Python metadata, pytest and Ruff policy
├── requirements.lock                     # Exact Python runtime/test dependencies
├── runtime-manifest.json                 # Runtime URLs, sizes and official SHA-256 digests
├── .gitignore                            # Excludes generated/local runtime data
├── assets/
│   ├── interface.json                    # PI V2 controller/resource/task/agent declaration
│   └── resource/
│       ├── pipeline/mail_smoke_test.json # Recognition-only state machine and four custom actions
│       └── image/
│           ├── home/home_marker.png      # Stable home-state marker
│           ├── home/panel_open.png       # Function-panel open target
│           ├── panel/panel_marker.png    # Stable function-panel marker
│           ├── panel/mail_entry.png      # Mail entry target
│           ├── panel/panel_close.png     # Function-panel close target
│           ├── mail/mail_marker.png      # Stable mail-page marker
│           └── mail/mail_close.png       # Mail close target
├── agent/
│   ├── __init__.py
│   ├── main.py                           # AgentServer entry and registration imports
│   ├── pretask.py                        # GUI pretask command
│   ├── errors.py                         # Stable error code enum and domain exception
│   ├── diagnostics.py                    # Per-run JSON/log/screenshot metadata
│   ├── actions/
│   │   ├── __init__.py
│   │   └── macos_foreground_click.py     # Box validation, coordinate mapping and cliclick call
│   ├── macos/
│   │   ├── __init__.py
│   │   ├── permissions.py                # Screen-recording/accessibility checks
│   │   ├── window_state.py               # Typed snapshots and atomic state persistence
│   │   └── window_lifecycle.py           # Discovery, activation, resize and idempotent restore
│   └── sinks/
│       ├── __init__.py
│       └── restore_window.py              # Task terminal-event restoration
├── tools/
│   ├── __init__.py
│   ├── setup.py                           # Idempotent download/verify/assemble command
│   ├── configure_mfa.py                   # Safe MFA instance configuration patcher
│   ├── capture_templates.py               # Controlled live fixture/template capture utility
│   ├── run_cli.py                         # MaaPiCli lifecycle wrapper
│   └── verify_install.py                  # Static and assembled-install verifier
├── tests/
│   ├── test_diagnostics.py
│   ├── test_permissions.py
│   ├── test_window_state.py
│   ├── test_window_lifecycle.py
│   ├── test_macos_foreground_click.py
│   ├── test_restore_window_sink.py
│   ├── test_project_interface.py
│   ├── test_capture_templates.py
│   ├── test_setup.py
│   ├── test_configure_mfa.py
│   ├── test_run_cli.py
│   └── test_verify_install.py
└── docs/testing/macos-mail-smoke-test.md   # Attended capture and three-run acceptance runbook
```

## Task 1: Establish the Python Project and Pinned Runtime Contract

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.lock`
- Create: `runtime-manifest.json`
- Create: `agent/__init__.py`
- Create: `agent/actions/__init__.py`
- Create: `agent/macos/__init__.py`
- Create: `agent/sinks/__init__.py`
- Create: `tools/__init__.py`
- Modify: `.gitignore`
- Test: `tests/test_project_contract.py`

- [ ] **Step 1: Write the failing repository-contract test**

```python
# tests/test_project_contract.py
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_pinned_contract_and_ignored_runtime_paths() -> None:
    requirements = (ROOT / "requirements.lock").read_text()
    assert requirements.splitlines() == [
        "MaaFw==5.12.2",
        "Pillow==12.1.1",
        "pyobjc-core==12.2.1",
        "pyobjc-framework-Cocoa==12.2.1",
        "pyobjc-framework-Quartz==12.2.1",
        "pytest==9.1.1",
        "ruff==0.16.0",
    ]
    manifest = json.loads((ROOT / "runtime-manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert {item["id"] for item in manifest["artifacts"]} == {"maafw", "mfa"}
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for path in (".venv/", "install/", "downloads/", "debug/", ".mja-state/"):
        assert path in ignored
```

- [ ] **Step 2: Run the test and confirm it fails because the contract files do not exist**

Run: `python3 -m pytest tests/test_project_contract.py -q`

Expected: `FAILED` with `FileNotFoundError: requirements.lock`.

- [ ] **Step 3: Add exact Python and runtime pins**

Create `requirements.lock` with the seven lines asserted above. Create this manifest exactly:

```json
{
  "schema_version": 1,
  "artifacts": [
    {
      "id": "maafw",
      "version": "5.12.2",
      "filename": "MAA-macos-aarch64-v5.12.2.zip",
      "size": 24888096,
      "sha256": "67c05e2b34e77017a79a6e252ccc9fab701eddb1a579bc17cc40a2931f08c87e",
      "url": "https://github.com/MaaXYZ/MaaFramework/releases/download/v5.12.2/MAA-macos-aarch64-v5.12.2.zip"
    },
    {
      "id": "mfa",
      "version": "2.13.0-beta.5",
      "filename": "MFAAvalonia-v2.13.0-beta.5-osx-arm64.tar.gz",
      "size": 87343871,
      "sha256": "ba9618ff6404d7468e146bab45b74f0ee48bbfc28d0c15cb056676e4c2593a93",
      "url": "https://github.com/MaaXYZ/MFAAvalonia/releases/download/v2.13.0-beta.5/MFAAvalonia-v2.13.0-beta.5-osx-arm64.tar.gz"
    }
  ]
}
```

Add `[project]` with `requires-python = ">=3.14,<3.15"`, `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, and Ruff line length 100 to `pyproject.toml`. Add the generated paths asserted by the test to `.gitignore` without removing existing entries.

- [ ] **Step 4: Create the project venv, install the lock, create package markers, and run quality checks**

Run: `python3 -m venv install/.venv && install/.venv/bin/python -m pip install -r requirements.lock && install/.venv/bin/python -m pytest tests/test_project_contract.py -q && install/.venv/bin/python -m ruff check tests/test_project_contract.py`

Expected: `1 passed`; Ruff prints `All checks passed!`.

- [ ] **Step 5: Run the full suite and commit**

Run: `install/.venv/bin/python -m pytest -q`

Expected: all tests pass.

```bash
git add pyproject.toml requirements.lock runtime-manifest.json .gitignore agent tools tests/test_project_contract.py
git commit -m "build: pin Python and macOS runtimes"
```

## Task 2: Implement Stable Errors and Per-Run Diagnostics

**Files:**
- Create: `agent/errors.py`
- Create: `agent/diagnostics.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Write failing tests for stable codes and atomic run metadata**

```python
# tests/test_diagnostics.py
import json
from agent.diagnostics import RunDiagnostics
from agent.errors import ErrorCode, MJAError


def test_failure_is_written_with_stable_code(tmp_path) -> None:
    run = RunDiagnostics.create(tmp_path, now=lambda: "20260727T120000.000000+0800")
    run.record_component("maafw", "5.12.2")
    run.record_window(window_id=41, pid=902, screenshot_size=(1280, 720))
    run.fail(MJAError(ErrorCode.MAIL_OPEN_TIMEOUT, "mail marker not found"))
    payload = json.loads((run.directory / "run.json").read_text())
    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "MAIL_OPEN_TIMEOUT",
        "message": "mail marker not found",
    }
    assert not list(tmp_path.rglob("*.tmp"))
```

- [ ] **Step 2: Run and observe the missing-module failure**

Run: `install/.venv/bin/python -m pytest tests/test_diagnostics.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'agent.diagnostics'`.

- [ ] **Step 3: Implement the error model**

```python
# agent/errors.py
from enum import StrEnum


class ErrorCode(StrEnum):
    PERMISSION_SCREEN_CAPTURE = "PERMISSION_SCREEN_CAPTURE"
    PERMISSION_ACCESSIBILITY = "PERMISSION_ACCESSIBILITY"
    APP_LAUNCH_TIMEOUT = "APP_LAUNCH_TIMEOUT"
    WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"
    WINDOW_RESIZE_FAILED = "WINDOW_RESIZE_FAILED"
    CONTROLLER_CONNECT_FAILED = "CONTROLLER_CONNECT_FAILED"
    HOME_RECOGNITION_TIMEOUT = "HOME_RECOGNITION_TIMEOUT"
    MAIL_OPEN_TIMEOUT = "MAIL_OPEN_TIMEOUT"
    HOME_RETURN_TIMEOUT = "HOME_RETURN_TIMEOUT"
    WINDOW_RESTORE_FAILED = "WINDOW_RESTORE_FAILED"


class MJAError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
```

- [ ] **Step 4: Implement atomic diagnostics writes**

`RunDiagnostics.create()` must create a directory under `debug/runs/` named with the injected ISO-like timestamp, initialize `run.json`, configure a UTF-8 rotating file handler at `agent.log`, and expose `record_component`, `record_window`, `event`, `succeed`, and `fail`. Every mutation updates an in-memory dictionary and writes JSON to a sibling `.tmp` before `Path.replace()`. `event()` appends a dictionary containing `name`, `monotonic_ms`, and `details`. Do not serialize environment variables, command lines, usernames, or account identifiers.

- [ ] **Step 5: Verify focused and full tests, then commit**

Run: `install/.venv/bin/python -m pytest tests/test_diagnostics.py -q && install/.venv/bin/python -m pytest -q`

Expected: focused test and full suite pass.

```bash
git add agent/errors.py agent/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add stable diagnostics model"
```

## Task 3: Model Permissions and Persist Window State Safely

**Files:**
- Create: `agent/macos/permissions.py`
- Create: `agent/macos/window_state.py`
- Test: `tests/test_permissions.py`
- Test: `tests/test_window_state.py`

- [ ] **Step 1: Write failing permission mapping tests using injected system probes**

```python
# tests/test_permissions.py
import pytest
from agent.errors import ErrorCode, MJAError
from agent.macos.permissions import ensure_permissions


@pytest.mark.parametrize(
    ("screen", "accessibility", "code"),
    [
        (False, True, ErrorCode.PERMISSION_SCREEN_CAPTURE),
        (True, False, ErrorCode.PERMISSION_ACCESSIBILITY),
    ],
)
def test_missing_permission_fails_before_window_work(screen, accessibility, code) -> None:
    with pytest.raises(MJAError) as caught:
        ensure_permissions(lambda: screen, lambda: accessibility)
    assert caught.value.code == code


def test_both_permissions_pass() -> None:
    ensure_permissions(lambda: True, lambda: True)
```

- [ ] **Step 2: Write failing round-trip and corruption tests for window state**

```python
# tests/test_window_state.py
import pytest
from agent.macos.window_state import Bounds, WindowSnapshot, WindowStateStore


def test_state_round_trip_and_consumed_marker(tmp_path) -> None:
    store = WindowStateStore(tmp_path / "window.json")
    snapshot = WindowSnapshot(41, 902, Bounds(10, 20, 1280, 720), "com.apple.Terminal")
    store.save(snapshot)
    assert store.load_pending() == snapshot
    store.mark_restored()
    assert store.load_pending() is None


def test_partial_json_is_rejected(tmp_path) -> None:
    path = tmp_path / "window.json"
    path.write_text('{"window_id":')
    with pytest.raises(ValueError, match="invalid window state"):
        WindowStateStore(path).load_pending()
```

- [ ] **Step 3: Run both files and confirm imports fail**

Run: `install/.venv/bin/python -m pytest tests/test_permissions.py tests/test_window_state.py -q`

Expected: collection errors for the two missing modules.

- [ ] **Step 4: Implement pure permission mapping and production probes**

`ensure_permissions(screen_probe=CGPreflightScreenCaptureAccess, accessibility_probe=AXIsProcessTrusted)` checks screen capture first, accessibility second, and raises the exact `MJAError`. Add `request_permissions()` only for the explicit `--request-permissions` CLI path; it may call `CGRequestScreenCaptureAccess()` and `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})`, but normal task execution must never trigger system prompts.

- [ ] **Step 5: Implement typed, versioned, atomic state storage**

```python
# public surface of agent/macos/window_state.py
@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowSnapshot:
    window_id: int
    pid: int
    bounds: Bounds
    previous_frontmost_bundle_id: str | None
```

`WindowStateStore` exposes `save(snapshot) -> None`, `load_pending() -> WindowSnapshot | None`, and `mark_restored() -> None`. The JSON has top-level keys `schema_version`, `restored`, and `snapshot`, with schema version 1 and a complete serialized `WindowSnapshot`. Validate exact integer bounds greater than zero and reject unknown schema versions. Use `.tmp` plus `replace()` for `save()` and `mark_restored()`.

- [ ] **Step 6: Verify and commit**

Run: `install/.venv/bin/python -m pytest tests/test_permissions.py tests/test_window_state.py -q && install/.venv/bin/python -m pytest -q`

Expected: all tests pass.

```bash
git add agent/macos/permissions.py agent/macos/window_state.py tests/test_permissions.py tests/test_window_state.py
git commit -m "feat: persist guarded macOS window state"
```

## Task 4: Implement Window Discovery, Normalization, and Idempotent Restore

**Files:**
- Create: `agent/macos/window_lifecycle.py`
- Create: `agent/pretask.py`
- Test: `tests/test_window_lifecycle.py`
- Test: `tests/test_pretask.py`

- [ ] **Step 1: Write a fake backend and failing lifecycle test**

```python
# tests/test_window_lifecycle.py
from agent.macos.window_lifecycle import GameWindow, WindowLifecycle
from agent.macos.window_state import Bounds, WindowStateStore


class FakeBackend:
    def __init__(self) -> None:
        self.window = GameWindow(41, 902, "对决！剑之川", Bounds(10, 20, 1366, 1024))
        self.calls: list[tuple] = []

    def find_window(self, title, deadline):
        self.calls.append(("find", title))
        return self.window

    def frontmost_bundle_id(self): return "com.apple.Terminal"
    def game_process_running(self): return True
    def activate_pid(self, pid): self.calls.append(("activate", pid))
    def set_bounds(self, window, bounds):
        self.calls.append(("set_bounds", bounds))
        self.window = GameWindow(window.window_id, window.pid, window.title, bounds)
    def read_window(self, window_id, pid): return self.window
    def activate_bundle(self, bundle): self.calls.append(("restore_frontmost", bundle))


def test_prepare_saves_before_resize_and_restore_is_idempotent(tmp_path) -> None:
    backend = FakeBackend()
    store = WindowStateStore(tmp_path / "window.json")
    lifecycle = WindowLifecycle(backend, store)
    prepared = lifecycle.prepare(timeout_seconds=60)
    assert prepared.bounds == Bounds(10, 20, 1280, 720)
    assert backend.calls[:3] == [
        ("find", "对决！剑之川"),
        ("activate", 902),
        ("set_bounds", Bounds(10, 20, 1280, 720)),
    ]
    lifecycle.restore()
    lifecycle.restore()
    assert backend.calls.count(("set_bounds", Bounds(10, 20, 1366, 1024))) == 1
```

- [ ] **Step 2: Write a failing pretask stale-state recovery test**

```python
# tests/test_pretask.py
def test_pretask_restores_stale_state_before_new_prepare(monkeypatch) -> None:
    calls = []
    lifecycle = type("L", (), {
        "has_pending_restore": lambda self: True,
        "restore": lambda self: calls.append("restore"),
        "prepare": lambda self, timeout_seconds: calls.append(("prepare", timeout_seconds)),
    })()
    monkeypatch.setattr("agent.pretask.build_lifecycle", lambda: lifecycle)
    from agent.pretask import main
    assert main([]) == 0
    assert calls == ["restore", ("prepare", 60)]
```

- [ ] **Step 3: Run and confirm red**

Run: `install/.venv/bin/python -m pytest tests/test_window_lifecycle.py tests/test_pretask.py -q`

Expected: missing-module collection failures.

- [ ] **Step 4: Implement the backend protocol and pure orchestration first**

Define `WindowBackend` with the exact methods used by `FakeBackend` plus `game_process_running() -> bool`. `prepare()` must: discover exact title, snapshot original bounds/frontmost bundle, atomically save, activate PID, set `1280×720`, read back, and require exact bounds. At the discovery deadline, an absent game process maps to `APP_LAUNCH_TIMEOUT`, while a running process without the exact window maps to `WINDOW_NOT_FOUND`; read-back mismatch maps to `WINDOW_RESIZE_FAILED`. `restore()` must load a pending snapshot, verify PID/window identity, restore bounds, restore the previous bundle if present, and only then mark restored.

- [ ] **Step 5: Add the PyObjC production backend**

Use `CGWindowListCopyWindowInfo` to select an on-screen layer-0 window whose `kCGWindowName` is exactly `对决！剑之川`; use the owning PID plus Accessibility API to locate the same AX window. Use `AXUIElementSetAttributeValue` for position and size, `NSRunningApplication.activateWithOptions_` for activation, and monotonic polling at 100 ms intervals. Define `Bounds` as the global captured-client rectangle used by ScreenCaptureKit; the backend alone translates between that rectangle and the AX outer frame so title-bar/chrome offsets never leak into click mapping. Keep all framework calls behind `PyObjCWindowBackend` so unit tests never need permissions.

- [ ] **Step 6: Implement `python -m agent.pretask` with stable exit reporting**

`main(argv)` runs `ensure_permissions()`, restores pending stale state, then prepares. Catch `MJAError`, write it through `RunDiagnostics`, print the concrete `CODE: message` pair from the exception to stderr, and return `2`; unexpected exceptions return `3`. `if __name__ == "__main__": raise SystemExit(main())` is required.

- [ ] **Step 7: Verify and commit**

Run: `install/.venv/bin/python -m pytest tests/test_window_lifecycle.py tests/test_pretask.py -q && install/.venv/bin/python -m pytest -q`

Expected: all tests pass without macOS permission prompts.

```bash
git add agent/macos/window_lifecycle.py agent/pretask.py tests/test_window_lifecycle.py tests/test_pretask.py
git commit -m "feat: prepare and restore the game window"
```

## Task 5: Implement the Box-Gated Foreground Click Agent Action

**Files:**
- Create: `agent/actions/macos_foreground_click.py`
- Create: `agent/main.py`
- Test: `tests/test_macos_foreground_click.py`
- Test: `tests/test_agent_main.py`

- [ ] **Step 1: Write failing coordinate mapping and refusal tests**

```python
# tests/test_macos_foreground_click.py
import pytest
from agent.actions.macos_foreground_click import ClickExecutor, map_box_center


def test_box_center_maps_from_capture_to_window() -> None:
    assert map_box_center((1200, 60, 40, 20), (1280, 720), (10, 20, 1280, 720)) == (1230, 90)


@pytest.mark.parametrize("box", [None, (0, 0, 0, 20), (-1, 0, 20, 20)])
def test_missing_or_invalid_recognition_box_never_invokes_process(box) -> None:
    calls = []
    executor = ClickExecutor(run=lambda *args, **kwargs: calls.append(args), sleep=lambda _: None)
    with pytest.raises(ValueError, match="recognition box"):
        executor.click(box, (1280, 720), (10, 20, 1280, 720), pid=902)
    assert calls == []
```

- [ ] **Step 2: Write the exact cliclick sequence test**

```python
def test_click_activates_then_restores_pointer() -> None:
    calls = []
    executor = ClickExecutor(
        run=lambda argv, **kwargs: calls.append(argv) or type("R", (), {"returncode": 0, "stderr": ""})(),
        sleep=lambda seconds: calls.append(["sleep", seconds]),
        pointer_position=lambda: (7, 8),
        activate=lambda pid: calls.append(["activate", pid]),
    )
    executor.click((100, 200, 20, 40), (1280, 720), (10, 20, 1280, 720), pid=902)
    assert calls == [
        ["activate", 902],
        ["sleep", 0.15],
        ["/opt/homebrew/bin/cliclick", "c:120,240"],
        ["/opt/homebrew/bin/cliclick", "m:7,8"],
    ]
```

- [ ] **Step 3: Run and confirm red**

Run: `install/.venv/bin/python -m pytest tests/test_macos_foreground_click.py -q`

Expected: import fails for `agent.actions.macos_foreground_click`.

- [ ] **Step 4: Implement validation, mapping, command execution, and pointer restoration**

`map_box_center(box, capture_size, window_bounds)` uses independent X/Y ratios and rounds to the nearest integer. Reject absent boxes, non-positive dimensions, out-of-capture centers, non-`1280×720` captures, and non-`1280×720` prepared windows. `ClickExecutor.click()` always restores the pointer in `finally` after a click attempt; a nonzero cliclick exit raises `RuntimeError` including the exit code but not the full environment.

- [ ] **Step 5: Register the Maa action and AgentServer entry**

```python
# registration shape in agent/actions/macos_foreground_click.py
@AgentServer.custom_action("MacOSForegroundClick")
class MacOSForegroundClick(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # argv.box is the only click target; controller.resolution supplies capture_size.
        executor = build_executor()
        window = build_lifecycle().current_prepared_window()
        executor.click(argv.box, context.tasker.controller.resolution, window.bounds_tuple, window.pid)
        return CustomAction.RunResult(success=True)
```

`agent/main.py` imports the action and sink modules before `AgentServer.start_up(socket_id)`, accepts exactly one socket argument, sets the Maa log directory from `MJA_DEBUG_DIR`, joins, and in `finally` shuts down the AgentServer and calls `build_lifecycle().restore()`. This process-finally restoration is the cancellation/disconnection fallback when Maa emits no separate stopped event.

- [ ] **Step 6: Test registration without starting a socket**

Patch `AgentServer.start_up`, `join`, `shut_down`, and `build_lifecycle` in `tests/test_agent_main.py`; assert one call each to shutdown and restoration on a simulated `KeyboardInterrupt`. Add a second test where `AgentServer.start_up` raises and assert diagnostics records `CONTROLLER_CONNECT_FAILED` before restoration.

- [ ] **Step 7: Verify and commit**

Run: `install/.venv/bin/python -m pytest tests/test_macos_foreground_click.py tests/test_agent_main.py -q && install/.venv/bin/python -m pytest -q`

Expected: all tests pass.

```bash
git add agent/actions/macos_foreground_click.py agent/main.py tests/test_macos_foreground_click.py tests/test_agent_main.py
git commit -m "feat: add box-gated macOS click action"
```

## Task 6: Record Pipeline Failures and Restore on Every Task Terminal Event

**Files:**
- Create: `agent/sinks/restore_window.py`
- Modify: `agent/main.py`
- Test: `tests/test_restore_window_sink.py`

- [ ] **Step 1: Write the failing terminal-event test**

```python
# tests/test_restore_window_sink.py
from agent.sinks.restore_window import RestoreWindowSink


def test_only_first_terminal_event_for_a_task_restores() -> None:
    calls = []
    sink = RestoreWindowSink(restore=lambda: calls.append("restore"))
    for message in ("Tasker.Task.Succeeded", "Tasker.Task.Failed", "Tasker.Task.Failed"):
        sink.on_raw_notification(None, message, {"task_id": 7})
    assert calls == ["restore"]

    sink.on_raw_notification(None, "Tasker.Task.Succeeded", {"task_id": 8})
    assert calls == ["restore", "restore"]


def test_nonterminal_events_do_not_restore() -> None:
    calls = []
    RestoreWindowSink(restore=lambda: calls.append("restore")).on_raw_notification(
        None, "Node.PipelineNode.Succeeded", {"task_id": 7}
    )
    assert calls == []
```

- [ ] **Step 2: Run and confirm the sink module is missing**

Run: `install/.venv/bin/python -m pytest tests/test_restore_window_sink.py -q`

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Add failing node-to-diagnostic mapping tests**

For `Node.Recognition.Failed`, assert these exact mappings and one saved `failure-screen.png`: `MJA_Start -> HOME_RECOGNITION_TIMEOUT`; `MJA_ConfirmPanel` and `MJA_ConfirmMail -> MAIL_OPEN_TIMEOUT`; `MJA_ConfirmPanelAfterMail` and `MJA_ConfirmHome -> HOME_RETURN_TIMEOUT`. Assert an unrelated failed node does not invent a stable timeout code.

- [ ] **Step 4: Implement an idempotent, lock-protected sink**

Subclass `TaskerEventSink`. Match exactly `Tasker.Task.Succeeded` and `Tasker.Task.Failed`, the two terminal messages exposed by MaaFramework 5.12.2. Protect a set of restored task IDs with `threading.Lock`; insert the ID before invoking restoration so duplicate/concurrent events cannot trigger twice while later task IDs still restore. On the mapped recognition failures, request one cached screenshot from the tasker's controller, save `failure-screen.png`, and fail diagnostics with the mapped code. On task success, save the positively recognized final frame as `last-screen.png` and mark diagnostics succeeded before restoration. Catch restoration exceptions, record `WINDOW_RESTORE_FAILED` as a warning, and do not rewrite the original task result.

- [ ] **Step 5: Register the sink at Agent import time and verify**

Import `agent.sinks.restore_window` from `agent/main.py`. Use `@AgentServer.tasker_sink()` on a zero-argument production subclass whose restore callable is `build_lifecycle().restore`.

Run: `install/.venv/bin/python -m pytest tests/test_restore_window_sink.py tests/test_agent_main.py -q && install/.venv/bin/python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add agent/sinks/restore_window.py agent/main.py tests/test_restore_window_sink.py tests/test_agent_main.py
git commit -m "feat: restore windows on task termination"
```

## Task 7: Capture Safe Templates and Define the PI V2 Pipeline

**Files:**
- Create: `tools/capture_templates.py`
- Create: `assets/interface.json`
- Create: `assets/resource/pipeline/mail_smoke_test.json`
- Create after attended capture: `assets/resource/image/home/home_marker.png`
- Create after attended capture: `assets/resource/image/home/panel_open.png`
- Create after attended capture: `assets/resource/image/panel/panel_marker.png`
- Create after attended capture: `assets/resource/image/panel/mail_entry.png`
- Create after attended capture: `assets/resource/image/panel/panel_close.png`
- Create after attended capture: `assets/resource/image/mail/mail_marker.png`
- Create after attended capture: `assets/resource/image/mail/mail_close.png`
- Test: `tests/test_capture_templates.py`
- Test: `tests/test_project_interface.py`

- [ ] **Step 1: Write a synthetic-image crop test for the capture utility**

```python
# tests/test_capture_templates.py
from PIL import Image
from tools.capture_templates import Crop, crop_templates


def test_named_crops_have_exact_dimensions(tmp_path) -> None:
    source = tmp_path / "screen.png"
    Image.new("RGB", (1280, 720), "navy").save(source)
    outputs = crop_templates(source, tmp_path / "out", {
        "home_marker": Crop(1040, 0, 240, 110),
        "panel_open": Crop(1200, 0, 80, 100),
    })
    assert Image.open(outputs["home_marker"]).size == (240, 110)
    assert Image.open(outputs["panel_open"]).size == (80, 100)
```

Pillow is already pinned and installed by Task 1; this task adds no new dependency.

- [ ] **Step 2: Write failing static safety tests for PI and pipeline**

```python
# tests/test_project_interface.py
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(path): return json.loads(path.read_text())


def test_interface_exposes_one_safe_default_task() -> None:
    pi = load(ROOT / "assets/interface.json")
    assert pi["interface_version"] == 2
    assert pi["controller"][0]["type"] == "MacOS"
    assert pi["controller"][0]["display_short_side"] == 720
    assert pi["task"] == [{
        "name": "mail_smoke_test",
        "label": "邮件菜单闭环测试",
        "entry": "MJA_Start",
        "default_check": True,
        "resource": ["mja"],
        "controller": ["macos"],
    }]
    assert pi["agent"] == {
        "child_exec": ".venv/bin/python3",
        "child_args": ["agent/main.py"],
        "identifier": "mja-python-agent",
    }


def test_pipeline_has_only_four_box_gated_inputs_and_no_claim_vocabulary() -> None:
    pipeline = load(ROOT / "assets/resource/pipeline/mail_smoke_test.json")
    serialized = json.dumps(pipeline, ensure_ascii=False).lower()
    assert all(term not in serialized for term in ("领取", "claim", "startapp", '"click"'))
    actions = [node for node in pipeline.values() if node.get("action") == "Custom"]
    assert [node["custom_action"] for node in actions] == [
        "MacOSForegroundClick",
        "MacOSForegroundClick",
        "MacOSForegroundClick",
        "MacOSForegroundClick",
    ]
    assert all(node["recognition"] == "TemplateMatch" for node in actions)
    assert all("template" in node for node in actions)
    for node in pipeline.values():
        if "template" in node:
            assert (ROOT / "assets/resource/image" / node["template"]).is_file()
```

- [ ] **Step 3: Run the tests and confirm both fail**

Run: `install/.venv/bin/python -m pytest tests/test_capture_templates.py tests/test_project_interface.py -q`

Expected: the crop test passes; the static pipeline test is collected and skips only when the seven live PNGs are not yet captured.

- [ ] **Step 4: Implement deterministic capture/crop support**

The tool accepts `capture home|panel|mail --window-id WINDOW_ID`. It creates a Maa `MacOSController` for that ID with ScreenCaptureKit, connects, sets screenshot short side to 720, calls `post_screencap().wait().get()`, requires the resulting frame to be exactly `1280×720`, and emits the following fixed crops:

```python
HOME_CROPS = {
    "home_marker": Crop(1040, 0, 240, 110),
    "panel_open": Crop(1200, 0, 80, 100),
}
PANEL_CROPS = {
    "panel_marker": Crop(840, 0, 280, 160),
    "mail_entry": Crop(1120, 115, 160, 210),
    "panel_close": Crop(1200, 0, 80, 100),
}
MAIL_CROPS = {
    "mail_marker": Crop(0, 0, 320, 140),
    "mail_close": Crop(1040, 80, 160, 160),
}
```

The capture utility must refuse to crop if dimensions differ, print every output path, and never define or accept a crop named with `claim`, `reward`, `领取`, or `奖励`.

- [ ] **Step 5: Add the exact safe pipeline**

Use these node responsibilities and timeouts:

```json
{
  "MJA_Start": {
    "recognition": "TemplateMatch",
    "template": "home/home_marker.png",
    "roi": [1040, 0, 240, 110],
    "threshold": 0.85,
    "timeout": 30000,
    "action": "DoNothing",
    "next": ["MJA_OpenPanel"]
  },
  "MJA_OpenPanel": {
    "recognition": "TemplateMatch",
    "template": "home/panel_open.png",
    "roi": [1200, 0, 80, 100],
    "threshold": 0.9,
    "timeout": 10000,
    "action": "Custom",
    "custom_action": "MacOSForegroundClick",
    "next": ["MJA_ConfirmPanel"]
  },
  "MJA_ConfirmPanel": {
    "recognition": "TemplateMatch",
    "template": "panel/panel_marker.png",
    "roi": [840, 0, 280, 160],
    "threshold": 0.88,
    "timeout": 10000,
    "action": "DoNothing",
    "next": ["MJA_OpenMail"]
  },
  "MJA_OpenMail": {
    "recognition": "TemplateMatch",
    "template": "panel/mail_entry.png",
    "roi": [1120, 115, 160, 210],
    "threshold": 0.88,
    "timeout": 10000,
    "action": "Custom",
    "custom_action": "MacOSForegroundClick",
    "next": ["MJA_ConfirmMail"]
  },
  "MJA_ConfirmMail": {
    "recognition": "TemplateMatch",
    "template": "mail/mail_marker.png",
    "roi": [0, 0, 320, 140],
    "threshold": 0.88,
    "timeout": 10000,
    "action": "DoNothing",
    "next": ["MJA_CloseMail"]
  },
  "MJA_CloseMail": {
    "recognition": "TemplateMatch",
    "template": "mail/mail_close.png",
    "roi": [1040, 80, 160, 160],
    "threshold": 0.9,
    "timeout": 10000,
    "action": "Custom",
    "custom_action": "MacOSForegroundClick",
    "next": ["MJA_ConfirmPanelAfterMail"]
  },
  "MJA_ConfirmPanelAfterMail": {
    "recognition": "TemplateMatch",
    "template": "panel/panel_marker.png",
    "roi": [840, 0, 280, 160],
    "threshold": 0.88,
    "timeout": 10000,
    "action": "DoNothing",
    "next": ["MJA_ClosePanel"]
  },
  "MJA_ClosePanel": {
    "recognition": "TemplateMatch",
    "template": "panel/panel_close.png",
    "roi": [1200, 0, 80, 100],
    "threshold": 0.9,
    "timeout": 10000,
    "action": "Custom",
    "custom_action": "MacOSForegroundClick",
    "next": ["MJA_ConfirmHome"]
  },
  "MJA_ConfirmHome": {
    "recognition": "TemplateMatch",
    "template": "home/home_marker.png",
    "roi": [1040, 0, 240, 110],
    "threshold": 0.85,
    "timeout": 10000,
    "action": "DoNothing"
  }
}
```

- [ ] **Step 6: Add PI V2 controller, resource, task, and Agent declarations**

Use controller name `macos`, title regex `^对决！剑之川$`, ScreenCaptureKit, GlobalEvent, and `display_short_side: 720`. Resource path is `resource`. Agent child executable is `.venv/bin/python3`; its only configured child argument is `agent/main.py`, because MaaFramework appends the generated socket ID automatically. The GUI pretask is configured by Task 9 because upstream PI does not itself execute arbitrary pre-controller commands.

- [ ] **Step 7: Perform the one-time attended, non-mutating template capture**

Run the pretask, open the game to the known home UI without overlays, then read the current window ID and capture with exact commands:

```bash
MJA_WINDOW_ID=$(install/.venv/bin/python -c 'import json; print(json.load(open(".mja-state/window.json"))["snapshot"]["window_id"])')
install/.venv/bin/python -m tools.capture_templates capture home --window-id "$MJA_WINDOW_ID"
```

Manually open the function panel, then capture its stable marker, mail entry, and close target; do not click the mail entry through automation during bootstrap:

```bash
install/.venv/bin/python -m tools.capture_templates capture panel --window-id "$MJA_WINDOW_ID"
```

Then manually open mail without selecting any list item and run:

```bash
install/.venv/bin/python -m tools.capture_templates capture mail --window-id "$MJA_WINDOW_ID"
```

Close mail and the function panel manually. Inspect only the seven generated crops and confirm none contains a claim/reward control. If a fixed crop misses its named element, adjust the corresponding named crop constant and ROI together, update the pipeline to the same numbers, and rerun the static tests before committing; never broaden the ROI to include the lower-left claim area.

- [ ] **Step 8: Verify and commit templates with safety tests**

Run: `install/.venv/bin/python -m pytest tests/test_capture_templates.py tests/test_project_interface.py -q && install/.venv/bin/python -m pytest -q`

Expected: all tests pass with the pipeline test skipped until live capture; after capture, all tests pass and exactly seven PNGs exist locally. The live PNGs remain ignored from Git.

```bash
git add requirements.lock tools/capture_templates.py assets tests/test_capture_templates.py tests/test_project_interface.py
git commit -m "feat: add safe mail smoke-test pipeline"
```

## Task 8: Build Idempotent Runtime Setup and Installation Verification

**Files:**
- Create: `tools/setup.py`
- Create: `tools/verify_install.py`
- Test: `tests/test_setup.py`
- Test: `tests/test_verify_install.py`

- [ ] **Step 1: Write failing digest and idempotent-copy tests**

```python
# tests/test_setup.py
import hashlib
import pytest
from tools.setup import verify_download


def test_verify_download_accepts_exact_size_and_digest(tmp_path) -> None:
    path = tmp_path / "asset"
    path.write_bytes(b"mja")
    verify_download(path, 3, hashlib.sha256(b"mja").hexdigest())


def test_verify_download_rejects_tampering(tmp_path) -> None:
    path = tmp_path / "asset"
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_download(path, 3, "0" * 64)
```

- [ ] **Step 2: Write a failing assembled-layout verifier test**

```python
# tests/test_verify_install.py
from tools.verify_install import verify_install


def test_missing_required_file_is_reported(tmp_path) -> None:
    errors = verify_install(tmp_path)
    assert "missing interface.json" in errors
    assert "missing .venv/bin/python3" in errors
    assert "missing MaaPiCli" in errors
```

- [ ] **Step 3: Run and confirm red**

Run: `install/.venv/bin/python -m pytest tests/test_setup.py tests/test_verify_install.py -q`

Expected: missing-module collection failures.

- [ ] **Step 4: Implement manifest parsing, streamed downloads, and verification**

Use `urllib.request.urlopen`, write each artifact to `downloads/` using its manifest filename plus `.part`, update SHA-256 while streaming 1 MiB chunks, `fsync`, validate expected size/digest, then atomically rename. On a later run, reuse only a fully verified final download. Reject non-HTTPS URLs and archive members containing absolute paths or `..` before extraction.

- [ ] **Step 5: Implement deterministic assembly**

`tools/setup.py --root .` must:

1. Require `platform.system() == "Darwin"` and `platform.machine() == "arm64"`.
2. Require `/opt/homebrew/bin/cliclick` executable.
3. Create/reuse `install/.venv` with `/opt/homebrew/bin/python3 -m venv`.
4. Run `install/.venv/bin/python -m pip install --requirement requirements.lock`.
5. Download/verify/extract both archives into temporary directories under `install/`.
6. Assemble `MFAAvalonia.app`, `MaaPiCli`, framework libs/runtimes, `interface.json`, `resource/`, and `agent/`.
7. Copy the venv into the final root only by creating it there; never copy an activated external venv.
8. Invoke `verify_install(install_root)` and return nonzero if any error exists.

Use `shutil.copytree(source, destination, dirs_exist_ok=True)` only for project-owned `assets/resource` and `agent`; replace runtime version directories atomically after extraction. Do not delete an unknown existing `install/` tree.

- [ ] **Step 6: Implement static and runtime verification**

Require the exact files, execute `.venv/bin/python -c 'import maa, Quartz, AppKit'`, execute `/opt/homebrew/bin/cliclick -V`, validate all template references, compare Maa/MFA version marker files with `runtime-manifest.json`, and run the pipeline safety checks from Task 7. Return a list of human-readable errors; the CLI prints each with `ERROR:` and exits 1, otherwise prints `MJA install verified` and exits 0.

- [ ] **Step 7: Verify unit tests and a clean local assembly**

Run: `install/.venv/bin/python -m pytest tests/test_setup.py tests/test_verify_install.py -q && install/.venv/bin/python -m tools.setup --root . && install/.venv/bin/python -m tools.verify_install install`

Expected: tests pass; setup downloads only on the first run; verifier prints `MJA install verified`.

- [ ] **Step 8: Run setup a second time and confirm idempotence**

Run: `install/.venv/bin/python -m tools.setup --root .`

Expected: both archives report `verified cache hit`; no duplicate app/runtime directories are created.

- [ ] **Step 9: Run full suite and commit**

Run: `install/.venv/bin/python -m pytest -q`

Expected: all tests pass.

```bash
git add tools/setup.py tools/verify_install.py tests/test_setup.py tests/test_verify_install.py
git commit -m "build: assemble pinned macOS runtime"
```

## Task 9: Add Safe MFA Configuration and CLI Lifecycle Wrapping

**Files:**
- Create: `tools/configure_mfa.py`
- Create: `tools/run_cli.py`
- Test: `tests/test_configure_mfa.py`
- Test: `tests/test_run_cli.py`

- [ ] **Step 1: Write a failing MFA minimal-patch test**

```python
# tests/test_configure_mfa.py
import json
from tools.configure_mfa import configure_instance


def test_configuration_preserves_unknown_fields_and_backs_up(tmp_path) -> None:
    path = tmp_path / "default.json"
    path.write_text(json.dumps({"theme": "dark", "startup": {"keep": 1}}))
    backup = configure_instance(path, install_root=tmp_path / "install", now=lambda: "20260727T120000")
    payload = json.loads(path.read_text())
    assert payload["theme"] == "dark"
    assert payload["startup"]["keep"] == 1
    assert payload["startup"]["program"] == "/usr/bin/open"
    assert payload["startup"]["args"] == ['-a', '对决！剑之川']
    assert payload["startup"]["wait_seconds"] == 60
    assert backup.name == "default.json.20260727T120000.bak"
```

- [ ] **Step 2: Write a failing CLI-finally test**

```python
# tests/test_run_cli.py
import pytest
from tools.run_cli import run_cli


def test_cli_restores_after_child_failure() -> None:
    calls = []
    lifecycle = type("L", (), {
        "prepare": lambda self, timeout_seconds: calls.append(("prepare", timeout_seconds)),
        "restore": lambda self: calls.append("restore"),
    })()
    with pytest.raises(RuntimeError, match="child failed"):
        run_cli(lifecycle, spawn=lambda argv: (_ for _ in ()).throw(RuntimeError("child failed")))
    assert calls == [("prepare", 60), "restore"]
```

Add a second test where `prepare()` returns window ID 41. Assert the wrapper atomically writes this exact local CLI configuration before spawning:

```json
{
  "controller": {"name": "macos"},
  "macos": {
    "window_id": 41,
    "title": "对决！剑之川",
    "screencap": "ScreenCaptureKit",
    "input": "GlobalEvent"
  },
  "resource": "mja",
  "task": [{"name": "mail_smoke_test"}]
}
```

- [ ] **Step 3: Run and confirm red**

Run: `install/.venv/bin/python -m pytest tests/test_configure_mfa.py tests/test_run_cli.py -q`

Expected: missing-module collection failures.

- [ ] **Step 4: Implement backup-first MFA patching**

Accept an explicit instance JSON path only; never search or guess a user configuration path. Parse JSON before backup, append `.YYYYMMDDTHHMMSS.bak` to the original filename, minimally merge startup program/args/wait, automatic MacOS window detection, project path `install/interface.json`, and the pretask command `install/.venv/bin/python -m agent.pretask`. Write atomically. With `--dry-run`, print the JSON patch and do not create backup or modify the file.

- [ ] **Step 5: Implement the CLI wrapper**

`run_cli()` runs `/usr/bin/open -a 对决！剑之川`, waits for lifecycle preparation, atomically writes `install/config/maa_pi_config.json` with the prepared window ID and the exact configuration above, sets `MJA_DEBUG_DIR`, and starts `./MaaPiCli -d` with `cwd=install/`. MaaPiCli discovers `interface.json` beside its executable. Forward SIGINT to the child and call `restore()` in `finally`. A child return code is returned unchanged unless restoration is the only failure. The wrapper must load the same assembled interface and must not contain its own click logic.

- [ ] **Step 6: Verify and commit**

Run: `install/.venv/bin/python -m pytest tests/test_configure_mfa.py tests/test_run_cli.py -q && install/.venv/bin/python -m pytest -q`

Expected: all tests pass.

```bash
git add tools/configure_mfa.py tools/run_cli.py tests/test_configure_mfa.py tests/test_run_cli.py
git commit -m "feat: integrate MFA and guarded CLI runs"
```

## Task 10: Document and Execute the Attended Acceptance Matrix

**Files:**
- Create: `docs/testing/macos-mail-smoke-test.md`
- Modify only if evidence finds defects: implementation/test files from Tasks 1–9
- Generate but never commit: `debug/runs/**`, `.mja-state/**`, `install/**`

- [ ] **Step 1: Write the acceptance runbook before live execution**

Document exact prerequisites and commands:

```bash
python3 -m tools.setup --root .
install/.venv/bin/python -m tools.verify_install install
install/.venv/bin/python -m agent.pretask
install/.venv/bin/python -m tools.run_cli
```

The checklist must record original window bounds, prior frontmost app, resulting `run.json`, whether exactly four clicks occurred, final home recognition, and restored bounds. Explicitly state that any claim/reward click is an immediate acceptance failure.

- [ ] **Step 2: Run all automated checks**

Run: `install/.venv/bin/python -m ruff check agent tools tests && install/.venv/bin/python -m pytest -q`

Expected: Ruff prints `All checks passed!`; all tests pass.

- [ ] **Step 3: Validate the safe failure path before a successful run**

Copy `home_marker.png` to an ignored temporary backup, replace it in `install/resource/image/home/` only with a synthetic mismatching image, then start via `tools.run_cli`. Do not alter the tracked source template.

Expected: `HOME_RECOGNITION_TIMEOUT`, zero custom-action click events, a failure screenshot, and restored original window/frontmost app. Re-run `tools.setup` to restore the assembled template.

- [ ] **Step 4: Validate cancellation restoration**

Start the CLI wrapper, interrupt with Ctrl-C while the initial recognition waits, and inspect the latest state/diagnostics.

Expected: no unrecognized click, child exits from SIGINT, and the original bounds/frontmost app are restored exactly once.

- [ ] **Step 5: Run cold-start MFA acceptance**

Quit the game manually, open `install/MFAAvalonia.app`, select `install/interface.json`, verify that MJA and “邮件菜单闭环测试” are visible, then start the task.

Expected: the game launches within 60 seconds, the window becomes `1280×720`, the panel/mail open-close sequence produces exactly four logged `MacOSForegroundClick` events, home is recognized, and the original state is restored.

- [ ] **Step 6: Run warm-start MFA acceptance**

Leave the game running at the known home UI and run the same MFA task.

Expected: no second game process, exactly four clicks, successful home return, and restoration.

- [ ] **Step 7: Run the required three consecutive MFA successes**

Run the task three times without modifying templates or configuration. Record the three run-directory names in the runbook.

Expected for each run: `status == "succeeded"`, final node `MJA_ConfirmHome`, exactly four custom clicks, no warning code, and original window state restored. Any failed run resets the consecutive-success count to zero after the defect is fixed.

- [ ] **Step 8: Audit tracked files and commit documentation/fixes**

Run: `git status --short && git ls-files | rg '^(install|downloads|debug|\.venv|\.mja-state)/'`

Expected: the second command prints nothing; status contains only intended source/docs changes and preserves the user's pre-existing `AGENTS.md` edit.

```bash
git add docs/testing/macos-mail-smoke-test.md
# Add only implementation/test files actually fixed during acceptance; never use git add -A.
git commit -m "test: certify macOS mail smoke test"
```

- [ ] **Step 9: Final verification**

Run: `install/.venv/bin/python -m ruff check agent tools tests && install/.venv/bin/python -m pytest -q && install/.venv/bin/python -m tools.verify_install install`

Expected: lint and tests pass; verifier prints `MJA install verified`; runbook contains three consecutive successful run IDs.

## Specification Coverage Review

- The plan preserves the approved minimal loop: launch/activate, home recognition, open mail, mail recognition, close mail, home recognition.
- Permission failures happen before controller/task input and use stable codes.
- Window preparation persists state before mutation; success, failure, cancellation, stale state, and CLI exceptions all restore idempotently.
- Only four nodes can produce input, all require a current recognition box, and static tests prohibit claim/reward vocabulary and standard click/start actions.
- MaaFramework/MFA/Python dependencies are fixed by version, URL, size, and SHA-256; setup is repeatable and local artifacts are ignored.
- GUI and CLI use the same assembled PI/resources/Agent; MFA configuration is explicit-path, backup-first, and minimally patched.
- Tests cover unit, Agent, config, setup, safe failure, cancellation, cold/warm start, and three consecutive successes.
- Out of scope remains unchanged: login, unknown popups, claims, background operation, other tasks, other machines, and upstream forks.
