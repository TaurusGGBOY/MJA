from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools.mfw_native_bundle import (
    DESTINATION_RELATIVE,
    LIBRARIES,
    install_mfw_native_bundle,
    install_mfw_shared_runtime,
    load_mfw_native_bundle,
    verify_mfw_shared_runtime,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "vendor/maafw/v5.12.3/macos-arm64"


def test_mfw_native_bundle_is_attested() -> None:
    bundle = load_mfw_native_bundle(BUNDLE, require_libraries=True)

    assert bundle.manifest["upstream_tag"] == "v5.12.3"
    assert set(bundle.libraries) == set(LIBRARIES)
    assert set(bundle.manifest["patches_sha256"]) == {
        "0001-macos-coregraphics-region-fallback.patch",
        "0002-macos-coregraphics-window-finder.patch",
        "0003-macos-coregraphics-preflight.patch",
        "0004-macos-coregraphics-capture-guard.patch",
    }


def test_install_replaces_both_runtime_layouts(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    bundle = load_mfw_native_bundle(BUNDLE, require_libraries=True)
    for relative in DESTINATION_RELATIVE:
        source = bundle.libraries[Path(relative).name]
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    install_mfw_native_bundle(candidate, BUNDLE)
    for relative in DESTINATION_RELATIVE:
        assert (candidate / relative).read_bytes() == bundle.libraries[Path(relative).name].read_bytes()


def test_install_rejects_unrelated_base_library(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    bundle = load_mfw_native_bundle(BUNDLE, require_libraries=True)
    for relative in DESTINATION_RELATIVE:
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle.libraries[Path(relative).name], destination)
    (candidate / DESTINATION_RELATIVE[0]).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="base digest mismatch"):
        install_mfw_native_bundle(candidate, BUNDLE)


def test_install_activates_parent_directory_runtime(tmp_path: Path) -> None:
    install_root = tmp_path / "install"
    install_root.mkdir()
    bundle = load_mfw_native_bundle(BUNDLE, require_libraries=True)
    for library in LIBRARIES:
        (install_root / library).write_bytes(bundle.libraries[library].read_bytes())

    install_mfw_shared_runtime(install_root, BUNDLE)
    verify_mfw_shared_runtime(install_root, BUNDLE)


def test_install_rejects_tampered_parent_directory_runtime(tmp_path: Path) -> None:
    install_root = tmp_path / "install"
    install_root.mkdir()
    bundle = load_mfw_native_bundle(BUNDLE, require_libraries=True)
    for library in LIBRARIES:
        (install_root / library).write_bytes(bundle.libraries[library].read_bytes())
    (install_root / "libMaaToolkit.dylib").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="shared MFW library digest mismatch"):
        install_mfw_shared_runtime(install_root, BUNDLE)
