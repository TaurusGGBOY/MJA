from agent.workflows.definitions.free_appraisal_daily import FREE_APPRAISAL_DAILY_DEFINITION
from tests.workflows.support import evaluate_decision


def test_free_appraisal_has_one_protected_action():
    decision, safety = evaluate_decision(
        FREE_APPRAISAL_DAILY_DEFINITION,
        "appraisal",
        ("appraisal.page", "appraisal.free_once"),
        texts=("免费鉴宝",),
    )
    assert decision.transition.intent.action_id == "claim_free_appraisal_once"
    assert safety.allowed


def test_free_appraisal_action_wins_over_ambiguous_used_ocr_marker():
    decision, safety = evaluate_decision(
        FREE_APPRAISAL_DAILY_DEFINITION,
        "appraisal",
        ("appraisal.page", "appraisal.free_once", "appraisal.used"),
        texts=("免费鉴宝",),
    )

    assert decision.transition.intent.action_id == "claim_free_appraisal_once"
    assert safety.allowed


def test_free_appraisal_used_marker_still_allows_already_complete():
    decision, safety = evaluate_decision(
        FREE_APPRAISAL_DAILY_DEFINITION,
        "appraisal",
        ("appraisal.page", "appraisal.used"),
    )

    assert decision.status.value == "already_complete"
    assert decision.transition is None
    assert safety is None


def test_free_appraisal_finishes_result_sheet_before_shared_home_boundary():
    transition = FREE_APPRAISAL_DAILY_DEFINITION.transitions["result_popup"]

    assert transition.intent.action_id == "close_appraisal_popup"
    assert transition.next_state == "appraisal_done"
    assert transition.postcondition == "appraisal.page"
    assert FREE_APPRAISAL_DAILY_DEFINITION.complete_markers["appraisal_done"] == (
        "appraisal.page",
    )
