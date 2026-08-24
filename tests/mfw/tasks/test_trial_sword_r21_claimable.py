from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
)
from tests.mfw.task_contract import TaskContract, assert_no_side_effect_retry


TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")
ROOT = Path(__file__).parents[3]


def _pipeline() -> dict[str, dict[str, object]]:
    path = ROOT / "assets/resource/base/pipeline" / TRIAL.pipeline_file
    return json.loads(path.read_text(encoding="utf-8"))


def test_trial_r21_claimable_reward_keeps_same_frame_evidence_and_cap() -> None:
    pipeline = _pipeline()
    claim = pipeline["1315-试剑-领取-奖励"]
    assert claim["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "1327-试剑-试炼-页面",
                "1328-试剑-试炼-奖励-领取",
            ],
            "box_index": 1,
        },
    }
    assert claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "1327-试剑-试炼-页面",
        "target_name": "1328-试剑-试炼-奖励-领取",
    }
    assert claim["custom_action_param"]["action_id"] == (
        "claim_trial_sword_reward"
    )
    assert claim["retry_times"] == 0
    assert TASK_POLICIES[TRIAL.task_id].action_caps["claim_trial_sword_reward"] == 1


def test_trial_r21_claimable_path_closes_popup_before_native_success_cleanup() -> None:
    pipeline = _pipeline()
    assert pipeline["1321-试剑-奖励-成功"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "next": ["1322-试剑-关闭-免费-奖励"],
    }
    assert pipeline["1322-试剑-关闭-免费-奖励"]["next"] == [
        "1324-试剑-关闭-成功"
    ]
    assert pipeline["1322-试剑-关闭-免费-奖励"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert pipeline["1324-试剑-关闭-成功"]["next"] == [
        "1325-试剑-成功-主页-探测"
    ]
    assert pipeline["1325-试剑-成功-主页-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]


def test_trial_r21_claimable_path_has_no_recorder_or_side_effect_retry() -> None:
    pipeline = _pipeline()
    assert_no_custom_outcome_nodes(pipeline)
    assert_no_side_effect_retry(pipeline, "claim_trial_sword_reward")
    assert_no_side_effect_retry(pipeline, "close_reward_popup")
    assert pipeline["1316-试剑-关闭-奖励"].get("on_error") is None
    assert pipeline["1319-试剑-确认-免费"].get("on_error") is None
    assert pipeline["1320-试剑-免费-奖励-探测"].get("on_error") is None
