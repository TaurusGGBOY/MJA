from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.native_bundle import load_patched_bundle

ROOT = Path(__file__).resolve().parents[1]
NOTICE_ROOT = ROOT / "vendor" / "maafw" / "v5.12.2" / "macos-arm64"
PATCH_PATH = (
    ROOT
    / "native"
    / "maafw-macos-fallback"
    / "patches"
    / "0001-macos-coregraphics-region-fallback.patch"
)
LIBRARY_NAME = "libMaaMacOSControlUnit.dylib"
EXPECTED_LICENSE_SHA256 = "446e755fae55ff034bbb21be44670b5f116c2b2667947e7036f2bfe6632539a8"
EXPECTED_SOURCE_SHA256 = "26c9c62f6038e76d66e5da53d4e8bed3ab22f2c597908865c2bc9a2133c353e7"
EXPECTED_MANIFEST_FIELDS = {
    "schema_version",
    "upstream_repository",
    "upstream_tag",
    "target",
    "base_library_sha256",
    "patch_sha256",
    "patched_library_sha256",
    "patched_library_size",
}


def extract_added_lines(patch_text: str) -> list[str]:
    return [
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def extract_added_tokens(patch_text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_:]*", "\n".join(extract_added_lines(patch_text)))


def _fallback_patch_text() -> str:
    assert PATCH_PATH.is_file(), f"missing native fallback patch: {PATCH_PATH}"
    return PATCH_PATH.read_text(encoding="utf-8")


def _manifest_for(library: Path | None = None) -> dict[str, Any]:
    if library is None:
        patched_digest = "3" * 64
        patched_size = 1
    else:
        data = library.read_bytes()
        patched_digest = hashlib.sha256(data).hexdigest()
        patched_size = len(data)
    return {
        "schema_version": 1,
        "upstream_repository": "https://github.com/MaaXYZ/MaaFramework",
        "upstream_tag": "v5.12.2",
        "target": "macos-arm64",
        "base_library_sha256": "1" * 64,
        "patch_sha256": "2" * 64,
        "patched_library_sha256": patched_digest,
        "patched_library_size": patched_size,
    }


def write_manifest_for_test(
    bundle_root: Path,
    library: Path | None = None,
    *,
    manifest: dict[str, Any] | None = None,
) -> Path:
    bundle_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(NOTICE_ROOT / "SOURCE.md", bundle_root / "SOURCE.md")
    shutil.copy2(NOTICE_ROOT / "LICENSE.md", bundle_root / "LICENSE.md")
    manifest_path = bundle_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest if manifest is not None else _manifest_for(library),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_manifest_parser_accepts_a_digest_bound_temp_bundle(tmp_path: Path) -> None:
    library = tmp_path / LIBRARY_NAME
    library.write_bytes(b"arm64-test-library")
    write_manifest_for_test(tmp_path, library)

    bundle = load_patched_bundle(tmp_path, require_library=True)

    assert bundle.root == tmp_path
    assert bundle.library == library
    assert bundle.manifest["patched_library_size"] == len(b"arm64-test-library")
    assert set(bundle.manifest) == EXPECTED_MANIFEST_FIELDS


def test_optional_library_may_be_absent_while_schema_and_notices_are_validated(
    tmp_path: Path,
) -> None:
    write_manifest_for_test(tmp_path)

    bundle = load_patched_bundle(tmp_path, require_library=False)

    assert bundle.library is None
    assert bundle.source_notice == tmp_path / "SOURCE.md"
    assert bundle.license_notice == tmp_path / "LICENSE.md"


def test_required_library_must_exist(tmp_path: Path) -> None:
    write_manifest_for_test(tmp_path)

    with pytest.raises(ValueError, match="required library is missing"):
        load_patched_bundle(tmp_path, require_library=True)


@pytest.mark.parametrize("field", sorted(EXPECTED_MANIFEST_FIELDS))
def test_manifest_rejects_every_missing_field(tmp_path: Path, field: str) -> None:
    manifest = _manifest_for()
    del manifest[field]
    write_manifest_for_test(tmp_path, manifest=manifest)

    with pytest.raises(ValueError, match="fields"):
        load_patched_bundle(tmp_path, require_library=False)


def test_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    manifest = _manifest_for()
    manifest["library_path"] = "../../outside.dylib"
    write_manifest_for_test(tmp_path, manifest=manifest)

    with pytest.raises(ValueError, match="fields"):
        load_patched_bundle(tmp_path, require_library=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("upstream_repository", "https://example.invalid/MaaFramework"),
        ("upstream_repository", 1),
        ("upstream_tag", "5.12.2"),
        ("upstream_tag", 5122),
        ("target", "macos-x86_64"),
        ("target", ["macos-arm64"]),
    ],
)
def test_manifest_rejects_wrong_contract_literals(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    manifest = _manifest_for()
    manifest[field] = value
    write_manifest_for_test(tmp_path, manifest=manifest)

    with pytest.raises(ValueError, match=field):
        load_patched_bundle(tmp_path, require_library=False)


@pytest.mark.parametrize(
    "digest",
    [
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        123,
        None,
    ],
)
@pytest.mark.parametrize(
    "field",
    ["base_library_sha256", "patch_sha256", "patched_library_sha256"],
)
def test_manifest_rejects_malformed_or_nonlowercase_sha256(
    tmp_path: Path,
    field: str,
    digest: object,
) -> None:
    manifest = _manifest_for()
    manifest[field] = digest
    write_manifest_for_test(tmp_path, manifest=manifest)

    with pytest.raises(ValueError, match=field):
        load_patched_bundle(tmp_path, require_library=False)


@pytest.mark.parametrize("size", [True, False, 0, -1, 1.0, "1", None])
def test_manifest_rejects_boolean_or_nonpositive_library_size(
    tmp_path: Path,
    size: object,
) -> None:
    manifest = _manifest_for()
    manifest["patched_library_size"] = size
    write_manifest_for_test(tmp_path, manifest=manifest)

    with pytest.raises(ValueError, match="patched_library_size"):
        load_patched_bundle(tmp_path, require_library=False)


@pytest.mark.parametrize("payload", ["[]", "null", '"manifest"', "{not-json}"])
def test_manifest_rejects_nonobject_or_invalid_json(tmp_path: Path, payload: str) -> None:
    manifest_path = write_manifest_for_test(tmp_path)
    manifest_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="manifest"):
        load_patched_bundle(tmp_path, require_library=False)


def test_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    manifest_path = write_manifest_for_test(tmp_path)
    payload = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        payload.replace('"schema_version": 1,', '"schema_version": 1,\n  "schema_version": 1,'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate field"):
        load_patched_bundle(tmp_path, require_library=False)


@pytest.mark.parametrize("notice_name", ["SOURCE.md", "LICENSE.md"])
def test_bundle_rejects_a_missing_notice(tmp_path: Path, notice_name: str) -> None:
    write_manifest_for_test(tmp_path)
    (tmp_path / notice_name).unlink()

    with pytest.raises(ValueError, match=notice_name):
        load_patched_bundle(tmp_path, require_library=False)


def test_source_notice_must_retain_reproducibility_metadata(tmp_path: Path) -> None:
    write_manifest_for_test(tmp_path)
    source = tmp_path / "SOURCE.md"
    source.write_text(
        source.read_text(encoding="utf-8").replace("v5.12.2", "v5.12.1"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SOURCE.md"):
        load_patched_bundle(tmp_path, require_library=False)


def test_license_notice_must_be_the_exact_upstream_v5_12_2_text(tmp_path: Path) -> None:
    write_manifest_for_test(tmp_path)
    license_path = tmp_path / "LICENSE.md"
    license_path.write_bytes(license_path.read_bytes() + b"\nmodified\n")

    with pytest.raises(ValueError, match="LICENSE.md"):
        load_patched_bundle(tmp_path, require_library=False)


def test_committed_license_matches_the_upstream_v5_12_2_digest() -> None:
    assert hashlib.sha256((NOTICE_ROOT / "LICENSE.md").read_bytes()).hexdigest() == (
        EXPECTED_LICENSE_SHA256
    )


def test_committed_source_notice_records_the_reproducible_inputs() -> None:
    source_path = NOTICE_ROOT / "SOURCE.md"
    source = source_path.read_text(encoding="utf-8")
    required = {
        "https://github.com/MaaXYZ/MaaFramework",
        "v5.12.2",
        "f625a60edeccd4549f9a71c0f74628d827ade8fb",
        "macos-arm64",
        "native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch",
        "native/maafw-macos-fallback/build.sh",
        "vendor/maafw/v5.12.2/macos-arm64/LICENSE.md",
    }
    assert all(item in source for item in required)
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == EXPECTED_SOURCE_SHA256


@pytest.mark.parametrize(
    "filename",
    ["manifest.json", "SOURCE.md", "LICENSE.md", LIBRARY_NAME],
)
def test_bundle_rejects_symlinked_contract_files(tmp_path: Path, filename: str) -> None:
    library = tmp_path / LIBRARY_NAME
    library.write_bytes(b"arm64-test-library")
    write_manifest_for_test(tmp_path, library)
    original = tmp_path / filename
    target = tmp_path / f"{filename}.target"
    original.replace(target)
    original.symlink_to(target.name)

    with pytest.raises(ValueError, match="symlink"):
        load_patched_bundle(tmp_path, require_library=True)


def test_bundle_rejects_a_symlinked_root_that_escapes_the_supplied_path(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    write_manifest_for_test(real_root)
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(ValueError, match="bundle root.*symlink"):
        load_patched_bundle(linked_root, require_library=False)


def test_bundle_rejects_a_symlinked_ancestor_in_the_supplied_path(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    bundle_root = real_parent / "bundle"
    write_manifest_for_test(bundle_root)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="bundle root.*symlink"):
        load_patched_bundle(linked_parent / "bundle", require_library=False)


def test_bundle_rejects_a_non_directory_root(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="bundle root.*directory"):
        load_patched_bundle(root, require_library=False)


def test_library_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    library = tmp_path / LIBRARY_NAME
    library.write_bytes(b"arm64-test-library")
    write_manifest_for_test(tmp_path, library)
    library.write_bytes(b"tampered-library")

    with pytest.raises(ValueError, match="size mismatch|SHA-256 mismatch"):
        load_patched_bundle(tmp_path, require_library=True)


def test_existing_optional_library_is_still_integrity_checked(tmp_path: Path) -> None:
    library = tmp_path / LIBRARY_NAME
    library.write_bytes(b"arm64-test-library")
    write_manifest_for_test(tmp_path, library)
    library.write_bytes(b"tampered-library-with-the-same-length")
    manifest = _manifest_for(library)
    manifest["patched_library_sha256"] = "0" * 64
    write_manifest_for_test(tmp_path, library, manifest=manifest)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_patched_bundle(tmp_path, require_library=False)


def test_library_must_be_a_regular_file(tmp_path: Path) -> None:
    library = tmp_path / LIBRARY_NAME
    library.write_bytes(b"arm64-test-library")
    write_manifest_for_test(tmp_path, library)
    library.unlink()
    library.mkdir()

    with pytest.raises(ValueError, match="regular file"):
        load_patched_bundle(tmp_path, require_library=True)


def test_fallback_patch_changes_only_the_two_screencap_sources() -> None:
    patch_text = _fallback_patch_text()
    changed_paths = {
        line.split()[2].removeprefix("a/")
        for line in patch_text.splitlines()
        if line.startswith("diff --git ")
    }

    assert changed_paths == {
        "source/MaaMacOSControlUnit/Screencap/ScreenCaptureKitScreencap.h",
        "source/MaaMacOSControlUnit/Screencap/ScreenCaptureKitScreencap.mm",
    }


def test_fallback_patch_applies_to_a_clean_source_snapshot(tmp_path: Path) -> None:
    source_root = os.environ.get("MJA_MAAFRAME_SOURCE")
    if not source_root:
        pytest.skip("set MJA_MAAFRAME_SOURCE to run the clean-source patch integration test")

    source = Path(source_root)
    if not source.is_dir():
        pytest.fail(f"MJA_MAAFRAME_SOURCE is not a directory: {source}")
    clone = tmp_path / "source"
    subprocess.run(
        ["git", "clone", "--no-local", "--quiet", os.fspath(source), os.fspath(clone)],
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
    subprocess.run(
        ["git", "-C", os.fspath(clone), "apply", "--check", os.fspath(PATCH_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_fallback_patch_contains_required_semantic_anchors() -> None:
    patch_text = _fallback_patch_text()
    added_lines = "\n".join(extract_added_lines(patch_text))
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
    assert "kCGWindowListOptionIncludingWindow" not in added_lines


def test_fallback_patch_validates_exact_onscreen_window_and_stable_bounds() -> None:
    added = "\n".join(extract_added_lines(_fallback_patch_text()))
    required = {
        "CGWindowListCopyWindowInfo",
        "kCGWindowNumber",
        "kCGWindowOwnerPID",
        "kCGWindowIsOnscreen",
        "CGRectMakeWithDictionaryRepresentation",
        "stable_window_bounds_",
        "same_bounds",
        "kMinimumWindowWidth = 640.0",
        "kMaximumWindowWidth = 4096.0",
        "kMinimumWindowHeight = 360.0",
        "kMaximumWindowHeight = 2160.0",
        "bounds.size.width <= bounds.size.height",
    }

    assert all(anchor in added for anchor in required)


def test_fallback_patch_rejects_front_window_occlusion() -> None:
    added = "\n".join(extract_added_lines(_fallback_patch_text()))
    required = {
        "front_index < target_index",
        "front_layer != 0",
        "front_owner_pid != target_owner_pid",
        "CGRectIntersection",
        "CGRectIsEmpty",
        "MJA CoreGraphicsRegion rejected occluded target window",
    }

    assert all(anchor in added for anchor in required)


def test_fallback_patch_owns_nominal_resolution_bgr_pixels() -> None:
    added = "\n".join(extract_added_lines(_fallback_patch_text()))
    required = {
        "CGWindowListCreateImage",
        "CGImageGetWidth",
        "CGImageGetHeight",
        "std::lround",
        "std::vector<std::uint8_t>",
        "CGColorSpaceCreateDeviceRGB",
        "CGBitmapContextCreate",
        "CGBitmapContextGetBytesPerRow",
        "CV_8UC4",
        "cv::cvtColor",
        "owned_bgr",
        "ScopedResource<CGImageRef, CGImageRelease>",
        "ScopedResource<CGColorSpaceRef, CGColorSpaceRelease>",
        "ScopedResource<CGContextRef, CGContextRelease>",
    }

    assert all(anchor in added for anchor in required)


def test_fallback_patch_switches_backend_only_after_success() -> None:
    added = "\n".join(extract_added_lines(_fallback_patch_text()))
    decision_rule = re.compile(
        r"if \(backend_ == CaptureBackend::CoreGraphicsRegion\) \{\s*"
        r"return screencap_window_core_graphics\(window_id_\);\s*\}\s*"
        r"if \(auto image = screencap_window_screen_capture_kit\(window_id_\)\) \{\s*"
        r"return image;\s*\}\s*"
        r"if \(auto image = screencap_window_core_graphics\(window_id_\)\) \{\s*"
        r"backend_ = CaptureBackend::CoreGraphicsRegion;\s*"
        r"LogWarn << \"MJA screencap backend switched to CoreGraphicsRegion\";\s*"
        r"return image;\s*\}\s*return std::nullopt;",
        re.MULTILINE,
    )

    assert decision_rule.search(added)
    assert added.count("backend_ = CaptureBackend::CoreGraphicsRegion;") == 1
    assert added.count("CaptureBackend::ScreenCaptureKit") == 1
