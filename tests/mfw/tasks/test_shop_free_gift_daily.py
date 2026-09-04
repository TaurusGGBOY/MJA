from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_reachable,
    load_task_nodes,
)

SHOP = TaskContract("SHOP_FREE_GIFT_DAILY", "daily/shop_free_gift_daily.json")
ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline/daily/shop_free_gift_daily.json"


def _pipeline() -> dict[str, dict[str, Any]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_shop_has_explicit_available_and_already_claimed_candidates() -> None:
    pipeline = _pipeline()

    assert pipeline["1229-商店免费礼包-商店-页面"]["next"] == [
        "1244-商店免费礼包-打开-周期-福利"
    ]
    open_period = pipeline["1244-商店免费礼包-打开-周期-福利"]
    assert open_period["recognition"]["param"] == {
        "all_of": [
            "1229-商店免费礼包-商店-页面",
            "1239-商店免费礼包-商店-周期-权益-页面",
        ],
        "box_index": 1,
    }
    assert open_period["custom_action"] == "GuardedInput"
    assert open_period["custom_action_param"] == {
        "task_id": "SHOP_FREE_GIFT_DAILY",
        "action_id": "open_period_benefits",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1229-商店免费礼包-商店-页面",
            "target_name": "1239-商店免费礼包-商店-周期-权益-页面",
        },
    }
    assert open_period["next"] == [
        "1230-商店免费礼包-已领取",
        "1232-商店免费礼包-领取",
    ]
    assert open_period["max_hit"] == 1
    assert open_period.get("retry_times", 0) == 0
    assert pipeline["1230-商店免费礼包-已领取"]["expected"] == [
        "已领取",
        "今日已领取",
        "领取完毕",
    ]
    assert pipeline["1230-商店免费礼包-已领取"]["next"] == [
        "1231-商店免费礼包-已完成"
    ]
    assert pipeline["1231-商店免费礼包-已完成"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "next": ["1235-商店免费礼包-关闭"],
    }

    available = pipeline["1232-商店免费礼包-领取"]
    assert available["recognition"]["param"] == {
        "all_of": [
            "1239-商店免费礼包-商店-周期-权益-页面",
            "1240-商店免费礼包-商店-日常-免费-礼包",
        ],
        "box_index": 1,
    }
    assert available["next"] == ["1233-商店免费礼包-关闭-奖励"]
    assert available["retry_times"] == 0


def test_shop_success_candidates_converge_on_native_cleanup() -> None:
    pipeline = _pipeline()
    nodes = load_task_nodes(SHOP)

    assert pipeline["1234-商店免费礼包-成功"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "next": ["1235-商店免费礼包-关闭"],
    }
    assert pipeline["1235-商店免费礼包-关闭"]["next"] == [
        "1236-商店免费礼包-关闭-面板"
    ]
    assert pipeline["1236-商店免费礼包-关闭-面板"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert_native_success_node(nodes["1369-公共-通用停止"])
    assert_reachable(nodes, "1231-商店免费礼包-已完成", "1369-公共-通用停止")
    assert_reachable(nodes, "1234-商店免费礼包-成功", "1369-公共-通用停止")


def test_shop_has_no_recorder_or_error_as_state_route() -> None:
    pipeline = _pipeline()

    assert_no_custom_outcome_nodes(pipeline)
    assert "1237-商店免费礼包-记录-失败" not in pipeline
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={"1369-公共-通用停止"},
    )
    assert pipeline["0019-商店免费礼包-任务入口"]["timeout"] == 5000
    assert pipeline["0019-商店免费礼包-任务入口"]["on_error"] == [
        "MJA-任务入口失败-SHOP_FREE_GIFT_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    for name in (
        "1227-商店免费礼包-打开-面板",
        "1228-商店免费礼包-打开-商店",
        "1229-商店免费礼包-商店-页面",
        "1231-商店免费礼包-已完成",
        "1232-商店免费礼包-领取",
        "1234-商店免费礼包-成功",
    ):
        assert pipeline[name].get("on_error") is None


def test_shop_cleanup_failure_stops_without_downgrading_claim_success() -> None:
    pipeline = _pipeline()

    assert pipeline["1233-商店免费礼包-关闭-奖励"]["on_error"] == [
        "1235-商店免费礼包-关闭"
    ]
    assert pipeline["1235-商店免费礼包-关闭"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert pipeline["1236-商店免费礼包-关闭-面板"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert pipeline["1233-商店免费礼包-关闭-奖励"]["retry_times"] == 0
    assert_no_side_effect_retry(load_task_nodes(SHOP), "claim_free_gift")


def test_shop_preserves_navigation_evidence_and_action_bounds() -> None:
    pipeline = _pipeline()
    nodes = load_task_nodes(SHOP)
    policy = TASK_POLICIES[SHOP.task_id]
    action_ids = [
        "open_function_panel",
        "open_shop",
        "open_period_benefits",
        "claim_free_gift",
        "dismiss_free_gift_reward",
        "close_shop",
        "close_function_panel",
    ]

    assert_guarded_actions(nodes, SHOP.task_id, action_ids)
    assert pipeline["0019-商店免费礼包-任务入口"]["next"] == [
        "1227-商店免费礼包-打开-面板"
    ]
    assert pipeline["1227-商店免费礼包-打开-面板"]["next"] == [
        "1228-商店免费礼包-打开-商店"
    ]
    assert pipeline["1228-商店免费礼包-打开-商店"]["next"] == [
        "1229-商店免费礼包-商店-页面"
    ]
    assert pipeline["1232-商店免费礼包-领取"]["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "1239-商店免费礼包-商店-周期-权益-页面",
        "target_name": "1240-商店免费礼包-商店-日常-免费-礼包",
    }
    assert pipeline["1233-商店免费礼包-关闭-奖励"]["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "1241-商店免费礼包-商店-免费-礼包-奖励",
        "target_name": "1242-商店免费礼包-商店-免费-礼包-关闭",
    }
    assert policy.action_caps == {
        "open_function_panel": 3,
        "open_shop": 3,
        "open_period_benefits": 3,
        "claim_free_gift": 1,
        "dismiss_free_gift_reward": 1,
        "close_shop": 1,
        "close_function_panel": 1,
    }
    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if params.get("task_id") != SHOP.task_id:
            continue
        action_id = params.get("action_id")
        if action_id not in policy.action_caps:
            continue
        assert node.get("retry_times", 0) == 0
        assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
