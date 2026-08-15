from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.mfw.fakes import FakeArgv, FakeContext, and_reco

from agent.custom.action.jianlin_planner import (
    ChallengePlan,
    PlanJianlinChallenge,
    plan_safe_challenge,
)


def _ocr(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        hit=True,
        best_result=SimpleNamespace(text=text),
        filtered_results=[],
    )


def _argv(
    *,
    stamina: int = 120,
    cost: int = 20,
    visible_max: int = 6,
    multipliers: tuple[int, ...] = (1, 2, 3),
) -> FakeArgv:
    sub_results = [
        _ocr(f"当前体力 {stamina}"),
        _ocr(f"消耗体力 {cost}"),
        _ocr(f"上限{visible_max}"),
        *[_ocr(f"{value}倍") for value in multipliers],
    ]
    payload = {
        "dispatch_node": "剑林凝结体体力-计划-派遣",
        "stamina_index": 0,
        "cost_index": 1,
        "visible_max_index": 2,
        "multiplier_indices": list(range(3, 3 + len(multipliers))),
    }
    return FakeArgv(
        custom_action_param=json.dumps(payload, ensure_ascii=False),
        reco_detail=and_reco(*sub_results),
    )


def _selected_argv() -> FakeArgv:
    sub_results = [
        _ocr("当前体力 400/310"),
        _ocr("消耗体力 360"),
        _ocr("上限6"),
        _ocr("挑战次数 x6"),
        _ocr("结算倍率 x3"),
        _ocr("挑战"),
    ]
    payload = {
        "dispatch_node": "剑林凝结体体力-计划-派遣",
        "stamina_index": 0,
        "cost_index": 1,
        "visible_max_index": 2,
        "selected_count_index": 3,
        "selected_multiplier_index": 4,
        "max_total_cost": 360,
    }
    return FakeArgv(
        custom_action_param=json.dumps(payload, ensure_ascii=False),
        reco_detail=and_reco(*sub_results),
    )


@pytest.mark.parametrize(
    ("stamina", "cost", "visible_max", "multipliers", "expected"),
    [
        (120, 20, 6, (1, 2, 3), ChallengePlan(2, 3)),
        (40, 20, 6, (1, 2, 3), ChallengePlan(1, 2)),
    ],
)
def test_plan_safe_challenge(
    stamina: int,
    cost: int,
    visible_max: int,
    multipliers: tuple[int, ...],
    expected: ChallengePlan,
):
    assert plan_safe_challenge(stamina, cost, visible_max, multipliers) == expected


@pytest.mark.parametrize(
    ("stamina", "cost", "visible_max", "multipliers"),
    [
        (19, 20, 6, (1, 2, 3)),
        (120, 0, 6, (1, 2, 3)),
        (120, 20, 0, (1, 2, 3)),
        (120, 20, 6, ()),
    ],
)
def test_plan_safe_challenge_rejects_unsafe_inputs(
    stamina: int,
    cost: int,
    visible_max: int,
    multipliers: tuple[int, ...],
):
    with pytest.raises(ValueError):
        plan_safe_challenge(stamina, cost, visible_max, multipliers)


def test_planner_action_selects_declared_branch_without_input_access():
    context = FakeContext(nodes={
        "剑林凝结体体力-计划-派遣",
        "剑林凝结体体力-设置-次数-次数-2-倍率-3",
    })

    assert PlanJianlinChallenge().run(context, _argv()) is True
    assert context.next_overrides == [
        (
            "剑林凝结体体力-计划-派遣",
            ["剑林凝结体体力-设置-次数-次数-2-倍率-3"],
        )
    ]
    assert context.controller.actions == []


def test_planner_accepts_a_safe_current_live_slider_selection():
    context = FakeContext(nodes={
        "剑林凝结体体力-计划-派遣",
        "剑林凝结体体力-设置-次数-次数-6-倍率-3",
    })

    assert PlanJianlinChallenge().run(context, _selected_argv()) is True
    assert context.next_overrides == [
        (
            "剑林凝结体体力-计划-派遣",
            ["剑林凝结体体力-设置-次数-次数-6-倍率-3"],
        )
    ]


def test_planner_reduces_an_unsafe_default_selection_to_an_affordable_plan():
    sub_results = [
        _ocr("当前体力 58/310"),
        _ocr("消耗体力 360"),
        _ocr("上限6"),
        _ocr("挑战次数 x6"),
        _ocr("结算倍率 x3"),
        _ocr("挑战"),
    ]
    payload = {
        "dispatch_node": "剑林凝结体体力-计划-派遣",
        "stamina_index": 0,
        "cost_index": 1,
        "visible_max_index": 2,
        "selected_count_index": 3,
        "selected_multiplier_index": 4,
        "max_total_cost": 360,
    }
    context = FakeContext(nodes={
        "剑林凝结体体力-计划-派遣",
        "剑林凝结体体力-设置-次数-次数-1-倍率-2",
    })

    assert PlanJianlinChallenge().run(
        context,
        FakeArgv(
            custom_action_param=json.dumps(payload, ensure_ascii=False),
            reco_detail=and_reco(*sub_results),
        ),
    ) is True
    assert context.next_overrides == [
        (
            "剑林凝结体体力-计划-派遣",
            ["剑林凝结体体力-设置-次数-次数-1-倍率-2"],
        )
    ]


def test_planner_action_rejects_malformed_ocr_and_missing_branch():
    context = FakeContext(nodes={"剑林凝结体体力-计划-派遣"})
    argv = _argv()
    argv.reco_detail.best_result.sub_results[1] = _ocr("unknown")

    assert PlanJianlinChallenge().run(context, argv) is False
    assert context.next_overrides == []

    context = FakeContext(nodes={"剑林凝结体体力-计划-派遣"})
    assert PlanJianlinChallenge().run(context, _argv()) is False
    assert context.next_overrides == []


def test_planner_source_has_no_runtime_input_or_capture_dependencies():
    source = Path("agent/custom/action/jianlin_planner.py").read_text(encoding="utf-8").lower()
    assert "controller" not in source
    assert "screencap" not in source
    assert "subprocess" not in source
