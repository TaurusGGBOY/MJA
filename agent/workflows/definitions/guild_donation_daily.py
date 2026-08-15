"""Bounded workflow for 帮会 → 捐献 → 免费捐献.

The donation counter is the business invariant, not the number of clicks made by
the process.  A run may click the free-donation target only when the current
frame proves ``10/10``.  It is successful only after a fresh frame proves
``9/10``.  Any other counter, paid surface, verification surface, or unknown
popup fails closed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ..models import ActionIntent, Decision, InputKind, StateSnapshot, TaskStatus, Transition

CANONICAL_TASK_ID = "GUILD_DONATION_DAILY"
ENTRY_NODE = f"MJA_{CANONICAL_TASK_ID}_START"
MAX_FREE_DONATIONS = 1
_COUNTER = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*10(?!\d)")


@dataclass(frozen=True, slots=True)
class GuildDonationPolicy:
    """Task-local finite policy used by the optional legacy workflow bridge."""

    task_id: str = CANONICAL_TASK_ID
    label: str = "帮会捐献"
    entry: str = ENTRY_NODE
    max_steps: int = 24
    action_caps: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_caps",
            MappingProxyType(
                {
                    "open_function_panel": 1,
                    "open_guild": 1,
                    "open_guild_donation": 1,
                    "donate_guild_free_once": MAX_FREE_DONATIONS,
                    "close_guild_donation": 1,
                    "resume_function_panel": 1,
                    "resume_guild": 1,
                    "resume_guild_donation": 1,
                }
            ),
        )


GUILD_DONATION_DAILY_POLICY = GuildDonationPolicy()


def _hit(snapshot: StateSnapshot, marker: str) -> bool:
    evidence = snapshot.evidence
    if evidence is None:
        return False
    return (
        evidence.page_hits.get(marker, 0) == 1
        or evidence.target_hits.get(marker, 0) == 1
    )


def _counter(snapshot: StateSnapshot) -> int | None:
    evidence = snapshot.evidence
    if evidence is None:
        return None
    for text in evidence.texts:
        match = _COUNTER.search(text)
        if match is not None:
            return int(match.group(1))
    for value, marker in (
        (9, "guild.donation.remaining_9_of_10"),
        (10, "guild.donation.remaining_10_of_10"),
    ):
        if _hit(snapshot, marker):
            return value
    return None


def _transition(
    action: str,
    page: str,
    target: str,
    postcondition: str,
    next_state: str,
    *,
    input_kind: InputKind = InputKind.CLICK,
) -> Transition:
    return Transition(
        ActionIntent(action, page, target, input_kind=input_kind),
        postcondition,
        next_state,
    )


class GuildDonationDailyDefinition:
    """Navigate to guild donation and perform at most one free donation."""

    task_id = CANONICAL_TASK_ID
    initial_state = "home"
    danger_markers = (
        "guild.donation.paid",
        "guild.donation.unknown_popup",
        "safety.paid",
        "safety.verification",
    )

    _state_recognizers = {
        "home": (
            "home",
            "function_panel.page",
            "function_panel.open",
            "guild.page",
            "guild.donation.page",
            "guild.donation.context",
            *danger_markers,
        ),
        "panel": (
            "function_panel.page",
            "guild.entry",
            "guild.page",
            "guild.donation.page",
            *danger_markers,
        ),
        "guild": (
            "guild.page",
            "guild.donation.entry",
            "guild.donation.page",
            *danger_markers,
        ),
        "donation": (
            "guild.donation.page",
            "guild.donation.context",
            "guild.donation.free",
            "guild.donation.remaining_10_of_10",
            "guild.donation.remaining_9_of_10",
            "guild.donation.remaining_invalid",
            "guild.donation.unavailable",
            *danger_markers,
        ),
        "verify": (
            "guild.donation.page",
            "guild.donation.remaining_9_of_10",
            *danger_markers,
        ),
    }

    terminal_postconditions = {
        TaskStatus.COMPLETED: "guild.donation.remaining_9_of_10",
        TaskStatus.ALREADY_COMPLETE: "guild.donation.remaining_9_of_10",
        TaskStatus.NOT_ELIGIBLE: "guild.donation.unavailable",
        TaskStatus.FAILED: "guild.donation.postcondition_missing",
    }

    def recognizers(self, state: str) -> tuple[str, ...]:
        return tuple(self._state_recognizers.get(state, ()))

    def _failed(self) -> Decision:
        return Decision.finish(TaskStatus.FAILED)

    def _safe(self, snapshot: StateSnapshot) -> bool:
        return not any(_hit(snapshot, marker) for marker in self.danger_markers)

    def _page(self, snapshot: StateSnapshot) -> bool:
        return _hit(snapshot, "guild.donation.page") and _hit(
            snapshot, "guild.donation.context"
        )

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        if snapshot.evidence is None or not self._safe(snapshot):
            return self._failed()

        if snapshot.state == "home":
            if self._page(snapshot):
                return Decision.act(
                    _transition(
                        "resume_guild_donation",
                        "guild.donation.page",
                        "guild.donation.context",
                        "guild.donation.page",
                        "donation",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "guild.page"):
                return Decision.act(
                    _transition(
                        "resume_guild",
                        "guild.page",
                        "guild.page",
                        "guild.page",
                        "guild",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "function_panel.page"):
                return Decision.act(
                    _transition(
                        "resume_function_panel",
                        "function_panel.page",
                        "function_panel.page",
                        "function_panel.page",
                        "panel",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "home"):
                return Decision.act(
                    _transition(
                        "open_function_panel",
                        "home",
                        "function_panel.open",
                        "function_panel.page",
                        "panel",
                    )
                )
            return self._failed()

        if snapshot.state == "panel":
            if self._page(snapshot):
                return Decision.act(
                    _transition(
                        "resume_guild_donation",
                        "guild.donation.page",
                        "guild.donation.context",
                        "guild.donation.page",
                        "donation",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "guild.page"):
                return Decision.act(
                    _transition(
                        "resume_guild",
                        "guild.page",
                        "guild.page",
                        "guild.page",
                        "guild",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "guild.entry"):
                return Decision.act(
                    _transition(
                        "open_guild",
                        "function_panel.page",
                        "guild.entry",
                        "guild.page",
                        "guild",
                    )
                )
            return self._failed()

        if snapshot.state == "guild":
            if self._page(snapshot):
                return Decision.act(
                    _transition(
                        "resume_guild_donation",
                        "guild.donation.page",
                        "guild.donation.context",
                        "guild.donation.page",
                        "donation",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "guild.donation.entry"):
                return Decision.act(
                    _transition(
                        "open_guild_donation",
                        "guild.page",
                        "guild.donation.entry",
                        "guild.donation.page",
                        "donation",
                    )
                )
            return self._failed()

        if snapshot.state == "donation":
            if _hit(snapshot, "guild.donation.unavailable"):
                return Decision.finish(TaskStatus.NOT_ELIGIBLE)
            remaining = _counter(snapshot)
            if remaining == 9:
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            if remaining != 10:
                return self._failed()
            if _hit(snapshot, "guild.donation.free") and _hit(
                snapshot, "guild.donation.page"
            ):
                return Decision.act(
                    _transition(
                        "donate_guild_free_once",
                        "guild.donation.page",
                        "guild.donation.free",
                        "guild.donation.page",
                        "verify",
                    )
                )
            return self._failed()

        if snapshot.state == "verify":
            if (
                counters.get("donate_guild_free_once", 0) == MAX_FREE_DONATIONS
                and self._page(snapshot)
                and _counter(snapshot) == 9
            ):
                return Decision.finish(TaskStatus.COMPLETED)
            return self._failed()

        return self._failed()


GUILD_DONATION_DAILY_DEFINITION = GuildDonationDailyDefinition()


def terminal_postcondition(status: TaskStatus) -> str:
    return GUILD_DONATION_DAILY_DEFINITION.terminal_postconditions[status]


__all__ = [
    "CANONICAL_TASK_ID",
    "ENTRY_NODE",
    "GUILD_DONATION_DAILY_DEFINITION",
    "GUILD_DONATION_DAILY_POLICY",
    "GuildDonationDailyDefinition",
    "GuildDonationPolicy",
    "MAX_FREE_DONATIONS",
    "terminal_postcondition",
]
