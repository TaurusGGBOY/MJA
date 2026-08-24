from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
    assert_native_success_node,
)
from tests.mfw.task_contract import TaskContract, load_task_nodes


TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")
ROOT = Path(__file__).parents[3]


def _pipeline() -> dict[str, dict[str, object]]:
    path = ROOT / "assets/resource/base/pipeline" / TRIAL.pipeline_file
    return json.loads(path.read_text(encoding="utf-8"))


def test_trial_free_claim_branch_uses_native_failure_for_unknown_state() -> None:
    pipeline = _pipeline()
    nodes = load_task_nodes(TRIAL)

    assert pipeline["1314-试剑-打开-试炼"]["next"] == ["1315-试剑-领取-奖励"]
    assert pipeline["1315-试剑-领取-奖励"]["on_error"] == [
        "1317-试剑-领取-免费"
    ]
    assert pipeline["1316-试剑-关闭-奖励"]["next"] == ["1317-试剑-领取-免费"]
    assert pipeline["1317-试剑-领取-免费"]["on_error"] == [
        "1323-试剑-记录-失败"
    ]
    assert "1318-试剑-已完成-探测" not in pipeline
    assert "1330-试剑-试炼-敬请期待" not in pipeline
    assert "敬请期待" not in json.dumps(pipeline, ensure_ascii=False)

    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_trial_already_complete_uses_native_success_without_custom_outcome() -> None:
    pipeline = _pipeline()
    assert_no_custom_outcome_nodes(pipeline)
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={
            "1369-公共-通用停止",
            "1372-公共-原生成功-尝试返回",
        },
    )
    assert pipeline["1324-试剑-关闭-成功"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert pipeline["1325-试剑-成功-主页-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
