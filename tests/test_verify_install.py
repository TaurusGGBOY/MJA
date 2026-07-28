from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

from tools.verify_install import verify_install, verify_patched_control_unit

CONTROL_UNIT_NAME = "libMaaMacOSControlUnit.dylib"
NOTICE_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "maafw" / "v5.12.2" / "macos-arm64"


def test_missing_required_file_is_reported(tmp_path: Path) -> None:
    errors = verify_install(tmp_path, run_runtime_checks=False)
    assert "missing interface.json" in errors
    assert "missing .venv/bin/python3" in errors
    assert "missing MaaPiCli" in errors


def _make_control_unit_bundle(root: Path, payload: bytes = b"patched-control-unit") -> Path:
    root.mkdir(parents=True)
    shutil.copy2(NOTICE_ROOT / "SOURCE.md", root / "SOURCE.md")
    shutil.copy2(NOTICE_ROOT / "LICENSE.md", root / "LICENSE.md")
    library = root / CONTROL_UNIT_NAME
    library.write_bytes(payload)
    manifest = {
        "schema_version": 1,
        "upstream_repository": "https://github.com/MaaXYZ/MaaFramework",
        "upstream_tag": "v5.12.2",
        "target": "macos-arm64",
        "base_library_sha256": "1" * 64,
        "patch_sha256": "2" * 64,
        "patched_library_sha256": hashlib.sha256(payload).hexdigest(),
        "patched_library_size": len(payload),
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _make_complete_install(root: Path) -> Path:
    (root / ".venv/bin").mkdir(parents=True)
    python = root / ".venv/bin/python3"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(python.stat().st_mode | os.X_OK)
    (root / "MaaPiCli").write_text("binary")
    (root / "MaaPiCli").chmod(0o755)
    (root / "MFAAvalonia.app/Contents/MacOS").mkdir(parents=True)
    (root / "MFAAvalonia.app/Contents/MacOS/MFAAvalonia").write_text("binary")
    (root / "interface.json").write_text(json.dumps({"resource": "resource"}))
    (root / "resource").mkdir()
    (root / "agent").mkdir()
    (root / "runtime/maafw").mkdir(parents=True)
    (root / "runtime/mfa").mkdir(parents=True)
    (root / "runtime/maafw/VERSION").write_text("5.12.2\n")
    (root / "runtime/mfa/VERSION").write_text("2.13.0-beta.5\n")
    bundle_root = _make_control_unit_bundle(root / "bundle")
    payload = (bundle_root / CONTROL_UNIT_NAME).read_bytes()
    (root / CONTROL_UNIT_NAME).write_bytes(payload)
    runtime_library = root / "runtime/maafw/bin" / CONTROL_UNIT_NAME
    runtime_library.parent.mkdir(parents=True)
    runtime_library.write_bytes(payload)
    native_library = root / "runtimes/osx-arm64/native" / CONTROL_UNIT_NAME
    native_library.parent.mkdir(parents=True)
    native_library.write_bytes(payload)
    python_library = (
        root / ".venv/lib/python3.14/site-packages/maa/bin" / CONTROL_UNIT_NAME
    )
    python_library.parent.mkdir(parents=True)
    python_library.write_bytes(payload)
    return bundle_root


def test_complete_install_passes_static_checks(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    result = verify_install(
        tmp_path,
        run_runtime_checks=False,
        cliclick_path=tmp_path / "cliclick",
    )
    assert result == []


def test_interface_template_reference_is_reported(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    (tmp_path / "interface.json").write_text(
        json.dumps({"resource": "resource", "pipeline": "resource/pipeline.json"})
    )
    assert "missing resource/pipeline.json" in verify_install(
        tmp_path,
        run_runtime_checks=False,
        cliclick_path=tmp_path / "cliclick",
    )


def test_pipeline_forbids_unapproved_input_actions(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    pipeline = tmp_path / "resource/pipeline.json"
    pipeline.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_text(json.dumps({"click": {"action": "Click"}}))

    errors = verify_install(
        tmp_path,
        run_runtime_checks=False,
        cliclick_path=tmp_path / "cliclick",
    )
    assert any("forbidden input action" in item for item in errors)


def test_runtime_checks_use_injected_runner(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        tool = Path(argv[0]).name
        if tool == "file":
            return SimpleNamespace(
                returncode=0,
                stdout="Mach-O 64-bit dynamically linked shared library arm64",
                stderr="",
            )
        if tool == "lipo":
            return SimpleNamespace(returncode=0, stdout="arm64", stderr="")
        if tool == "otool":
            return SimpleNamespace(
                returncode=0,
                stdout="ApplicationServices ScreenCaptureKit CoreGraphics",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    cliclick = tmp_path / "cliclick"
    cliclick.write_text("binary")
    cliclick.chmod(0o755)
    assert verify_install(
        tmp_path,
        runner=runner,
        cliclick_path=cliclick,
        bundle_root=bundle_root,
    ) == []
    assert any("import maa" in " ".join(argv) for argv in calls)


def _native_runner(
    *,
    archs: str = "arm64",
    signature_returncode: int = 0,
    linkage: str = "ApplicationServices ScreenCaptureKit CoreGraphics",
) -> tuple[list[list[str]], object]:
    calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        tool = Path(argv[0]).name
        if tool == "file":
            return SimpleNamespace(
                returncode=0,
                stdout="Mach-O 64-bit dynamically linked shared library arm64",
                stderr="",
            )
        if tool == "lipo":
            return SimpleNamespace(returncode=0, stdout=archs, stderr="")
        if tool == "codesign":
            return SimpleNamespace(returncode=signature_returncode, stdout="", stderr="")
        if tool == "otool":
            return SimpleNamespace(returncode=0, stdout=linkage, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return calls, runner


def test_verify_patched_control_unit_reports_missing_root_copy(tmp_path: Path) -> None:
    bundle_root = _make_control_unit_bundle(tmp_path / "bundle")
    (tmp_path / "runtime/maafw/bin").mkdir(parents=True)
    (tmp_path / "runtime/maafw/bin" / CONTROL_UNIT_NAME).write_bytes(
        (bundle_root / CONTROL_UNIT_NAME).read_bytes()
    )

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root)

    assert any("missing root control-unit dylib" in error for error in errors)


def test_verify_patched_control_unit_reports_mismatched_runtime_copy(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    (tmp_path / "runtime/maafw/bin" / CONTROL_UNIT_NAME).write_bytes(b"tampered")

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root)

    assert any("runtime control-unit" in error and "mismatch" in error for error in errors)


def test_verify_patched_control_unit_reports_wrong_attested_digest(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    manifest_path = bundle_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["patched_library_sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root)

    assert any("patched library SHA-256 mismatch" in error for error in errors)


def test_verify_patched_control_unit_reports_wrong_attested_size(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    manifest_path = bundle_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["patched_library_size"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root)

    assert any("patched library size mismatch" in error for error in errors)


def test_verify_patched_control_unit_requires_arm64(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    _, runner = _native_runner(archs="x86_64")

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root, runner=runner)

    assert any("missing the arm64 architecture" in error for error in errors)


def test_verify_patched_control_unit_requires_a_valid_signature(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    _, runner = _native_runner(signature_returncode=1)

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root, runner=runner)

    assert any("signature verification failed" in error for error in errors)


def test_verify_patched_control_unit_requires_patched_framework_linkage(tmp_path: Path) -> None:
    bundle_root = _make_complete_install(tmp_path)
    _, runner = _native_runner(
        linkage="/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )

    errors = verify_patched_control_unit(tmp_path, bundle_root=bundle_root, runner=runner)

    assert any("missing ApplicationServices linkage" in error for error in errors)
    assert any("missing ScreenCaptureKit linkage" in error for error in errors)
