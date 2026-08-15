from __future__ import annotations

from pathlib import Path

from tools.mfw_pyqt6_patch import (
    PatchResult,
    apply_mfw_pyqt6_runtime_patch,
    is_pyinstaller_executable,
    verify_mfw_pyqt6_runtime_patch,
)


def test_fake_runtime_is_not_treated_as_pyinstaller(tmp_path: Path) -> None:
    runtime = tmp_path / "MFW"
    runtime.write_bytes(b"test-runtime")

    assert not is_pyinstaller_executable(runtime)
    assert apply_mfw_pyqt6_runtime_patch(runtime) == PatchResult(
        "skipped", False, False, "not a PyInstaller executable"
    )
    assert verify_mfw_pyqt6_runtime_patch(runtime) is True


def test_runtime_patch_provenance_is_checked_in() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "native/mfw-pyqt6/README.md").read_text(encoding="utf-8")
    patch = (
        root / "native/mfw-pyqt6/patches/0001-return-false-on-task-failure.patch"
    ).read_text(encoding="utf-8")

    assert "Python 3.12" in readme
    assert "no external watchdog" in readme
    assert "-            return\n+            return False" in patch
