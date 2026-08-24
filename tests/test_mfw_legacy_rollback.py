from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from tools.mfw_artifact_verification import (
    verify_legacy_rollback,
    write_legacy_rollback,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo_with_tag(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "MJA test")
    (repo / "README").write_text("legacy\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-qm", "legacy")
    _git(repo, "tag", "-a", "mja-legacy-final-2026-08-05", "-m", "legacy")

    artifact = repo / "install/legacy-final"
    artifact.mkdir(parents=True)
    (artifact / "MFW").write_bytes(b"legacy-runtime")
    (artifact / "build-metadata.json").write_text("{}\n", encoding="utf-8")
    manifest = repo / "install/legacy-final.sha256"
    lines = []
    for path in sorted(artifact.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  ./{path.relative_to(artifact).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo, artifact, manifest


def test_write_and_verify_legacy_rollback_record(tmp_path: Path) -> None:
    repo, artifact, manifest = _repo_with_tag(tmp_path)
    record_path = repo / "verification/mfw/legacy-rollback.json"

    record = write_legacy_rollback(
        record_path,
        tag="mja-legacy-final-2026-08-05",
        artifact=artifact,
        manifest=manifest,
        repo_root=repo,
    )
    verified = verify_legacy_rollback(record_path, repo_root=repo)

    assert record["verified"] is True
    assert verified["commit"] == verified["tag_commit"]
    assert verified["artifact_storage"] == "local-pending-publication"


def test_legacy_rollback_rejects_mismatched_file_sha(tmp_path: Path) -> None:
    repo, artifact, manifest = _repo_with_tag(tmp_path)
    manifest.write_text("0" * 64 + "  ./MFW\n", encoding="utf-8")
    record_path = repo / "rollback.json"

    with pytest.raises(ValueError, match="SHA mismatch"):
        write_legacy_rollback(
            record_path,
            tag="mja-legacy-final-2026-08-05",
            artifact=artifact,
            manifest=manifest,
            repo_root=repo,
        )
    assert not record_path.exists()


def test_legacy_rollback_rejects_dirty_manifest(tmp_path: Path) -> None:
    repo, artifact, manifest = _repo_with_tag(tmp_path)
    record_path = repo / "rollback.json"
    write_legacy_rollback(
        record_path,
        tag="mja-legacy-final-2026-08-05",
        artifact=artifact,
        manifest=manifest,
        repo_root=repo,
    )
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest hash"):
        verify_legacy_rollback(record_path, repo_root=repo)
