from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.setup import (
    assemble_install,
    assert_supported_platform,
    ensure_venv,
    extract_archive,
    stream_download,
    verify_download,
)


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


def test_artifact_from_manifest_requires_all_integrity_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "runtime-manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "artifacts": [{}]}))
    from tools.setup import load_manifest

    with pytest.raises(ValueError, match="id"):
        load_manifest(manifest)


def test_assemble_copies_maafw_bin_runtime_files_beside_cli(tmp_path: Path) -> None:
    source = tmp_path / "maafw"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "MaaPiCli").write_bytes(b"cli")
    (source / "bin" / "libMaaToolkit.dylib").write_bytes(b"toolkit")

    install = tmp_path / "install"
    assemble_install(install, {"maafw": source}, project_root=tmp_path / "project")

    assert (install / "MaaPiCli").read_bytes() == b"cli"
    assert (install / "libMaaToolkit.dylib").read_bytes() == b"toolkit"
