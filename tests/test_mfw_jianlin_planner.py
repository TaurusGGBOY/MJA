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
) -> FakeArgv:
    sub_results = [
        _ocr(f"当前体力 {stamina}"),
        _ocr("上限6"),
        _ocr("上限3"),
    ]
    payload = {
        "dispatch_node": "0788-剑林凝结体体力-计划",
        "stamina_index": 0,
        "count_max_index": 1,
        "multiplier_max_index": 2,
        "stamina_per_attempt": 20,
        "stop_stamina_at_or_below": 20,
        "insufficient_node": "0789-剑林凝结体体力-体力耗尽",
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


def test_plan_safe_challenge_respects_task_cost_cap():
    assert plan_safe_challenge(
        400,
        20,
        12,
        (1, 2, 3),
        max_total_cost=360,
    ) == ChallengePlan(count=6, multiplier=3)


def test_planner_action_clicks_count_and_multiplier_from_live_limits():
    context = FakeContext(nodes={
        "0788-剑林凝结体体力-计划",
        "0789-剑林凝结体体力-体力耗尽",
        "0934-剑林凝结体体力-挑战-凝结体",
    })

    assert PlanJianlinChallenge().run(context, _argv()) is True
    assert context.next_overrides == []
    assert context.controller.actions == [
        ("click", (985, 504)),
        ("click", (1206, 427)),
    ]


def test_planner_uses_one_count_when_only_one_run_is_affordable():
    context = FakeContext(nodes={
        "0788-剑林凝结体体力-计划",
        "0789-剑林凝结体体力-体力耗尽",
        "0934-剑林凝结体体力-挑战-凝结体",
    })

    assert PlanJianlinChallenge().run(context, _argv(stamina=60)) is True
    assert context.next_overrides == []
    assert context.controller.actions == [
        ("click", (930, 504)),
        ("click", (1206, 427)),
    ]


def test_planner_uses_five_count_for_the_observed_refill_follow_up():
    context = FakeContext(nodes={
        "0788-剑林凝结体体力-计划",
        "0789-剑林凝结体体力-体力耗尽",
        "0934-剑林凝结体体力-挑战-凝结体",
    })

    assert PlanJianlinChallenge().run(context, _argv(stamina=317)) is True
    assert context.controller.actions == [
        ("click", (1151, 504)),
        ("click", (1206, 427)),
    ]


def test_planner_routes_low_stamina_without_touching_either_slider():
    context = FakeContext(nodes={
        "0788-剑林凝结体体力-计划",
        "0789-剑林凝结体体力-体力耗尽",
        "0934-剑林凝结体体力-挑战-凝结体",
    })

    assert PlanJianlinChallenge().run(context, _argv(stamina=20)) is True
    assert context.controller.actions == []
    assert context.next_overrides == [
        (
            "0788-剑林凝结体体力-计划",
            ["0789-剑林凝结体体力-体力耗尽"],
        )
    ]


def test_planner_action_rejects_malformed_ocr_and_missing_branch():
    context = FakeContext(nodes={"0788-剑林凝结体体力-计划"})
    argv = _argv()
    argv.reco_detail.best_result.sub_results[0] = _ocr("unknown")

    assert PlanJianlinChallenge().run(context, argv) is False
    assert context.next_overrides == []

    context = FakeContext(nodes={"0789-剑林凝结体体力-体力耗尽"})
    assert PlanJianlinChallenge().run(context, _argv()) is False
    assert context.next_overrides == []

    context = FakeContext(nodes={
        "0788-剑林凝结体体力-计划",
        "0789-剑林凝结体体力-体力耗尽",
        "0934-剑林凝结体体力-挑战-凝结体",
    })
    argv = _argv()
    argv.reco_detail.best_result.sub_results[1] = _ocr("挑战次数")
    assert PlanJianlinChallenge().run(context, argv) is False
    assert context.controller.actions == []


def test_planner_source_has_no_runtime_capture_or_shell_dependencies():
    source = Path("agent/custom/action/jianlin_planner.py").read_text(encoding="utf-8").lower()
    assert "screencap" not in source
    assert "subprocess" not in source


def test_jianlin_routes_victory_result_before_prepare_page_detection():
    pipeline = json.loads(
        Path(
            "assets/resource/base/pipeline/daily/"
            "jianlin_resource_condensate_stamina_daily.json"
        ).read_text(encoding="utf-8")
    )

    battle_result = "0953-剑林凝结体体力-战斗-结果-探测"
    battle_wait = "0952-剑林凝结体体力-战斗-中-等待"
    battle_page = "0935-剑林凝结体体力-战斗-页面-探测"
    assert pipeline["0934-剑林凝结体体力-挑战-凝结体"]["timeout"] == 180_000
    assert pipeline["0934-剑林凝结体体力-挑战-凝结体"]["next"] == [
        battle_result,
        battle_wait,
        battle_page,
    ]
    assert pipeline[battle_wait] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["1018-剑林凝结体体力-剑林-战斗-中"],
            },
        },
        "max_hit": 12,
        "timeout": 180_000,
        "action": "Custom",
        "custom_action": "GuardedInput",
        "custom_action_param": {
            "task_id": "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
            "action_id": "wait_jianlin_battle",
            "kind": "none",
            "evidence": {
                "page_index": 0,
                "target_index": 0,
                "page_name": "1018-剑林凝结体体力-剑林-战斗-中",
                "target_name": "1018-剑林凝结体体力-剑林-战斗-中",
            },
        },
        "next": [battle_result],
        "retry_times": 0,
    }
    assert "post_delay" not in pipeline[battle_wait]
    assert pipeline["1018-剑林凝结体体力-剑林-战斗-中"] == {
        "recognition": "OCR",
        "expected": [
            "^自动战斗中$",
            "^自动中(?:…|\\.\\.\\.)?$",
            "^战斗中$",
        ],
        "roi": [1030, 620, 240, 100],
        "action": "DoNothing",
    }
    assert all(
        pipeline[name]["timeout"] == 180_000
        and pipeline[name]["next"] == [battle_result, battle_wait]
        for name in pipeline
        if name.startswith("剑林凝结体体力-开始-战斗-")
    )
    assert pipeline["0934-剑林凝结体体力-挑战-凝结体"]["next"] == [
        battle_result,
        battle_wait,
        battle_page,
    ]
    assert pipeline[battle_page]["next"][0] == battle_result
    assert "战斗胜利" in pipeline["1022-剑林凝结体体力-剑林-战斗-结果"]["expected"]
    assert "获得奖励" in pipeline["1022-剑林凝结体体力-剑林-战斗-结果"]["expected"]
    assert (
        pipeline["0959-剑林凝结体体力-清理-页面-关闭"]["custom_action_param"]
        ["fixed_click_mode"]
        == "jianlin_page_close"
    )
