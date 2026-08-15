from agent.workflows.definitions.collection_deployment_daily import (
    COLLECTION_DEPLOYMENT_DAILY_DEFINITION,
)
from tests.workflows.support import evaluate_decision


def test_collection_harvest_is_the_only_claim_target():
    decision, safety = evaluate_decision(
        COLLECTION_DEPLOYMENT_DAILY_DEFINITION,
        "collection",
        ("采集部署-采集-页面", "采集部署-采集-收获-全部"),
    )
    assert decision.transition.intent.action_id == "claim_all_collection"
    assert safety.allowed


def test_collection_reward_popup_returns_to_painting_before_shared_home_boundary():
    decision, safety = evaluate_decision(
        COLLECTION_DEPLOYMENT_DAILY_DEFINITION,
        "collection_reward_popup",
        ("采集部署-采集-奖励-弹窗", "采集部署-采集-弹窗-关闭"),
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "close_reward_popup"
    assert decision.transition.next_state == "painting_scroll_done"
    assert decision.transition.postcondition == "painting_scroll.page"
    assert safety is not None and safety.allowed
