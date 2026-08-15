from __future__ import annotations

from agent.workflows.definitions.guild_donation_daily import (
    GUILD_DONATION_DAILY_DEFINITION as DEFINITION,
    GUILD_DONATION_DAILY_POLICY as POLICY,
    MAX_FREE_DONATIONS,
    terminal_postcondition,
)
from agent.workflows.models import (
    CapturedFrame,
    Recognition,
    StateSnapshot,
    TaskStatus,
    VisualEvidence,
)


def snapshot(
    state: str,
    *markers: str,
    texts: tuple[str, ...] = (),
) -> StateSnapshot:
    frame_id = f"guild-donation-{state}"
    hits = {marker: 1 for marker in markers}
    evidence = VisualEvidence(
        frame_id,
        hits,
        hits,
        {},
        {marker: frame_id for marker in markers},
        texts=texts,
    )
    recognitions = tuple(
        Recognition(marker, frame_id, 1, ((10, 10, 20, 20),)) for marker in markers
    )
    return StateSnapshot(CapturedFrame(frame_id, (1280, 720)), state, recognitions, evidence)


def test_navigation_path_is_bounded_and_uses_free_target_only():
    panel = DEFINITION.decide(snapshot("home", "home"), {})
    assert panel.transition is not None
    assert panel.transition.intent.action_id == "open_function_panel"

    guild = DEFINITION.decide(snapshot("panel", "guild.entry"), {})
    assert guild.transition is not None
    assert guild.transition.intent.action_id == "open_guild"

    donation = DEFINITION.decide(snapshot("guild", "帮派捐献-帮派-捐献-入口"), {})
    assert donation.transition is not None
    assert donation.transition.intent.action_id == "open_guild_donation"


def test_9_of_10_is_already_complete_without_clicking():
    decision = DEFINITION.decide(
        snapshot(
            "donation",
            "帮派捐献-帮派-捐献-页面",
            "帮派捐献-帮派-捐献-上下文",
            "帮派捐献-帮派-捐献-剩余-9-共-10",
            "帮派捐献-帮派-捐献-免费",
            texts=("今日可捐献次数 9/10",),
        ),
        {},
    )
    assert decision.status is TaskStatus.ALREADY_COMPLETE


def test_only_10_of_10_authorizes_one_free_donation():
    decision = DEFINITION.decide(
        snapshot(
            "donation",
            "帮派捐献-帮派-捐献-页面",
            "帮派捐献-帮派-捐献-上下文",
            "帮派捐献-帮派-捐献-剩余-10-共-10",
            "帮派捐献-帮派-捐献-免费",
            texts=("今日可捐献次数 10/10",),
        ),
        {},
    )
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "donate_guild_free_once"
    assert decision.transition.next_state == "verify"
    assert POLICY.action_caps["donate_guild_free_once"] == MAX_FREE_DONATIONS


def test_postcondition_requires_one_click_and_exact_9_of_10():
    completed = DEFINITION.decide(
        snapshot(
            "verify",
            "帮派捐献-帮派-捐献-页面",
            "帮派捐献-帮派-捐献-上下文",
            "帮派捐献-帮派-捐献-剩余-9-共-10",
            texts=("今日可捐献次数 9/10",),
        ),
        {"donate_guild_free_once": 1},
    )
    assert completed.status is TaskStatus.COMPLETED

    no_click = DEFINITION.decide(
        snapshot(
            "verify",
            "帮派捐献-帮派-捐献-页面",
            "帮派捐献-帮派-捐献-上下文",
            "帮派捐献-帮派-捐献-剩余-9-共-10",
            texts=("今日可捐献次数 9/10",),
        ),
        {},
    )
    assert no_click.status is TaskStatus.FAILED

    wrong_counter = DEFINITION.decide(
        snapshot(
            "verify",
            "帮派捐献-帮派-捐献-页面",
            "帮派捐献-帮派-捐献-上下文",
            texts=("今日可捐献次数 8/10",),
        ),
        {"donate_guild_free_once": 1},
    )
    assert wrong_counter.status is TaskStatus.FAILED


def test_paid_or_unknown_surface_fails_closed_and_terminal_marker_is_stable():
    decision = DEFINITION.decide(
        snapshot(
            "donation",
            "帮派捐献-帮派-捐献-页面",
            "帮派捐献-帮派-捐献-上下文",
            "帮派捐献-帮派-捐献-剩余-10-共-10",
            "帮派捐献-帮派-捐献-免费",
            "guild.donation.paid",
        ),
        {},
    )
    assert decision.status is TaskStatus.FAILED
    assert terminal_postcondition(TaskStatus.COMPLETED) == (
        "guild.donation.remaining_9_of_10"
    )
    assert terminal_postcondition(TaskStatus.ALREADY_COMPLETE) == (
        "guild.donation.remaining_9_of_10"
    )
