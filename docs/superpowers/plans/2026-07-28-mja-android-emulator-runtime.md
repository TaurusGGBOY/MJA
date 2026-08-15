# MJA Android Emulator Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline task execution with checkpoints. The environment does not provide the referenced subagent skill; execute each task in this session and verify it before continuing.

**Goal:** Install and operate a reproducible Android Studio ARM64 emulator on macOS, connect MJA through MaaFramework's ADB controller, pause only for account login, and complete a live 1280×720 mail-menu verification.

**Architecture:** Keep the existing macOS controller intact and add an Android runtime beside it. A project-local Android environment module owns SDK/AVD/ADB lifecycle; an Android runner owns game installation, login gating, MaaPiCli configuration, diagnostics, and cleanup. Android uses a separate resource bundle whose templates are captured from live emulator frames.

**Tech Stack:** Python 3.14, `subprocess`, Android SDK command-line tools, `adb`, Android Emulator, ARM64 AVD, MaaFramework 5.12.2, MFAAvalonia ProjectInterface V2, pytest, Ruff.

## Global Constraints

- Host platform is macOS Apple Silicon (`Darwin`, `arm64`).
- The Android device contract is exactly 1280×720 in landscape; mismatches fail before business input.
- The emulator AVD name is `mja-api35`; the default serial is `emulator-5554`.
- Login credentials and verification codes are never collected, stored, or entered by MJA.
- The only permitted game task is the existing mail-menu open/close smoke test; no claim, purchase, recharge, or payment action is added.
- Existing macOS files remain available for rollback and are not deleted.
- Every external command is injectable in unit tests and all real-run failures leave diagnostics under `diagnostics/android/`.

---

### Task 1: Establish Android runtime configuration and stable errors

**Files:**
- Create: `config/android.json`
- Create: `agent/android/__init__.py`
- Create: `agent/android/config.py`
- Modify: `agent/errors.py`
- Test: `tests/test_android_config.py`
- Test: `tests/test_project_contract.py`

**Interfaces:**
- `AndroidConfig.load(path: Path) -> AndroidConfig`
- `AndroidConfig.avd_name: str`, `.serial: str`, `.package_name: str | None`, `.game_label: str`, `.display_size: tuple[int, int]`, `.apk_path: Path | None`, `.keep_running: bool`
- `AndroidConfig.validate() -> None`
- Add stable codes `ANDROID_SDK_UNAVAILABLE`, `ANDROID_AVD_FAILED`, `ADB_DEVICE_FAILED`, `ANDROID_GAME_NOT_FOUND`, `ANDROID_LOGIN_REQUIRED`, and `ANDROID_INSTALL_FAILED`.

- [x] **Step 1: Write failing config tests** for defaults, path resolution relative to repository root, invalid display sizes, invalid serials, and rejection of non-ARM/portrait settings.
- [x] **Step 2: Run `install/.venv/bin/python -m pytest tests/test_android_config.py -q` and confirm the new module is missing.**
- [x] **Step 3: Implement immutable JSON-backed configuration** with defaults:

```json
{
  "avd_name": "mja-api35",
  "serial": "emulator-5554",
  "package_name": null,
  "game_label": "对决！剑之川",
  "display_size": [1280, 720],
  "apk_path": null,
  "keep_running": true,
  "login_timeout_seconds": 900,
  "sdk_root": "install/android-sdk"
}
```

- [x] **Step 4: Add error codes and project contract assertions** requiring the Android configuration and 1280×720 contract.
- [x] **Step 5: Run the focused tests and Ruff.** Expected: all pass.
- [x] **Step 6: Commit:** `feat: add android runtime configuration contract`.

### Task 2: Build an idempotent SDK and AVD bootstrapper

**Files:**
- Create: `agent/android/sdk.py`
- Create: `agent/android/avd.py`
- Create: `tools/android_setup.py`
- Modify: `tools/setup.py`
- Test: `tests/test_android_sdk.py`
- Test: `tests/test_android_avd.py`
- Test: `tests/test_android_setup.py`

**Interfaces:**
- `CommandRunner.run(argv: Sequence[str], *, check: bool, timeout: float | None) -> CompletedProcess[str]`
- `AndroidSdk.ensure() -> SdkPaths`
- `AndroidSdk.sdkmanager() -> Path`, `.adb() -> Path`, `.emulator() -> Path`
- `AndroidAvd.ensure() -> Path`
- `AndroidAvd.start() -> subprocess.Popen[str]`
- `AndroidAvd.stop() -> None`

- [x] **Step 1: Write tests** asserting SDK discovery prefers `config.sdk_root`, falls back to `ANDROID_SDK_ROOT` and Homebrew command-line tools, and constructs only the required packages: `platform-tools`, `emulator`, `platforms;android-35`, and `system-images;android-35;google_apis_playstore;arm64-v8a`.
- [x] **Step 2: Write tests** asserting AVD creation uses `avdmanager create avd`, never wipes an existing AVD during normal setup, and writes `config.ini` values `hw.lcd.width=1280`, `hw.lcd.height=720`, `hw.initialOrientation=landscape`, `hw.lcd.density=320`, `hw.gpu.enabled=yes`, `hw.gpu.mode=host`.
- [x] **Step 3: Implement SDK bootstrap** using Homebrew only to install missing `android-commandlinetools` and `openjdk@17`; use `sdkmanager --sdk_root` for Android components, accept licenses through stdin, and persist an install manifest with component versions and SHA-256 where available.
- [x] **Step 4: Implement AVD bootstrap** with `avdmanager`, a named AVD, a Google Play ARM64 image, and safe launch flags `-no-boot-anim -gpu host`; reserve `-wipe-data` for an explicit `--wipe-data` argument.
- [x] **Step 5: Implement `tools/android_setup.py`** with `--check`, `--install`, `--wipe-data`, and `--print-env`; make normal execution idempotent and machine-readable.
- [x] **Step 6: Run focused tests and a read-only `--check`.** On the current host, record missing tools without modifying unrelated files.
- [x] **Step 7: Commit:** `feat: bootstrap android sdk and avd`.

### Task 3: Implement ADB readiness, screenshots, and login gate

**Files:**
- Create: `agent/android/adb.py`
- Create: `agent/android/login.py`
- Create: `tools/android_device.py`
- Modify: `agent/macos/display_contract.py` (extract or reuse the shared 1280×720 contract without changing macOS behavior)
- Test: `tests/test_android_adb.py`
- Test: `tests/test_android_login.py`

**Interfaces:**
- `AdbDevice.wait_ready(timeout_seconds: int) -> DeviceInfo`
- `AdbDevice.shell(*args: str) -> str`
- `AdbDevice.screencap(destination: Path) -> ImageSize`
- `AdbDevice.tap(x: int, y: int) -> None`
- `AdbDevice.launch(package_name: str) -> None`
- `LoginGate.wait_until_ready(device: AdbDevice, *, timeout_seconds: int) -> LoginState`

- [x] **Step 1: Write tests** for offline devices, multiple devices, a device whose `sys.boot_completed` remains `0`, and a ready device whose screenshot is not 1280×720.
- [x] **Step 2: Write tests** for login detection: return immediately when the configured home marker is visible, emit one `LOGIN_REQUIRED` event when login UI is present, and never call `input text` or read credentials.
- [x] **Step 3: Implement ADB commands** with an explicit serial on every invocation, timeout handling, and captured stdout/stderr. `wait_ready` must require exactly one configured device and `sys.boot_completed=1`.
- [x] **Step 4: Implement PNG capture** through `adb exec-out screencap -p`, validate dimensions with Pillow, and save the last frame on every failure.
- [x] **Step 5: Implement the login gate** using only screenshots, configured login markers, and package foreground state. Print `请完成 Google/游戏账号登录，完成后无需点击继续` once, then poll until the home marker or package state is ready.
- [x] **Step 6: Run focused tests and Ruff.** Expected: all pass without an emulator.
- [x] **Step 7: Commit:** `feat: add adb readiness and login gate`.

### Task 4: Add game installation and MaaFramework Adb execution

**Files:**
- Create: `agent/android/game.py`
- Create: `tools/android_run.py`
- Create: `tools/android_run.sh`
- Modify: `tools/run_cli.py`
- Modify: `assets/interface.json`
- Modify: `tests/test_run_cli.py`
- Create: `tests/test_android_game.py`
- Create: `tests/test_android_run.py`

**Interfaces:**
- `GameInstaller.ensure_installed() -> str`
- `GameInstaller.install_apk(path: Path) -> str`
- `GameInstaller.install_from_play_store() -> str`
- `AndroidRun.run(task_name: str = "mail_smoke_test") -> int`
- `_android_maa_config(adb_path: Path, serial: str, task_name: str) -> dict[str, object]`

- [x] **Step 1: Write tests** for APK installation, already-installed games, Play Store fallback, and refusal to install a path outside the repository/configured download directory.
- [x] **Step 2: Write tests** asserting the MaaPiCli config uses controller name `android`, `adb_path`, `adb_serial`, resource `mja_android`, and task `mail_smoke_test`.
- [x] **Step 3: Implement APK installation** with `adb install -r`, verify the package using `pm path`, and launch only the verified package.
- [x] **Step 4: Implement Play Store fallback** by launching a search intent for `game_label`, taking a package-list snapshot, driving only visible Install/Open/Continue controls through UIAutomator text, and requiring exactly one newly installed package before persisting `package_name`.
- [x] **Step 5: Implement Android runner lifecycle**:

```text
SDK_READY → AVD_READY → DEVICE_READY → GAME_READY → LOGIN_REQUIRED/LOGIN_READY → TASK_RUNNING → SUCCEEDED/FAILED
```

Always close the MaaPiCli child and save diagnostics in `finally`; stop the emulator only when `keep_running` is false or `--stop` is passed.
- [x] **Step 6: Add `tools/android_run.sh`** that resolves the repository root, uses `install/.venv/bin/python`, and forwards arguments without modifying shell startup files.
- [x] **Step 7: Update ProjectInterface V2** with `android` `Adb` controller, Android resource binding, and task visibility. Retain the macOS controller and task as a rollback-compatible entry.
- [x] **Step 8: Run focused tests and Ruff.** Expected: all pass.
- [x] **Step 9: Commit:** `feat: run mja through maa adb controller`.

### Task 5: Create Android resources and enforce the device contract

**Files:**
- Create: `assets/resource_android/calibration.json`
- Create: `assets/resource_android/pipeline/mail_smoke_test.json`
- Create: `assets/resource_android/image/home/.gitkeep`
- Create: `assets/resource_android/image/panel/.gitkeep`
- Create: `assets/resource_android/image/mail/.gitkeep`
- Modify: `tools/capture_templates.py`
- Modify: `tools/verify_install.py`
- Test: `tests/test_android_resources.py`
- Test: `tests/test_capture_templates.py`
- Test: `tests/test_verify_install.py`

- [x] **Step 1: Write tests** requiring every Android ROI to fit inside 1280×720, every template to be no larger than its ROI, and Android calibration to identify a live emulator capture rather than the macOS/iOS legacy profile.
- [x] **Step 2: Implement an Android capture command** that refuses to capture before `AdbDevice.wait_ready`, writes a raw PNG and metadata, and never projects 1051×820 macOS coordinates into Android resources.
- [x] **Step 3: Add the initial Android pipeline** with the same safe mail-menu semantics and empty template directories until live capture is complete; make installation verification report “live capture required” rather than silently accepting placeholders.
- [ ] **Step 4: Boot the AVD, complete login if prompted, launch the game, and use the capture tool to create home/panel/mail templates from live 1280×720 frames.** Do not stage screenshots that contain login UI, loading UI, or an unrelated background.
- [ ] **Step 5: Run the resource verifier and focused tests.** Expected: no placeholder template is admitted.
- [ ] **Step 6: Commit:** `feat: add android mail smoke resources`.

### Task 6: Run live acceptance and document the only user intervention

**Files:**
- Create: `docs/testing/android-emulator-mail-smoke-test.md`
- Create: `docs/verification/android-emulator-mail-regression.md`
- Modify: `README.md` (create if absent)
- Modify: `docs/superpowers/specs/2026-07-28-mja-android-emulator-runtime-design.md`
- Test: `tests/test_android_acceptance_contract.py`

- [x] **Step 1: Add acceptance-contract tests** for command order, login pause/resume, 50-frame capture, evidence paths, and guaranteed cleanup on task failure.
- [x] **Step 2: Run the complete local suite:** `install/.venv/bin/python -m pytest -q`; expected all existing tests plus Android tests pass.
- [x] **Step 3: Run static checks:** `install/.venv/bin/ruff check .` and `git diff --check`.
- [x] **Step 4: Run `tools/android_setup.py --check` and install missing components if the host permits it.** If a Google/account login screen appears, pause and let the user log in; then continue automatically.
- [ ] **Step 5: Run `tools/android_run.sh --task mail_smoke_test --keep-running`, verify controller connection, 50 non-empty 1280×720 frames, live template recognition, mail open/close, and home return.
- [ ] **Step 6: Save a redacted acceptance record** containing AVD name, SDK packages, serial, package name, dimensions, task result, timestamps, and evidence paths; never save account identifiers or credentials.
- [ ] **Step 7: Commit:** `test: verify android emulator mail workflow`.

### Task 7: Final handoff

- [ ] **Step 1: Run `tools/verify_install.py install` and confirm Android configuration, resource contract, and existing macOS runtime remain valid.**
- [ ] **Step 2: Check `git status --short` and ensure only the pre-existing user change in `AGENTS.md` is outside intended commits.
- [ ] **Step 3: Summarize the one-time login action, the one-command run entry, evidence location, and any real emulator compatibility blocker.**
- [ ] **Step 4: Push the implementation branch and create a PR only if GitHub connectivity/authentication is available; otherwise retain the local commits and report the exact blocker.**
