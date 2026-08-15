from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.verify_mfw_evidence import verify_failure_contract

ROOT = Path(__file__).parents[1]


def test_failure_probe_has_abort_then_sentinel():
    nodes = json.loads(
        (ROOT / "tests/mfw/probes/resource/pipeline/failure_contract.json").read_text(
            encoding="utf-8"
        )
    )
    failure = nodes["MJA_PROBE_BUSINESS_FAILURE"]
    assert failure["next"] == ["公共-通用中止"]
    assert failure["Abort"] is True
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert nodes["MJA_PROBE_SENTINEL"]["next"] == ["公共-通用停止"]


def test_evidence_rejects_abort_without_following_sentinel(tmp_path: Path):
    evidence = tmp_path / "failure-contract.json"
    evidence.write_text(
        json.dumps({"abort_failed": True, "sentinel_ran": False}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sentinel"):
        verify_failure_contract(evidence)


def test_evidence_accepts_reproducible_metadata_links(tmp_path: Path):
    base_metadata = tmp_path / "build-metadata.json"
    base_metadata.write_text('{"payload_sha256":"' + "b" * 64 + '"}\n', encoding="utf-8")
    base_metadata_sha = hashlib.sha256(base_metadata.read_bytes()).hexdigest()
    probe_metadata = tmp_path / "probe-metadata.json"
    probe_metadata.write_text(
        json.dumps(
            {
                "base_metadata_sha256": base_metadata_sha,
                "base_payload_sha256": "b" * 64,
                "overlay_sha256": "c" * 64,
            }
        ),
        encoding="utf-8",
    )
    probe_metadata_sha = hashlib.sha256(probe_metadata.read_bytes()).hexdigest()
    evidence = tmp_path / "failure-contract.json"
    evidence.write_text(
        json.dumps(
            {
                "abort_failed": True,
                "sentinel_ran": True,
                "base_metadata_sha256": base_metadata_sha,
                "base_payload_sha256": "b" * 64,
                "overlay_sha256": "c" * 64,
                "probe_metadata_sha256": probe_metadata_sha,
                "probe_metadata_path": "probe-metadata.json",
                "base_metadata_path": "build-metadata.json",
            }
        ),
        encoding="utf-8",
    )

    assert verify_failure_contract(evidence)["sentinel_ran"] is True


def test_production_interface_and_tasks_never_contain_probe_names():
    paths = [ROOT / "assets/interface.json"]
    paths.extend(sorted((ROOT / "assets/tasks").glob("*.json")))
    for path in paths:
        assert "MJA_PROBE_" not in path.read_text(encoding="utf-8")
