from __future__ import annotations

from agent.safety import SafetyReason, authorize_action
from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.definitions.batch23 import (
    RING_CHALLENGE_DAILY_DEFINITION,
)
from agent.workflows.models import (
    CapturedFrame,
    Recognition,
    StateSnapshot,
    TaskStatus,
    VisualEvidence,
)

DEFINITION = RING_CHALLENGE_DAILY_DEFINITION
POLICY = TASK_POLICIES[DEFINITION.task_id]


def _snapshot(
    state: str,
    markers: tuple[str, ...],
    *,
    texts: tuple[str, ...] = (),
    resources: tuple[str, ...] = (),
    danger: tuple[str, ...] = (),
) -> StateSnapshot:
    frame_id = f"ring-{state}"
    page_hits = {marker: 1 for marker in markers}
    target_hits = {marker: 1 for marker in markers}
    danger_hits = {marker: 1 for marker in danger}
    all_markers = (*markers, *danger, *resources)
    evidence = VisualEvidence(
        frame_id,
        page_hits,
        target_hits,
        danger_hits,
        {marker: frame_id for marker in all_markers},
        texts,
        resources,
    )
    recognitions = tuple(
        Recognition(marker, frame_id, 1, ((0, 0, 1, 1),)) for marker in all_markers
    )
    return StateSnapshot(CapturedFrame(frame_id, (1280, 720)), state, recognitions, evidence)


def test_ring_resumes_from_an_already_open_daily_list():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            ("daily.page", "ring_daily_task_text", "ring_daily_row"),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_challenge"


def test_ring_completed_daily_list_still_opens_arena_to_verify_all_attempts():
    decision = DEFINITION.decide(
        _snapshot("home", ("daily.page", "ring_daily_done")),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_challenge"


def test_ring_open_accepts_the_daily_reward_popup_as_a_transition_surface():
    decision = DEFINITION.decide(
        _snapshot(
            "daily",
            ("daily.page", "ring_daily_task_text", "ring_daily_row"),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_challenge"
    assert decision.transition.postcondition_alternatives == ("daily.reward_popup",)


def test_ring_daily_reward_popup_must_close_before_completed_row_is_reopened():
    decision = DEFINITION.decide(
        _snapshot("ring", ("daily.reward_popup", "daily.reward_popup_close")),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_reward_popup"
    assert decision.transition.next_state == "daily"

    reopened = DEFINITION.decide(
        _snapshot("daily", ("daily.page", "ring_daily_done")),
        {},
    )
    assert reopened.transition is not None
    assert reopened.transition.intent.action_id == "open_ring_challenge"


def test_ring_resumes_from_master_mode_page_in_initial_state():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            ("ring_page", "ring_start", "ring_master_mode", "ring_master_rank"),
            texts=("大师赛模式", "大师排名 75"),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_attempt_mode"
    assert decision.transition.next_state == "opponents_sweep"


def test_ring_not_open_is_not_eligible_instead_of_a_workflow_failure():
    decision = DEFINITION.decide(
        _snapshot("ring", ("ring_page", "ring_not_open")),
        {},
    )

    assert decision.status is TaskStatus.NOT_ELIGIBLE


def test_ring_score_accepts_separate_current_score_value_text():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_score_label", "ring_score_value"),
            texts=("当前积分", "1000分"),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_attempt_mode"
    assert decision.transition.next_state == "opponents_fight"


def test_ring_resumes_at_verified_sweep_confirmation_in_initial_state():
    snapshot = _snapshot(
        "home",
        ("ring_sweep_prompt", "ring_sweep_confirm", "擂台券"),
        texts=("是否消耗剩余的12张擂台券，兑换120擂台币？", "确认"),
        resources=("擂台券",),
    )

    decision = DEFINITION.decide(snapshot, {})

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_ring_sweep"
    assert authorize_action(snapshot.evidence, decision.transition.intent, POLICY, {}).allowed


def test_ring_resumes_after_sweep_with_zero_tickets_and_closes_opponents():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            (
                "ring_opponent_page",
                "ring_attempts_exhausted",
                "ring_opponent_close",
            ),
            texts=("0/12",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_ring_opponents"
    assert decision.transition.next_state == "ring_after"


def test_master_mode_takes_precedence_over_unrelated_top_right_currency():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_master_mode", "ring_master_rank", "擂台券"),
            texts=("大师赛模式", "大师排名 12", "擂台券 990"),
            resources=("擂台券",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_attempt_mode"
    assert decision.transition.next_state == "opponents_sweep"


def test_master_mode_alone_proves_the_post_5000_sweep_branch():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_master_mode"),
            texts=("大师赛",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.next_state == "opponents_sweep"


def test_explicit_score_at_5000_allows_sweep_when_score_is_visible():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_score_label", "ring_score_value"),
            texts=("擂台积分 5000",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.next_state == "opponents_sweep"


def test_current_updated_ring_page_without_score_uses_manual_branch():
    decision = DEFINITION.decide(
        _snapshot("ring", ("ring_page", "ring_start", "擂台券"), resources=("擂台券",)),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.next_state == "opponents_fight"


def test_low_explicit_score_enters_bounded_fight_branch():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_score_label", "ring_score_value"),
            texts=("擂台积分 4999",),
        ),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.next_state == "opponents_fight"

    fight = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            ("ring_opponent_page", "ring_fight_target", "ring_attempts"),
            texts=("挑战次数 11/12",),
        ),
        {},
    )
    assert fight.transition is not None
    assert fight.transition.intent.action_id == "fight_ring_opponent"
    assert fight.transition.intent.approved_resource == "擂台券"


def test_sweep_and_confirmation_require_same_frame_ticket_evidence():
    opponents = _snapshot(
        "opponents_sweep",
        ("ring_opponent_page", "ring_sweep", "擂台券"),
        resources=("擂台券",),
    )
    sweep = DEFINITION.decide(opponents, {})
    assert sweep.transition is not None
    assert sweep.transition.intent.action_id == "sweep_ring"
    assert authorize_action(
        opponents.evidence, sweep.transition.intent, POLICY, {}
    ).allowed

    prompt = _snapshot(
        "sweep_interstitial",
        ("ring_sweep_prompt", "ring_sweep_confirm", "擂台券"),
        texts=("是否消耗擂台券", "确认"),
        resources=("擂台券",),
    )
    confirm = DEFINITION.decide(prompt, {})
    assert confirm.transition is not None
    assert confirm.transition.intent.action_id == "confirm_ring_sweep"
    assert authorize_action(
        prompt.evidence, confirm.transition.intent, POLICY, {}
    ).allowed


def test_fight_branch_closes_only_after_all_attempts_are_exhausted():
    decision = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            ("ring_opponent_page", "ring_attempts_exhausted", "ring_opponent_close"),
            texts=("挑战次数 0/12",),
        ),
        {"fight_ring_opponent": 12},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_ring_opponents"


def test_manual_fight_branch_does_not_stop_at_the_daily_row_tick():
    decision = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            (
                "ring_opponent_page",
                "ring_fight_target",
                "ring_attempts",
                "ring_challenge_target.done",
            ),
            texts=("剩余次数 11/12",),
            resources=("擂台券",),
        ),
        {"fight_ring_opponent": 1},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "fight_ring_opponent"

    exhausted = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            (
                "ring_opponent_page",
                "ring_opponent_close",
                "ring_attempts_exhausted",
                "ring_challenge_target.done",
            ),
            texts=("剩余次数 0/12",),
        ),
        {"fight_ring_opponent": 12},
    )
    assert exhausted.transition is not None
    assert exhausted.transition.intent.action_id == "close_ring_opponents"


def test_manual_fight_handles_the_live_battle_prepare_page_before_skipping():
    decision = DEFINITION.decide(
        _snapshot("fight", ("ring_battle_prepare_page", "ring_ready")),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "start_ring_battle"
    assert decision.transition.next_state == "fight"


def test_manual_fight_polls_the_loading_surface_without_sending_another_tap():
    decision = DEFINITION.decide(
        _snapshot("fight", ("ring_fight_page", "ring_battle_loading")),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "wait_ring_battle"
    assert decision.transition.intent.input_kind.value == "none"
    assert decision.transition.postcondition == "ring_battle_loading"


def test_start_ring_battle_accepts_the_loading_surface_as_an_intermediate_postcondition():
    decision = DEFINITION.decide(
        _snapshot("fight", ("ring_battle_prepare_page", "ring_ready")),
        {},
    )

    assert decision.transition is not None
    assert "ring_battle_loading" in decision.transition.postcondition_alternatives


def test_opening_ring_can_land_directly_on_battle_prepare_page():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_battle_prepare_page", "ring_ready"),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_attempt_mode"
    assert "ring_battle_prepare_page" in decision.transition.postcondition_alternatives


def test_updated_ring_opens_the_team_setup_surface_before_matching():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_score_label", "ring_score_value"),
            texts=("当前积分 1237",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_ring_attempt_mode"
    assert "ring_match_setup_page" in decision.transition.postcondition_alternatives

    matching = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            ("ring_match_setup_page", "ring_match_start", "ring_attempts"),
            texts=("剩余挑战次数 11/12",),
        ),
        {},
    )
    assert matching.transition is not None
    assert matching.transition.intent.action_id == "start_ring_matching"
    assert matching.transition.intent.approved_resource == "擂台券"
    assert matching.transition.next_state == "fight"


def test_updated_ring_dismisses_reward_then_returns_to_ring_for_the_next_attempt():
    reward = DEFINITION.decide(
        _snapshot(
            "fight",
            ("ring_reward_popup", "ring_battle_result", "ring_result_close"),
        ),
        {"start_ring_matching": 1},
    )
    assert reward.transition is not None
    assert reward.transition.intent.action_id == "dismiss_ring_reward"
    assert reward.transition.next_state == "fight"

    result = DEFINITION.decide(
        _snapshot("fight", ("ring_battle_result", "ring_result_close")),
        {"start_ring_matching": 1, "dismiss_ring_reward": 1},
    )
    assert result.transition is not None
    assert result.transition.intent.action_id == "dismiss_ring_result"
    assert result.transition.next_state == "ring"
    assert result.transition.postcondition == "ring_page"


def test_updated_ring_does_not_close_from_a_local_cap_without_zero_proof():
    decision = DEFINITION.decide(
        _snapshot("ring", ("ring_page", "ring_start")),
        {"start_ring_matching": 12},
    )

    assert decision.status is TaskStatus.FAILED


def test_ring_page_with_zero_remaining_attempts_is_already_complete():
    decision = DEFINITION.decide(
        _snapshot(
            "ring",
            ("ring_page", "ring_start", "ring_attempts_exhausted"),
            texts=("0/12",),
        ),
        {"fight_ring_opponent": 11},
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_resumed_opponent_page_with_eleven_remaining_attempts_continues_fighting():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            (
                "ring_opponent_page",
                "ring_fight_target",
                "ring_attempts",
                "ring_daily_done",
            ),
            texts=("剩余次数 11/12",),
        ),
        {"fight_ring_opponent": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "fight_ring_opponent"


def test_resumed_master_opponent_page_uses_only_the_visible_sweep_control():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            ("ring_opponent_page", "ring_sweep", "擂台券"),
            resources=("擂台券",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "sweep_ring"


def test_manual_fight_fails_closed_when_remaining_counter_is_not_visible():
    decision = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            ("ring_opponent_page", "ring_fight_target"),
        ),
        {},
    )

    assert decision.status is TaskStatus.FAILED


def test_zero_attempts_without_close_control_never_emits_a_close_click():
    decision = DEFINITION.decide(
        _snapshot(
            "opponents_fight",
            ("ring_opponent_page", "ring_attempts_exhausted"),
            texts=("0/12",),
        ),
        {},
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE
    assert decision.transition is None


def test_ring_sweep_result_is_terminal_success_without_cleanup():
    completed = DEFINITION.decide(
        _snapshot("sweep_result", ("ring_sweep_result",)),
        {"sweep_ring": 1, "confirm_ring_sweep": 1},
    )

    assert completed.status is TaskStatus.COMPLETED
    assert completed.transition is None


def test_ring_explicit_challenge_complete_is_also_terminal_success():
    completed = DEFINITION.decide(
        _snapshot("sweep_result", ("ring_challenge_target.done",)),
        {"sweep_ring": 1, "confirm_ring_sweep": 1},
    )

    assert completed.status is TaskStatus.COMPLETED
    assert completed.transition is None


def test_ring_result_without_completion_evidence_still_fails():
    failed = DEFINITION.decide(
        _snapshot("sweep_result", ("ring_result_close",)),
        {"sweep_ring": 1, "confirm_ring_sweep": 1},
    )

    assert failed.status is TaskStatus.FAILED


def test_ring_terminal_state_does_not_reenter_dynamic_home_navigation():
    completed = DEFINITION.decide(
        _snapshot("done", ("home", "daily.page")),
        {},
    )

    assert completed.status is TaskStatus.COMPLETED


def test_ring_unknown_currency_is_recorded_without_blocking_input():
    snapshot = _snapshot(
        "opponents_sweep",
        ("ring_opponent_page", "ring_sweep", "擂台券"),
        resources=("擂台券",),
        danger=("ring_unknown_currency",),
    )
    decision = DEFINITION.decide(snapshot, {})
    assert decision.transition is not None
    safety = authorize_action(snapshot.evidence, decision.transition.intent, POLICY, {})
    assert safety.allowed is True
    assert safety.reason is SafetyReason.ALLOWED
    assert safety.allowed is True
