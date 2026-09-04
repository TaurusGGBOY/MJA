from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_reachable,
    assert_resource_guard,
    assert_shared_resource_budget,
    load_task_nodes,
)


CONDENSATE = TaskContract(
    "SPEND_CONDENSATE_DAILY",
    "daily/spend_condensate_daily.json",
)
PIPELINE_PATH = (
    Path(__file__).parents[3]
    / "assets/resource/base/pipeline"
    / CONDENSATE.pipeline_file
)
FAILURE = "1279-消耗凝结体-预算-不安全"
VERIFY_OPEN_PANEL = "1320-消耗凝结体-完成-打开-面板"
VERIFY_OPEN_DAILY = "1321-消耗凝结体-完成-打开-日常"
VERIFY_COMPLETION = "1322-消耗凝结体-日常-消费完成-探测"
VERIFY_CLOSE_DAILY = "1323-消耗凝结体-完成-关闭-日常"
VERIFY_CLOSE_PANEL = "1324-消耗凝结体-完成-关闭-面板"


def _scoped_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def _targets(node: Mapping[str, object]) -> list[str]:
    targets: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list):
            continue
        targets.extend(target for target in values if isinstance(target, str))
    return targets


def test_currency_entry_uses_tight_green_masked_icon_templates_in_both_regions() -> None:
    nodes = load_task_nodes(CONDENSATE)

    pairs = (
        (
            "1256-消耗凝结体-打开-偃武",
            "1293-消耗凝结体-凝结体-偃武-页面",
            "1294-消耗凝结体-凝结体-偃武-货币-入口",
            "daily/SPEND_CONDENSATE_DAILY/yanwu_currency_icon.png",
        ),
        (
            "1266-消耗凝结体-打开-云州-恢复",
            "1303-消耗凝结体-凝结体-云州-页面",
            "1304-消耗凝结体-凝结体-云州-货币-入口",
            "daily/SPEND_CONDENSATE_DAILY/yunzhou_currency_icon.png",
        ),
    )
    for action_name, page_name, target_name, template in pairs:
        target = nodes[target_name]
        assert target["recognition"] == "TemplateMatch"
        assert target["template"] == template
        expected_roi = [991, 25, 32, 40]
        assert target["roi"] == expected_roi
        expected_threshold = 0.72 if "云州" in target_name else 0.8
        assert target["threshold"] == expected_threshold
        assert target["green_mask"] is True
        assert target["action"] == "DoNothing"
        assert "expected" not in target
        image_path = PIPELINE_PATH.parents[2] / "image" / template
        png = image_path.read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", png[16:24]) == (26, 32)

        action = nodes[action_name]
        assert action["recognition"]["param"] == {
            "all_of": [page_name, target_name],
            "box_index": 1,
        }
        assert action["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": page_name,
            "target_name": target_name,
        }


def test_first_region_purchase_recognition_failure_is_not_treated_as_zero() -> None:
    nodes = _scoped_nodes()

    assert nodes["1256-消耗凝结体-打开-偃武"]["on_error"] == [FAILURE]
    assert nodes["1260-消耗凝结体-设置-偃武-最大"]["on_error"] == [FAILURE]
    assert nodes["1261-消耗凝结体-购买-偃武"]["on_error"] == [FAILURE]
    assert nodes["1315-消耗凝结体-关闭-偃武购买页面"]["next"] == [
        "1264-消耗凝结体-选择-云州-之后-购买"
    ]


def test_condensate_purchases_bind_resource_and_cost_to_the_confirm_frame() -> None:
    nodes = load_task_nodes(CONDENSATE)
    icon = "1312-消耗凝结体-凝结体-货币"
    purchases = (
        (
            "1261-消耗凝结体-购买-偃武",
            "1295-消耗凝结体-凝结体-偃武-购买-页面",
            "1299-消耗凝结体-凝结体-偃武-购买-确认",
            "1300-消耗凝结体-凝结体-偃武-消耗-50000",
            "buy_yanwu_currency_max",
        ),
        (
            "1271-消耗凝结体-购买-云州-恢复",
            "1305-消耗凝结体-凝结体-云州-购买-页面",
            "1309-消耗凝结体-凝结体-云州-购买-确认",
            "1310-消耗凝结体-凝结体-云州-消耗-50000",
            "buy_yunzhou_currency_max",
        ),
    )

    for action_name, page_name, target_name, amount_name, action_id in purchases:
        node = nodes[action_name]
        assert node["recognition"]["param"] == {
            "all_of": [page_name, target_name, icon, amount_name],
            "box_index": 1,
        }
        params = node["custom_action_param"]
        assert params["resource_id"] == "凝晶"
        assert params["resource_evidence_name"] == icon
        assert params["resource_index"] == 2
        assert params["amount_index"] == 3
        assert params["observed_amount"] == 50000
        assert params["budget_amount"] == 50000
        assert_resource_guard(
            nodes,
            action_id,
            "凝晶",
            9_999_999,
            task_id=CONDENSATE.task_id,
        )

    assert_shared_resource_budget(nodes, "凝晶", 9_999_999)


def test_zero_remaining_skips_only_that_region_and_requires_both_regions() -> None:
    nodes = _scoped_nodes()

    assert nodes["1256-消耗凝结体-打开-偃武"]["next"] == [
        "1257-消耗凝结体-偃武-今日剩余为0-跳过",
        "1260-消耗凝结体-设置-偃武-最大",
    ]
    assert nodes["1257-消耗凝结体-偃武-今日剩余为0-跳过"]["recognition"]["param"] == {
        "all_of": [
            "1295-消耗凝结体-凝结体-偃武-购买-页面",
            "1296-消耗凝结体-凝结体-偃武-售罄",
        ],
        "box_index": 1,
    }
    assert nodes["1257-消耗凝结体-偃武-今日剩余为0-跳过"]["next"] == [
        "1315-消耗凝结体-关闭-偃武购买页面"
    ]
    assert nodes["1260-消耗凝结体-设置-偃武-最大"]["on_error"] == [FAILURE]
    assert nodes["1261-消耗凝结体-购买-偃武"]["on_error"] == [FAILURE]

    assert nodes["1266-消耗凝结体-打开-云州-恢复"]["next"] == [
        "1267-消耗凝结体-云州-今日剩余为0-跳过",
        "1270-消耗凝结体-设置-云州-最大-恢复",
    ]
    assert nodes["1267-消耗凝结体-云州-今日剩余为0-跳过"]["recognition"]["param"] == {
        "all_of": [
            "1305-消耗凝结体-凝结体-云州-购买-页面",
            "1306-消耗凝结体-凝结体-云州-售罄",
        ],
        "box_index": 1,
    }
    assert nodes["1267-消耗凝结体-云州-今日剩余为0-跳过"]["next"] == [
        "1269-消耗凝结体-关闭-云州-恢复"
    ]
    assert nodes["1270-消耗凝结体-设置-云州-最大-恢复"]["on_error"] == [FAILURE]
    assert nodes["1271-消耗凝结体-购买-云州-恢复"]["on_error"] == [FAILURE]
    assert nodes["1269-消耗凝结体-关闭-云州-恢复"]["next"] == [
        "1276-消耗凝结体-完成-收尾"
    ]

    for name in (
        "1296-消耗凝结体-凝结体-偃武-售罄",
        "1306-消耗凝结体-凝结体-云州-售罄",
    ):
        assert nodes[name]["expected"] == [
            "(?:今日)?剩余数量\\s*[：:]?\\s*0(?:\\s*/\\s*12500)?",
            "^0\\s*(?:/\\s*12500)?$",
        ]


def test_final_region_purchase_failure_is_the_only_condensate_business_failure() -> None:
    nodes = _scoped_nodes()
    assert_native_failure_node(nodes[FAILURE])

    assert nodes["1266-消耗凝结体-打开-云州-恢复"]["on_error"] == [FAILURE]
    assert nodes["1270-消耗凝结体-设置-云州-最大-恢复"]["on_error"] == [FAILURE]
    assert nodes["1271-消耗凝结体-购买-云州-恢复"]["on_error"] == [FAILURE]
    assert_reachable(nodes, "1271-消耗凝结体-购买-云州-恢复", FAILURE)


def test_quantity_max_uses_the_highest_confidence_template_match() -> None:
    nodes = _scoped_nodes()

    for name in (
        "1298-消耗凝结体-凝结体-偃武-最大-数量",
        "1308-消耗凝结体-凝结体-云州-最大-数量",
    ):
        target = nodes[name]
        assert target["recognition"] == "TemplateMatch"
        assert target["order_by"] == "Score"
        assert target["index"] == 0


def test_native_success_requires_the_exact_daily_completion_postcondition() -> None:
    nodes = _scoped_nodes()

    assert nodes["1276-消耗凝结体-完成-收尾"]["next"] == [VERIFY_OPEN_PANEL]

    expected_actions = {
        VERIFY_OPEN_PANEL: "open_function_panel",
        VERIFY_OPEN_DAILY: "open_daily_tasks_initial",
        VERIFY_CLOSE_DAILY: "close_daily_tasks",
        VERIFY_CLOSE_PANEL: "close_function_panel",
    }
    for name, action_id in expected_actions.items():
        node = nodes[name]
        assert node["custom_action"] == "GuardedInput"
        assert node["custom_action_param"]["action_id"] == action_id
        assert node["on_error"] == [FAILURE]

    verifier = nodes[VERIFY_COMPLETION]
    all_of = verifier["recognition"]["param"]["all_of"]
    assert all_of[0] == "1288-消耗凝结体-凝结体-日常-页面"
    task_row, completion_state = all_of[1:]
    assert task_row["sub_name"] == "spend_condensate_daily_completion_row_1322"
    assert task_row["recognition"] == "OCR"
    assert task_row["expected"] == r"^消耗\s*10000\s*凝晶[。.]?$"
    assert completion_state["sub_name"] == (
        "spend_condensate_daily_completion_state_1322"
    )
    assert completion_state["recognition"] == "OCR"
    assert completion_state["expected"] == r"^(?:领取|已领取)$"
    assert completion_state["roi"] == task_row["sub_name"]
    assert completion_state["roi_offset"] == [650, -20, 450, 40]
    assert verifier["recognition"]["param"]["box_index"] == 2
    assert verifier["on_error"] == [FAILURE]
    assert verifier["next"] == [VERIFY_CLOSE_DAILY]
    assert nodes[VERIFY_CLOSE_DAILY]["next"] == [VERIFY_CLOSE_PANEL]
    assert nodes[VERIFY_CLOSE_PANEL]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]


def test_condensate_has_no_legacy_outcome_recorder_and_native_success_cleanup() -> None:
    nodes = _scoped_nodes()
    assert_no_custom_outcome_nodes(nodes)
    assert_on_error_contract(
        nodes,
        shared_targets={
            "1369-公共-通用停止",
            "1372-公共-原生成功-尝试返回",
        },
    )
    assert_reachable(
        nodes,
        "1276-消耗凝结体-完成-收尾",
        "1371-公共-原生成功-主页边界",
    )


def test_consumptive_inputs_keep_policy_caps_and_no_replay() -> None:
    nodes = load_task_nodes(CONDENSATE)
    policy = TASK_POLICIES[CONDENSATE.task_id]

    guarded = [
        (name, node)
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == CONDENSATE.task_id
    ]
    assert guarded

    for name, node in guarded:
        params = node["custom_action_param"]
        action_id = params["action_id"]
        assert action_id in policy.action_caps, name
        assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
        assert node.get("retry_times", 0) == 0
        assert_no_side_effect_retry(nodes, action_id)

    assert all(
        FAILURE not in target
        for node in nodes.values()
        for target in _targets(node)
        if target != FAILURE
    )
