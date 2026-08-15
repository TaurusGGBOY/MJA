"""Bounded Android workflow for 活动 → 破阵演武 → 开始挑战.

This module is intentionally task-local.  The shared catalog and ProjectInterface
are not changed by this task; the MFW registration points are reported with the
handoff.  The state machine requires an explicit daily terminal marker after
all remaining results, so challenge clicks alone can never be reported as
success.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from ..models import ActionIntent, Decision, InputKind, StateSnapshot, TaskStatus, Transition

CANONICAL_TASK_ID = "BREAK_ARRAY_MARTIAL_DAILY"
MAX_CHALLENGES = 3
MAX_STARTUP_POLLS = 12
MAX_BATTLE_POLLS = 12
MAX_RESULT_POLLS = 3
ENTRY_NODE = f"MJA_{CANONICAL_TASK_ID}_START"

_REMAINING_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*([1-9]\d?)(?!\d)")
_CONFIRM_STATE_PREFIX = "confirm_break_array:"
_POST_CONFIRM_STATE_PREFIX = "post_confirm_break_array:"
_LIVE_TOTAL_CHALLENGES = 9


@dataclass(frozen=True, slots=True)
class BreakArrayMartialPolicy:
    """Task-local finite policy, kept out of the shared catalog by design."""

    task_id: str = CANONICAL_TASK_ID
    label: str = "破阵演武（每日三次）"
    entry: str = ENTRY_NODE
    max_steps: int = 64
    action_caps: Mapping[str, int] = field(default_factory=dict)
    eligible_weekdays: frozenset[int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_caps",
            {
                "open_break_array_activity": 1,
                "open_break_array": 1,
                "wait_break_array_startup": MAX_STARTUP_POLLS,
                "resume_break_array": 1,
                "start_break_array_challenge": MAX_CHALLENGES,
                "confirm_break_array_challenge": MAX_CHALLENGES,
                "start_break_array_battle": MAX_CHALLENGES,
                "wait_break_array_battle": MAX_BATTLE_POLLS,
                "wait_break_array_result": MAX_RESULT_POLLS,
                "resume_break_array_result": 1,
                "dismiss_break_array_result": MAX_CHALLENGES,
            },
        )


BREAK_ARRAY_MARTIAL_DAILY_POLICY = BreakArrayMartialPolicy()


def _hit(snapshot: StateSnapshot, marker: str) -> bool:
    evidence = snapshot.evidence
    return evidence is not None and evidence.target_hits.get(marker, 0) == 1


def _page_or_target_hit(snapshot: StateSnapshot, marker: str) -> bool:
    evidence = snapshot.evidence
    if evidence is None:
        return False
    return (
        evidence.page_hits.get(marker, 0) == 1
        or evidence.target_hits.get(marker, 0) == 1
    )


def _remaining_counter(snapshot: StateSnapshot) -> tuple[int, int] | None:
    """Read the task-local ``remaining/total`` counter from OCR evidence.

    The counter is deliberately read from the recognizer's ROI text rather
    than inferred from the number of clicks in this process.  That makes a
    resumed run safe: if challenges were completed before a process failure,
    the next run never exceeds the visible remainder or the three-action cap.
    """

    evidence = snapshot.evidence
    if evidence is None:
        return None
    for text in evidence.texts:
        match = _REMAINING_PATTERN.search(text)
        if match is not None:
            remaining = int(match.group(1))
            total = int(match.group(2))
            if remaining <= total:
                return remaining, total
    if _hit(snapshot, "break_array.remaining_exhausted"):
        return 0, _LIVE_TOTAL_CHALLENGES
    return None


def _remaining_attempts(snapshot: StateSnapshot) -> int | None:
    counter = _remaining_counter(snapshot)
    return counter[0] if counter is not None else None


def _counter_state(prefix: str, counter: tuple[int, int] | None) -> str:
    if counter is None:
        return f"{prefix}unknown"
    return f"{prefix}{counter[0]}_of_{counter[1]}"


def _goal_reached(snapshot: StateSnapshot, challenge_count: int) -> bool:
    remaining = _remaining_attempts(snapshot)
    return challenge_count >= MAX_CHALLENGES or remaining == 0


def _transition(
    action: str,
    page: str,
    target: str,
    postcondition: str,
    next_state: str,
    *,
    input_kind: InputKind = InputKind.CLICK,
    alternatives: tuple[str, ...] = (),
) -> Transition:
    return Transition(
        ActionIntent(action, page, target, input_kind=input_kind),
        postcondition,
        next_state,
        alternatives,
    )


class BreakArrayMartialDailyDefinition:
    """Activity entry plus a three-result finite combat loop."""

    task_id = CANONICAL_TASK_ID
    initial_state = "home"
    danger_markers = (
        "break_array.unknown_dialog",
        "safety.paid",
        "safety.verification",
    )

    _state_recognizers = {
        "home": (
            "activity.entry",
            "activity.page",
            "break_array.page",
            "break_array.entry",
            "break_array.completed",
            "break_array.remaining_exhausted",
            "break_array.startup_loading",
        ),
        "activity": (
            "activity.page",
            "break_array.entry",
            "break_array.page",
            "break_array.unavailable",
        ),
        "break_array": (
            "break_array.page",
            "break_array.start",
            "break_array.remaining",
            "break_array.remaining_exhausted",
            "break_array.completed",
            "break_array.unavailable",
            "break_array.result",
            "break_array.success",
            "break_array.failure",
            "break_array.result_close",
        ),
        "battle": (
            "break_array.prepare_page",
            "break_array.prepare_formation",
            "break_array.prepare_boss",
            "break_array.prepare_duration",
            "break_array.prepare_tactics",
            "break_array.prepare_start",
            "break_array.confirm_transition",
            "break_array.battle_loading",
            "break_array.battle",
            "break_array.result",
            "break_array.success",
            "break_array.failure",
            "break_array.result_close",
        ),
        "result": (
            "break_array.result",
            "break_array.success",
            "break_array.failure",
            "break_array.result_close",
        ),
        "verify": (
            "break_array.page",
            "break_array.remaining",
            "break_array.remaining_exhausted",
            "break_array.completed",
        ),
    }

    terminal_postconditions = {
        TaskStatus.COMPLETED: "break_array.three_challenges",
        TaskStatus.ALREADY_COMPLETE: "break_array.daily_exhausted",
        TaskStatus.NOT_ELIGIBLE: "break_array.unavailable",
        TaskStatus.FAILED: "break_array.postcondition_missing",
    }

    def recognizers(self, state: str) -> tuple[str, ...]:
        if state.startswith(_CONFIRM_STATE_PREFIX):
            values = [
                "break_array.start_confirm_dialog",
                "break_array.start_confirm_button",
            ]
        elif state.startswith(_POST_CONFIRM_STATE_PREFIX):
            values = [
                "break_array.prepare_page",
                "break_array.prepare_formation",
                "break_array.prepare_boss",
                "break_array.prepare_duration",
                "break_array.prepare_tactics",
                "break_array.prepare_start",
                "break_array.confirm_transition",
                "break_array.battle_loading",
                "break_array.battle",
                "break_array.result",
                "break_array.success",
                "break_array.failure",
                "break_array.page",
                "break_array.start",
                "break_array.remaining",
                "break_array.remaining_exhausted",
                "break_array.completed",
            ]
        else:
            values = list(self._state_recognizers.get(state, ()))
        values.extend(self.danger_markers)
        return tuple(dict.fromkeys(values))

    def _failed(self) -> Decision:
        return Decision.finish(TaskStatus.FAILED)

    def _terminal_from_break_array(
        self,
        snapshot: StateSnapshot,
        challenge_count: int,
    ) -> Decision | None:
        if _hit(snapshot, "break_array.unavailable"):
            return Decision.finish(TaskStatus.NOT_ELIGIBLE)
        completed = (
            _hit(snapshot, "break_array.completed")
            or _hit(snapshot, "break_array.remaining_exhausted")
            or _remaining_attempts(snapshot) == 0
        )
        if not completed:
            return None
        if challenge_count > 0:
            return Decision.finish(TaskStatus.COMPLETED)
        return Decision.finish(TaskStatus.ALREADY_COMPLETE)

    def _decide_break_array_page(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        challenge_count = counters.get("start_break_array_challenge", 0)
        confirm_count = counters.get("confirm_break_array_challenge", 0)
        battle_start_count = counters.get("start_break_array_battle", 0)
        if not challenge_count == confirm_count == battle_start_count:
            return self._failed()
        terminal = self._terminal_from_break_array(snapshot, challenge_count)
        if terminal is not None:
            return terminal
        if _hit(snapshot, "break_array.failure"):
            return self._failed()
        if _page_or_target_hit(snapshot, "break_array.result") or _hit(
            snapshot, "break_array.success"
        ):
            result_target = (
                "break_array.result"
                if _hit(snapshot, "break_array.result")
                else "break_array.success"
            )
            return Decision.act(
                _transition(
                    "resume_break_array_result",
                    "break_array.result",
                    result_target,
                    "break_array.result",
                    "result",
                    input_kind=InputKind.NONE,
                    alternatives=("break_array.success",),
                )
            )
        remaining_counter = _remaining_counter(snapshot)
        remaining = remaining_counter[0] if remaining_counter is not None else None
        if _hit(snapshot, "break_array.remaining") and remaining is None:
            return self._failed()
        if challenge_count >= MAX_CHALLENGES or remaining == 0:
            return self._failed()
        # A new consumptive challenge is allowed only after the previous
        # challenge, confirmation, and formation-page start are fully paired.
        if _page_or_target_hit(snapshot, "break_array.page") and _hit(
            snapshot, "break_array.start"
        ):
            return Decision.act(
                _transition(
                    "start_break_array_challenge",
                    "break_array.page",
                    "break_array.start",
                    "break_array.start_confirm_dialog",
                    _counter_state(_CONFIRM_STATE_PREFIX, remaining_counter),
                )
            )
        return self._failed()

    def _decide_confirm(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        # The generic unknown-dialog recognizer also sees the popup's Cancel
        # button. It may be ignored only when title + both body semantics +
        # the exact right-hand confirmation target all coexist in this frame.
        if any(
            _hit(snapshot, marker)
            for marker in ("safety.paid", "safety.verification")
        ):
            return self._failed()
        if not (
            _hit(snapshot, "break_array.start_confirm_dialog")
            and _hit(snapshot, "break_array.start_confirm_button")
        ):
            return self._failed()

        challenge_count = counters.get("start_break_array_challenge", 0)
        confirm_count = counters.get("confirm_break_array_challenge", 0)
        battle_start_count = counters.get("start_break_array_battle", 0)
        if (
            challenge_count <= 0
            or challenge_count > MAX_CHALLENGES
            or confirm_count != challenge_count - 1
            or battle_start_count != confirm_count
        ):
            return self._failed()

        post_state = snapshot.state.replace(
            _CONFIRM_STATE_PREFIX,
            _POST_CONFIRM_STATE_PREFIX,
            1,
        )
        return Decision.act(
            _transition(
                "confirm_break_array_challenge",
                "break_array.start_confirm_dialog",
                "break_array.start_confirm_button",
                "break_array.prepare_page",
                post_state,
            )
        )

    def _decide_post_confirm(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        if any(_hit(snapshot, marker) for marker in self.danger_markers):
            return self._failed()

        # Confirmation verification remains inside the engine until the
        # fully rendered formation page is captured.  A black Unity hand-off
        # is not a battle boundary and must never consume a wait action.
        if _hit(snapshot, "break_array.prepare_page"):
            return self._decide_prepare_page(snapshot, counters)
        return self._failed()

    def _decide_prepare_page(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        """Start exactly one battle from one confirmed formation page."""

        challenge_count = counters.get("start_break_array_challenge", 0)
        confirm_count = counters.get("confirm_break_array_challenge", 0)
        battle_start_count = counters.get("start_break_array_battle", 0)
        if not (
            _hit(snapshot, "break_array.prepare_page")
            and _hit(snapshot, "break_array.prepare_start")
            and challenge_count == confirm_count
            and battle_start_count == confirm_count - 1
            and confirm_count <= MAX_CHALLENGES
        ):
            return self._failed()
        return Decision.act(
            _transition(
                "start_break_array_battle",
                "break_array.prepare_page",
                "break_array.prepare_start",
                "break_array.battle_loading",
                "battle",
                alternatives=(
                    "break_array.battle",
                    "break_array.result",
                    "break_array.success",
                    "break_array.failure",
                ),
            )
        )

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        evidence = snapshot.evidence
        if evidence is None:
            return self._failed()
        if snapshot.state.startswith(_CONFIRM_STATE_PREFIX):
            return self._decide_confirm(snapshot, counters)
        if snapshot.state.startswith(_POST_CONFIRM_STATE_PREFIX):
            return self._decide_post_confirm(snapshot, counters)
        if any(_hit(snapshot, marker) for marker in self.danger_markers):
            return self._failed()

        challenge_count = counters.get("start_break_array_challenge", 0)
        confirm_count = counters.get("confirm_break_array_challenge", 0)
        battle_start_count = counters.get("start_break_array_battle", 0)
        poll_count = counters.get("wait_break_array_battle", 0)
        result_poll_count = counters.get("wait_break_array_result", 0)

        if snapshot.state == "home":
            if _page_or_target_hit(snapshot, "break_array.page"):
                return Decision.act(
                    _transition(
                        "resume_break_array",
                        "break_array.page",
                        "break_array.page",
                        "break_array.page",
                        "break_array",
                        input_kind=InputKind.NONE,
                    )
                )
            if _page_or_target_hit(snapshot, "activity.page"):
                return Decision.act(
                    _transition(
                        "resume_break_array",
                        "activity.page",
                        "activity.page",
                        "activity.page",
                        "activity",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "activity.entry"):
                return Decision.act(
                    _transition(
                        "open_break_array_activity",
                        "home",
                        "activity.entry",
                        "activity.page",
                        "activity",
                    )
                )
            if _hit(snapshot, "break_array.startup_loading"):
                if counters.get("wait_break_array_startup", 0) >= MAX_STARTUP_POLLS:
                    return self._failed()
                return Decision.act(
                    _transition(
                        "wait_break_array_startup",
                        "break_array.startup_loading",
                        "break_array.startup_loading",
                        "break_array.startup_loading",
                        "home",
                        input_kind=InputKind.NONE,
                        alternatives=(
                            "break_array.home",
                            "activity.entry",
                            "activity.page",
                            "break_array.page",
                            "break_array.completed",
                            "break_array.remaining_exhausted",
                            "break_array.unavailable",
                        ),
                    )
                )
            return self._failed()

        if snapshot.state == "activity":
            if _hit(snapshot, "break_array.unavailable"):
                return Decision.finish(TaskStatus.NOT_ELIGIBLE)
            if _page_or_target_hit(snapshot, "break_array.page"):
                return Decision.act(
                    _transition(
                        "resume_break_array",
                        "break_array.page",
                        "break_array.page",
                        "break_array.page",
                        "break_array",
                        input_kind=InputKind.NONE,
                    )
                )
            if _hit(snapshot, "break_array.entry"):
                return Decision.act(
                    _transition(
                        "open_break_array",
                        "activity.page",
                        "break_array.entry",
                        "break_array.page",
                        "break_array",
                    )
                )
            return self._failed()

        if snapshot.state == "break_array":
            return self._decide_break_array_page(snapshot, counters)

        if snapshot.state == "battle":
            if _hit(snapshot, "break_array.prepare_page"):
                return self._decide_prepare_page(snapshot, counters)
            if _hit(snapshot, "break_array.failure"):
                return self._failed()
            if (
                challenge_count <= 0
                or not challenge_count == confirm_count == battle_start_count
            ):
                return self._failed()
            if _hit(snapshot, "break_array.success"):
                result_target = (
                    "break_array.result"
                    if _hit(snapshot, "break_array.result")
                    else "break_array.success"
                )
                return Decision.act(
                    _transition(
                        "resume_break_array_result",
                        "break_array.result",
                        result_target,
                        "break_array.result",
                        "result",
                        input_kind=InputKind.NONE,
                        alternatives=("break_array.success",),
                    )
                )
            if _hit(snapshot, "break_array.result"):
                return self._failed()
            if poll_count >= MAX_BATTLE_POLLS:
                return self._failed()
            if (
                _hit(snapshot, "break_array.battle_loading")
                or _hit(snapshot, "break_array.battle")
            ):
                poll_target = (
                    "break_array.battle_loading"
                    if _hit(snapshot, "break_array.battle_loading")
                    else "break_array.battle"
                )
                return Decision.act(
                    _transition(
                        "wait_break_array_battle",
                        "break_array.battle",
                        poll_target,
                        poll_target,
                        "battle",
                        input_kind=InputKind.NONE,
                        alternatives=tuple(
                            marker
                            for marker in (
                                "break_array.battle",
                                "break_array.battle_loading",
                                "break_array.success",
                                "break_array.failure",
                                "break_array.result",
                            )
                            if marker != poll_target
                        ),
                    )
                )
            return self._failed()

        if snapshot.state == "result":
            if not challenge_count == confirm_count == battle_start_count:
                return self._failed()
            if _hit(snapshot, "break_array.failure"):
                return self._failed()
            if _hit(snapshot, "break_array.success"):
                if _hit(snapshot, "break_array.result_close"):
                    if _goal_reached(snapshot, challenge_count):
                        return Decision.act(
                            _transition(
                                "dismiss_break_array_result",
                                "break_array.result",
                                "break_array.result_close",
                                "break_array.page",
                                "verify",
                                alternatives=(
                                    "break_array.completed",
                                    "break_array.remaining_exhausted",
                                ),
                            )
                        )
                    return Decision.act(
                        _transition(
                            "dismiss_break_array_result",
                            "break_array.result",
                            "break_array.result_close",
                            "break_array.page",
                            "break_array",
                            alternatives=(
                                "break_array.remaining",
                                "break_array.remaining_exhausted",
                                "break_array.completed",
                            ),
                        )
                    )
                if result_poll_count >= MAX_RESULT_POLLS:
                    return self._failed()
                wait_target = (
                    "break_array.result"
                    if _hit(snapshot, "break_array.result")
                    else "break_array.success"
                )
                return Decision.act(
                    _transition(
                        "wait_break_array_result",
                        "break_array.result",
                        wait_target,
                        "break_array.result",
                        "result",
                        input_kind=InputKind.NONE,
                        alternatives=("break_array.success", "break_array.result_close"),
                    )
                )
            return self._failed()

        if snapshot.state == "verify":
            if (
                challenge_count == 0
                or not challenge_count == confirm_count == battle_start_count
            ):
                return self._failed()
            remaining = _remaining_attempts(snapshot)
            if (
                _hit(snapshot, "break_array.completed")
                or _hit(snapshot, "break_array.remaining_exhausted")
                or remaining == 0
                or (
                    challenge_count >= MAX_CHALLENGES
                    and _page_or_target_hit(snapshot, "break_array.page")
                    and remaining is not None
                )
            ):
                return Decision.finish(TaskStatus.COMPLETED)
            return self._failed()

        return self._failed()


BREAK_ARRAY_MARTIAL_DAILY_DEFINITION = BreakArrayMartialDailyDefinition()


def terminal_postcondition(status: TaskStatus) -> str:
    """Return the stable business postcondition for MFW result persistence."""

    return BREAK_ARRAY_MARTIAL_DAILY_DEFINITION.terminal_postconditions[status]


__all__ = [
    "BREAK_ARRAY_MARTIAL_DAILY_DEFINITION",
    "BREAK_ARRAY_MARTIAL_DAILY_POLICY",
    "BreakArrayMartialDailyDefinition",
    "CANONICAL_TASK_ID",
    "ENTRY_NODE",
    "MAX_BATTLE_POLLS",
    "MAX_CHALLENGES",
    "MAX_RESULT_POLLS",
    "MAX_STARTUP_POLLS",
    "terminal_postcondition",
]
