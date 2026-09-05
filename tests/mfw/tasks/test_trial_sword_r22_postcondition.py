from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
)

ROOT = Path(__file__).parents[3]
TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")


def _pipeline() -> dict[str, dict[str, object]]:
    path = ROOT / "assets/resource/base/pipeline" / TRIAL.pipeline_file
    return json.loads(path.read_text(encoding="utf-8"))


def test_trial_r22_does_not_keep_the_obsolete_completion_marker() -> None:
    pipeline = _pipeline()
    assert "1318-试剑-已完成-探测" not in pipeline
    assert "敬请期待" not in json.dumps(pipeline, ensure_ascii=False)


def test_trial_r22_unavailable_claim_checks_already_complete_state() -> None:
    pipeline = _pipeline()
    assert pipeline["1317-试剑-领取-免费"]["on_error"] == ["1318-试剑-已领取-关闭"]
    assert pipeline["1318-试剑-已领取-关闭"]["next"] == ["1324-试剑-关闭-成功"]


def test_trial_r22_unknown_failure_is_stateless_native_fail_task() -> None:
    pipeline = _pipeline()
    failure = pipeline["1323-试剑-记录-失败"]
    assert_native_failure_node(failure)
    assert_no_custom_outcome_nodes(pipeline)
    assert "status" not in failure
    assert "postcondition" not in failure
    assert "error_code" not in failure


def test_trial_r22_confirmed_success_cleanup_never_becomes_failed() -> None:
    pipeline = _pipeline()
    assert pipeline["1322-试剑-关闭-免费-奖励"]["on_error"] == ["1369-公共-通用停止"]
    assert pipeline["1324-试剑-关闭-成功"]["on_error"] == ["1369-公共-通用停止"]
    assert pipeline["1325-试剑-成功-主页-探测"]["on_error"] == ["1372-公共-原生成功-尝试返回"]
    assert_no_side_effect_retry(pipeline, "close_reward_popup")
    assert_no_side_effect_retry(pipeline, "close_trial")
