import pytest

from agent.safety import SafetyReason, authorize_action
from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.definitions.batch23 import (
    DUNGEON_SWEEP_DAILY_DEFINITION,
    EAT_STAMINA_FOOD_DAILY_DEFINITION,
    HERO_DISPATCH_DAILY_DEFINITION,
    MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
    SHADOW_RUINS_DAILY_DEFINITION,
    SPEND_CONDENSATE_DAILY_DEFINITION,
)
from agent.workflows.definitions.buy_tea_daily import BUY_TEA_DAILY_DEFINITION
from agent.workflows.models import ActionIntent, InputKind, TaskStatus, VisualEvidence
from agent.workflows.registry import WORKFLOW_DEFINITIONS
from tests.workflows.support import evaluate_decision


@pytest.mark.parametrize(
    "task_id",
    (
        "BUY_TEA_DAILY",
        "HERO_DISPATCH_DAILY",
        "SHADOW_RUINS_DAILY",
        "SPEND_CONDENSATE_DAILY",
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "EAT_STAMINA_FOOD_DAILY",
        "DUNGEON_SWEEP_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "RING_CHALLENGE_DAILY",
    ),
)
def test_batch23_definitions_are_registered_with_finite_named_caps(task_id):
    definition = WORKFLOW_DEFINITIONS[task_id]
    policy = TASK_POLICIES[task_id]
    assert definition.task_id == task_id
    assert policy.max_steps > 0
    assert all(cap > 0 for cap in policy.action_caps.values())


def test_consumptive_purchase_requires_same_frame_resource_evidence():
    intent = ActionIntent(
        "buy_tea",
        "quantity_panel",
        "buy_confirm",
        approved_resource="文",
        input_kind="click",
    )
    stale = VisualEvidence(
        "new",
        {"quantity_panel": 1},
        {"buy_confirm": 1},
        {},
        {"quantity_panel": "new", "buy_confirm": "new", "文": "old"},
        (),
        ("文",),
    )
    decision = authorize_action(
        stale,
        intent,
        TASK_POLICIES["BUY_TEA_DAILY"],
        {},
    )
    assert decision.reason is SafetyReason.ALLOWED
    assert decision.allowed is True


def test_buy_tea_hidden_card_scrolls_once_instead_of_claiming_completion():
    decision, _ = evaluate_decision(
        BUY_TEA_DAILY_DEFINITION,
        "tea",
        ("universal_shop_page",),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "scroll_tea_list"
    assert decision.transition.next_state == "tea_scrolled"


def test_buy_tea_reuses_a_card_already_left_in_the_scrolled_view():
    recognizers = set(BUY_TEA_DAILY_DEFINITION.recognizers("tea"))
    assert "tea_item_scrolled" in recognizers

    decision, _ = evaluate_decision(
        BUY_TEA_DAILY_DEFINITION,
        "tea",
        ("universal_shop_page", "tea_item_scrolled"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_tea_tab"
    assert decision.transition.intent.target_marker == "tea_item_scrolled"


def test_buy_tea_recognizers_include_clipped_card_label_recovery():
    assert "tea_card_label" in BUY_TEA_DAILY_DEFINITION.recognizers("tea")
    assert "tea_card_label" in BUY_TEA_DAILY_DEFINITION.recognizers("tea_scrolled")


def test_buy_tea_quantity_panel_uses_a_title_fallback_recognizer():
    assert "quantity_panel_title" in BUY_TEA_DAILY_DEFINITION.recognizers("quantity_panel")


def test_buy_tea_after_scroll_requires_the_shifted_card():
    decision, _ = evaluate_decision(
        BUY_TEA_DAILY_DEFINITION,
        "tea_scrolled",
        ("universal_shop_page", "tea_item_scrolled"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_tea_tab"
    assert decision.transition.intent.target_marker == "tea_item_scrolled"


def test_buy_tea_explicit_sold_out_is_already_complete():
    decision, _ = evaluate_decision(
        BUY_TEA_DAILY_DEFINITION,
        "tea_selected",
        ("universal_shop_page", "tea_item", "tea_sold_out"),
    )
    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_buy_tea_uses_explicit_purchase_result_marker():
    transition = BUY_TEA_DAILY_DEFINITION.transitions["quantity_panel_selected"]
    assert transition.postcondition == "tea_purchase_result"


def test_hero_dispatch_treats_duration_as_dispatchable_not_in_progress():
    decision, _ = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.first_task_dispatchable"),
        texts=("耗时:4小时",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "select_first_visible_dispatch"
    assert decision.transition.next_state == "configure"


def test_hero_dispatch_uses_live_painting_text_instead_of_day_night_home_template():
    decision, safety = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "home",
        ("home.painting_scroll_text", "painting_scroll_entry"),
        texts=("画卷",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.page_marker == "home.painting_scroll_text"
    assert decision.transition.intent.action_id == "open_painting_scroll"
    assert safety is not None and safety.allowed is True


def test_hero_dispatch_explicit_in_progress_state_is_already_complete():
    decision, _ = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.first_task_in_progress"),
        texts=("派遣中 剩余3小时",),
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE
    assert "hero.dispatch.close" in HERO_DISPATCH_DAILY_DEFINITION.recognizers("inspect")


def test_hero_dispatch_finishes_an_all_completed_account():
    decision, safety = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.all_completed"),
        texts=("任务:6/9 已完成:9",),
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE
    assert safety is None


def test_hero_dispatch_empty_task_state_is_already_complete_without_input():
    decision, safety = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        (
            "hero.dispatch.page",
            "hero.no_dispatch_tasks",
        ),
        texts=("任务:0/9 已完成:0 尚未选择派遣任务",),
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE
    assert safety is None
    assert "hero.no_dispatch_tasks" in HERO_DISPATCH_DAILY_DEFINITION.recognizers("inspect")


def test_hero_dispatch_does_not_treat_six_completed_slots_as_daily_terminal():
    decision, safety = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.first_task_claimable"),
        texts=("任务:6/9 已完成:6",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "select_first_visible_dispatch"
    assert decision.transition.next_state == "claim"
    assert safety is not None and safety.allowed is True


def test_hero_dispatch_claimable_row_wins_over_stale_all_completed_marker():
    decision, safety = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        (
            "hero.dispatch.page",
            "hero.first_task_claimable",
            "hero.all_completed",
        ),
        texts=("完成派遣 任务:6/9 已完成:6",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "select_first_visible_dispatch"
    assert decision.transition.next_state == "claim"
    assert safety is not None and safety.allowed is True


def test_hero_dispatch_claims_then_returns_to_top_first_inspection():
    claimable, _ = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.first_task_claimable"),
        texts=("可领取",),
    )
    assert claimable.transition is not None
    assert claimable.transition.next_state == "claim"

    popup = HERO_DISPATCH_DAILY_DEFINITION.transitions["reward_popup"]
    assert popup.intent.action_id == "close_reward_popup"
    assert popup.next_state == "inspect"


def test_hero_dispatch_smart_configures_and_dispatches_up_to_six_teams():
    configure = HERO_DISPATCH_DAILY_DEFINITION.transitions["configure"]
    send = HERO_DISPATCH_DAILY_DEFINITION.transitions["send"]
    assert configure.intent.action_id == "smart_configure_team"
    assert configure.postcondition == "hero.dispatch_button"
    assert send.intent.action_id == "dispatch_team"
    assert send.postcondition == "hero.first_task_in_progress"
    assert send.next_state == "inspect"

    capped, _ = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.first_task_dispatchable"),
        counters={"dispatch_team": 6},
    )
    assert capped.transition is not None
    assert capped.transition.intent.action_id == "close_hero_dispatch"


def test_hero_dispatch_closes_after_a_dispatch_has_been_verified():
    decision, _ = evaluate_decision(
        HERO_DISPATCH_DAILY_DEFINITION,
        "inspect",
        ("hero.dispatch.page", "hero.first_task_in_progress"),
        counters={"dispatch_team": 1},
        texts=("派遣中 剩余03:00:00",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_hero_dispatch"


def test_shadow_entry_accepts_already_completed_stage():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "popup",
        ("shadow_popup", "shadow_go"),
    )
    assert decision.transition is not None
    assert decision.transition.postcondition == "shadow_stage_any"


def test_shadow_card_list_clicks_live_exploration_status_text_before_popup():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "painting",
        ("shadow_card_list", "shadow_active_card"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "select_active_shadow_card"
    assert decision.transition.intent.target_marker == "shadow_active_card"
    assert decision.transition.postcondition == "shadow_popup"
    assert TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps[
        "select_active_shadow_card"
    ] == 1


def test_shadow_entry_waits_for_card_page_before_selecting_active_card():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "painting",
        ("painting_page", "shadow_challenge"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_shadow"
    assert decision.transition.postcondition == "shadow_page"
    assert decision.transition.next_state == "shadow_page"


def test_shadow_card_page_finishes_when_no_new_card_is_available():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "shadow_page",
        ("shadow_page", "shadow_card_list", "shadow_no_active_card"),
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_shadow_entry_can_open_painting_scroll_with_policy_cap():
    evidence = VisualEvidence(
        "frame",
        {"home": 1},
        {"painting_scroll_entry": 1},
        {},
        {"home": "frame", "painting_scroll_entry": "frame"},
        (),
        (),
    )
    decision = authorize_action(
        evidence,
        ActionIntent(
            "open_painting_scroll",
            "home",
            "painting_scroll_entry",
            input_kind="click",
        ),
        TASK_POLICIES["SHADOW_RUINS_DAILY"],
        {},
    )
    assert decision.allowed is True


def test_shadow_victory_is_dismissed_before_grid_progression():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "battle_done",
        ("shadow_battle_result",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_shadow_battle_result"
    assert decision.transition.postcondition == "shadow_reward_popup"
    assert decision.transition.next_state == "reward_popup"


def test_shadow_defeat_is_dismissed_before_retrying_from_stage():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "battle_done",
        ("shadow_battle_failure",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_shadow_battle_failure"
    assert decision.transition.postcondition == "shadow_stage_any"
    assert decision.transition.postcondition_alternatives == (
        "shadow_exploration_page",
        "shadow_formation_page",
    )


def test_shadow_reward_popup_is_dismissed_before_next_lane():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "explore_left",
        ("shadow_reward_popup",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_shadow_reward_popup"
    assert decision.transition.postcondition == "shadow_stage_any"


def test_shadow_grid_repeats_the_complete_verified_triplet():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_exploration_page", "shadow_foreground_left"),
        counters={"advance_shadow_foreground_triplet": 1},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "advance_shadow_foreground_triplet"
    assert decision.transition.postcondition == "shadow_grid_advanced"
    assert decision.transition.postcondition_alternatives == ("shadow_grid_stalled",)


def test_shadow_stalled_grid_uses_bounded_transfer_recovery():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_exploration_page", "shadow_grid_stalled", "shadow_transfer"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "transfer_shadow_stage"
    assert decision.transition.intent.target_marker == "shadow_transfer"
    assert decision.transition.postcondition == "shadow_transfer_page"
    assert decision.transition.next_state == "transfer"
    assert decision.transition.postcondition_alternatives == ()
    assert TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps["transfer_shadow_stage"] == 8


def test_shadow_transfer_sheet_confirms_from_its_live_ocr_box():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "transfer",
        ("shadow_transfer_page", "shadow_confirm_transfer"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_shadow_transfer"
    assert decision.transition.intent.target_marker == "shadow_confirm_transfer"
    assert decision.transition.postcondition == "shadow_stage_any"
    assert decision.transition.next_state == "exploration"
    assert decision.transition.postcondition_alternatives == (
        "shadow_exploration_page",
        "shadow_transfer_page",
    )
    assert TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps[
        "confirm_shadow_transfer"
    ] == 8


def test_shadow_transfer_sheet_stops_after_bounded_confirmation_retries():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_transfer_page", "shadow_confirm_transfer"),
        counters={"confirm_shadow_transfer": 8},
    )

    assert decision.status == TaskStatus.FAILED


def test_shadow_exploration_transfer_button_does_not_confirm_transfer_sheet():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        (
            "shadow_exploration_page",
            "shadow_transfer_right_page",
            "shadow_confirm_transfer_right",
        ),
    )

    assert decision.transition is None
    assert decision.status is TaskStatus.FAILED


def test_shadow_formation_starts_battle_and_returns_to_progress_loop():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_formation_page", "shadow_battle_target"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "battle"
    assert decision.transition.postcondition == "shadow_battle_result"
    assert decision.transition.next_state == "battle_done"
    assert decision.transition.postcondition_alternatives == ("shadow_battle_failure",)


def test_shadow_formation_does_not_require_optional_recommended_team():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_formation_page", "shadow_battle_target", "shadow_recommended_team"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "battle"
    assert decision.transition.postcondition == "shadow_battle_result"


def test_shadow_recommended_team_surface_is_not_a_production_dependency():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_recommended_team_page", "shadow_use_recommended_team"),
    )

    assert decision.transition is None
    assert decision.status == TaskStatus.FAILED


def test_shadow_final_boss_prompt_is_confirmed_before_completion_marker():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        (
            "shadow_final_prompt",
            "shadow_final_confirm",
            "shadow_challenge.done",
        ),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_shadow_completion"
    assert decision.transition.postcondition == "shadow_reward_popup"
    assert decision.transition.postcondition_alternatives == (
        "shadow_progress_any",
        "home",
        "shadow_challenge.done",
    )
    assert TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps[
        "confirm_shadow_completion"
    ] == 1


def test_shadow_cross_map_auto_route_prompt_is_confirmed_once():
    decision, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_auto_route_prompt", "shadow_auto_route_confirm"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_shadow_auto_route"
    assert decision.transition.intent.target_marker == "shadow_auto_route_confirm"
    assert decision.transition.postcondition == "shadow_stage_any"
    assert decision.transition.postcondition_alternatives == (
        "shadow_exploration_page",
        "shadow_stage_page",
        "shadow_auto_route_prompt",
    )
    assert TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps[
        "confirm_shadow_auto_route"
    ] == 2


def test_shadow_final_reward_returns_home_and_finishes_completed():
    reward, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "exploration",
        ("shadow_reward_popup",),
        counters={"confirm_shadow_completion": 1},
    )
    assert reward.transition is not None
    assert reward.transition.intent.action_id == "dismiss_shadow_reward_popup"
    assert reward.transition.postcondition == "home"
    assert reward.transition.next_state == "home"

    finished, _ = evaluate_decision(
        SHADOW_RUINS_DAILY_DEFINITION,
        "home",
        ("home",),
        counters={"confirm_shadow_completion": 1},
    )
    assert finished.status == TaskStatus.COMPLETED


def test_spend_condensate_skips_an_already_sold_out_yanwu_purchase():
    decision, safety = evaluate_decision(
        SPEND_CONDENSATE_DAILY_DEFINITION,
        "purchase",
        ("yanwu_currency_purchase", "yanwu_currency_sold_out"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_yanwu_currency_purchase"
    assert safety is not None and safety.allowed is True


def test_spend_condensate_can_begin_when_no_completion_markers_are_configured():
    """The direct definition must retain mapping defaults for normal states."""

    decision, safety = evaluate_decision(
        SPEND_CONDENSATE_DAILY_DEFINITION,
        "home",
        ("home.painting_scroll_text", "painting_scroll_entry"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_painting_scroll"
    assert safety is not None and safety.allowed is True


def test_spend_condensate_retry_resumes_from_open_yanwu_purchase_panel():
    decision, safety = evaluate_decision(
        SPEND_CONDENSATE_DAILY_DEFINITION,
        "home",
        (
            "yanwu_currency_purchase",
            "yanwu_currency_purchase_target",
            "凝晶",
        ),
        resources=("凝晶",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "buy_yanwu_currency_max"
    assert safety is not None and safety.allowed is True


def test_spend_condensate_reward_close_waits_for_the_live_world_page():
    decision, _ = evaluate_decision(
        SPEND_CONDENSATE_DAILY_DEFINITION,
        "yunzhou_reward",
        ("yunzhou_currency_purchase_target.done",),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_yunzhou_reward_popup"
    assert decision.transition.postcondition == "yunzhou_world_page"


def test_spend_condensate_home_recognizes_both_partial_purchase_pages():
    recognizers = set(SPEND_CONDENSATE_DAILY_DEFINITION.recognizers("home"))

    assert {
        "yanwu_currency_purchase",
        "yunzhou_currency_purchase",
        "yanwu_currency_sold_out",
        "yunzhou_currency_sold_out",
        "凝晶",
    } <= recognizers


def test_martial_claim_only_mode_claims_success_card_without_starting_study():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_page", "martial_success_card"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "claim_success_card"
    assert decision.transition.intent.approved_resource is None
    assert decision.transition.postcondition == "martial_claim_progress"


def test_martial_claim_only_mode_stops_before_detail_study_action():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_study_detail",),
    )

    assert decision.status is TaskStatus.NOT_ELIGIBLE


def test_martial_claim_only_mode_closes_completed_detail_without_new_study():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "home",
        ("martial_claim_progress", "martial_close"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_martial"
    assert decision.transition.postcondition == "martial_page"


def test_martial_claim_only_mode_finishes_immediately_after_reward_is_closed():
    close, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_success_result", "martial_result_close"),
        counters={"claim_success_card": 1},
    )

    assert close.transition is not None
    assert close.transition.intent.action_id == "close_reward_popup"
    assert close.transition.postcondition == "martial_claim_progress"
    assert close.transition.next_state == "claimed"

    close_detail, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "claimed",
        ("martial_claim_progress", "martial_close"),
        counters={"claim_success_card": 1, "close_reward_popup": 1},
    )
    assert close_detail.transition is not None
    assert close_detail.transition.intent.action_id == "close_martial"
    assert close_detail.transition.postcondition == "martial_page"
    assert close_detail.transition.next_state == "page"

    close_page, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "page",
        ("martial_page", "martial_close"),
        counters={"claim_success_card": 1, "close_reward_popup": 1},
    )
    assert close_page.transition is not None
    assert close_page.transition.intent.action_id == "close_martial_page"
    assert close_page.transition.postcondition == "function_panel.page"
    assert close_page.transition.next_state == "done"

    done, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "done",
        ("function_panel.page",),
        counters={
            "claim_success_card": 1,
            "close_reward_popup": 1,
            "close_martial": 1,
            "close_martial_page": 1,
        },
    )
    assert done.status is TaskStatus.COMPLETED


def test_martial_claim_only_mode_reports_no_prepared_card_as_not_eligible():
    initial, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_page", "martial_close"),
    )

    assert initial.status is TaskStatus.NOT_ELIGIBLE


def test_martial_claim_only_mode_closes_after_success_card_is_claimed():
    close, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_page", "martial_close"),
        counters={"claim_success_card": 1},
    )

    assert close.transition is not None
    assert close.transition.intent.action_id == "close_martial_page"
    assert close.transition.postcondition == "function_panel.page"

    finished, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "done",
        ("function_panel.page",),
    )
    assert finished.status is TaskStatus.COMPLETED


def test_martial_claim_only_policy_forbids_new_study_and_retry_actions():
    policy = TASK_POLICIES["MARTIAL_STUDY_BREAKTHROUGH_DAILY"]

    assert "study" not in policy.action_caps
    assert "retry" not in policy.action_caps
    assert "study_success_detail" not in policy.action_caps
    assert policy.approved_resources == frozenset()
    assert policy.action_caps["claim_success_card"] == 3
    assert policy.action_caps["close_martial_page"] == 1


def test_martial_empty_slot_is_opened_before_study():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_page", "martial_plus_slot_2"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_martial_plus_slot_2"
    assert decision.transition.postcondition == "martial_study_detail"


def test_martial_slot_studies_then_breaks_through_and_confirms():
    study, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "slot_detail",
        ("martial_study_detail", "martial_study_action"),
    )
    assert study.transition is not None
    assert study.transition.intent.action_id == "study_martial_slot"

    breakthrough, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "slot_detail",
        (
            "martial_study_detail",
            "martial_breakthrough_action",
            "martial_materials_sufficient",
        ),
        counters={"study_martial_slot": 3},
    )
    assert breakthrough.transition is not None
    assert breakthrough.transition.intent.action_id == "breakthrough_martial_slot"

    confirm, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "confirm",
        ("martial_confirm_breakthrough",),
    )
    assert confirm.transition is not None
    assert confirm.transition.intent.action_id == "confirm_martial_breakthrough"
    assert confirm.transition.postcondition_alternatives == (
        "martial_study_detail",
        "martial_candidate_in_progress",
    )


def test_martial_insufficient_breakthrough_reselects_study_before_spending():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "slot_detail",
        (
            "martial_study_detail",
            "martial_breakthrough_action",
            "martial_materials_insufficient",
        ),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "study_martial_slot"
    assert decision.transition.intent.target_marker == "martial_breakthrough_action"


def test_martial_without_safe_material_configuration_is_not_eligible():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "slot_detail",
        (
            "martial_study_detail",
            "martial_no_sufficient_configuration",
        ),
    )

    assert decision.status is TaskStatus.NOT_ELIGIBLE
    assert decision.transition is None


def test_martial_retry_from_open_detail_continues_study_before_closing():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "home",
        ("martial_study_detail", "martial_study_action"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "study_martial_slot"
    assert decision.transition.postcondition == "martial_study_detail"


def test_martial_generic_detail_button_allows_remaining_global_study_budget():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "home",
        ("martial_study_detail", "martial_study_button"),
        counters={"study_martial_slot": 3},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "study_martial_slot"

    exhausted, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "home",
        ("martial_study_detail", "martial_study_button"),
        counters={"study_martial_slot": 9},
    )
    assert exhausted.status is TaskStatus.FAILED


def test_martial_partial_breakthrough_glyph_authorizes_breakthrough_after_three_studies():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "home",
        (
            "martial_study_detail",
            "martial_breakthrough_action",
            "martial_materials_sufficient",
        ),
        counters={"study_martial_slot": 3},
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "breakthrough_martial_slot"
    assert decision.transition.intent.target_marker == "martial_breakthrough_action"


def test_martial_full_countdown_slots_are_complete_for_today():
    decision, _ = evaluate_decision(
        MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
        "martial",
        ("martial_page", "martial_full_slots"),
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_food_route_targets_the_live_card_on_all_consumables_page():
    assert TASK_POLICIES["EAT_STAMINA_FOOD_DAILY"].action_caps[
        "inspect_food_candidate"
    ] == 6
    assert TASK_POLICIES["EAT_STAMINA_FOOD_DAILY"].action_caps[
        "open_resource_page"
    ] == 1

    resource_transition = EAT_STAMINA_FOOD_DAILY_DEFINITION.transitions["home"]
    bag_transition = EAT_STAMINA_FOOD_DAILY_DEFINITION.transitions["bag"]
    food_transition = EAT_STAMINA_FOOD_DAILY_DEFINITION.transitions["food"]
    detail_transition = EAT_STAMINA_FOOD_DAILY_DEFINITION.transitions["food_detail"]
    confirm_transition = EAT_STAMINA_FOOD_DAILY_DEFINITION.transitions[
        "confirm_food_buff_replace"
    ]

    assert resource_transition.intent.action_id == "open_resource_page"
    assert resource_transition.intent.page_marker == "home"
    assert resource_transition.intent.target_marker == "resource_entry"
    assert resource_transition.intent.input_kind is InputKind.CLICK
    assert resource_transition.postcondition == "bag_page"
    assert resource_transition.next_state == "bag"
    assert bag_transition.intent.action_id == "open_food_category"
    assert bag_transition.postcondition == "consumables_page"
    assert bag_transition.next_state == "food"
    assert food_transition.intent.action_id == "inspect_food_candidate"
    assert food_transition.intent.page_marker == "consumables_page"
    assert food_transition.postcondition == "food_detail_changed"
    assert food_transition.next_state == "food_detail"
    assert detail_transition.intent.action_id == "eat_longjing_shrimp"
    assert detail_transition.intent.page_marker == "food_detail_changed"
    assert detail_transition.postcondition == "food_use_result"
    assert detail_transition.next_state == "food"
    assert confirm_transition.intent.action_id == "confirm_food_buff_replace"
    assert confirm_transition.intent.page_marker == "food_buff_replace_prompt"
    assert confirm_transition.postcondition == "food_use_result"
    assert confirm_transition.next_state == "food"


def test_food_resource_shortcut_is_authorized_from_home():
    decision, _ = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "home",
        ("home", "resource_entry"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_resource_page"


def test_food_eats_six_verified_longjing_cards_without_stamina_text():
    markers = (
        "consumables_page",
        "food_detail_changed",
        "longjing_shrimp_eat_target",
        "龙井虾仁",
    )

    decision, _ = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "food_detail",
        markers,
        texts=("使用",),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "eat_longjing_shrimp"

    completed, _ = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "food",
        markers,
        counters={"eat_longjing_shrimp": 6},
    )
    assert completed.status is TaskStatus.COMPLETED


def test_food_stops_as_already_complete_when_game_reports_full():
    decision, _ = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "food",
        ("consumables_page", "food_overfull"),
    )

    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_food_selects_the_card_before_trusting_existing_detail_panel():
    decision, _ = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "food",
        (
            "consumables_page",
            "food_candidate",
            "food_detail_changed",
            "longjing_shrimp_eat_target",
            "龙井虾仁",
        ),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "inspect_food_candidate"


def test_food_confirms_only_the_explicit_same_food_replacement_prompt():
    decision, safety = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "food",
        (
            "food_buff_replace_prompt",
            "food_buff_replace_confirm",
        ),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_food_buff_replace"
    assert safety is not None and safety.allowed is True


def test_food_replacement_prompt_returns_to_consumables_loop():
    decision, safety = evaluate_decision(
        EAT_STAMINA_FOOD_DAILY_DEFINITION,
        "food",
        (
            "food_use_result",
            "food_buff_replace_prompt",
            "food_buff_replace_confirm",
        ),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "confirm_food_buff_replace"
    assert decision.transition.postcondition == "food_use_result"
    assert decision.transition.next_state == "food"
    assert safety is not None and safety.allowed is True


def test_dungeon_ticket_control_is_not_an_already_complete_marker():
    decision, _ = evaluate_decision(
        DUNGEON_SWEEP_DAILY_DEFINITION,
        "dungeon",
        ("dungeon_page", "ticket_plus.done"),
    )

    assert decision.status is None
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "scroll_dungeon_list"


def test_dungeon_full_bag_is_not_a_consumptive_action_target():
    decision, safety = evaluate_decision(
        DUNGEON_SWEEP_DAILY_DEFINITION,
        "selected",
        ("yanwangling_title", "sweep_target", "dungeon_bag_full"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_sweep_panel"
    assert safety is not None and safety.allowed is True


def test_dungeon_without_sweep_tickets_is_not_eligible():
    decision, _ = evaluate_decision(
        DUNGEON_SWEEP_DAILY_DEFINITION,
        "selected",
        ("yanwangling_title", "sweep_target", "dungeon_no_sweep_ticket"),
    )

    assert decision.status is TaskStatus.NOT_ELIGIBLE


def test_dungeon_open_sweep_panel_assigns_tickets_without_reselecting_card():
    decision, safety = evaluate_decision(
        DUNGEON_SWEEP_DAILY_DEFINITION,
        "sweep",
        ("sweep_panel_page", "ticket_plus"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "assign_sweep_ticket"
    assert decision.transition.next_state == "sweep_ready"
    assert safety is not None and safety.allowed is True


def test_dungeon_retry_resumes_from_open_sweep_panel():
    decision, safety = evaluate_decision(
        DUNGEON_SWEEP_DAILY_DEFINITION,
        "home",
        ("sweep_panel_page", "ticket_plus"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "assign_sweep_ticket"
    assert safety is not None and safety.allowed is True


def test_dungeon_retry_resumes_from_selected_yanwangling_detail_page():
    decision, safety = evaluate_decision(
        DUNGEON_SWEEP_DAILY_DEFINITION,
        "home",
        ("yanwangling_title", "sweep_target"),
    )

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "open_sweep_panel"
    assert safety is not None and safety.allowed is True


def test_dungeon_selection_uses_title_as_postcondition_not_internal_state():
    transition = DUNGEON_SWEEP_DAILY_DEFINITION.transitions["dungeon_scroll_2"]

    assert transition.postcondition == "yanwangling_title"
    assert transition.next_state == "selected"


def test_dungeon_retry_does_not_request_the_internal_selected_state_as_pipeline():
    assert "selected" not in DUNGEON_SWEEP_DAILY_DEFINITION.recognizers("home")


def test_dungeon_finishes_when_reward_popup_returns_to_dungeon():
    result_transition = DUNGEON_SWEEP_DAILY_DEFINITION.transitions["result"]

    assert result_transition.intent.action_id == "dismiss_sweep_result"
    assert result_transition.next_state == "done"
    assert DUNGEON_SWEEP_DAILY_DEFINITION.complete_markers["done"] == ("dungeon_page",)
