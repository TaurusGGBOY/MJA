from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
PIPELINE = (
    ROOT
    / "assets/resource/base/pipeline/daily"
    / "jianlin_resource_condensate_stamina_daily.json"
)

PRICE_FIFTY = "0790-剑林凝结体体力-购买-体力-80可选50"
READ_STAMINA = "0787-剑林凝结体体力-重新识别-体力"
PLAN = "0788-剑林凝结体体力-计划"
EXHAUSTED = "0789-剑林凝结体体力-体力耗尽"
RESULT_PROBE = "0953-剑林凝结体体力-战斗-结果-探测"
RESULT_CLOSE = "0954-剑林凝结体体力-关闭-凝结体-结果"
CLEANUP = "0959-剑林凝结体体力-清理-页面-关闭"
SUCCESS = "1371-公共-原生成功-主页边界"


def _nodes() -> dict[str, dict]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_price_fifty_skips_only_purchase_and_still_enters_planning() -> None:
    optional = _nodes()[PRICE_FIFTY]

    assert optional["action"] == "Custom"
    assert optional["custom_action"] == "GuardedInput"
    assert optional["custom_action_param"]["action_id"] == (
        "dismiss_jianlin_stamina_purchase"
    )
    assert optional["max_hit"] == 1
    assert optional["post_delay"] == 1_000
    assert optional["next"] == [READ_STAMINA]
    assert SUCCESS not in optional["next"]


def test_each_confirmed_battle_result_replans_before_success() -> None:
    nodes = _nodes()

    assert nodes[RESULT_PROBE]["action"] == "DoNothing"
    assert nodes[RESULT_PROBE]["next"] == [RESULT_CLOSE]
    assert nodes[RESULT_CLOSE]["action"] == "Custom"
    assert nodes[RESULT_CLOSE]["custom_action"] == "GuardedInput"
    assert nodes[RESULT_CLOSE]["max_hit"] == 12
    assert nodes[RESULT_CLOSE]["retry_times"] == 0
    assert nodes[RESULT_CLOSE]["next"] == [READ_STAMINA]
    assert SUCCESS not in nodes[RESULT_CLOSE]["next"]
    assert nodes[READ_STAMINA]["next"] == [f"[JumpBack]{PLAN}"]


def test_replan_loop_is_bounded_and_exhaustion_enters_success_cleanup() -> None:
    nodes = _nodes()
    planner = nodes[PLAN]

    assert planner["custom_action"] == "PlanJianlinChallenge"
    assert 1 <= planner["max_hit"] <= 12
    assert planner["custom_action_param"]["insufficient_node"] == EXHAUSTED
    assert planner["custom_action_param"]["stop_stamina_at_or_below"] == 20
    assert planner["custom_action_param"]["max_multiplier"] == 6
    assert "fixed_count" not in planner["custom_action_param"]
    assert "count_slider_max" not in planner["custom_action_param"]
    assert "0996-剑林凝结体体力-剑林-次数-条" not in nodes
    assert "0997-剑林凝结体体力-剑林-次数-已选择" not in nodes

    challenge = nodes["0934-剑林凝结体体力-挑战-凝结体"]
    assert challenge["recognition"]["param"] == {
        "all_of": [
            "0973-剑林凝结体体力-剑林-页面",
            "1012-剑林凝结体体力-剑林-倍率-已选择",
            "1016-剑林凝结体体力-剑林-挑战-按钮",
        ],
        "box_index": 2,
    }
    assert challenge["custom_action_param"]["evidence"]["target_index"] == 2
    assert nodes["1012-剑林凝结体体力-剑林-倍率-已选择"]["expected"] == [
        r"结算倍率\s*[:：]?\s*[xX×]\s*(?:[1-6]|[lI])",
        r"[xX×]\s*(?:[1-6]|[lI])",
        r"(?:[1-6]|[lI])\s*倍",
    ]
    assert nodes[EXHAUSTED]["next"] == [CLEANUP]

    assert SUCCESS not in nodes[PRICE_FIFTY].get("next", [])
    assert SUCCESS not in nodes[RESULT_CLOSE].get("next", [])
    assert nodes[CLEANUP]["next"] == [
        "0960-剑林凝结体体力-清理-日常-关闭",
        SUCCESS,
    ]
