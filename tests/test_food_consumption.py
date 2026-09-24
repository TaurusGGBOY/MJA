from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent.custom.action.food_progress import FoodConsumptionConfirmed
from agent.custom.action.guarded_input import GuardedInput
from agent.custom.support.state import RUN_STORE
from tests.mfw.fakes import FakeArgv, FakeContext, and_reco, hit_reco

TASK = "EAT_STAMINA_FOOD_DAILY"
VERIFY = "0400-吃体力食物-消耗数量-确认"


def ocr(text):
    return SimpleNamespace(hit=True, best_result=SimpleNamespace(text=text))


def confirmation(after, *, item="龙井虾仁"):
    return FakeArgv(
        json.dumps({"task_id": TASK, "action_id": "eat_longjing_shrimp", "limit": 6}),
        node_name=VERIFY,
        reco_detail=and_reco(hit_reco("详情"), ocr(item), ocr(str(after))),
    )


def test_six_verified_consumptions_route_to_home_without_a_seventh_use():
    RUN_STORE.begin(TASK)
    context = FakeContext()
    action = FoodConsumptionConfirmed()
    for count in range(1, 7):
        RUN_STORE.increment(TASK, "eat_longjing_shrimp")
        RUN_STORE.set_marker(TASK, "food.longjing_shrimp.before_amount", 20 - count)
        assert action.run(context, confirmation(19 - count))
        expected = (
            "0401-吃体力食物-六次消耗-关闭背包" if count == 6 else "0385-吃体力食物-候选-循环"
        )
        assert context.next_overrides[-1] == (VERIFY, [expected])
        assert not action.run(context, confirmation(19 - count)), "same frame cannot count twice"
    assert RUN_STORE.get_marker(TASK, "food.confirmed_uses") == 6


@pytest.mark.parametrize(
    "after,item",
    [(20, "龙井虾仁"), (21, "龙井虾仁"), (18, "龙井虾仁"), (19, "其他食物"), ("", "龙井虾仁")],
)
def test_unchanged_wrong_item_or_unknown_quantity_does_not_advance(after, item):
    RUN_STORE.begin(TASK)
    RUN_STORE.increment(TASK, "eat_longjing_shrimp")
    RUN_STORE.set_marker(TASK, "food.longjing_shrimp.before_amount", 20)
    context = FakeContext()
    assert not FoodConsumptionConfirmed().run(context, confirmation(after, item=item))
    assert context.next_overrides == []


def test_six_clicks_with_only_one_verified_decrement_cannot_succeed():
    RUN_STORE.begin(TASK)
    for _ in range(6):
        RUN_STORE.increment(TASK, "eat_longjing_shrimp")
    RUN_STORE.set_marker(TASK, "food.longjing_shrimp.before_amount", 20)
    assert not FoodConsumptionConfirmed().run(FakeContext(), confirmation(19))


@pytest.mark.parametrize("override_ok", [True, False])
def test_use_installs_exact_postcondition_before_sending_click(override_ok):
    RUN_STORE.begin(TASK)
    context = FakeContext()
    overrides = []

    def override(data):
        overrides.append(data)
        return override_ok

    context.override_pipeline = override
    params = {
        "task_id": TASK,
        "action_id": "eat_longjing_shrimp",
        "kind": "click",
        "resource_id": "龙井虾仁",
        "budget_amount": 1,
        "amount_index": 2,
        "resource_index": 3,
        "evidence": {"page_index": 0, "target_index": 1},
    }
    argv = FakeArgv(
        json.dumps(params),
        reco_detail=and_reco(hit_reco("物品"), hit_reco("使用"), ocr("20"), ocr("龙井虾仁")),
    )
    assert GuardedInput().run(context, argv) is override_ok
    assert overrides == [
        {"0424-吃体力食物-食物-消耗后数量": {"expected": r"^(?:当前拥有|拥有|有)?\s*19$"}}
    ]
    assert bool(context.tasker.controller.actions) is override_ok


@pytest.mark.parametrize("label", ["36", "有36", "拥有36", "当前拥有36"])
def test_ocr_merged_ownership_label_still_requires_exact_single_decrement(label):
    RUN_STORE.begin(TASK)
    RUN_STORE.increment(TASK, "eat_longjing_shrimp")
    RUN_STORE.set_marker(TASK, "food.longjing_shrimp.before_amount", 37)
    assert FoodConsumptionConfirmed().run(FakeContext(), confirmation(label))
    assert RUN_STORE.get_marker(TASK, "food.confirmed_uses") == 1
