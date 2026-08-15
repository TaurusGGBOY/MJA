import json
from pathlib import Path

import pytest

from tools.verification_records import VerificationRecord, load_record, write_record


def record(**overrides):
    values = {
        "schema_version": 1,
        "task_id": "MAIL_REWARD_DAILY",
        "status": "live_pending",
        "checkout_revision": "abc123",
        "avd": "mja-api35-apis",
        "serial": "emulator-5556",
        "resource_digest": "sha256:fixture",
        "fixture_paths": ["tests/fixtures/MAIL_REWARD_DAILY/actionable.png"],
        "diagnostic_path": None,
        "result_status": None,
        "postcondition_evidence": [],
        "limitations": ["fixture-only; live capture pending"],
    }
    values.update(overrides)
    return values


def test_pending_record_round_trips_atomically(tmp_path: Path):
    path = tmp_path / "record.json"
    values = {key: value for key, value in record().items() if key != "schema_version"}
    write_record(path, VerificationRecord(**values))
    assert load_record(path).status == "live_pending"
    assert not path.with_name("record.json.tmp").exists()


def test_live_record_requires_after_frame_and_diagnostics_path(tmp_path: Path):
    path = tmp_path / "record.json"
    path.write_text(
        json.dumps(
            record(
                status="live_verified",
                diagnostic_path="diagnostics/2026-07-28/MAIL_REWARD_DAILY/run-1",
                result_status="completed",
            )
        )
    )
    with pytest.raises(ValueError, match="after-frame"):
        load_record(path, diagnostics_root=tmp_path / "diagnostics")


def test_record_rejects_forbidden_keys_and_outside_diagnostics(tmp_path: Path):
    path = tmp_path / "record.json"
    payload = record(account="must-not-appear")
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="forbidden"):
        load_record(path)

    path.write_text(
        json.dumps(
            record(
                status="live_verified",
                diagnostic_path="/tmp/outside",
                result_status="completed",
                postcondition_evidence=["after.png"],
            )
        )
    )
    with pytest.raises(ValueError, match="under diagnostics"):
        load_record(path, diagnostics_root=tmp_path / "diagnostics")
