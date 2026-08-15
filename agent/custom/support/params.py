"""Strict decoding for MFW CustomAction parameters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .policy import TASK_POLICIES

_REQUIRED_FIELDS = frozenset({"task_id", "action_id", "kind", "evidence"})
_ACTION_KINDS = frozenset({"click", "swipe", "none"})


def _raw_payload(argv: Any) -> Any:
    if isinstance(argv, Mapping):
        return dict(argv)
    if isinstance(argv, (str, bytes, bytearray)):
        return argv
    if hasattr(argv, "custom_action_param"):
        return argv.custom_action_param
    raise ValueError("CustomAction parameters must be a JSON object or RunArg")


def _non_empty_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_non_negative_int(payload: Mapping[str, Any], field_name: str) -> None:
    if field_name not in payload:
        return
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def parse_action_params(argv: Any) -> Mapping[str, Any]:
    """Parse and normalize a narrow MFW action payload.

    Policy membership and action-cap membership are checked here so malformed or
    unknown requests cannot reach a controller dispatch implementation.
    """

    raw = _raw_payload(argv)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("CustomAction parameters must be UTF-8 JSON") from exc
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("CustomAction parameters must be valid JSON") from exc
    else:
        payload = raw
    if not isinstance(payload, Mapping):
        raise ValueError("CustomAction parameters must be a JSON object")

    missing = _REQUIRED_FIELDS - payload.keys()
    if missing:
        raise ValueError(f"missing action parameter: {sorted(missing)[0]}")

    task_id = _non_empty_string(payload, "task_id").upper()
    action_id = _non_empty_string(payload, "action_id").lower()
    kind = _non_empty_string(payload, "kind").lower()
    try:
        policy = TASK_POLICIES[task_id]
    except KeyError as exc:
        raise ValueError(f"unknown task_id: {task_id}") from exc
    if action_id not in policy.action_caps:
        raise ValueError(f"unknown action_id for {task_id}: {action_id}")
    if kind not in _ACTION_KINDS:
        raise ValueError(f"unsupported action kind: {kind}")
    evidence = payload["evidence"]
    if not isinstance(evidence, Mapping):
        raise ValueError("evidence must be an object")

    for field_name in ("observed_amount", "budget_amount"):
        _optional_non_negative_int(payload, field_name)
    resource_id = None
    if "resource_id" in payload:
        resource_id = _non_empty_string(payload, "resource_id")

    normalized = dict(payload)
    normalized.update(
        {
            "task_id": task_id,
            "action_id": action_id,
            "kind": kind,
            "evidence": dict(evidence),
        }
    )
    if resource_id is not None:
        normalized["resource_id"] = resource_id
    return normalized


__all__ = ["parse_action_params"]
