from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.custom.action.guarded_input import GuardedInput
from agent.custom.support.state import RUN_STORE
from tests.mfw.fakes import FakeArgv, FakeContext, and_reco, hit_reco, miss_reco

PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)
TITLE = "1598-MJA-影之遗迹-奖励弹窗文案"
CLOSE_HINT = "0038-公共-已知-点击空白关闭"


def _params():
    nodes = json.loads(PIPELINE.read_text(encoding="utf-8"))
    return nodes["1597-MJA-影之遗迹-关闭奖励弹窗"]["custom_action_param"]


def test_shadow_settlement_drag_taps_the_calibrated_blank_area():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    argv = FakeArgv(
        json.dumps(_params()),
        reco_detail=and_reco(
            hit_reco(TITLE, (169, 296, 52, 176)),
            hit_reco(CLOSE_HINT, (574, 664, 133, 22)),
        ),
    )
    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("swipe", (650, 555, 651, 556, 100))]


def test_shadow_settlement_denies_an_uncalibrated_target_click():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    params = _params()
    params.pop("fixed_click_mode")
    argv = FakeArgv(
        json.dumps(params),
        reco_detail=and_reco(
            hit_reco(TITLE, (169, 296, 52, 176)),
            hit_reco(CLOSE_HINT, (574, 664, 133, 22)),
        ),
    )
    assert GuardedInput().run(context, argv) is False
    assert context.tasker.controller.actions == []


@pytest.mark.parametrize("missing", [TITLE, CLOSE_HINT])
def test_shadow_settlement_requires_both_title_and_ready_hint(missing):
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    observations = [
        miss_reco(name) if name == missing else hit_reco(name, box)
        for name, box in (
            (TITLE, (169, 296, 52, 176)),
            (CLOSE_HINT, (574, 664, 133, 22)),
        )
    ]
    argv = FakeArgv(json.dumps(_params()), reco_detail=and_reco(*observations))
    assert GuardedInput().run(context, argv) is False
    assert context.tasker.controller.actions == []
