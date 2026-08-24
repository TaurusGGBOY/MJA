from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mfw_artifact_verification import BuildMetadata, load_metadata


def _metadata() -> BuildMetadata:
    digest = "a" * 64
    return BuildMetadata(
        mja_commit="native-status-commit",
        target="macos-aarch64",
        resolved_at="2026-08-20T00:00:00+00:00",
        mfw={"repo": "MaaXYZ/MFW", "tag": "v1", "sha256": digest},
        maafw={"repo": "MaaXYZ/MaaFramework", "tag": "v2", "sha256": digest},
        payload_sha256=digest,
        immutable_tree_sha256=digest,
    )


def test_candidate_metadata_round_trip_preserves_provenance_and_hashes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    metadata = _metadata()
    (candidate / "build-metadata.json").write_text(
        json.dumps(metadata.to_mapping(), ensure_ascii=False), encoding="utf-8"
    )

    loaded = load_metadata(candidate)

    assert loaded == metadata
    assert loaded.mja_commit == "native-status-commit"
    assert loaded.mfw["sha256"] == "a" * 64
    assert loaded.payload_sha256 == "a" * 64


def test_candidate_metadata_rejects_invalid_target_or_digest(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    payload = _metadata().to_mapping()
    payload["target"] = "linux-x86_64"
    payload["mfw"]["sha256"] = "not-a-sha"
    (candidate / "build-metadata.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported candidate target"):
        load_metadata(candidate)


def test_candidate_metadata_has_no_runtime_evidence_surface(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    payload = _metadata().to_mapping()
    (candidate / "build-metadata.json").write_text(json.dumps(payload), encoding="utf-8")

    text = (candidate / "build-metadata.json").read_text(encoding="utf-8")

    assert "result.json" not in text
    assert "batch" not in text
    assert set(payload) == {
        "mja_commit",
        "target",
        "resolved_at",
        "mfw",
        "maafw",
        "payload_sha256",
        "immutable_tree_sha256",
        "base_metadata_sha256",
    }
