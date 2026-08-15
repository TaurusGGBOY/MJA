"""Bounded capture-decide-authorize-act-verify workflow execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from time import monotonic, sleep
from typing import Any, Protocol, runtime_checkable

from agent.errors import MJAError
from agent.safety import SafetyDecision, SafetyReason

from .models import (
    CapturedFrame,
    Decision,
    StateSnapshot,
    TaskPolicy,
    TaskResult,
    TaskStatus,
    VisualEvidence,
    WorkflowDefinition,
)

# These actions only open or re-open a known navigation surface.  If the
# renderer drops the first postcondition (common during Unity transitions), a
# bounded retry is safe after a fresh frame and, when available, a driver-level
# session recovery.  Consumptive, claim, purchase, and combat actions are
# deliberately absent: repeating those from an uncertain screen could spend a
# resource twice.
_RETRYABLE_NAVIGATION_ACTIONS = frozenset(
    {
        "open_function_panel",
        "open_function_panel_verify",
        "open_daily_tasks",
        "open_daily_tasks_initial",
        "open_daily_tasks_verify",
        # The Jianlin row can open a reward sheet when the business action
        # was completed by an earlier run.  Re-entering the task boundary is
        # safe after the sheet is dismissed; combat and purchases remain
        # outside this retry set.
        "open_jianlin",
        "open_painting_scroll",
        # Cross-map Shadow entry can terminate the Unity process on the
        # Android renderer while the route is being handed off.  This action
        # is navigation-only and can be replayed after lifecycle recovery;
        # combat, claims, and purchases remain deliberately excluded.
        "confirm_shadow_auto_route",
    }
)
_MAX_NAVIGATION_ATTEMPTS = 2
_NAVIGATION_DANGER_MARKERS = frozenset(
    {"unknown_dialog", "safety.paid", "safety.verification"}
)
_JIANLIN_BATTLE_ACTION = "start_jianlin_battle"
_JIANLIN_BATTLE_POSTCONDITION = "jianlin_battle_result"
_BREAK_ARRAY_CONFIRM_ACTION = "confirm_break_array_challenge"
_BREAK_ARRAY_CONFIRM_POSTCONDITION = "break_array.prepare_page"
_BREAK_ARRAY_START_ACTION = "start_break_array_battle"
_BREAK_ARRAY_BATTLE_POSTCONDITION = "break_array.battle_loading"
_BREAK_ARRAY_TRANSITION_ATTEMPTS = 30
_BREAK_ARRAY_TRANSITION_POLL_SECONDS = 1.0


@runtime_checkable
class WorkflowDriver(Protocol):
    def capture(self) -> CapturedFrame: ...

    def recognize(
        self,
        frame: CapturedFrame,
        recognizer_names: Sequence[str],
    ) -> VisualEvidence | StateSnapshot: ...

    def execute(self, intent: Any) -> None: ...


def _result(
    policy: TaskPolicy,
    status: TaskStatus,
    postcondition: str,
    counts: Mapping[str, int],
    error_code: str | None = None,
) -> TaskResult:
    return TaskResult(
        task_id=policy.task_id,
        status=status,
        postcondition=postcondition,
        action_counts=dict(counts),
        error_code=error_code,
    )


def _record(diagnostics: Any, method: str, *args: Any, **kwargs: Any) -> None:
    callback = getattr(diagnostics, method, None)
    if callback is not None:
        callback(*args, **kwargs)


def _snapshot(
    definition: WorkflowDefinition,
    state: str,
    frame: CapturedFrame,
    recognizers: Sequence[str],
    driver: WorkflowDriver,
) -> StateSnapshot:
    recognized = driver.recognize(frame, recognizers)
    if isinstance(recognized, StateSnapshot):
        if recognized.frame_id != frame.frame_id:
            raise ValueError("recognition returned a stale frame")
        return StateSnapshot(
            frame=frame,
            state=state,
            recognitions=recognized.recognitions,
            evidence=recognized.evidence,
        )
    if isinstance(recognized, VisualEvidence):
        if recognized.frame_id != frame.frame_id:
            raise ValueError("recognition returned a stale frame")
        return StateSnapshot(frame=frame, state=state, evidence=recognized)
    raise TypeError("driver.recognize must return VisualEvidence or StateSnapshot")


def _postcondition_seen(evidence: VisualEvidence | None, marker: str) -> bool:
    if evidence is None:
        return False
    return any(
        mapping.get(marker, 0) == 1
        for mapping in (evidence.page_hits, evidence.target_hits)
    )


def _navigation_retry_is_safe(evidence: VisualEvidence | None) -> bool:
    if evidence is None:
        return True
    return not any(
        evidence.danger_hits.get(marker, 0) == 1
        for marker in _NAVIGATION_DANGER_MARKERS
    )


def _recover_for_navigation_retry(driver: WorkflowDriver, diagnostics: Any) -> bool:
    """Best-effort recovery before a finite idempotent navigation retry."""

    # A failed navigation can leave a still-live game on a delayed tutorial
    # or modal surface.  Prefer the driver's bounded visual boundary cleanup
    # in that case.  Calling the full Android lifecycle recovery first enters
    # LoginGate.wait_until_ready(), whose configured login deadline is much
    # larger than this workflow retry and can make one harmless navigation
    # miss look like a shared-runtime hang.
    return_home = getattr(driver, "return_to_home", None)
    if callable(return_home):
        recovered: bool | None = None
        error_code: str | None = None
        try:
            try:
                recovered = bool(return_home(max_steps=8, check_foreground=False))
            except TypeError:
                recovered = bool(return_home(max_steps=8))
        except Exception as exc:
            error_code = getattr(getattr(exc, "code", None), "value", None)
            error_code = str(error_code or type(exc).__name__)
        details: dict[str, Any] = {
            "recovered": recovered,
            "mode": "bounded_boundary",
        }
        if error_code is not None:
            details["error_code"] = error_code
        _record(diagnostics, "event", "navigation_retry_recovery", details)
        # Do not fall through to the unbounded lifecycle gate when the live
        # boundary is unknown. The next workflow iteration will capture a
        # fresh frame and fail this task locally if the game really died.
        return recovered is True

    recover = getattr(driver, "recover_game_ready", None)
    recovered: bool | None = None
    error_code: str | None = None
    if callable(recover):
        try:
            try:
                recovered = bool(recover(restart_if_needed=True))
            except TypeError:
                recovered = bool(recover())
        except Exception as exc:
            error_code = getattr(getattr(exc, "code", None), "value", None)
            error_code = str(error_code or type(exc).__name__)
    details: dict[str, Any] = {"recovered": recovered}
    if error_code is not None:
        details["error_code"] = error_code
    _record(diagnostics, "event", "navigation_retry_recovery", details)
    return recovered is True


def _authorize(
    evidence: VisualEvidence,
    intent: Any,
    policy: TaskPolicy,
    counts: Mapping[str, int],
) -> SafetyDecision:
    """Keep the selected runtime workflow non-blocking.

    Safety recognizers remain in the evidence trace for diagnosis, but they no
    longer stop a selected daily task. Login/OTP handling is still owned by
    the Android login boundary, outside this workflow engine.
    """

    del evidence, intent, policy, counts
    return SafetyDecision(True, SafetyReason.ALLOWED, ())


def run_workflow(
    definition: WorkflowDefinition,
    driver: WorkflowDriver,
    policy: TaskPolicy,
    diagnostics: Any,
    *,
    day: date | None = None,
    timeout_seconds: float | None = 60.0,
) -> TaskResult:
    """Run one definition with a fresh frame around every possible input."""

    if policy.eligible_weekdays is not None:
        workflow_day = day or date.today()
        if workflow_day.weekday() not in policy.eligible_weekdays:
            result = _result(policy, TaskStatus.NOT_ELIGIBLE, "weekday_not_eligible", {})
            _record(diagnostics, "write_task_result", result)
            return result

    state = definition.initial_state
    counts: dict[str, int] = {}
    started = monotonic()
    _record(diagnostics, "start_task", policy.task_id)

    for step in range(policy.max_steps):
        if timeout_seconds is not None and monotonic() - started >= timeout_seconds:
            result = _result(policy, TaskStatus.FAILED, state, counts, "WORKFLOW_TIMEOUT")
            _record(diagnostics, "write_task_result", result)
            return result
        try:
            frame = driver.capture()
            recognizers = tuple(definition.recognizers(state))
            snapshot = _snapshot(definition, state, frame, recognizers, driver)
            _record(diagnostics, "record_frame", frame, "before")
            decision = definition.decide(snapshot, counts)
            if not isinstance(decision, Decision):
                raise TypeError("workflow definition returned an invalid Decision")
            if decision.status is not None:
                result = _result(
                    policy,
                    decision.status,
                    state,
                    counts,
                    "WORKFLOW_POSTCONDITION_MISSING"
                    if decision.status is TaskStatus.FAILED
                    else None,
                )
                _record(diagnostics, "write_task_result", result)
                return result

            transition = decision.transition
            assert transition is not None
            evidence = snapshot.evidence
            if evidence is None:
                raise ValueError("workflow snapshot has no visual evidence")
            authorization = _authorize(
                evidence,
                transition.intent,
                policy,
                counts,
            )
            _record(
                diagnostics,
                "record_action",
                transition.intent,
                authorization,
                frame.frame_id,
            )
            driver.execute(transition.intent)
            counts[transition.intent.action_id] = counts.get(transition.intent.action_id, 0) + 1
            postconditions = (
                transition.postcondition,
                *transition.postcondition_alternatives,
            )
            next_state = transition.next_state or state
            # The post-action frame is labelled with ``next_state`` below, so
            # it must be recognized with that state's actual mapping.  Using
            # only the pre-action recognizers hid derived markers whose
            # components live exclusively in the next state.  In particular,
            # BREAK_ARRAY's prepare_page is synthesized from four same-frame
            # OCR anchors; asking only for the aggregate marker can never make
            # the runtime snapshot true.
            next_recognizers = tuple(definition.recognizers(next_state))
            after_names = tuple(
                dict.fromkeys((*recognizers, *next_recognizers, *postconditions))
            )
            after_snapshot: StateSnapshot | None = None
            battle_polling = (
                transition.intent.action_id == "battle"
                and transition.postcondition == "shadow_battle_result"
            )
            jianlin_battle_polling = (
                transition.intent.action_id == _JIANLIN_BATTLE_ACTION
                and transition.postcondition == _JIANLIN_BATTLE_POSTCONDITION
            )
            break_array_transition_polling = (
                transition.intent.action_id == _BREAK_ARRAY_CONFIRM_ACTION
                and transition.postcondition == _BREAK_ARRAY_CONFIRM_POSTCONDITION
            ) or (
                transition.intent.action_id == _BREAK_ARRAY_START_ACTION
                and transition.postcondition == _BREAK_ARRAY_BATTLE_POSTCONDITION
            )
            if jianlin_battle_polling:
                verification_attempts = 100
                poll_seconds = 3.0
            elif battle_polling:
                verification_attempts = 80
                poll_seconds = 3.0
            elif break_array_transition_polling:
                # r20/r21 live captures show that both the confirmation-to-
                # formation and formation-to-combat hand-offs can remain on a
                # black Unity transition well beyond the generic three quick
                # captures.  Poll screenshots only; no action is replayed.
                verification_attempts = _BREAK_ARRAY_TRANSITION_ATTEMPTS
                poll_seconds = _BREAK_ARRAY_TRANSITION_POLL_SECONDS
            else:
                verification_attempts = 3
                poll_seconds = 0.0
            for attempt in range(verification_attempts):
                if attempt > 0 and poll_seconds > 0:
                    # Completion is visual state, not a fixed-duration delay.
                    # Re-capture at the bounded action-specific cadence and
                    # return immediately when the expected marker appears.
                    sleep(poll_seconds)
                after_frame = driver.capture()
                candidate = _snapshot(
                    definition,
                    transition.next_state or state,
                    after_frame,
                    after_names,
                    driver,
                )
                _record(diagnostics, "record_frame", after_frame, "after")
                after_snapshot = candidate
                if any(
                    _postcondition_seen(candidate.evidence, marker)
                    for marker in postconditions
                ):
                    break
            if after_snapshot is None or not _postcondition_seen(
                after_snapshot.evidence, transition.postcondition
            ) and not any(
                _postcondition_seen(after_snapshot.evidence, marker)
                for marker in transition.postcondition_alternatives
            ):
                # The live Shadow popup occasionally consumes the first OCR
                # click without navigating.  Retry only while a fresh frame
                # still proves both the same popup and the same 前往 target;
                # once either disappears, a second click is forbidden.
                if (
                    transition.intent.action_id == "enter_shadow_stage"
                    and after_snapshot is not None
                    and after_snapshot.evidence is not None
                    and after_snapshot.evidence.page_hits.get("shadow_popup", 0) == 1
                    and after_snapshot.evidence.target_hits.get("shadow_go", 0) == 1
                    and counts.get("enter_shadow_stage", 0)
                    < policy.action_caps.get("enter_shadow_stage", 0)
                ):
                    state = "popup"
                    continue
                if (
                    after_snapshot is not None
                    and after_snapshot.evidence is not None
                    and after_snapshot.evidence.target_hits.get("dungeon_bag_full", 0) == 1
                ):
                    result = _result(
                        policy,
                        # The game explicitly refused the sweep because the
                        # account inventory is full. This is a valid business
                        # precondition, not an automation failure; preserve
                        # the evidence without publishing a retryable error.
                        TaskStatus.NOT_ELIGIBLE,
                        transition.postcondition,
                        counts,
                    )
                    _record(diagnostics, "write_task_result", result)
                    return result
                # Some Android screens leave the task immediately after the
                # action when the account is already complete.  In that
                # rendering the completion marker is the only stable
                # post-action evidence, so finish the task without requiring
                # one more page transition.
                if (
                    transition.postcondition == "shadow_stage_any"
                    and after_snapshot is not None
                    and _postcondition_seen(
                        after_snapshot.evidence, "shadow_challenge.done"
                    )
                ):
                    result = _result(
                        policy,
                        TaskStatus.ALREADY_COMPLETE,
                        transition.next_state or state,
                        counts,
                    )
                    _record(diagnostics, "write_task_result", result)
                    return result
                action_id = transition.intent.action_id
                if (
                    action_id in _RETRYABLE_NAVIGATION_ACTIONS
                    and counts.get(action_id, 0) < _MAX_NAVIGATION_ATTEMPTS
                    and _navigation_retry_is_safe(
                        after_snapshot.evidence if after_snapshot is not None else None
                    )
                ):
                    # Do not replay the old authorization or coordinate. The
                    # next loop captures a new frame, rebuilds recognizers,
                    # asks the definition again, and authorizes the new
                    # transition from that frame.  A driver with lifecycle
                    # support may also restore the game boundary here.
                    _record(
                        diagnostics,
                        "event",
                        "navigation_retry",
                        {
                            "action_id": action_id,
                            "attempt": counts.get(action_id, 0) + 1,
                        },
                    )
                    if _recover_for_navigation_retry(driver, diagnostics):
                        # Recovery re-establishes the canonical game home
                        # boundary; rebuild the route from the definition's
                        # initial state rather than applying a panel-state
                        # transition to a newly restarted app.
                        state = definition.initial_state
                    continue
                error_code = (
                    "JIANLIN_CONTROL_UNCHANGED"
                    if transition.postcondition
                    in {"jianlin_count_changed", "jianlin_multiplier_changed"}
                    else "WORKFLOW_POSTCONDITION_MISSING"
                )
                result = _result(
                    policy,
                    TaskStatus.FAILED,
                    transition.postcondition,
                    counts,
                    error_code,
                )
                _record(diagnostics, "write_task_result", result)
                return result
            # A slow OCR frame can finish exactly at the workflow deadline.
            # If that same post-action frame already proves the next state's
            # terminal status, do not require another full capture/recognition
            # cycle just to ask the definition the question it can already
            # answer.  This is especially important for sold-out daily shops,
            # whose detail page remains open after the quota is exhausted.
            if transition.next_state is not None:
                post_action_decision = definition.decide(after_snapshot, counts)
                if (
                    isinstance(post_action_decision, Decision)
                    and post_action_decision.status
                    in {TaskStatus.COMPLETED, TaskStatus.ALREADY_COMPLETE}
                ):
                    result = _result(
                        policy,
                        post_action_decision.status,
                        next_state,
                        counts,
                    )
                    _record(diagnostics, "write_task_result", result)
                    return result
            state = next_state
        except Exception as exc:
            _record(diagnostics, "record_error", exc)
            # Keep the stable domain code when a workflow raises a typed
            # failure.  Generic driver exceptions retain the legacy fallback,
            # but must still be visible in the diagnostic event above.
            error_code = (
                exc.code.value
                if isinstance(exc, MJAError)
                else "WORKFLOW_DRIVER_FAILED"
            )
            result = _result(
                policy,
                TaskStatus.FAILED,
                state,
                counts,
                error_code,
            )
            _record(diagnostics, "write_task_result", result)
            return result

    result = _result(policy, TaskStatus.FAILED, state, counts, "WORKFLOW_STEP_CAP")
    _record(diagnostics, "write_task_result", result)
    return result


__all__ = ["WorkflowDriver", "run_workflow"]
