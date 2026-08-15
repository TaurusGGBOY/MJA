"""Strict, redacted metadata records for Android live admission evidence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
LIVE_STATUSES = frozenset({"live_pending", "live_verified"})
FORBIDDEN_KEYS = frozenset({"account", "phone", "password", "code", "token", "credential"})


def _scan_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold()
            if any(part in normalized for part in FORBIDDEN_KEYS):
                raise ValueError(f"verification record contains forbidden key: {key}")
            _scan_forbidden(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _scan_forbidden(item)


def _contained(path: str | Path, root: Path, label: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    elif candidate.parts and candidate.parts[0] == root.name:
        resolved = (root.parent / candidate).resolve()
    else:
        resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"{label} must remain under diagnostics root {root}")
    return os.fspath(resolved)


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    task_id: str
    status: str
    checkout_revision: str
    avd: str
    serial: str
    resource_digest: str
    fixture_paths: tuple[str, ...]
    diagnostic_path: str | None
    result_status: str | None
    postcondition_evidence: tuple[str, ...]
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "task_id": self.task_id,
            "status": self.status,
            "checkout_revision": self.checkout_revision,
            "avd": self.avd,
            "serial": self.serial,
            "resource_digest": self.resource_digest,
            "fixture_paths": list(self.fixture_paths),
            "diagnostic_path": self.diagnostic_path,
            "result_status": self.result_status,
            "postcondition_evidence": list(self.postcondition_evidence),
            "limitations": list(self.limitations),
        }


def load_record(
    path: str | Path,
    *,
    diagnostics_root: str | Path = "diagnostics",
) -> VerificationRecord:
    record_path = Path(path)
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification record must be an object")
    _scan_forbidden(payload)
    expected = {
        "schema_version", "task_id", "status", "checkout_revision", "avd", "serial",
        "resource_digest", "fixture_paths", "diagnostic_path", "result_status",
        "postcondition_evidence", "limitations",
    }
    unknown = set(payload) - expected
    if unknown:
        raise ValueError(f"verification record contains unknown keys: {sorted(unknown)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("verification record schema_version must be 1")
    status = payload.get("status")
    if status not in LIVE_STATUSES:
        raise ValueError("verification record status must be live_pending or live_verified")
    diagnostic_path = payload.get("diagnostic_path")
    diagnostic = None
    if diagnostic_path is not None:
        diagnostic = _contained(diagnostic_path, Path(diagnostics_root), "diagnostic_path")
    fixtures = tuple(str(item) for item in payload.get("fixture_paths", ()))
    evidence = tuple(str(item) for item in payload.get("postcondition_evidence", ()))
    limitations = tuple(str(item) for item in payload.get("limitations", ()))
    if status == "live_verified":
        if not payload.get("result_status"):
            raise ValueError("live_verified record needs result_status")
        if not evidence or not any("after" in item.casefold() for item in evidence):
            raise ValueError("live_verified record needs independent after-frame evidence")
        if not diagnostic:
            raise ValueError("live_verified record needs diagnostic_path")
        if any("fixture" in item.casefold() for item in limitations):
            raise ValueError("fixture-only evidence cannot be live_verified")
    return VerificationRecord(
        task_id=str(payload.get("task_id", "")),
        status=status,
        checkout_revision=str(payload.get("checkout_revision", "")),
        avd=str(payload.get("avd", "")),
        serial=str(payload.get("serial", "")),
        resource_digest=str(payload.get("resource_digest", "")),
        fixture_paths=fixtures,
        diagnostic_path=diagnostic,
        result_status=payload.get("result_status"),
        postcondition_evidence=evidence,
        limitations=limitations,
    )


def write_record(path: str | Path, record: VerificationRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(record.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


__all__ = ["VerificationRecord", "load_record", "write_record"]
