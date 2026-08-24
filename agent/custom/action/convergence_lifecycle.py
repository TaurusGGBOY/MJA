"""MFW action adapter that keeps one convergence budget across JumpBacks."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from threading import RLock
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.convergence import (
    BudgetExceeded,
    ConvergenceOutcome,
    ConvergenceSession,
)
from agent.custom.support.policy import TASK_POLICIES

from .task_lifecycle import _context_key

_SESSIONS: dict[tuple[int, str], ConvergenceSession] = {}
_LOCK = RLock()
_LOGGER = logging.getLogger(__name__)


def _payload(argv: Any) -> dict[str, Any]:
    raw = getattr(argv, "custom_action_param", argv)
    if isinstance(raw, Mapping):
        value = dict(raw)
    elif isinstance(raw, (str, bytes, bytearray)):
        try:
            decoded = raw.decode("utf-8") if not isinstance(raw, str) else raw
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("convergence parameters must be valid JSON") from exc
    else:
        raise ValueError("convergence parameters must be a JSON object")
    if not isinstance(value, dict):
        raise ValueError("convergence parameters must be a JSON object")
    return value


def _task_id(payload: Mapping[str, Any]) -> str:
    value = payload.get("task_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("task_id must be a non-empty string")
    key = value.strip().upper()
    if key not in TASK_POLICIES:
        raise ValueError(f"unknown task_id: {key}")
    return key


def _key(context: Any, task_id: str) -> tuple[int, str]:
    return (_context_key(context), task_id)


def session_for(context: Any, task_id: str) -> ConvergenceSession | None:
    """Return the context/task session, including a closed terminal session."""

    key = _key(context, task_id.strip().upper())
    with _LOCK:
        return _SESSIONS.get(key)


def _record(context: Any, task_id: str, action_id: str, details: Mapping[str, Any]) -> None:
    del context
    _LOGGER.debug(
        "convergence event task=%s action=%s details=%s",
        task_id,
        action_id,
        dict(details),
    )


@AgentServer.custom_action("ConvergenceLifecycle")
class ConvergenceLifecycle(CustomAction):
    """Create, reuse, charge, observe, and close one convergence session.

    A repeated ``begin`` for the same context/task reuses the existing open
    session.  A closed session is retained as a tombstone until the MFW
    context ends, so a later JumpBack cannot silently reset its budget.
    """

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _payload(argv)
            task_id = _task_id(payload)
            operation = payload.get("operation", "begin")
            if not isinstance(operation, str) or not operation.strip():
                raise ValueError("operation must be a non-empty string")
            operation = operation.strip().casefold()
            key = _key(context, task_id)

            if operation == "begin":
                with _LOCK:
                    current = _SESSIONS.get(key)
                    if current is not None:
                        return not current.closed
                    _SESSIONS[key] = ConvergenceSession(task_id)
                _record(context, task_id, "convergence.begin", {"reused": False})
                return True

            with _LOCK:
                session = _SESSIONS.get(key)
            if session is None or session.closed:
                return False

            if operation == "observe":
                state = payload.get("state")
                evidence = payload.get("evidence", "")
                frame_id = payload.get("frame_id")
                observation = session.observe(state, evidence=evidence, frame_id=frame_id)
                _record(
                    context,
                    task_id,
                    "convergence.observe",
                    {
                        "state": observation.state.value,
                        "evidence": observation.evidence,
                        "frame_id": observation.frame_id,
                        "elapsed_seconds": observation.elapsed_seconds,
                    },
                )
                return True

            if operation == "action":
                action = payload.get("action")
                state = payload.get("state")
                evidence = payload.get("evidence", "")
                frame_id = payload.get("frame_id")
                succeeded = payload.get("succeeded", True)
                record = session.record_action(
                    action,
                    state=state,
                    evidence=evidence,
                    frame_id=frame_id,
                    succeeded=succeeded,
                )
                _record(
                    context,
                    task_id,
                    "convergence.action",
                    {
                        "action": record.action.value,
                        "state": record.state.value if record.state else None,
                        "succeeded": record.succeeded,
                        "elapsed_seconds": record.elapsed_seconds,
                        "budget": record.budget.__dict__
                        if hasattr(record.budget, "__dict__")
                        else str(record.budget),
                    },
                )
                return True

            if operation == "spend":
                kind = payload.get("kind")
                amount = payload.get("amount", 1)
                budget = session.spend(kind, amount)
                _record(
                    context,
                    task_id,
                    "convergence.spend",
                    {"kind": str(kind), "amount": amount, "budget": str(budget)},
                )
                return True

            if operation in {"finish", "fail"}:
                raw_outcome = (
                    payload.get("outcome", ConvergenceOutcome.CONVERGED.value)
                    if operation == "finish"
                    else ConvergenceOutcome.FAILED.value
                )
                outcome = ConvergenceOutcome(raw_outcome)
                session.finish(outcome)
                _record(
                    context,
                    task_id,
                    "convergence.finish",
                    {"outcome": outcome.value},
                )
                return True

            raise ValueError(f"unknown convergence operation: {operation}")
        except (BudgetExceeded, KeyError, RuntimeError, TypeError, ValueError):
            return False


__all__ = ["ConvergenceLifecycle", "session_for"]
