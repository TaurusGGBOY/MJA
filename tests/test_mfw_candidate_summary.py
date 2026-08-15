from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_mfw_evidence import _write_full_candidate
from tools.verify_mfw_evidence import (
    verify_candidate_summary,
    write_candidate_summary,
)


def test_candidate_summary_matches_verified_candidate_metadata(tmp_path: Path) -> None:
    _write_full_candidate(tmp_path)
    summary_path = tmp_path / "candidate-summary.json"

    summary = write_candidate_summary(summary_path, tmp_path)
    verified = verify_candidate_summary(summary_path, evidence_root=tmp_path)

    metadata = json.loads(
        (tmp_path / "mfw-full-candidate-build-metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["build_metadata_sha256"] == verified["build_metadata_sha256"]
    assert summary["mja_commit"] == metadata["mja_commit"]
    assert summary["payload_sha256"] == metadata["payload_sha256"]
    assert summary["automatic_tests"] == "passed"
    assert summary["macos_ios_full_preset"] == "passed"
    assert summary["macos_ios_manual_all"] == "passed"
    assert len(summary["evidence_manifest"]) > 20


def test_candidate_summary_rejects_tampered_metadata(tmp_path: Path) -> None:
    _write_full_candidate(tmp_path)
    summary_path = tmp_path / "candidate-summary.json"
    write_candidate_summary(summary_path, tmp_path)

    metadata_path = tmp_path / "mfw-full-candidate-build-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["mja_commit"] = "tampered"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata hash"):
        verify_candidate_summary(summary_path, evidence_root=tmp_path)


def test_summary_is_not_written_when_full_candidate_is_incomplete(tmp_path: Path) -> None:
    summary_path = tmp_path / "candidate-summary.json"

    with pytest.raises(ValueError, match="missing full-candidate task evidence"):
        write_candidate_summary(summary_path, tmp_path)
    assert not summary_path.exists()
