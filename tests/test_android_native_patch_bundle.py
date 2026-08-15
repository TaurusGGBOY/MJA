from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "native/maafw-android-cli/build.sh"
PATCH = ROOT / "native/maafw-android-cli/patches/0001-plain-adb-defaults.patch"


def test_android_patch_bundle_is_pinned_and_supports_android_15_orientation() -> None:
    patch = PATCH.read_text(encoding="utf-8")
    assert "source/MaaPiCli/Impl/Runner.cpp" in patch
    assert "source/MaaAdbControlUnit/General/DeviceInfo.cpp" in patch
    assert "f625a60edeccd4549f9a71c0f74628d827ade8fb" in SCRIPT.read_text(encoding="utf-8")
    assert "MaaAdbScreencapMethod_Default" in patch
    assert "adb_param.input = MaaAdbInputMethod_Default;" in patch
    assert "MaaAdbInputMethod_AdbShell" not in patch
    assert "MaaAdbInputMethod_Maatouch" not in patch
    assert "MaaAdbInputMethod_MinitouchAndAdbKey" not in patch
    assert 'adb_param.config = "{}"' in patch
    assert "mDisplayRotation=ROTATION_" in patch
    script = SCRIPT.read_text(encoding="utf-8")
    assert "adb_control_unit_sha256" in script
    assert "adb_control_unit_size" in script
    assert patch.count("diff --git ") == 2


def test_android_build_script_help_is_available() -> None:
    result = subprocess.run(
        [os.fspath(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--source" in result.stdout
    assert "--official-bin" in result.stdout
    assert "--output" in result.stdout


def test_android_build_script_rejects_reference_checkout(tmp_path: Path) -> None:
    official_bin = tmp_path / "official-bin"
    official_bin.mkdir()
    (official_bin / "MaaPiCli").write_bytes(b"reference-placeholder")
    result = subprocess.run(
        [
            os.fspath(SCRIPT),
            "--source",
            "/Users/gaoguobin/project/MaaFramework",
            "--official-bin",
            os.fspath(official_bin),
            "--output",
            os.fspath(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "reference MaaFramework checkout" in result.stderr


def test_android_patch_applies_to_clean_v5122_source(tmp_path: Path) -> None:
    source_root = os.environ.get("MJA_MAAFRAME_V5122_SOURCE")
    if not source_root:
        pytest.skip("set MJA_MAAFRAME_V5122_SOURCE for clean-source integration test")
    clone = tmp_path / "source"
    subprocess.run(
        ["git", "clone", "--no-local", "--quiet", source_root, os.fspath(clone)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", os.fspath(clone), "apply", "--check", os.fspath(PATCH)],
        check=True,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ["git", "-C", os.fspath(clone), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""
