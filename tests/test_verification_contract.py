from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.workflows.verification import load_verification_record


def _payload(**overrides):
    value = {
        "schema_version": 1,
        "task_id": "MAIL_REWARD_DAILY",
        "state": "live_pending",
        "implementation_commit": "1ef968d3be174f2b327e3ee485b49077ac413367",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "controller_backend": "ScreenCaptureKit",
        "logical_window_size": [1280, 720],
        "maa_capture_size": [1280, 720],
        "normal_run_status": "already_complete",
        "noop_run_status": "already_complete",
        "evidence": [],
        "postcondition_evidence": [],
        "pending_branches": ["live emulator capture pending"],
    }
    value.update(overrides)
    return value


def test_pending_record_is_strictly_loadable(tmp_path: Path):
    path = tmp_path / "record.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    record = load_verification_record(path, repository_root=tmp_path)
    assert record.state.value == "live_pending"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"task_id": "NOPE"}, "unknown task ID"),
        ({"implementation_commit": "abc"}, "40-hex"),
        ({"controller_backend": "Android"}, "unsupported"),
        ({"verified_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, "future"),
        ({"normal_run_status": "live_pending"}, "runtime"),
    ],
)
def test_record_rejects_invalid_metadata(tmp_path: Path, change: dict, message: str):
    path = tmp_path / "record.json"
    path.write_text(json.dumps(_payload(**change)), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_verification_record(path, repository_root=tmp_path)


def test_live_record_requires_all_evidence_and_local_digests(tmp_path: Path):
    root = tmp_path
    diagnostics = root / "diagnostics" / "run"
    diagnostics.mkdir(parents=True)
    entries = []
    for name in (
        "before.png", "after.png", "result.json", "action-trace.jsonl", "agent.log", "maafw.log"
    ):
        target = diagnostics / name
        target.write_bytes(name.encode())
        entries.append(
            {
                "path": str(target.relative_to(root)),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    post = entries[:1]
    path = root / "record.json"
    path.write_text(
        json.dumps(
            _payload(
                state="live_verified",
                evidence=entries,
                postcondition_evidence=post,
                pending_branches=[],
            )
        ),
        encoding="utf-8",
    )
    assert (
        load_verification_record(
            path, repository_root=root, require_local_evidence=True
        ).state.value
        == "live_verified"
    )
