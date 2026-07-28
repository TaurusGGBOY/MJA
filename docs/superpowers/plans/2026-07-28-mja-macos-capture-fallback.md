# MJA macOS Capture Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, bundle, install, and verify a MaaFramework v5.12.2 macOS arm64 control-unit dylib that keeps ScreenCaptureKit as the first choice and safely falls back to a nominal-resolution CoreGraphics capture of the visible game-window rectangle.

**Architecture:** Patch only `ScreenCaptureKitScreencap` in a clean v5.12.2 source snapshot. The screencap object owns a connection-local backend state, retries ScreenCaptureKit on every new controller connection, switches once to `CoreGraphicsRegion` after a ScreenCaptureKit failure, and never performs input when both backends fail. MJA stores the minimal patch, reproducible build script, signed-off metadata, license notice, and built dylib; setup overlays the dylib only after validating the exact official base version and digest.

**Tech Stack:** Objective-C++17, CoreGraphics/ApplicationServices, ScreenCaptureKit, OpenCV, CMake/Ninja, Bash, Python 3.14, pytest, MaaFramework 5.12.2, MFAAvalonia 2.13.0-beta.5.

## Global Constraints

- Never modify `/Users/gaoguobin/project/MaaFramework`; it contains user changes. Build from a separate clean v5.12.2 clone or archive.
- Never stage or commit `AGENTS.md`. Every commit command below uses explicit paths.
- Keep the ProjectInterface controller type and configuration as `MacOS` + `ScreenCaptureKit` + `GlobalEvent` so MaaPiCli and MFAAvalonia use the same ABI and configuration.
- CoreGraphics remains subject to macOS Screen Recording permission. A permission failure is a hard runtime failure, not a bypass opportunity.
- Capture the on-screen window rectangle with `kCGNullWindowID`; do not use `kCGWindowListOptionIncludingWindow`, which is known to fail for this iOS compatibility window.
- Use `kCGWindowImageNominalResolution`; the returned image must remain in logical window coordinates.
- A minimized, hidden, transparent, non-layer-zero, missing, resized, or occluded window must fail safely. Live probes run from an already authorized Terminal host and keep the game foreground.
- Generated evidence under `diagnostics/` and build scratch directories stay untracked.

---

### Task 1: Define the native patch-bundle contract

**Files:**

- Create: `native/maafw-macos-fallback/README.md`
- Create: `tools/native_bundle.py`
- Create: `vendor/maafw/v5.12.2/macos-arm64/SOURCE.md`
- Create: `vendor/maafw/v5.12.2/macos-arm64/LICENSE.md`
- Create: `tests/test_native_patch_bundle.py`

**Interfaces:**

```python
# tests/test_native_patch_bundle.py exercises this committed JSON shape.
class PatchedControlUnitManifest(TypedDict):
    schema_version: Literal[1]
    upstream_repository: Literal["https://github.com/MaaXYZ/MaaFramework"]
    upstream_tag: Literal["v5.12.2"]
    target: Literal["macos-arm64"]
    base_library_sha256: str
    patch_sha256: str
    patched_library_sha256: str
    patched_library_size: int

def load_patched_bundle(bundle_root: Path, *, require_library: bool) -> PatchedBundle: ...
```

- [ ] **Step 1: Add failing manifest-parser tests**

```python
def test_manifest_parser_accepts_a_digest_bound_temp_bundle(tmp_path: Path) -> None:
    library = tmp_path / "libMaaMacOSControlUnit.dylib"
    library.write_bytes(b"arm64-test-library")
    write_manifest_for_test(tmp_path, library)
    bundle = load_patched_bundle(tmp_path, require_library=True)
    assert bundle.library == library
```

- [ ] **Step 2: Run the test and confirm the missing module failure**

Run: `install/.venv/bin/python -m pytest tests/test_native_patch_bundle.py -q`

Expected: FAIL because `tools.native_bundle` does not exist.

- [ ] **Step 3: Implement strict manifest and optional-library validation**

Reject unknown/missing fields, wrong schema/tag/target, malformed lowercase SHA-256 values, Boolean/nonpositive size, symlinked files, path escapes, missing source/license notices, and a library whose size or digest does not match. `require_library=False` validates schema and notices without requiring the later build output.

- [ ] **Step 4: Write the source and license notices**

Record the upstream repository, exact tag, local build command, patch path, target architecture, and MaaFramework license. Copy the exact upstream `LICENSE.md` text from the clean v5.12.2 snapshot into the vendor directory; do not paraphrase the license.

- [ ] **Step 5: Run parser tests and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_native_patch_bundle.py -q
install/.venv/bin/python -m ruff check tools/native_bundle.py tests/test_native_patch_bundle.py
```

Expected: all parser and notice checks pass without requiring a committed dylib.

- [ ] **Step 6: Commit the contract and notices**

```bash
git add -- native/maafw-macos-fallback/README.md \
  tools/native_bundle.py \
  vendor/maafw/v5.12.2/macos-arm64/SOURCE.md \
  vendor/maafw/v5.12.2/macos-arm64/LICENSE.md \
  tests/test_native_patch_bundle.py
git commit -m "test: define macOS control-unit bundle contract"
```

### Task 2: Implement connection-local ScreenCaptureKit fallback

**Files:**

- Create through patch: `source/MaaMacOSControlUnit/Screencap/ScreenCaptureKitScreencap.h`
- Create through patch: `source/MaaMacOSControlUnit/Screencap/ScreenCaptureKitScreencap.mm`
- Update: `native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch`
- Update: `tests/test_native_patch_bundle.py`

**Interfaces:**

```cpp
class ScreenCaptureKitScreencap : public ScreencapBase
{
public:
    enum class CaptureBackend { ScreenCaptureKit, CoreGraphicsRegion };
    explicit ScreenCaptureKitScreencap(uint32_t window_id);
    std::optional<cv::Mat> screencap() override;

private:
    std::optional<cv::Mat> screencap_window_screen_capture_kit(uint32_t wid);
    std::optional<cv::Mat> screencap_window_core_graphics(uint32_t wid);
    std::optional<cv::Mat> screencap_display();
    CaptureBackend backend_ = CaptureBackend::ScreenCaptureKit;
    uint32_t window_id_ = 0;
};
```

- [ ] **Step 1: Strengthen the failing static contract test**

Assert that the committed patch contains these exact semantic anchors:

```python
required = {
    "CaptureBackend::CoreGraphicsRegion",
    "kCGWindowListOptionOnScreenOnly",
    "kCGNullWindowID",
    "kCGWindowImageBoundsIgnoreFraming",
    "kCGWindowImageNominalResolution",
    "kCGWindowLayer",
    "kCGWindowAlpha",
    "cv::COLOR_BGRA2BGR",
}
assert required <= set(extract_added_tokens(patch_text))
assert "kCGWindowListOptionIncludingWindow" not in extract_added_lines(patch_text)
```

- [ ] **Step 2: Run the focused test and observe the missing anchors**

Run: `install/.venv/bin/python -m pytest tests/test_native_patch_bundle.py -q`

Expected: FAIL because the patch does not yet implement and validate the fallback.

- [ ] **Step 3: Create a clean source tree without touching the reference checkout**

Run from the MJA root:

```bash
MJA_NATIVE_WORKTREE="$(mktemp -d /tmp/mja-maafw-v5.12.2.XXXXXX)"
git clone --no-local --branch v5.12.2 --depth 1 \
  /Users/gaoguobin/project/MaaFramework "$MJA_NATIVE_WORKTREE/source"
git -C "$MJA_NATIVE_WORKTREE/source" status --short
```

Expected: the final command prints nothing. Keep this task-specific variable; never reuse `HOME` or another system variable.

- [ ] **Step 4: Implement exact-window and occlusion validation**

In the clean source, enumerate `CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)` and select the dictionary whose `kCGWindowNumber` matches `wid`. Require layer `0`, alpha greater than `0`, `kCGWindowIsOnscreen == true`, positive bounds, width greater than height, and dimensions within `640..4096` by `360..2160`. Cache the first accepted bounds and reject position or size drift for the rest of this connection. Before capture, reject an earlier layer-zero window from another owner whose nonempty bounds intersect the target rectangle; this prevents returning a composited image of an obscured game. Return `std::nullopt` on every validation failure.

- [ ] **Step 5: Implement nominal-resolution visible-region capture**

Use the validated `CGRect` with:

```objective-c++
CGImageRef image = CGWindowListCreateImage(
    bounds,
    kCGWindowListOptionOnScreenOnly,
    kCGNullWindowID,
    kCGWindowImageBoundsIgnoreFraming | kCGWindowImageNominalResolution);
```

Allocate an owned BGRA buffer, draw with a deterministic device-RGB bitmap context, construct a `CV_8UC4` matrix with the real row stride, convert to owned BGR pixels, and release every CoreFoundation/CoreGraphics object on all paths. Reject an empty image or dimensions different from rounded logical bounds.

- [ ] **Step 6: Implement one-way fallback for the current connection**

Use this exact decision rule:

```cpp
if (backend_ == CaptureBackend::CoreGraphicsRegion) {
    return screencap_window_core_graphics(window_id_);
}
if (auto image = screencap_window_screen_capture_kit(window_id_)) {
    return image;
}
if (auto image = screencap_window_core_graphics(window_id_)) {
    backend_ = CaptureBackend::CoreGraphicsRegion;
    LogWarn << "MJA screencap backend switched to CoreGraphicsRegion";
    return image;
}
return std::nullopt;
```

Do not switch back within the same object. A new controller connection constructs a new object and starts from ScreenCaptureKit.

- [ ] **Step 7: Export the minimal patch**

Generate a zero-context-independent Git patch containing only the two screencap files, place it at the committed patch path, and confirm `git diff --check` succeeds in the clean source before export.

- [ ] **Step 8: Run static tests**

Run: `install/.venv/bin/python -m pytest tests/test_native_patch_bundle.py -q`

Expected: all patch semantic checks pass; this task does not yet assert the built dylib.

- [ ] **Step 9: Commit the native source patch**

```bash
git add -- native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch \
  tests/test_native_patch_bundle.py
git commit -m "fix: add CoreGraphics macOS capture fallback patch"
```

### Task 3: Build and attest the patched arm64 dylib reproducibly

**Files:**

- Create: `native/maafw-macos-fallback/build.sh`
- Update: `native/maafw-macos-fallback/README.md`
- Create: `vendor/maafw/v5.12.2/macos-arm64/libMaaMacOSControlUnit.dylib`
- Create: `vendor/maafw/v5.12.2/macos-arm64/manifest.json`
- Update: `tests/test_native_patch_bundle.py`

**Interfaces:**

```text
native/maafw-macos-fallback/build.sh \
  --source /absolute/clean/MaaFramework-v5.12.2 \
  --official-bin /absolute/official-v5.12.2/bin \
  --output /absolute/MJA/vendor/maafw/v5.12.2/macos-arm64
```

- [ ] **Step 1: Add failing build-script and committed-bundle tests**

Test `--help`, rejection of a dirty source tree, rejection of a tag other than `v5.12.2`, rejection of non-arm64 output, rejection when the official base dylib is absent, deterministic manifest field ordering, and `load_patched_bundle` against the committed vendor directory.

- [ ] **Step 2: Run the focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_native_patch_bundle.py -q`

Expected: FAIL because `build.sh` and its attested output do not exist.

- [ ] **Step 3: Implement the guarded build script**

The script must use `set -euo pipefail`, resolve all three absolute paths, verify the source tag with `git describe --tags --exact-match`, require an empty `git status --porcelain` before applying the patch, run `git submodule update --init --recursive`, run `python3 tools/maadeps-download.py`, then run:

```bash
cmake --preset NinjaMulti -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build build --config Release --target MaaMacOSControlUnit
```

Use `file` and `lipo -archs` to require a Mach-O arm64 dylib. Apply a local ad-hoc signature with `/usr/bin/codesign --force --sign - --timestamp=none`, verify it with `/usr/bin/codesign --verify --strict`, and only then compute the base official dylib digest, patch digest, signed output digest, and signed output size with `/usr/bin/shasum -a 256` and `/usr/bin/stat -f %z`. Atomically replace the vendor binary and manifest only after every check succeeds.

- [ ] **Step 4: Build from the clean snapshot**

Extract the official v5.12.2 archive already pinned by `runtime-manifest.json`, pass its `bin` directory as `--official-bin`, and execute the script from the MJA checkout. The output must contain only arm64 and link successfully against the official runtime dependencies.

- [ ] **Step 5: Verify the binary and metadata**

Run:

```bash
install/.venv/bin/python -m pytest tests/test_native_patch_bundle.py -q
file vendor/maafw/v5.12.2/macos-arm64/libMaaMacOSControlUnit.dylib
lipo -archs vendor/maafw/v5.12.2/macos-arm64/libMaaMacOSControlUnit.dylib
/usr/bin/codesign --verify --strict \
  vendor/maafw/v5.12.2/macos-arm64/libMaaMacOSControlUnit.dylib
```

Expected: all tests pass; `file` reports a dynamically linked shared library and `lipo` reports exactly `arm64`.

- [ ] **Step 6: Commit the reproducible build and attested artifact**

```bash
git add -- native/maafw-macos-fallback/build.sh \
  native/maafw-macos-fallback/README.md \
  vendor/maafw/v5.12.2/macos-arm64/libMaaMacOSControlUnit.dylib \
  vendor/maafw/v5.12.2/macos-arm64/manifest.json \
  tests/test_native_patch_bundle.py
git commit -m "build: bundle attested macOS control unit"
```

### Task 4: Overlay the patched dylib only on the exact official base

**Files:**

- Update: `tools/setup.py`
- Update: `tests/test_setup.py`

**Interfaces:**

```python
def sha256_file(path: Path) -> str: ...

def overlay_patched_macos_control_unit(
    install_root: Path,
    *,
    bundle_root: Path,
) -> None: ...
```

- [ ] **Step 1: Add failing setup tests**

Cover: exact base digest overlays both `install/libMaaMacOSControlUnit.dylib` and `install/runtime/maafw/bin/libMaaMacOSControlUnit.dylib`; wrong base digest changes neither file; wrong Maa version stops; tampered vendor binary stops; staging files are removed after success and failure.

- [ ] **Step 2: Run the focused setup tests**

Run: `install/.venv/bin/python -m pytest tests/test_setup.py -q`

Expected: FAIL because setup currently copies only official runtime files.

- [ ] **Step 3: Implement digest-bound overlay**

Read the vendor manifest, verify schema/tag/target, verify the installed version file is `5.12.2`, hash both official installed copies, and require both to equal `base_library_sha256`. Hash and size-check the vendor dylib, copy it to sibling `.staging` files, fsync, then atomically replace both destinations. If any precondition fails, leave both official copies untouched.

- [ ] **Step 4: Call the overlay at the correct point**

Invoke it in `assemble_install` after the MaaFramework archive has been copied and versioned, but before ProjectInterface resources are copied and before `verify_install` runs.

- [ ] **Step 5: Run setup tests and the existing regression suite**

Run:

```bash
install/.venv/bin/python -m pytest tests/test_setup.py tests/test_verify_install.py -q
install/.venv/bin/python -m pytest -q
```

Expected: focused and full suites pass.

- [ ] **Step 6: Commit setup overlay support**

```bash
git add -- tools/setup.py tests/test_setup.py
git commit -m "feat: install patched macOS control unit safely"
```

### Task 5: Verify installed dylib identity and linkage

**Files:**

- Update: `tools/verify_install.py`
- Update: `tests/test_verify_install.py`

**Interfaces:**

```python
def verify_patched_control_unit(
    install_root: Path,
    *,
    bundle_root: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> list[str]: ...
```

- [ ] **Step 1: Add failing verification tests**

Cover missing root dylib, mismatched runtime copy, wrong patched digest, wrong byte size, missing arm64 slice, failed ad-hoc signature verification, and an `otool -L` result that lacks ApplicationServices or ScreenCaptureKit.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `install/.venv/bin/python -m pytest tests/test_verify_install.py -q`

Expected: FAIL because installed patched-library checks are absent.

- [ ] **Step 3: Implement static and Mach-O verification**

Compare both installed dylibs byte-for-byte to the attested vendor digest and size. Under runtime checks, call `/usr/bin/file`, `/usr/bin/lipo -archs`, `/usr/bin/codesign --verify --strict`, and `/usr/bin/otool -L` through the injected runner; require arm64, a valid local signature, and the frameworks/libraries needed by the patched implementation.

- [ ] **Step 4: Reassemble from the current checkout**

Run:

```bash
install/.venv/bin/python -m tools.setup --root "$PWD"
install/.venv/bin/python -m tools.verify_install "$PWD/install"
```

Expected: setup completes and install verification reports no errors.

- [ ] **Step 5: Commit installed-runtime verification**

```bash
git add -- tools/verify_install.py tests/test_verify_install.py
git commit -m "test: verify patched macOS control unit identity"
```

### Task 6: Expose one explicit native permission-request command

**Files:**

- Create: `tools/request_permissions.py`
- Create: `tests/test_request_permissions.py`
- Update: `agent/macos/permissions.py`
- Update: `tests/test_permissions.py`

**Interfaces:**

```python
def request_native_permissions(
    *,
    request: Callable[[], None] = request_permissions,
    verify: Callable[[], None] = ensure_permissions,
) -> None: ...
```

- [ ] **Step 1: Add failing explicit-request tests**

Prove request occurs before verification, request exceptions map to a stable nonzero exit, verification failure tells the user to enable the requesting host in System Settings, and ordinary `pretask`/Agent execution never imports or calls this command.

- [ ] **Step 2: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_request_permissions.py tests/test_permissions.py tests/test_pretask.py -q`

Expected: FAIL because the explicit command does not exist.

- [ ] **Step 3: Implement the one-shot command**

Call `CGRequestScreenCaptureAccess()` and `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})` only through the existing `request_permissions()` function, then run nonprompting verification. Print which permission still needs System Settings when macOS requires the host to restart. Do not loop, poll, alter TCC databases, or toggle System Settings controls.

- [ ] **Step 4: Run tests and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_request_permissions.py tests/test_permissions.py tests/test_pretask.py -q
install/.venv/bin/python -m ruff check tools/request_permissions.py agent/macos/permissions.py \
  tests/test_request_permissions.py tests/test_permissions.py
```

Expected: all checks pass.

- [ ] **Step 5: Exercise the native prompt only when needed**

From the exact Terminal or MFAAvalonia host intended for live execution, run `install/.venv/bin/python -m tools.request_permissions`. The user handles only the native macOS confirmation window. If access was already granted, the command must complete without manufacturing a second prompt.

- [ ] **Step 6: Commit the explicit permission path**

```bash
git add -- tools/request_permissions.py tests/test_request_permissions.py \
  agent/macos/permissions.py tests/test_permissions.py
git commit -m "feat: add explicit macOS permission request command"
```

### Task 7: Add a read-only 50-frame controller probe

**Files:**

- Create: `tools/verify_macos_controller.py`
- Create: `tests/test_verify_macos_controller.py`
- Update: `agent/errors.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ProbeResult:
    window_id: int
    frames: int
    width: int
    height: int
    nonempty_frames: int
    backend: Literal["ScreenCaptureKit", "CoreGraphicsRegion"]

def probe_controller(
    window_id: int,
    *,
    frames: int = 50,
    controller_factory: Callable[[int], Any] | None = None,
    log_path: Path | None = None,
) -> ProbeResult: ...
```

- [ ] **Step 1: Add failing unit tests with a fake controller**

Cover 50 stable frames, first-frame empty data, dimension drift, connection failure, a fallback log transition appearing exactly once, and rejection when the log reports repeated ScreenCaptureKit retries after fallback.

- [ ] **Step 2: Run the focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_verify_macos_controller.py -q`

Expected: FAIL because the probe does not exist.

- [ ] **Step 3: Implement the read-only probe**

Connect a standard `MacOSController`, set short side `720`, capture exactly the requested number of frames without any click/swipe/key call, require positive equal dimensions and nonzero pixel variance, and parse the run-local Maa log for the backend transition marker. Write the result as JSON to stdout and return nonzero with a stable `MJAError` code on failure.

- [ ] **Step 4: Run unit and lint checks**

Run:

```bash
install/.venv/bin/python -m pytest tests/test_verify_macos_controller.py -q
install/.venv/bin/python -m ruff check tools/verify_macos_controller.py tests/test_verify_macos_controller.py agent/errors.py
```

Expected: tests and Ruff pass.

- [ ] **Step 5: Run the live read-only probe from an authorized Terminal**

Bring the game fully foreground and unobscured, resolve its current layer-zero window ID, and run:

```bash
install/.venv/bin/python -m tools.verify_macos_controller \
  --window-id "$MJA_GAME_WINDOW_ID" \
  --frames 50 \
  --evidence-root diagnostics/controller-probe
```

Expected: 50/50 nonempty frames, one stable logical size, and exactly one switch to `CoreGraphicsRegion` on the current machine. Save stdout JSON, Maa log, first frame, and last frame in the evidence directory.

- [ ] **Step 6: Verify safe failure modes**

Repeat with an invalid window ID and confirm no input event occurs. Then, with Computer Use visual evidence, test minimized and deliberately obscured states separately; each must fail before any task action and preserve its screenshot/log. Restore the game and prior foreground application after each probe.

- [ ] **Step 7: Commit the controller probe**

```bash
git add -- tools/verify_macos_controller.py tests/test_verify_macos_controller.py agent/errors.py
git commit -m "test: add macOS controller stability probe"
```

### Task 8: Regress the existing mail navigation loop on the patched runtime

**Files:**

- Update: `tools/capture_templates.py`
- Update: `tests/test_capture_templates.py`
- Create: `assets/resource/calibration.json`
- Update: `assets/resource/pipeline/mail_smoke_test.json`
- Update from live captures: `assets/resource/image/home/*.png`
- Update from live captures: `assets/resource/image/panel/*.png`
- Update from live captures: `assets/resource/image/mail/*.png`
- Create: `docs/verification/macos-controller-mail-regression.md`

**Interfaces:**

```python
def capture_screen(
    window_id: int,
    *,
    expected_short_side: int = 720,
    controller_factory: Callable[[int], Any] | None = None,
) -> Image.Image: ...

@dataclass(frozen=True, slots=True)
class CaptureCalibration:
    logical_window_size: tuple[int, int]
    maa_capture_size: tuple[int, int]
    display_short_side: int
```

- [ ] **Step 1: Add failing tests for non-1280 logical captures**

Replace the fixed `1280x720` assumption with validation that the short side is 720 after Maa scaling and that crop profiles use an explicit calibrated MAA capture size. Cover the current `1051x820` nominal input before Maa scaling and its expected `923x720` aspect-preserving output, a true 1280x720 resizable window, and a dimension mismatch.

- [ ] **Step 2: Run the focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_capture_templates.py -q`

Expected: FAIL because the current helper requires exactly `1280x720` at capture time.

- [ ] **Step 3: Implement dimension-aware capture and crop mapping**

Read the verified logical and MAA output sizes into `CaptureCalibration`; do not assume the iOS window accepted the requested 1280x720 resize. Keep committed templates and pipeline ROIs in the exact calibrated MAA output coordinate system produced by the patched controller. Reject aspect-ratio drift greater than one percent and reject a live size that differs from committed calibration.

- [ ] **Step 4: Recalibrate mail assets from the patched controller**

Run the read-only capture helper on the real home, function-panel, and mail pages. Write the observed logical and MAA sizes to `assets/resource/calibration.json`, recrop all seven templates from those frames, and update every ROI in `mail_smoke_test.json` to the same coordinate system. Review each crop visually and confirm it contains no claim/reward/payment target.

- [ ] **Step 5: Run all automated regressions**

Run:

```bash
install/.venv/bin/python -m pytest -q
install/.venv/bin/python -m ruff check agent tools tests
install/.venv/bin/python -m tools.verify_install install
```

Expected: all commands pass.

- [ ] **Step 6: Run the existing `mail_smoke_test` live**

From an authorized Terminal and the freshly assembled checkout, capture full-screen and MAA images before input, run only `mail_smoke_test`, and verify the exact path `home -> function panel -> mail -> function panel -> home`. This task must not click `全部领取` or any reward control.

- [ ] **Step 7: Verify restoration and record evidence**

Confirm the final page is home, the game window ID and bounds remain the prepared values, the previously foreground application is restored, and Maa logs show the cached fallback rather than repeated ScreenCaptureKit failures. Record evidence paths and exact commands in the verification document.

- [ ] **Step 8: Commit the verified regression changes**

```bash
git add -- tools/capture_templates.py tests/test_capture_templates.py \
  assets/resource/calibration.json assets/resource/pipeline/mail_smoke_test.json \
  assets/resource/image/home assets/resource/image/panel assets/resource/image/mail \
  docs/verification/macos-controller-mail-regression.md
git commit -m "test: verify mail loop with macOS capture fallback"
```

### Task 9: Final capture-fallback quality gate

**Files:**

- Verify only; no expected source changes.

**Interfaces:** none.

- [ ] **Step 1: Verify the reference worktree is untouched**

Run: `git -C /Users/gaoguobin/project/MaaFramework status --short`

Expected: it still shows only the user's pre-existing changes; no MJA implementation file appears there.

- [ ] **Step 2: Run the complete gate**

```bash
git diff --check
install/.venv/bin/python -m pytest -q
install/.venv/bin/python -m ruff check agent tools tests
install/.venv/bin/python -m tools.verify_install install
git status --short
```

Expected: checks pass and `git status --short` contains only the user's `AGENTS.md` modification plus any intentionally uncommitted local evidence under ignored paths.

- [ ] **Step 3: Confirm acceptance evidence**

Require the attested dylib manifest, successful 50-frame probe, invalid/minimized/occluded safe failures, and the patched-runtime mail loop evidence before starting the workflow-foundation plan.
