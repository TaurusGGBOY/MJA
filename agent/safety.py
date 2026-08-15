"""Compatibility records for workflow evidence.

The project no longer uses safety decisions as runtime blockers.  The types
and recognizer helpers remain available so existing diagnostics and integrations
can still record what was visible in a frame.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from agent.workflows.models import ActionIntent, TaskPolicy, VisualEvidence


class SafetyReason(StrEnum):
    """Legacy labels retained for diagnostic compatibility."""

    ALLOWED = "allowed"
    PAGE_MISSING = "page_missing"
    TARGET_MISSING = "target_missing"
    TARGET_AMBIGUOUS = "target_ambiguous"
    FRAME_MISMATCH = "frame_mismatch"
    PAID_SIGNAL = "paid_signal"
    VERIFICATION_SIGNAL = "verification_signal"
    UNKNOWN_CURRENCY = "unknown_currency"
    UNKNOWN_DIALOG = "unknown_dialog"
    ACTION_CAP_REACHED = "action_cap_reached"


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    """The result of authorization, with raw evidence findings for diagnostics."""

    allowed: bool
    reason: SafetyReason
    findings: tuple[str, ...] = ()


def _unique_findings(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Keep the first occurrence of each raw finding, preserving its spelling."""

    return tuple(dict.fromkeys(values))


def _decision(
    allowed: bool,
    reason: SafetyReason,
    findings: tuple[str, ...] | list[str] = (),
) -> SafetyDecision:
    return SafetyDecision(allowed, reason, _unique_findings(list(findings)))


def authorize_action(
    evidence: VisualEvidence,
    intent: ActionIntent,
    policy: TaskPolicy,
    action_counts: Mapping[str, int],
) -> SafetyDecision:
    """Return an always-allowed compatibility decision.

    The recognizers, page/target evidence, resource labels, and action caps are
    still passed through by callers for tracing, but none of those signals is a
    safety stop anymore.  Workflow state machines and their finite step/action
    bounds remain responsible for ordinary navigation and loop control.
    """

    del intent, policy, action_counts
    findings = [
        *(
            marker
            for marker, hits in evidence.danger_hits.items()
            if hits != 0
        ),
        *evidence.texts,
    ]
    return _decision(True, SafetyReason.ALLOWED, findings)


__all__ = [
    "ActionIntent",
    "SafetyDecision",
    "SafetyReason",
    "TaskPolicy",
    "VisualEvidence",
    "authorize_action",
]
