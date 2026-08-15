from __future__ import annotations

import json

from agent.custom.action.guarded_input import GuardedInput
from agent.custom.support.state import RUN_STORE
from tests.mfw.fakes import FakeArgv, FakeContext, and_reco, hit_reco


def test_trial_entry_uses_fixed_button_after_same_frame_home_evidence() -> None:
    context = FakeContext()
    RUN_STORE.begin("TRIAL_SWORD_DAILY")
    payload = {
        "task_id": "TRIAL_SWORD_DAILY",
        "action_id": "open_trial_sword",
        "kind": "click",
        "fixed_click_mode": "trial_entry_button",
        "evidence": {
            "page_index": 0,
            "target_index": 0,
            "page_name": "公共-游戏主页-页面",
            "target_name": "公共-游戏主页-页面",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("公共-游戏主页-页面", (940, 660, 140, 40)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1013, 560))]
