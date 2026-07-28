from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

SCHEMA_VERSION = 1
UPSTREAM_REPOSITORY = "https://github.com/MaaXYZ/MaaFramework"
UPSTREAM_TAG = "v5.12.2"
UPSTREAM_COMMIT = "f625a60edeccd4549f9a71c0f74628d827ade8fb"
TARGET = "macos-arm64"
MANIFEST_NAME = "manifest.json"
LIBRARY_NAME = "libMaaMacOSControlUnit.dylib"
SOURCE_NOTICE_NAME = "SOURCE.md"
LICENSE_NOTICE_NAME = "LICENSE.md"
SOURCE_NOTICE_SHA256 = "26c9c62f6038e76d66e5da53d4e8bed3ab22f2c597908865c2bc9a2133c353e7"
UPSTREAM_LICENSE_SHA256 = "446e755fae55ff034bbb21be44670b5f116c2b2667947e7036f2bfe6632539a8"

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "upstream_repository",
        "upstream_tag",
        "target",
        "base_library_sha256",
        "patch_sha256",
        "patched_library_sha256",
        "patched_library_size",
    }
)
_SOURCE_NOTICE_REQUIRED_FRAGMENTS = (
    UPSTREAM_REPOSITORY,
    UPSTREAM_TAG,
    UPSTREAM_COMMIT,
    TARGET,
    "native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch",
    "native/maafw-macos-fallback/build.sh",
    "--source \"$MJA_MAAFW_V5122_SOURCE\"",
    "--official-bin \"$MJA_MAAFW_V5122_OFFICIAL_BIN\"",
    "--output \"$PWD/vendor/maafw/v5.12.2/macos-arm64\"",
    "vendor/maafw/v5.12.2/macos-arm64/LICENSE.md",
)


class PatchedControlUnitManifest(TypedDict):
    schema_version: Literal[1]
    upstream_repository: Literal["https://github.com/MaaXYZ/MaaFramework"]
    upstream_tag: Literal["v5.12.2"]
    target: Literal["macos-arm64"]
    base_library_sha256: str
    patch_sha256: str
    patched_library_sha256: str
    patched_library_size: int


@dataclass(frozen=True, slots=True)
class PatchedBundle:
    root: Path
    manifest_path: Path
    source_notice: Path
    license_notice: Path
    library: Path | None
    manifest: PatchedControlUnitManifest


class _DuplicateManifestField(ValueError):
    """Raised when JSON object parsing encounters a repeated manifest field."""


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateManifestField(f"duplicate field {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def _validated_root(bundle_root: Path) -> Path:
    root = Path(bundle_root).absolute()
    try:
        for component in reversed((root, *root.parents)):
            mode = component.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(
                    f"bundle root path component must not be a symlink: {component}"
                )
    except OSError as exc:
        raise ValueError(f"bundle root is unavailable: {root}") from exc
    if not stat.S_ISDIR(mode):
        raise ValueError(f"bundle root must be a directory: {root}")
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"bundle root cannot be resolved: {root}") from exc


def _regular_bundle_file(root: Path, name: str, *, required: bool = True) -> Path | None:
    path = root / name
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if required:
            raise ValueError(f"required bundle file is missing: {name}") from None
        return None
    except OSError as exc:
        raise ValueError(f"bundle file is unavailable: {name}") from exc
    if stat.S_ISLNK(mode):
        raise ValueError(f"bundle file must not be a symlink: {name}")
    if not stat.S_ISREG(mode):
        raise ValueError(f"bundle file must be a regular file: {name}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"bundle file cannot be resolved: {name}") from exc
    if resolved.parent != root:
        raise ValueError(f"bundle file path escapes bundle root: {name}")
    return resolved


def _load_manifest(path: Path) -> PatchedControlUnitManifest:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("manifest must be readable UTF-8 JSON") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_fields,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")

    actual_fields = set(payload)
    if actual_fields != _MANIFEST_FIELDS:
        missing = sorted(_MANIFEST_FIELDS - actual_fields)
        unknown = sorted(actual_fields - _MANIFEST_FIELDS)
        raise ValueError(f"manifest fields mismatch: missing={missing}, unknown={unknown}")

    _require_literal(payload, "schema_version", SCHEMA_VERSION, expected_type=int)
    _require_literal(payload, "upstream_repository", UPSTREAM_REPOSITORY, expected_type=str)
    _require_literal(payload, "upstream_tag", UPSTREAM_TAG, expected_type=str)
    _require_literal(payload, "target", TARGET, expected_type=str)
    for field in (
        "base_library_sha256",
        "patch_sha256",
        "patched_library_sha256",
    ):
        digest = payload[field]
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError(f"manifest {field} must be a lowercase SHA-256 digest")
    size = payload["patched_library_size"]
    if type(size) is not int or size <= 0:
        raise ValueError("manifest patched_library_size must be a positive integer")
    return cast(PatchedControlUnitManifest, payload)


def _require_literal(
    payload: dict[str, Any],
    field: str,
    expected: object,
    *,
    expected_type: type[object],
) -> None:
    value = payload[field]
    if type(value) is not expected_type or value != expected:
        raise ValueError(f"manifest {field} must equal {expected!r}")


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ValueError(f"bundle file cannot be read: {path.name}") from exc
    return digest.hexdigest(), size


def _validate_source_notice(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("SOURCE.md must be readable UTF-8 text") from exc
    missing = [fragment for fragment in _SOURCE_NOTICE_REQUIRED_FRAGMENTS if fragment not in text]
    if missing:
        raise ValueError(f"SOURCE.md is missing required provenance metadata: {missing}")
    if "\x00" in text:
        raise ValueError("SOURCE.md must not contain NUL bytes")
    digest, _ = _sha256_and_size(path)
    if digest != SOURCE_NOTICE_SHA256:
        raise ValueError("SOURCE.md must exactly match the committed provenance notice")


def _validate_license_notice(path: Path) -> None:
    digest, _ = _sha256_and_size(path)
    if digest != UPSTREAM_LICENSE_SHA256:
        raise ValueError("LICENSE.md must exactly match MaaFramework v5.12.2")


def load_patched_bundle(bundle_root: Path, *, require_library: bool) -> PatchedBundle:
    """Load and integrity-check the fixed-layout MaaFramework patch bundle."""

    if type(require_library) is not bool:
        raise TypeError("require_library must be a bool")
    root = _validated_root(bundle_root)
    manifest_path = _regular_bundle_file(root, MANIFEST_NAME)
    source_notice = _regular_bundle_file(root, SOURCE_NOTICE_NAME)
    license_notice = _regular_bundle_file(root, LICENSE_NOTICE_NAME)
    assert manifest_path is not None
    assert source_notice is not None
    assert license_notice is not None

    manifest = _load_manifest(manifest_path)
    _validate_source_notice(source_notice)
    _validate_license_notice(license_notice)

    library = _regular_bundle_file(root, LIBRARY_NAME, required=False)
    if library is None and require_library:
        raise ValueError(f"required library is missing: {LIBRARY_NAME}")
    if library is not None:
        digest, size = _sha256_and_size(library)
        if size != manifest["patched_library_size"]:
            raise ValueError(
                "patched library size mismatch: "
                f"expected {manifest['patched_library_size']}, got {size}"
            )
        if digest != manifest["patched_library_sha256"]:
            raise ValueError("patched library SHA-256 mismatch")

    return PatchedBundle(
        root=root,
        manifest_path=manifest_path,
        source_notice=source_notice,
        license_notice=license_notice,
        library=library,
        manifest=manifest,
    )
