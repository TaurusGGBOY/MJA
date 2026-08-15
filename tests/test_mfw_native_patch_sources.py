from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_ROOT = ROOT / "native/maafw-macos-fallback/patches"


def _added_lines(name: str) -> str:
    text = (PATCH_ROOT / name).read_text(encoding="utf-8")
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def test_window_finder_uses_coregraphics_metadata_without_screen_capturekit() -> None:
    added = _added_lines("0002-macos-coregraphics-window-finder.patch")

    assert "CGWindowListCopyWindowInfo(kCGWindowListOptionAll" in added
    assert "kCGWindowIsOnscreen" in added
    assert "SCShareableContent" not in added
    assert "bounds.size.width > bounds.size.height" in added


def test_preflight_patch_keeps_screen_capturekit_as_first_choice() -> None:
    added = _added_lines("0003-macos-coregraphics-preflight.patch")

    assert "CGPreflightScreenCaptureAccess()" in added
    assert "CGRequestScreenCaptureAccess()" in added
    assert "std::call_once" in added
    assert "trying ScreenCaptureKit before fallback" in added
    assert "return screencap_window_core_graphics(window_id_)" not in added


def test_capture_guard_rejects_unsafe_cross_space_coregraphics_fallback() -> None:
    added = _added_lines("0004-macos-coregraphics-capture-guard.patch")

    assert "bool has_onscreen_state = false;" in added
    assert "target_is_full_screen" in added
    assert "cannot capture a window in another Space" in added


def test_build_script_pins_version_and_strips_build_rpaths() -> None:
    script = (ROOT / "native/maafw-macos-fallback/build-v5123.sh").read_text(
        encoding="utf-8"
    )

    assert 'MAA_RUNTIME_VERSION="v5.12.2"' in script
    assert "-DENABLE_HASH_VERSION=ON" in script
    assert '-DMAA_HASH_VERSION="$MAA_RUNTIME_VERSION"' in script
    assert "install_name_tool -delete_rpath" in script
    assert "absolute build RPATH remains" in script
