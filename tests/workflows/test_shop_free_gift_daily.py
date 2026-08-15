from agent.safety import SafetyReason
from agent.workflows.definitions.shop_free_gift_daily import SHOP_FREE_GIFT_DAILY_DEFINITION
from tests.workflows.support import evaluate_decision


def test_shop_free_gift_requires_free_same_frame_text():
    _, denied = evaluate_decision(
        SHOP_FREE_GIFT_DAILY_DEFINITION,
        "benefits",
        ("shop.period_benefits.page", "shop.daily_free_gift"),
    )
    assert denied is None
    decision, allowed = evaluate_decision(
        SHOP_FREE_GIFT_DAILY_DEFINITION,
        "benefits",
        ("shop.period_benefits.page", "shop.daily_free_gift"),
        texts=("每日特惠", "免费"),
    )
    assert decision.transition is not None
    assert allowed.reason is SafetyReason.ALLOWED


def test_shop_free_gift_dismisses_reward_before_close():
    transition = SHOP_FREE_GIFT_DAILY_DEFINITION.transitions["reward"]

    assert transition.intent.target_marker == "shop.free_gift.dismiss"
    assert transition.postcondition == "shop.daily_free_gift_claimed"
    assert transition.next_state == "claimed"
    assert "shop.period_benefits.page" in SHOP_FREE_GIFT_DAILY_DEFINITION.recognizers(
        "reward"
    )
