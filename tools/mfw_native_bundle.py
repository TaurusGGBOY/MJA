"""Integrity checks and installation helpers for the patched MFW macOS runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

UPSTREAM_REPOSITORY = "https://github.com/MaaXYZ/MaaFramework"
UPSTREAM_TAG = "v5.12.3"
UPSTREAM_COMMIT = "0c3f6454902b8ff9f7697cc6b09a7a935a41cdbb"
TARGET = "macos-arm64"
MANIFEST_NAME = "manifest.json"
SOURCE_NOTICE_NAME = "SOURCE.md"
LICENSE_NOTICE_NAME = "LICENSE.md"
PATCH_DIR = Path("native/maafw-macos-fallback/patches")
PATCH_FILES = (
    "0001-macos-coregraphics-region-fallback.patch",
    "0002-macos-coregraphics-window-finder.patch",
    "0003-macos-coregraphics-preflight.patch",
    "0004-macos-coregraphics-capture-guard.patch",
)
LIBRARIES = ("libMaaMacOSControlUnit.dylib", "libMaaToolkit.dylib")
DESTINATION_RELATIVE = tuple(
    f"{prefix}/{library}"
    for prefix in ("maafw", "runtimes/osx-arm64")
    for library in LIBRARIES
)
SHARED_RUNTIME_RELATIVE = LIBRARIES
# Existing MJA installs may contain the v5.12.2 archive libraries or the
# earlier locally-built v5.12.3 overlay. They are accepted as migration
# inputs; every successful activation ends with the current attested bundle.
LEGACY_SHARED_RUNTIME_SHA256 = {
    "libMaaMacOSControlUnit.dylib": frozenset(
        {
            "f9f341ca13db62ef6f8bd642862510d191efbfc55de896fdec523b5b507ffc9a",
            "37a2fee6c7397d2d8207f8cbcfac16b42434156a5e83a4f97818c46e518a8c6c",
            "65e3d1974559e3345013cdb5bed94bc1a67471d4be804af617a4c566870df0b5",
            "0843d0e6bd52e2da4771693035f40dc0f65ddf48b13be77097a3761775bd5324",
            "109f1971a17306be2ec9554e1fa2fc6f88f38286497d3591bacee487eb9a4694",
        }
    ),
    "libMaaToolkit.dylib": frozenset(
        {"9ed85c4855122898eba1fbd837b03a4377758feb83d7b427693488c72377b9dd"}
    ),
}
# Candidate directories can survive a patch-bundle upgrade. Accept only
# previously attested MJA/official hashes while replacing them atomically with
# the current bundle; unrelated or tampered binaries remain rejected.
LEGACY_CANDIDATE_LIBRARY_SHA256 = {
    "libMaaMacOSControlUnit.dylib": frozenset(
        {
            *LEGACY_SHARED_RUNTIME_SHA256["libMaaMacOSControlUnit.dylib"],
        }
    ),
    "libMaaToolkit.dylib": frozenset(
        {
            *LEGACY_SHARED_RUNTIME_SHA256["libMaaToolkit.dylib"],
        }
    ),
}
LICENSE_SHA256 = "446e755fae55ff034bbb21be44670b5f116c2b2667947e7036f2bfe6632539a8"
_SHA256_LENGTH = 64


@dataclass(frozen=True, slots=True)
class MfwNativeBundle:
    root: Path
    manifest_path: Path
    source_notice: Path
    license_notice: Path
    libraries: Mapping[str, Path]
    manifest: Mapping[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_root(bundle_root: Path) -> Path:
    root = Path(bundle_root).absolute()
    try:
        mode = root.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError(f"MFW native bundle root must be a real directory: {root}")
        for parent in root.parents:
            if stat.S_ISLNK(parent.lstat().st_mode):
                raise ValueError(f"MFW native bundle parent must not be a symlink: {parent}")
        return root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"MFW native bundle root is unavailable: {root}") from exc


def _regular_file(root: Path, relative: str, *, required: bool = True) -> Path | None:
    path = root / relative
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if required:
            raise ValueError(f"MFW native bundle file is missing: {relative}") from None
        return None
    except OSError as exc:
        raise ValueError(f"MFW native bundle file is unavailable: {relative}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ValueError(f"MFW native bundle file must be regular: {relative}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"MFW native bundle file cannot be resolved: {relative}") from exc
    if resolved.parent != root:
        raise ValueError(f"MFW native bundle file escapes its root: {relative}")
    return resolved


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH:
        raise ValueError(f"manifest {field} must be a SHA-256 digest")
    if value.lower() != value or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"manifest {field} must be lowercase hexadecimal")
    return value


def _exact_digest_map(payload: object, field: str, keys: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(payload, dict) or set(payload) != set(keys):
        raise ValueError(f"manifest {field} keys do not match the fixed bundle layout")
    return {key: _digest(payload[key], f"{field}.{key}") for key in keys}


def _exact_size_map(payload: object, field: str, keys: tuple[str, ...]) -> dict[str, int]:
    if not isinstance(payload, dict) or set(payload) != set(keys):
        raise ValueError(f"manifest {field} keys do not match the fixed library layout")
    result: dict[str, int] = {}
    for key in keys:
        value = payload[key]
        if type(value) is not int or value <= 0:
            raise ValueError(f"manifest {field}.{key} must be a positive integer")
        result[key] = value
    return result


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("MFW native bundle manifest must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("MFW native bundle manifest must be an object")
    fields = {
        "schema_version",
        "upstream_repository",
        "upstream_tag",
        "upstream_commit",
        "target",
        "base_libraries_sha256",
        "patches_sha256",
        "patched_libraries_sha256",
        "patched_libraries_size",
    }
    if set(payload) != fields:
        raise ValueError("MFW native bundle manifest fields are not exact")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("manifest schema_version must be integer 1")
    literals = {
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_tag": UPSTREAM_TAG,
        "upstream_commit": UPSTREAM_COMMIT,
        "target": TARGET,
    }
    for field, expected in literals.items():
        if type(payload[field]) is not str or payload[field] != expected:
            raise ValueError(f"manifest {field} must equal {expected!r}")
    _exact_digest_map(payload["base_libraries_sha256"], "base_libraries_sha256", DESTINATION_RELATIVE)
    _exact_digest_map(payload["patches_sha256"], "patches_sha256", PATCH_FILES)
    _exact_digest_map(payload["patched_libraries_sha256"], "patched_libraries_sha256", LIBRARIES)
    _exact_size_map(payload["patched_libraries_size"], "patched_libraries_size", LIBRARIES)
    return payload


def _validate_source_notice(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        UPSTREAM_REPOSITORY,
        UPSTREAM_TAG,
        UPSTREAM_COMMIT,
        TARGET,
        "native/maafw-macos-fallback/build-v5123.sh",
        *PATCH_FILES,
    )
    missing = [fragment for fragment in required if fragment not in text]
    if missing:
        raise ValueError(f"SOURCE.md is missing provenance: {missing}")
    if "\x00" in text:
        raise ValueError("SOURCE.md must not contain NUL bytes")


def load_mfw_native_bundle(bundle_root: Path, *, require_libraries: bool) -> MfwNativeBundle:
    if type(require_libraries) is not bool:
        raise TypeError("require_libraries must be bool")
    root = _validated_root(bundle_root)
    manifest_path = _regular_file(root, MANIFEST_NAME)
    source_notice = _regular_file(root, SOURCE_NOTICE_NAME)
    license_notice = _regular_file(root, LICENSE_NOTICE_NAME)
    assert manifest_path and source_notice and license_notice
    manifest = _load_manifest(manifest_path)
    _validate_source_notice(source_notice)
    if sha256_file(license_notice) != LICENSE_SHA256:
        raise ValueError("LICENSE.md does not match the upstream MaaFramework license")

    libraries: dict[str, Path] = {}
    for library in LIBRARIES:
        path = _regular_file(root, library, required=require_libraries)
        if path is None:
            continue
        expected_size = manifest["patched_libraries_size"][library]
        if path.stat().st_size != expected_size:
            raise ValueError(f"patched library size mismatch: {library}")
        if sha256_file(path) != manifest["patched_libraries_sha256"][library]:
            raise ValueError(f"patched library digest mismatch: {library}")
        libraries[library] = path
    return MfwNativeBundle(root, manifest_path, source_notice, license_notice, libraries, manifest)


def install_mfw_native_bundle(candidate: Path, bundle_root: Path) -> None:
    """Replace all four MFW MaaFramework copies after validating official bases."""

    candidate = Path(candidate)
    bundle = load_mfw_native_bundle(bundle_root, require_libraries=True)
    base_digests = bundle.manifest["base_libraries_sha256"]
    patched_digests = bundle.manifest["patched_libraries_sha256"]
    stages: list[tuple[Path, Path]] = []
    try:
        for relative in DESTINATION_RELATIVE:
            destination = candidate / relative
            if destination.is_symlink() or not destination.is_file():
                raise ValueError(f"candidate MFW library is missing: {relative}")
            actual = sha256_file(destination)
            library = Path(relative).name
            accepted = {
                base_digests[relative],
                patched_digests[library],
                *LEGACY_CANDIDATE_LIBRARY_SHA256[library],
            }
            if actual not in accepted:
                raise ValueError(f"candidate MFW library base digest mismatch: {relative}")
            stage = destination.with_name(destination.name + ".mja-staging")
            stage.unlink(missing_ok=True)
            shutil.copy2(bundle.libraries[library], stage)
            stages.append((stage, destination))
        for stage, destination in stages:
            os.replace(stage, destination)
        stages.clear()
    finally:
        for stage, _ in stages:
            stage.unlink(missing_ok=True)


def _shared_runtime_destinations(install_root: Path) -> dict[str, Path]:
    root = _validated_root(install_root)
    return {library: root / library for library in SHARED_RUNTIME_RELATIVE}


def install_mfw_shared_runtime(install_root: Path, bundle_root: Path) -> None:
    """Activate libraries reached through MFW's parent-directory RPATH."""

    bundle = load_mfw_native_bundle(bundle_root, require_libraries=True)
    expected = bundle.manifest["patched_libraries_sha256"]
    destinations = _shared_runtime_destinations(install_root)
    stages: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    backup_candidates: list[Path] = []
    try:
        for library, destination in destinations.items():
            if destination.is_symlink() or not destination.is_file():
                raise ValueError(f"shared MFW library is missing: {destination}")
            actual = sha256_file(destination)
            accepted = {expected[library], *LEGACY_SHARED_RUNTIME_SHA256[library]}
            if actual not in accepted:
                raise ValueError(f"shared MFW library digest mismatch: {destination}")
            stage = destination.with_name(destination.name + ".mja-staging")
            stage.unlink(missing_ok=True)
            shutil.copy2(bundle.libraries[library], stage)
            stages.append((stage, destination))

        for _, destination in stages:
            fd, name = tempfile.mkstemp(
                prefix=f".{destination.name}.backup.", dir=destination.parent
            )
            os.close(fd)
            backup = Path(name)
            backup.unlink(missing_ok=True)
            backup_candidates.append(backup)
            os.replace(destination, backup)
            backups.append((destination, backup))

        for stage, destination in stages:
            os.replace(stage, destination)
        stages.clear()
    except Exception:
        for stage, _ in stages:
            stage.unlink(missing_ok=True)
        for destination, backup in reversed(backups):
            destination.unlink(missing_ok=True)
            if backup.exists():
                os.replace(backup, destination)
        raise
    finally:
        for stage, _ in stages:
            stage.unlink(missing_ok=True)
        for backup in backup_candidates:
            backup.unlink(missing_ok=True)


def verify_mfw_shared_runtime(install_root: Path, bundle_root: Path) -> None:
    """Require parent-directory libraries to match the current bundle."""

    bundle = load_mfw_native_bundle(bundle_root, require_libraries=True)
    expected = bundle.manifest["patched_libraries_sha256"]
    for library, destination in _shared_runtime_destinations(install_root).items():
        if destination.is_symlink() or not destination.is_file():
            raise ValueError(f"shared MFW library is missing: {destination}")
        if sha256_file(destination) != expected[library]:
            raise ValueError(f"shared MFW library is not patched: {destination}")


def verify_mfw_native_bundle(candidate: Path, bundle_root: Path) -> None:
    """Require every candidate copy to be the attested patched library."""

    candidate = Path(candidate)
    bundle = load_mfw_native_bundle(bundle_root, require_libraries=True)
    expected = bundle.manifest["patched_libraries_sha256"]
    for relative in DESTINATION_RELATIVE:
        destination = candidate / relative
        if destination.is_symlink() or not destination.is_file():
            raise ValueError(f"candidate MFW library is missing: {relative}")
        library = Path(relative).name
        if sha256_file(destination) != expected[library]:
            raise ValueError(f"candidate MFW library is not patched: {relative}")


__all__ = [
    "DESTINATION_RELATIVE",
    "LEGACY_SHARED_RUNTIME_SHA256",
    "LIBRARIES",
    "PATCH_FILES",
    "TARGET",
    "UPSTREAM_COMMIT",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_TAG",
    "MfwNativeBundle",
    "install_mfw_native_bundle",
    "install_mfw_shared_runtime",
    "load_mfw_native_bundle",
    "sha256_file",
    "verify_mfw_native_bundle",
    "verify_mfw_shared_runtime",
]
