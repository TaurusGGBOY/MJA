from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.setup import (
    _assemble_install_in_place,
    assemble_install,
    assert_supported_platform,
    build_android_maapi_cli,
    ensure_venv,
    extract_archive,
    overlay_patched_macos_control_unit,
    _preserved_android_control_unit,
    stream_download,
    sync_project_payload,
    verify_download,
)

NOTICE_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "maafw" / "v5.12.2" / "macos-arm64"
CONTROL_UNIT_NAME = "libMaaMacOSControlUnit.dylib"


@pytest.fixture(autouse=True)
def _test_official_base_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.setup.OFFICIAL_BASE_LIBRARY_SHA256",
        hashlib.sha256(b"official-base").hexdigest(),
    )


def _make_bundle(bundle_root: Path, base: bytes, patched: bytes) -> Path:
    bundle_root.mkdir(parents=True)
    for notice_name in ("SOURCE.md", "LICENSE.md"):
        shutil.copyfile(NOTICE_ROOT / notice_name, bundle_root / notice_name)
    (bundle_root / CONTROL_UNIT_NAME).write_bytes(patched)
    (bundle_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "upstream_repository": "https://github.com/MaaXYZ/MaaFramework",
                "upstream_tag": "v5.12.2",
                "target": "macos-arm64",
                "base_library_sha256": hashlib.sha256(base).hexdigest(),
                "patch_sha256": hashlib.sha256(b"patch").hexdigest(),
                "patched_library_sha256": hashlib.sha256(patched).hexdigest(),
                "patched_library_size": len(patched),
            }
        ),
        encoding="utf-8",
    )
    return bundle_root


def _make_install(install_root: Path, base: bytes, version: str = "5.12.2\n") -> Path:
    runtime_root = install_root / "runtime" / "maafw"
    (runtime_root / "bin").mkdir(parents=True)
    (runtime_root / "VERSION").write_text(version, encoding="utf-8")
    (install_root / CONTROL_UNIT_NAME).write_bytes(base)
    (runtime_root / "bin" / CONTROL_UNIT_NAME).write_bytes(base)
    native_root = install_root / "runtimes" / "osx-arm64" / "native"
    native_root.mkdir(parents=True)
    (native_root / CONTROL_UNIT_NAME).write_bytes(base)
    return install_root


def test_verify_download_accepts_exact_size_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "asset"
    path.write_bytes(b"mja")
    verify_download(path, 3, hashlib.sha256(b"mja").hexdigest())


def test_verify_download_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "asset"
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_download(path, 3, "0" * 64)


def test_stream_download_requires_https_and_atomically_replaces_part(
    tmp_path: Path,
) -> None:
    payload = b"runtime-bytes"
    response = io.BytesIO(payload)
    response.geturl = lambda: "https://example.test/runtime.zip"  # type: ignore[attr-defined]
    destination = tmp_path / "runtime.zip"

    stream_download(
        "https://example.test/runtime.zip",
        destination,
        len(payload),
        hashlib.sha256(payload).hexdigest(),
        opener=lambda request: response,
    )

    assert destination.read_bytes() == payload
    assert not destination.with_name(destination.name + ".part").exists()


def test_stream_download_rejects_http_before_open(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        stream_download("http://example.test/runtime.zip", tmp_path / "x", 0, "0" * 64)


@pytest.mark.parametrize("member_name", ["/escape.txt", "../escape.txt", "folder/../../escape.txt"])
def test_tar_path_traversal_is_rejected(tmp_path: Path, member_name: str) -> None:
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as handle:
        info = tarfile.TarInfo(member_name)
        info.size = 1
        handle.addfile(info, io.BytesIO(b"x"))

    with pytest.raises(ValueError, match="path traversal"):
        extract_archive(archive, tmp_path / "out")


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../../escape.txt", "x")

    with pytest.raises(ValueError, match="path traversal"):
        extract_archive(archive, tmp_path / "out")


def test_platform_guard_requires_apple_silicon() -> None:
    assert_supported_platform(system="Darwin", machine="arm64")
    with pytest.raises(RuntimeError, match="Darwin"):
        assert_supported_platform(system="Linux", machine="arm64")
    with pytest.raises(RuntimeError, match="arm64"):
        assert_supported_platform(system="Darwin", machine="x86_64")


def test_ensure_venv_reuses_existing_python_without_recreating(tmp_path: Path) -> None:
    python = tmp_path / "install" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    calls: list[list[str]] = []

    result = ensure_venv(
        tmp_path / "install",
        python_executable="/opt/homebrew/bin/python3",
        runner=lambda argv, **kwargs: calls.append(list(argv)),
    )

    assert result == python
    assert calls == []


def test_assemble_does_not_emit_retired_workflow_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True)
    (project / "assets" / "interface.json").write_text(
        json.dumps(
            {
                "task": [
                    {
                        "name": "daily_all",
                        "entry": "MJA_Daily_All",
                        "resource": ["mja_android"],
                        "controller": ["android"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    install = tmp_path / "install"
    _assemble_install_in_place(install, {}, project_root=project)
    assert not (install / "mja-workflow-manifest.json").exists()


def test_assemble_replaces_stale_android_resource_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source_pipeline = (
        project / "assets" / "resource_android" / "pipeline" / "daily"
    )
    source_pipeline.mkdir(parents=True)
    (source_pipeline / "trial_sword_daily.json").write_text(
        '{"MJA_Daily_TRIAL_SWORD_DAILY": {"recognition": "DirectHit"}}\n',
        encoding="utf-8",
    )
    install = tmp_path / "install"
    stale_pipeline = install / "resource_android" / "pipeline"
    stale_pipeline.mkdir(parents=True)
    (stale_pipeline / "trial_sword_daily.json").write_text(
        '{"MJA_Daily_TRIAL_SWORD_DAILY": {"recognition": "DirectHit"}}\n',
        encoding="utf-8",
    )
    (stale_pipeline / "old_location.json").write_text(
        '{"MJA_Daily_TRIAL_SWORD_DAILY": {"recognition": "DirectHit"}}\n',
        encoding="utf-8",
    )

    _assemble_install_in_place(install, {}, project_root=project)

    assert not (install / "resource_android" / "pipeline" / "old_location.json").exists()
    assert (
        install
        / "resource_android"
        / "pipeline"
        / "daily"
        / "trial_sword_daily.json"
    ).is_file()


def test_sync_project_payload_preserves_runtime_and_replaces_project_files(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    daily = project / "assets/resource_android/pipeline/daily"
    daily.mkdir(parents=True)
    (daily / "daily_all.json").write_text(
        '{"MJA_Daily_All":{"recognition":"DirectHit"}}\n',
        encoding="utf-8",
    )
    (project / "assets/interface.json").write_text(
        json.dumps(
            {
                "task": [
                    {
                        "name": "daily_all",
                        "entry": "MJA_Daily_All",
                        "resource": ["mja_android"],
                        "controller": ["android"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (project / "agent").mkdir()
    (project / "agent/new.py").write_text("VALUE = 1\n", encoding="utf-8")
    install = project / "install"
    (install / ".venv/bin").mkdir(parents=True)
    (install / ".venv/bin/python3").write_text("runtime", encoding="utf-8")
    (install / "runtime/maafw").mkdir(parents=True)
    (install / "runtime/maafw/VERSION").write_text("5.12.2\n", encoding="utf-8")
    (install / "agent").mkdir()
    (install / "agent/stale.py").write_text("stale", encoding="utf-8")

    sync_project_payload(project, install)

    assert (install / ".venv/bin/python3").read_text(encoding="utf-8") == "runtime"
    assert (install / "runtime/maafw/VERSION").read_text(encoding="utf-8") == "5.12.2\n"
    assert (install / "agent/new.py").is_file()
    assert not (install / "agent/stale.py").exists()
    assert (install / "resource_android/pipeline/daily/daily_all.json").is_file()
    assert not (install / "mja-workflow-manifest.json").exists()


def test_sync_project_payload_requires_existing_install(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="existing install is required"):
        sync_project_payload(tmp_path, tmp_path / "missing")


def test_artifact_from_manifest_requires_all_integrity_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "runtime-manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "artifacts": [{}]}))
    from tools.setup import load_manifest

    with pytest.raises(ValueError, match="id"):
        load_manifest(manifest)


def test_overlay_uses_exact_pinned_base_and_replaces_both_copies(tmp_path: Path) -> None:
    base = b"official-base"
    patched = b"patched-control-unit"
    install = _make_install(tmp_path / "install", base)
    bundle = _make_bundle(tmp_path / "bundle", base, patched)

    overlay_patched_macos_control_unit(install, bundle)

    assert (install / CONTROL_UNIT_NAME).read_bytes() == patched
    assert (install / "runtime" / "maafw" / "bin" / CONTROL_UNIT_NAME).read_bytes() == patched
    assert (
        install / "runtimes" / "osx-arm64" / "native" / CONTROL_UNIT_NAME
    ).read_bytes() == patched
    assert not list(install.rglob("*.staging"))
    assert not list(install.rglob("*.backup"))


def test_overlay_rejects_wrong_base_without_changing_either_copy(tmp_path: Path) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", b"wrong-base")
    runtime_copy = install / "runtime" / "maafw" / "bin" / CONTROL_UNIT_NAME
    runtime_copy.write_bytes(base)
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched")
    before = (install / CONTROL_UNIT_NAME).read_bytes(), runtime_copy.read_bytes()

    with pytest.raises(ValueError, match="base library digest"):
        overlay_patched_macos_control_unit(install, bundle)

    assert (install / CONTROL_UNIT_NAME).read_bytes() == before[0]
    assert runtime_copy.read_bytes() == before[1]
    assert not list(install.rglob("*.staging"))


def test_overlay_rejects_wrong_maafw_version_without_changes(tmp_path: Path) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", base, version="5.12.1\n")
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched")
    before = (install / CONTROL_UNIT_NAME).read_bytes()

    with pytest.raises(ValueError, match="version must be 5.12.2"):
        overlay_patched_macos_control_unit(install, bundle)

    assert (install / CONTROL_UNIT_NAME).read_bytes() == before
    assert not list(install.rglob("*.staging"))


def test_overlay_rejects_tampered_vendor_library_without_changes(tmp_path: Path) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", base)
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched!")
    (bundle / CONTROL_UNIT_NAME).write_bytes(b"tamper!!")
    before = (install / CONTROL_UNIT_NAME).read_bytes()

    with pytest.raises(ValueError, match="patched library SHA-256"):
        overlay_patched_macos_control_unit(install, bundle)

    assert (install / CONTROL_UNIT_NAME).read_bytes() == before
    assert not list(install.rglob("*.staging"))


def test_overlay_rejects_a_bundle_bound_to_a_different_base(tmp_path: Path) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", base)
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["base_library_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="bound to the official base"):
        overlay_patched_macos_control_unit(install, bundle)


def test_overlay_rolls_back_when_the_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", base)
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched")
    original_replace = os.replace
    replacements = 0

    def fail_second_stage(source: str | Path, destination: str | Path) -> None:
        nonlocal replacements
        if Path(source).name.endswith(".staging") and Path(destination).name == CONTROL_UNIT_NAME:
            replacements += 1
            if replacements == 2:
                raise OSError("simulated second replace failure")
        original_replace(source, destination)

    monkeypatch.setattr("tools.setup.os.replace", fail_second_stage)
    with pytest.raises(OSError, match="second replace"):
        overlay_patched_macos_control_unit(install, bundle)

    assert (install / CONTROL_UNIT_NAME).read_bytes() == base
    assert (install / "runtime" / "maafw" / "bin" / CONTROL_UNIT_NAME).read_bytes() == base
    assert not (install / ".mja-macos-control-unit-overlay.json").exists()


@pytest.mark.parametrize("component", ["runtime", "maafw", "bin"])
def test_overlay_rejects_symlinked_install_parent(tmp_path: Path, component: str) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", base)
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched")
    if component == "runtime":
        real = tmp_path / "runtime-real"
        (install / "runtime").rename(real)
        (install / "runtime").symlink_to(real, target_is_directory=True)
    elif component == "maafw":
        real = tmp_path / "maafw-real"
        (install / "runtime" / "maafw").rename(real)
        (install / "runtime" / "maafw").symlink_to(real, target_is_directory=True)
    else:
        real = tmp_path / "bin-real"
        (install / "runtime" / "maafw" / "bin").rename(real)
        (install / "runtime" / "maafw" / "bin").symlink_to(real, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        overlay_patched_macos_control_unit(install, bundle)


def test_overlay_cleans_staging_files_when_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = b"official-base"
    install = _make_install(tmp_path / "install", base)
    bundle = _make_bundle(tmp_path / "bundle", base, b"patched")
    original_copyfile = shutil.copyfile

    def copy_then_fail(source: str | Path, destination: str | Path) -> Path:
        result = original_copyfile(source, destination)
        if Path(destination).name.endswith(".staging"):
            raise OSError("simulated staging failure")
        return result

    monkeypatch.setattr("tools.setup.shutil.copyfile", copy_then_fail)

    with pytest.raises(OSError, match="simulated staging failure"):
        overlay_patched_macos_control_unit(install, bundle)

    assert (install / CONTROL_UNIT_NAME).read_bytes() == base
    assert not list(install.rglob("*.staging"))
    assert not list(install.rglob("*.backup"))


def test_assemble_copies_maafw_bin_runtime_files_beside_cli(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _make_bundle(
        project / "vendor" / "maafw" / "v5.12.2" / "macos-arm64",
        b"official-base",
        b"patched-control-unit",
    )
    source = tmp_path / "maafw"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "MaaPiCli").write_bytes(b"cli")
    (source / "bin" / "libMaaToolkit.dylib").write_bytes(b"toolkit")
    (source / "bin" / CONTROL_UNIT_NAME).write_bytes(b"official-base")

    install = tmp_path / "install"
    assemble_install(install, {"maafw": source}, project_root=project)

    assert (install / "MaaPiCli").read_bytes() == b"cli"
    assert (install / "libMaaToolkit.dylib").read_bytes() == b"toolkit"
    assert (install / CONTROL_UNIT_NAME).read_bytes() == b"patched-control-unit"


def test_build_android_maapi_cli_uses_pinned_build_script_when_source_is_given(
    tmp_path: Path,
) -> None:
    install = tmp_path / "install"
    install.mkdir()
    (install / "MaaPiCli").write_bytes(b"old-cli")
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> None:
        calls.append(argv)
        (install / "MaaPiCli").write_bytes(b"new-cli")

    build_android_maapi_cli(
        install,
        source=tmp_path / "clean-source",
        official_bin=install,
        runner=runner,
    )

    assert calls == [[
        os.fspath(Path(__file__).resolve().parents[1] / "native/maafw-android-cli/build.sh"),
        "--source",
        os.fspath(tmp_path / "clean-source"),
        "--official-bin",
        os.fspath(install),
        "--output",
        os.fspath(install),
    ]]


def test_preserved_android_control_unit_prefers_previous_patched_runtime(
    tmp_path: Path,
) -> None:
    previous = tmp_path / "runtime/maafw.previous/bin/libMaaAdbControlUnit.dylib"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"patched-adb-control-unit")
    (tmp_path / "libMaaAdbControlUnit.dylib").write_bytes(b"official-adb-control-unit")
    (tmp_path / "MaaPiCli.android.manifest.json").write_text(
        json.dumps({"schema_version": 1}),
        encoding="utf-8",
    )

    payload = _preserved_android_control_unit(tmp_path)

    assert payload is not None
    assert payload[0] == b"patched-adb-control-unit"


def test_assemble_invokes_android_maapi_validation_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _make_bundle(
        project / "vendor" / "maafw" / "v5.12.2" / "macos-arm64",
        b"official-base",
        b"patched-control-unit",
    )
    source = tmp_path / "maafw"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "MaaPiCli").write_bytes(b"cli")
    (source / "bin" / CONTROL_UNIT_NAME).write_bytes(b"official-base")
    calls: list[Path] = []
    monkeypatch.setattr("tools.setup.build_android_maapi_cli", lambda root: calls.append(root))

    install = tmp_path / "install"
    assemble_install(install, {"maafw": source}, project_root=project)

    assert len(calls) == 1
    assert calls[0].parent == install.parent
    assert calls[0].name.startswith(f".{install.name}.staging-")


def test_assemble_preflights_bundle_before_mutating_existing_install(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _make_bundle(
        project / "vendor" / "maafw" / "v5.12.2" / "macos-arm64",
        b"official-base",
        b"patched-control-unit",
    )
    source = tmp_path / "maafw"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "MaaPiCli").write_bytes(b"cli")
    (source / "bin" / CONTROL_UNIT_NAME).write_bytes(b"wrong-base")
    install = tmp_path / "install"
    install.mkdir()
    (install / "sentinel").write_bytes(b"keep")

    with pytest.raises(ValueError, match="official base library digest mismatch"):
        assemble_install(install, {"maafw": source}, project_root=project)

    assert (install / "sentinel").read_bytes() == b"keep"
