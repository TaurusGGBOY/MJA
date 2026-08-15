from agent.safety import SafetyReason
from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.definitions.mail_reward_daily import MAIL_REWARD_DAILY_DEFINITION
from agent.workflows.models import TaskStatus
from tests.workflows.support import evaluate_decision


def test_mail_contract_and_actionable_decision():
    policy = TASK_POLICIES["MAIL_REWARD_DAILY"]
    assert policy.action_caps["claim_all_mail"] == 1
    decision, safety = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.claim_all")
    )
    assert decision.transition.intent.action_id == "claim_all_mail"
    assert decision.transition.postcondition == "mail.reward_popup"
    assert safety.reason is SafetyReason.ALLOWED


def test_mail_claim_result_closes_expected_reward_popup():
    decision, safety = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION,
        "mail_reward_popup",
        ("mail.reward_popup", "mail.reward_popup_close"),
    )

    assert decision.transition.intent.action_id == "close_reward_popup"
    assert decision.transition.postcondition == "mail.page"
    assert safety.reason is SafetyReason.ALLOWED


def test_mail_close_returns_to_panel_before_closing_panel_to_home():
    policy = TASK_POLICIES["MAIL_REWARD_DAILY"]
    assert policy.action_caps["close_function_panel"] == 1

    decision, safety = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION,
        "mail_after_claim",
        ("mail.page", "mail.close"),
    )
    assert decision.transition.intent.action_id == "close_mail"
    assert decision.transition.postcondition == "function_panel.page"
    assert safety.reason is SafetyReason.ALLOWED

    decision, safety = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION,
        "function_panel_after_mail",
        ("function_panel.page", "reset.panel_close"),
    )
    assert decision.transition.intent.action_id == "close_function_panel"
    assert decision.transition.postcondition == "home"
    assert safety.reason is SafetyReason.ALLOWED


def test_mail_completed_and_safety():
    decision, _ = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.empty")
    )
    assert decision.status is TaskStatus.ALREADY_COMPLETE
    _, paid = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION,
        "mail",
        ("mail.page", "mail.claim_all"),
        texts=("Apple Pay",),
    )
    assert paid.reason is SafetyReason.ALLOWED
    assert paid.allowed is True


def test_mail_claim_button_wins_over_read_footer_during_transition():
    decision, _ = evaluate_decision(
        MAIL_REWARD_DAILY_DEFINITION,
        "mail",
        ("mail.page", "mail.empty", "mail.claim_all"),
    )

    assert decision.status is None
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "claim_all_mail"
