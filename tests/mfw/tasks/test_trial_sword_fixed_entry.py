from __future__ import annotations

import json
from pathlib import Path

from agent.custom.action.guarded_input import GuardedInput
from agent.custom.support.state import RUN_STORE
from tests.mfw.fakes import FakeArgv, FakeContext, and_reco, hit_reco
from tests.mfw.task_contract import TaskContract, load_task_nodes


TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")
ROOT = Path(__file__).parents[3]


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
            "page_name": "0026-公共-游戏主页-页面",
            "target_name": "0026-公共-游戏主页-页面",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0026-公共-游戏主页-页面", (940, 660, 140, 40)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1078, 550))]


def test_trial_entry_has_bounded_restart_route() -> None:
    nodes = load_task_nodes(TRIAL)
    entry = nodes[TRIAL.entry]
    assert entry["next"] == ["1314-试剑-打开-试炼"]
    assert entry["timeout"] == 5000
    assert entry["on_error"] == [
        "MJA-任务入口失败-TRIAL_SWORD_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]


def test_trial_entry_keeps_the_fixed_target_definition() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource/base/pipeline" / TRIAL.pipeline_file).read_text(
            encoding="utf-8"
        )
    )
    open_trial = pipeline["1314-试剑-打开-试炼"]
    assert open_trial["custom_action_param"]["fixed_click_mode"] == (
        "trial_entry_button"
    )
    assert open_trial["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0026-公共-游戏主页-页面",
        "target_name": "1326-试剑-试炼-主页-入口",
    }
    assert open_trial["retry_times"] == 0


def test_trial_entry_roi_covers_the_current_bottom_right_label() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource/base/pipeline" / TRIAL.pipeline_file).read_text(
            encoding="utf-8"
        )
    )

    assert pipeline["1326-试剑-试炼-主页-入口"] == {
        "recognition": "OCR",
        "expected": "试剑",
        "roi": [930, 540, 180, 70],
        "action": "DoNothing",
    }
