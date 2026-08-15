from datetime import date
from types import SimpleNamespace

from agent.workflows.catalog import TASK_POLICIES
from agent.workflows.definitions.weekly_free_gift_monday import WEEKLY_FREE_GIFT_MONDAY_DEFINITION
from agent.workflows.engine import run_workflow
from agent.workflows.models import CapturedFrame, TaskStatus, VisualEvidence
from tests.workflows.support import evaluate_decision


def test_weekly_policy_is_monday_only():
    assert TASK_POLICIES["WEEKLY_FREE_GIFT_MONDAY"].eligible_weekdays == frozenset({0})

    class NoCapture:
        def capture(self):
            raise AssertionError("Tuesday must not capture")

    result = run_workflow(
        WEEKLY_FREE_GIFT_MONDAY_DEFINITION,
        NoCapture(),
        TASK_POLICIES["WEEKLY_FREE_GIFT_MONDAY"],
        object(),
        day=date(2026, 7, 28),
    )
    assert result.status is TaskStatus.NOT_ELIGIBLE


def test_paid_weekly_tab_is_not_eligible_without_free_claim_target():
    assert "周一免费礼包-商店-每周-付费" in WEEKLY_FREE_GIFT_MONDAY_DEFINITION.recognizers("gift_tab")
    assert "周一免费礼包-商店-每周-付费" in WEEKLY_FREE_GIFT_MONDAY_DEFINITION.recognizers("weekly")

    decision, safety = evaluate_decision(
        WEEKLY_FREE_GIFT_MONDAY_DEFINITION,
        "weekly",
        ("周一免费礼包-商店-每周-页面", "周一免费礼包-商店-每周-付费"),
        texts=("每周特价", "￥6.00"),
    )

    assert decision.status is TaskStatus.NOT_ELIGIBLE
    assert safety is None


def test_weekly_claim_has_an_explicit_reward_dismissal_state():
    claim = WEEKLY_FREE_GIFT_MONDAY_DEFINITION.transitions["weekly"]
    dismiss = WEEKLY_FREE_GIFT_MONDAY_DEFINITION.transitions["weekly_reward"]

    assert claim.next_state == "weekly_reward"
    assert claim.postcondition == "shop.weekly.reward"
    assert dismiss.intent.action_id == "dismiss_weekly_reward"
    assert dismiss.postcondition == "shop.weekly_lucky_bag_claimed"


def test_weekly_reward_can_resume_from_the_initial_state():
    from agent.workflows.models import StateSnapshot

    frame = CapturedFrame("weekly-reward", (1280, 720))
    evidence = VisualEvidence(
        frame.frame_id,
        {"周一免费礼包-商店-每周-奖励": 1},
        {"周一免费礼包-商店-每周-奖励-关闭": 1},
        {},
        {"周一免费礼包-商店-每周-奖励": frame.frame_id, "周一免费礼包-商店-每周-奖励-关闭": frame.frame_id},
        (),
        (),
    )
    snapshot = StateSnapshot(frame, "home", (), evidence)

    decision = WEEKLY_FREE_GIFT_MONDAY_DEFINITION.decide(snapshot, {})

    assert decision.transition is not None
    assert decision.transition.intent.action_id == "dismiss_weekly_reward"


def test_weekly_route_survives_slow_android_frames_and_reaches_free_claim(monkeypatch):
    """The second tab must not fall back to the engine's 60-second default."""

    clock = iter(range(0, 181, 20))
    monkeypatch.setattr("agent.workflows.engine.monotonic", lambda: next(clock))

    class SlowShopDriver:
        def __init__(self):
            self.frame_number = 0
            self.actions = []

        def capture(self):
            self.frame_number += 1
            return CapturedFrame(f"frame-{self.frame_number}", (1280, 720))

        def recognize(self, frame, names):
            hits = {
                name: 1
                for name in names
                if (
                    name not in {"周一免费礼包-商店-每周-奖励", "周一免费礼包-商店-每周-奖励-关闭"}
                    or "claim_weekly_lucky_bag" in self.actions
                )
                and (
                    name != "周一免费礼包-商店-每周-幸运-背包-已领取"
                    or "dismiss_weekly_reward" in self.actions
                )
            }
            return VisualEvidence(
                frame.frame_id,
                hits,
                hits,
                {},
                {name: frame.frame_id for name in names},
                ("免费",),
                (),
            )

        def execute(self, intent):
            self.actions.append(intent.action_id)

    driver = SlowShopDriver()
    result = run_workflow(
        WEEKLY_FREE_GIFT_MONDAY_DEFINITION,
        driver,
        TASK_POLICIES["WEEKLY_FREE_GIFT_MONDAY"],
        SimpleNamespace(),
        day=date(2026, 8, 3),
        timeout_seconds=240.0,
    )

    assert result.status is TaskStatus.COMPLETED
    assert "open_weekly_must_buy" in driver.actions
    assert "claim_weekly_lucky_bag" in driver.actions
