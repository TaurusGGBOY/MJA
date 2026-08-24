from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_native_terminal_contract,
    assert_no_side_effect_retry,
    load_task_nodes,
)


ROOT = Path(__file__).parents[3]
BATTLE_PASS = TaskContract(
    "BATTLE_PASS_REWARD_DAILY",
    "daily/battle_pass_reward_daily.json",
)
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / BATTLE_PASS.pipeline_file
RECORDER = "0069-战令奖励-记录-失败"
TASK_FAILURES = (
    "0066-战令奖励-任务-歧义",
    "0067-战令奖励-奖励-歧义",
)
NATIVE_SUCCESS = (
    "0064-战令奖励-全部已领取",
    "0065-战令奖励-全部已领取-成功",
)


def _scoped_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def _contains(roi: list[int], box: list[int]) -> bool:
    x, y, width, height = roi
    bx, by, bwidth, bheight = box
    return (
        x <= bx
        and y <= by
        and bx + bwidth <= x + width
        and by + bheight <= y + height
    )


def test_r20_start_keeps_direct_home_entry_without_recorder_fallback() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    start = nodes["0001-战令奖励-任务入口"]

    assert start["next"] == ["0043-战令奖励-主页-探测"]
    assert start["on_error"] == [
        "MJA-任务入口失败-BATTLE_PASS_REWARD_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert RECORDER not in start["on_error"]
    assert "MJA_BP_OPEN_PANEL" not in nodes
    assert "MJA_BP_PANEL_PROBE" not in nodes
    assert "open_function_panel" not in TASK_POLICIES[BATTLE_PASS.task_id].action_caps


def test_r20_home_ocr_proves_direct_top_level_battle_pass_entry() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    home = nodes["0070-战令奖励-战斗-战令-主页-页面"]
    entry = nodes["0075-战令奖励-战斗-战令-打开"]

    assert home == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": [
                    "0071-战令奖励-战斗-战令-主页-活动",
                    "0072-战令奖励-战斗-战令-主页-祈福",
                    "0073-战令奖励-战斗-战令-主页-副本",
                    "0074-战令奖励-战斗-战令-主页-画卷",
                ],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }
    assert entry == {
        "recognition": "OCR",
        "expected": "战令",
        "roi": [760, 20, 140, 90],
        "action": "DoNothing",
    }

    assert _contains(entry["roi"], [824, 56, 30, 18])
    assert _contains(nodes["0071-战令奖励-战斗-战令-主页-活动"]["roi"], [882, 58, 35, 14])
    assert _contains(nodes["0072-战令奖励-战斗-战令-主页-祈福"]["roi"], [1001, 58, 31, 14])
    assert _contains(nodes["0073-战令奖励-战斗-战令-主页-副本"]["roi"], [1057, 58, 36, 14])
    assert _contains(nodes["0074-战令奖励-战斗-战令-主页-画卷"]["roi"], [1116, 58, 32, 14])

    assert nodes["0043-战令奖励-主页-探测"]["recognition"]["param"] == {
        "all_of": [
            "0070-战令奖励-战斗-战令-主页-页面",
            "0075-战令奖励-战斗-战令-打开",
        ],
        "box_index": 0,
    }
    opened = nodes["0044-战令奖励-打开-战斗-战令"]
    assert opened["recognition"]["param"] == {
        "all_of": [
            "0070-战令奖励-战斗-战令-主页-页面",
            "0075-战令奖励-战斗-战令-打开",
        ],
        "box_index": 1,
    }
    assert opened["max_hit"] == 1
    assert opened["retry_times"] == 0


def test_r20_task_rewards_keep_bounded_claim_and_no_claim_branch() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    page = nodes["0047-战令奖励-任务-页面-探测"]
    assert nodes["0079-战令奖励-战斗-战令-任务"]["recognition"]["param"] == {
        "all_of": [
            "0076-战令奖励-战斗-战令-页面",
            "0081-战令奖励-战斗-战令-任务-标签",
            "0080-战令奖励-战斗-战令-任务-内容",
        ],
        "box_index": 0,
    }
    assert nodes["0080-战令奖励-战斗-战令-任务-内容"]["expected"] == [
        "^每周任务$",
        "^当期任务$",
        "^追赶任务$",
    ]
    assert page["next"] == [
        "0048-战令奖励-任务-领取",
        "0049-战令奖励-任务-无-领取-探测",
    ]

    claim = nodes["0048-战令奖励-任务-领取"]
    assert claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0079-战令奖励-战斗-战令-任务",
        "target_name": "0082-战令奖励-战斗-战令-任务-奖励-领取",
    }
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0
    assert claim["next"] == [
        "0050-战令奖励-任务-奖励-探测",
        "0051-战令奖励-任务-物品-探测",
    ]

    target = nodes["0082-战令奖励-战斗-战令-任务-奖励-领取"]
    assert target["expected"] == "^领取$"
    assert target["roi"] == [700, 190, 220, 180]
    no_claim = nodes["0083-战令奖励-战斗-战令-任务-无-可领取"]
    assert no_claim["expected"] == [
        "^已领取$",
        "^暂无可领取$",
        "^未完成$",
        "^前往$",
    ]
    assert "已完成" not in no_claim["expected"]


def test_r20_basic_rewards_keep_finite_claim_and_popup_recovery() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    page = nodes["0055-战令奖励-奖励-页面-探测"]
    assert page["next"] == [
        "0056-战令奖励-基础-领取",
        "0057-战令奖励-基础-已全部领取-探测",
    ]
    claim = nodes["0056-战令奖励-基础-领取"]
    assert claim["recognition"]["param"] == {
        "all_of": [
            "0085-战令奖励-战斗-战令-奖励",
            "0088-战令奖励-战斗-战令-基础-红色-红点-奖励",
        ],
        "box_index": 1,
    }
    assert claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0085-战令奖励-战斗-战令-奖励",
        "target_name": "0088-战令奖励-战斗-战令-基础-红色-红点-奖励",
    }
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0
    assert claim["next"] == [
        "0058-战令奖励-基础-奖励-探测",
        "0059-战令奖励-基础-物品-探测",
    ]

    assert nodes["0058-战令奖励-基础-奖励-探测"]["timeout"] == 12000
    assert nodes["0059-战令奖励-基础-物品-探测"]["timeout"] == 12000
    assert nodes["0058-战令奖励-基础-奖励-探测"].get("on_error") != [RECORDER]
    assert nodes["0059-战令奖励-基础-物品-探测"].get("on_error") != [RECORDER]


def test_r20_native_success_requires_home_observation_after_close() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    assert nodes["0098-战令奖励-战斗-战令-关闭"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BUY_TEA_DAILY/shop_close.png",
        "roi": [1170, 0, 110, 110],
        "threshold": 0.36,
        "action": "DoNothing",
    }

    routes = (
        ("0062-战令奖励-关闭-已完成", "0064-战令奖励-全部已领取"),
        ("0063-战令奖励-关闭-成功", "0065-战令奖励-全部已领取-成功"),
    )
    for close_name, success_name in routes:
        close = nodes[close_name]
        assert close["next"] == [success_name]
        assert close["on_error"] == ["0068-战令奖励-主页边界-失败"]
        assert close["max_hit"] == 1
        assert close["retry_times"] == 0
        assert nodes[success_name]["recognition"]["param"] == {
            "all_of": [
                "0070-战令奖励-战斗-战令-主页-页面",
                "0075-战令奖励-战斗-战令-打开",
            ],
            "box_index": 0,
        }

    scoped = _scoped_nodes()
    assert_native_terminal_contract(
        scoped,
        success_nodes=list(NATIVE_SUCCESS),
        failure_nodes=[],
    )
    assert scoped["0068-战令奖励-主页边界-失败"]["action"] == "StopTask"


def test_r20_ambiguous_states_use_native_failure_without_status_payload() -> None:
    scoped = _scoped_nodes()
    assert_native_terminal_contract(
        scoped,
        success_nodes=[],
        failure_nodes=list(TASK_FAILURES),
    )


def test_r20_migrated_pipeline_has_only_native_terminals_and_local_recovery() -> None:
    scoped = _scoped_nodes()
    assert_no_custom_outcome_nodes(scoped)
    assert_on_error_contract(
        scoped,
        shared_targets={"1365-公共-主页边界-失败"},
    )
    assert all(
        RECORDER not in node.get("on_error", [])
        for node in scoped.values()
    )
    assert RECORDER not in scoped


def test_r20_every_battle_pass_side_effect_is_non_retrying_and_capped() -> None:
    nodes = _scoped_nodes()
    policy = TASK_POLICIES[BATTLE_PASS.task_id]

    for action_id in policy.action_caps:
        assert_no_side_effect_retry(nodes, action_id)

    for node in nodes.values():
        params = node.get("custom_action_param", {})
        action_id = params.get("action_id")
        if (
            params.get("task_id") != BATTLE_PASS.task_id
            or action_id not in policy.action_caps
        ):
            continue
        assert node["retry_times"] == 0
        assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
