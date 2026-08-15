"""Strict, redacted admission records for live workflow verification."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from .catalog import TASK_POLICIES
from .models import TaskStatus

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_EVIDENCE = frozenset(
    {"before.png", "after.png", "result.json", "action-trace.jsonl", "agent.log", "maafw.log"}
)
ControllerBackend = Literal["ScreenCaptureKit", "CoreGraphicsRegion"]


class VerificationState(StrEnum):
    FIXTURE_VERIFIED = "fixture_verified"
    LIVE_PENDING = "live_pending"
    LIVE_VERIFIED = "live_verified"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class EvidenceDigest:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class LiveVerificationRecord:
    task_id: str
    state: VerificationState
    implementation_commit: str
    verified_at: datetime
    controller_backend: ControllerBackend
    logical_window_size: tuple[int, int]
    maa_capture_size: tuple[int, int]
    normal_run_status: TaskStatus
    noop_run_status: TaskStatus | None
    evidence: tuple[EvidenceDigest, ...]
    postcondition_evidence: tuple[EvidenceDigest, ...]
    pending_branches: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_in_diagnostics(path: str, repository_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (repository_root / candidate).resolve()
    diagnostics = (repository_root / "diagnostics").resolve()
    if resolved == diagnostics or diagnostics not in resolved.parents:
        raise ValueError(f"evidence path must remain under diagnostics/: {path}")
    return resolved


def _digest(value: object, repository_root: Path, *, require_local: bool) -> EvidenceDigest:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("evidence entries must contain only path and sha256")
    path = value["path"]
    sha256 = value["sha256"]
    if not isinstance(path, str) or not path.strip():
        raise ValueError("evidence path must be non-empty")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("evidence sha256 must be 64 lowercase hex characters")
    resolved = _path_in_diagnostics(path, repository_root)
    if require_local:
        if resolved.is_symlink() or not resolved.is_file():
            raise ValueError(f"local evidence file does not exist or is a symlink: {path}")
        if _sha256(resolved) != sha256:
            raise ValueError(f"evidence digest mismatch: {path}")
    return EvidenceDigest(path, sha256)


def _size(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value
    ):
        raise ValueError(f"{label} must contain two positive integers")
    return (value[0], value[1])


def _status(value: object, label: str, *, optional: bool = False) -> TaskStatus | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or value in {item.value for item in VerificationState}:
        raise ValueError(f"{label} must be a runtime TaskStatus")
    try:
        parsed = TaskStatus(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid TaskStatus") from exc
    if parsed not in {TaskStatus.COMPLETED, TaskStatus.ALREADY_COMPLETE}:
        raise ValueError(f"{label} must be completed or already_complete")
    return parsed


def load_verification_record(
    path: Path,
    *,
    repository_root: Path,
    require_local_evidence: bool = False,
) -> LiveVerificationRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification record must be an object")
    expected = {
        "schema_version", "task_id", "state", "implementation_commit", "verified_at",
        "controller_backend", "logical_window_size", "maa_capture_size",
        "normal_run_status", "noop_run_status", "evidence", "postcondition_evidence",
        "pending_branches",
    }
    unknown = set(payload) - expected
    if unknown:
        raise ValueError(f"verification record contains unknown keys: {sorted(unknown)}")
    if payload.get("schema_version") != 1:
        raise ValueError("verification record schema_version must be 1")
    task_id = payload.get("task_id")
    if task_id not in TASK_POLICIES:
        raise ValueError(f"unknown task ID: {task_id}")
    try:
        state = VerificationState(payload["state"])
    except (KeyError, ValueError) as exc:
        raise ValueError("state must be a supported verification state") from exc
    commit = payload.get("implementation_commit")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ValueError("implementation_commit must be a 40-hex git commit")
    try:
        verified_at = datetime.fromisoformat(str(payload["verified_at"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("verified_at must be an ISO-8601 datetime") from exc
    if verified_at.tzinfo is None:
        raise ValueError("verified_at must include a timezone")
    if verified_at > datetime.now(verified_at.tzinfo):
        raise ValueError("verified_at cannot be in the future")
    backend = payload.get("controller_backend")
    if backend not in {"ScreenCaptureKit", "CoreGraphicsRegion"}:
        raise ValueError("unsupported controller backend")
    logical = _size(payload.get("logical_window_size"), "logical_window_size")
    maa = _size(payload.get("maa_capture_size"), "maa_capture_size")
    if logical != (1280, 720) or maa != (1280, 720):
        raise ValueError("verification capture sizes must be 1280x720")
    normal = _status(payload.get("normal_run_status"), "normal_run_status")
    noop = _status(payload.get("noop_run_status"), "noop_run_status", optional=True)
    raw_evidence = payload.get("evidence")
    raw_post = payload.get("postcondition_evidence")
    if not isinstance(raw_evidence, list) or not isinstance(raw_post, list):
        raise ValueError("evidence fields must be arrays")
    evidence = tuple(
        _digest(item, repository_root, require_local=require_local_evidence)
        for item in raw_evidence
    )
    post = tuple(
        _digest(item, repository_root, require_local=require_local_evidence)
        for item in raw_post
    )
    names = {Path(item.path).name for item in evidence}
    if state == VerificationState.LIVE_VERIFIED:
        missing = _REQUIRED_EVIDENCE - names
        if missing:
            raise ValueError(f"live_verified record is missing evidence: {sorted(missing)}")
        if not post:
            raise ValueError("live_verified record needs postcondition evidence")
        if payload.get("pending_branches"):
            raise ValueError("live_verified record cannot have pending branches")
    pending = payload.get("pending_branches")
    if not isinstance(pending, list) or any(
        not isinstance(item, str) or not item.strip() for item in pending
    ):
        raise ValueError("pending_branches must be an array of non-empty strings")
    return LiveVerificationRecord(
        task_id=task_id,
        state=state,
        implementation_commit=commit,
        verified_at=verified_at,
        controller_backend=backend,
        logical_window_size=logical,
        maa_capture_size=maa,
        normal_run_status=normal,
        noop_run_status=noop,
        evidence=evidence,
        postcondition_evidence=post,
        pending_branches=tuple(pending),
    )


__all__ = [
    "EvidenceDigest",
    "LiveVerificationRecord",
    "VerificationState",
    "load_verification_record",
]
