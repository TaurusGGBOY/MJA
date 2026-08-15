from __future__ import annotations

import pytest

from agent.safety import SafetyReason, authorize_action
from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.definitions.jianlin_resource_condensate_stamina_daily import (
    JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION,
    MAX_DAILY_SCROLLS,
    plan_safe_challenge,
)
from agent.workflows.models import (
    CapturedFrame,
    Recognition,
    StateSnapshot,
    TaskStatus,
    VisualEvidence,
)

DEFINITION = JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION
POLICY = TASK_POLICIES[DEFINITION.task_id]


def _snapshot(
    state: str,
    markers: tuple[str, ...],
    *,
    texts: tuple[str, ...] = (),
    resources: tuple[str, ...] = (),
    danger: tuple[str, ...] = (),
) -> StateSnapshot:
    frame_id = f"jianlin-{state}"
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


def _resource_snapshot(*, count: str = "x1", multiplier: str = "x1") -> StateSnapshot:
    count_value = int(count[1:])
    multiplier_value = int(multiplier[1:])
    displayed_cost = 20 * count_value * multiplier_value
    return _snapshot(
        "resource",
        (
            "jianlin_condensate_selected",
            "jianlin_stamina_current",
            "jianlin_stamina_cost",
            "jianlin_stamina_cost_value",
            "jianlin_count_bar",
            "jianlin_count_selected",
            "jianlin_multiplier_bar",
            "jianlin_multiplier_selected",
            "jianlin_multiplier_1",
            "jianlin_multiplier_2",
            "jianlin_multiplier_3",
            "jianlin_challenge_button",
        ),
        texts=(
            "当前体力 180",
            "消耗体力",
            str(displayed_cost),
            f"挑战次数 {count}/6",
            f"结算倍率 {multiplier}",
        ),
        resources=("体力",),
    )


def test_safe_planner_uses_remaining_stamina_and_highest_safe_multiplier():
    assert plan_safe_challenge(180, 20, 6, (1, 2, 3)).count == 3
    assert plan_safe_challenge(180, 20, 6, (1, 2, 3)).multiplier == 3


def test_live_resource_header_and_upper_limits_plan_x6_x3():
    snapshot = _snapshot(
        "resource",
        (
            "jianlin_condensate_selected",
            "jianlin_stamina_current",
            "jianlin_stamina_cost",
            "jianlin_count_bar",
            "jianlin_count_selected",
            "jianlin_count_max",
            "jianlin_multiplier_bar",
            "jianlin_multiplier_selected",
            "jianlin_multiplier_1",
            "jianlin_multiplier_3",
        ),
        texts=("507/310", "消耗体力 20", "挑战次数 x1", "上限6", "结算倍率 x1", "上限3"),
        resources=("体力",),
    )
    decision = DEFINITION.decide(snapshot, {"close_postpurchase_stamina_prompt": 1})
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "set_safe_count"
    assert decision.transition.intent.parameter == 6


def test_safe_planner_rejects_missing_controls_without_x1_fallback():
    with pytest.raises(ValueError, match="unsafe challenge inputs"):
        plan_safe_challenge(180, 60, 6, ())
    with pytest.raises(ValueError, match="insufficient stamina"):
        plan_safe_challenge(19, 20, 6, (1, 2, 3))


def test_jianlin_daily_row_is_already_complete_without_inputs():
    snapshot = _snapshot(
        "daily", ("日常任务奖励-日常-页面", "jianlin_daily_row", "jianlin_daily_done")
    )
    decision = DEFINITION.decide(snapshot, {})
    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_jianlin_resumes_from_an_already_open_completed_daily_list():
    snapshot = _snapshot(
        "home", ("日常任务奖励-日常-页面", "jianlin_daily_row", "jianlin_daily_done")
    )

    decision = DEFINITION.decide(snapshot, {})

    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_jianlin_resumes_from_open_formation_page():
    decision = DEFINITION.decide(
        _snapshot("home", ("jianlin_battle_page", "jianlin_battle_start")),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "start_jianlin_battle"
    assert decision.transition.next_state == "battle_result"


def test_jianlin_opens_only_from_the_recognized_boss_row():
    decision = DEFINITION.decide(
        _snapshot("daily", ("日常任务奖励-日常-页面", "jianlin_daily_row")),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_jianlin"
    assert decision.transition.intent.target_marker == "jianlin_daily_row"


def test_jianlin_scrolls_daily_list_before_using_a_row_button():
    decision = DEFINITION.decide(_snapshot("daily", ("日常任务奖励-日常-页面",)), {})
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "scroll_daily_jianlin"
    assert decision.transition.intent.input_kind.value == "swipe"
    assert decision.transition.postcondition == "daily.page"

    exhausted = DEFINITION.decide(
        _snapshot("daily", ("日常任务奖励-日常-页面",)),
        {"scroll_daily_jianlin": MAX_DAILY_SCROLLS},
    )
    assert exhausted.status is TaskStatus.FAILED


def test_jianlin_configures_maximum_safe_count_before_challenge():
    decision = DEFINITION.decide(_resource_snapshot(), {"buy_stamina_once": 1})
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "set_safe_count"
    assert decision.transition.intent.parameter == 3


def test_jianlin_ignores_low_value_ocr_fragment_before_total_cost():
    snapshot = _snapshot(
        "resource",
        (
            "jianlin_condensate_selected",
            "jianlin_stamina_current",
            "jianlin_stamina_cost",
            "jianlin_stamina_cost_value",
            "jianlin_count_bar",
            "jianlin_count_selected",
            "jianlin_multiplier_bar",
            "jianlin_multiplier_selected",
            "jianlin_multiplier_1",
            "jianlin_multiplier_2",
            "jianlin_multiplier_3",
            "jianlin_challenge_button",
        ),
        texts=(
            "147/310",
            "消耗体力",
            "2",
            "120",
            "挑战次数 x2/6",
            "结算倍率 x3",
        ),
        resources=("体力",),
    )

    decision = DEFINITION.decide(
        snapshot,
        {"close_postpurchase_stamina_prompt": 1, "set_safe_count": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "challenge_condensate"


def test_jianlin_selects_condensate_before_any_stamina_purchase():
    decision = DEFINITION.decide(
        _snapshot("resource", ("jianlin_page", "jianlin_condensate_resource")),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "select_jianlin_condensate"
    assert decision.transition.intent.target_marker == "jianlin_condensate_resource"

    missing = DEFINITION.decide(
        _snapshot("resource", ("jianlin_page",)),
        {},
    )
    assert missing.status is TaskStatus.FAILED


def test_jianlin_resource_state_keeps_same_frame_page_evidence():
    recognizers = set(DEFINITION.recognizers("resource"))

    assert "jianlin_page" in recognizers
    assert "jianlin_stamina_plus" in recognizers


def test_jianlin_retry_reuses_an_already_open_resource_page():
    decision = DEFINITION.decide(
        _snapshot("home", ("jianlin_page", "jianlin_condensate_resource")),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "select_jianlin_condensate"
    assert "jianlin_page" in DEFINITION.recognizers("home")


def test_expected_stamina_prompt_is_not_treated_as_an_unknown_refill():
    decision = DEFINITION.decide(
        _snapshot(
            "stamina_prompt",
            (
                "jianlin_stamina_purchase_prompt",
                "jianlin_stamina_purchase_confirm",
                "jianlin_stamina_amount",
                "jianlin_stamina_price",
                "jianlin_stamina_resource",
            ),
            texts=("+80", "10"),
            resources=("紫色魂玉",),
            danger=("jianlin_refill_prompt",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "buy_stamina_once"


def test_jianlin_retry_reuses_an_open_verified_stamina_prompt():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            (
                "jianlin_stamina_purchase_prompt",
                "jianlin_stamina_purchase_confirm",
                "jianlin_stamina_amount",
                "jianlin_stamina_price",
                "jianlin_stamina_resource",
            ),
            texts=("+80", "10"),
            resources=("紫色魂玉",),
            danger=("jianlin_refill_prompt",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "buy_stamina_once"
    assert "jianlin_stamina_amount" in DEFINITION.recognizers("home")


def test_jianlin_resumes_at_verified_second_stamina_confirmation():
    markers = (
        "jianlin_stamina_confirmation_prompt",
        "jianlin_stamina_confirmation_price",
        "jianlin_stamina_confirmation_amount",
        "jianlin_stamina_confirmation_resource",
        "jianlin_stamina_confirmation_confirm",
    )
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            markers,
            texts=("体力将于2026/7/31 20:39恢复满", "是否花费10魂玉购买80体力", "确认"),
            resources=("紫色魂玉",),
            danger=("jianlin_refill_prompt",),
        ),
        {},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_jianlin_stamina_purchase"
    assert decision.transition.intent.approved_resource == "紫色魂玉"
    assert decision.transition.next_state == "stamina_result"
    assert "jianlin_stamina_result_close" in DEFINITION.recognizers("stamina_confirmation")


def test_jianlin_does_not_reopen_refill_after_second_confirmation():
    decision = DEFINITION.decide(
        _resource_snapshot(),
        {"confirm_jianlin_stamina_purchase": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "set_safe_count"


def test_jianlin_resumes_at_stamina_reward_and_marks_purchase_complete():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            ("jianlin_stamina_purchase_result", "jianlin_stamina_result_close"),
            texts=("恭喜获得", "80", "点击空白处关闭"),
        ),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_jianlin_stamina_result"
    assert decision.transition.postcondition == "jianlin_stamina_purchase_prompt"
    assert decision.transition.next_state == "home"

    after_close = DEFINITION.decide(
        _resource_snapshot(),
        {"dismiss_jianlin_stamina_result": 1},
    )
    assert after_close.transition is not None
    assert after_close.transition.intent.action_id == "set_safe_count"


def test_jianlin_reward_dismiss_accepts_the_escalated_offer_as_postpurchase_surface():
    decision = DEFINITION.decide(
        _snapshot(
            "stamina_result",
            ("jianlin_stamina_purchase_result", "jianlin_stamina_result_close"),
            texts=("恭喜获得", "80", "点击空白处关闭"),
        ),
        {"confirm_jianlin_stamina_purchase": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_jianlin_stamina_result"
    assert decision.transition.postcondition == "jianlin_postpurchase_surface"
    assert decision.transition.next_state == "home"


def test_normal_resource_text_never_masquerades_as_stamina_reward():
    snapshot = _resource_snapshot()
    evidence = snapshot.evidence
    assert evidence is not None
    markers = tuple((*evidence.page_hits, "jianlin_stamina_purchase_result"))
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            markers,
            texts=(*evidence.texts, "可获得凝晶", "消耗体力 20"),
            resources=("体力",),
        ),
        {"close_postpurchase_stamina_prompt": 1},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id != "dismiss_jianlin_stamina_result"


def test_jianlin_closes_escalated_second_offer_without_buying_again():
    decision = DEFINITION.decide(
        _snapshot(
            "home",
            (
                "jianlin_stamina_purchase_prompt",
                "jianlin_stamina_amount",
                "jianlin_stamina_escalated_price",
            ),
            texts=("补充体力", "+80", "50"),
            danger=("jianlin_refill_prompt",),
        ),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_postpurchase_stamina_prompt"
    assert decision.transition.intent.approved_resource is None


def test_jianlin_closes_escalated_offer_after_opening_refill_panel():
    decision = DEFINITION.decide(
        _snapshot(
            "stamina_prompt",
            (
                "jianlin_stamina_purchase_prompt",
                "jianlin_stamina_amount",
                "jianlin_stamina_escalated_price",
            ),
            texts=("补充体力", "+80", "50"),
            danger=("jianlin_refill_prompt",),
        ),
        {"open_jianlin_stamina_purchase": 1},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_postpurchase_stamina_prompt"
    assert "jianlin_stamina_escalated_price" in DEFINITION.recognizers("stamina_prompt")


def test_jianlin_configures_highest_safe_multiplier_after_count():
    decision = DEFINITION.decide(
        _resource_snapshot(count="x3", multiplier="x1"),
        {"buy_stamina_once": 1},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "set_safe_multiplier"
    assert decision.transition.intent.parameter == 3


def test_jianlin_challenges_only_after_both_controls_are_verified():
    decision = DEFINITION.decide(
        _resource_snapshot(count="x3", multiplier="x3"),
        {"buy_stamina_once": 1},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "challenge_condensate"
    assert decision.transition.intent.parameter == 3
    safety = authorize_action(
        _resource_snapshot(count="x3", multiplier="x3").evidence,
        decision.transition.intent,
        POLICY,
        {"buy_stamina_once": 1},
    )
    assert safety.allowed is True


def test_jianlin_purchase_requires_exact_plus_80_and_ten_purple_soul_jade():
    snapshot = _snapshot(
        "stamina_prompt",
        (
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_amount",
            "jianlin_stamina_price",
            "jianlin_stamina_resource",
            "紫色魂玉",
        ),
        texts=("购买体力 +80", "消耗 10 紫色魂玉", "购买"),
        resources=("紫色魂玉",),
    )
    decision = DEFINITION.decide(snapshot, {})
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "buy_stamina_once"
    assert decision.transition.intent.approved_resource == "紫色魂玉"
    safety = authorize_action(snapshot.evidence, decision.transition.intent, POLICY, {})
    assert safety.reason is SafetyReason.ALLOWED


def test_jianlin_never_buys_stamina_twice():
    snapshot = _snapshot(
        "stamina_prompt",
        (
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_amount",
            "jianlin_stamina_price",
            "jianlin_stamina_resource",
        ),
        texts=("购买体力 +80", "消耗 10 紫色魂玉"),
        resources=("紫色魂玉",),
    )
    decision = DEFINITION.decide(snapshot, {"buy_stamina_once": 1})
    assert decision.status is TaskStatus.FAILED


def test_jianlin_incomplete_refill_prompt_is_a_normal_failure():
    snapshot = _snapshot(
        "stamina_prompt",
        ("jianlin_stamina_purchase_prompt",),
        danger=("jianlin_refill_prompt",),
    )
    decision = DEFINITION.decide(snapshot, {})
    assert decision.status is TaskStatus.FAILED


def test_jianlin_requires_daily_postcondition_after_resource_loop():
    completed = DEFINITION.decide(
        _snapshot(
            "daily_verify", ("日常任务奖励-日常-页面", "jianlin_daily_row", "jianlin_daily_done")
        ),
        {"buy_stamina_once": 1, "challenge_condensate": 1},
    )
    assert completed.status is TaskStatus.COMPLETED


def test_jianlin_closes_resource_page_when_no_recognized_safe_run_fits():
    snapshot = _snapshot(
        "resource",
        (
            "jianlin_condensate_selected",
            "jianlin_stamina_current",
            "jianlin_stamina_cost",
            "jianlin_stamina_cost_value",
            "jianlin_count_bar",
            "jianlin_count_selected",
            "jianlin_count_max",
            "jianlin_multiplier_bar",
            "jianlin_multiplier_selected",
            "jianlin_multiplier_3",
            "jianlin_challenge_button",
            "jianlin_page_close",
        ),
        texts=(
            "29/310",
            "消耗体力",
            "120",
            "挑战次数 x2/6",
            "结算倍率 x3",
            "上限3",
        ),
        resources=("体力",),
    )

    decision = DEFINITION.decide(
        snapshot,
        {"close_postpurchase_stamina_prompt": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_jianlin_page"
    assert decision.transition.postcondition == "home"
    assert decision.transition.next_state == "done"


def test_jianlin_done_state_finishes_after_a_completed_resource_loop():
    decision = DEFINITION.decide(
        _snapshot("done", ("home",)),
        {"challenge_condensate": 1},
    )

    assert decision.status is TaskStatus.COMPLETED
    assert decision.transition is None
