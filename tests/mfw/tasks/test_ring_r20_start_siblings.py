from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract, load_task_nodes


ROOT = Path(__file__).resolve().parents[3]
RING = TaskContract("RING_CHALLENGE_DAILY", "daily/ring_challenge_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / RING.pipeline_file


def _load_pipeline() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_r20_pipeline_uses_native_terminals_and_local_recovery_only() -> None:
    pipeline = _load_pipeline()

    assert_no_custom_outcome_nodes(pipeline)
    assert "1125-擂台挑战-记录-失败" not in pipeline
    assert_on_error_contract(pipeline, local_nodes=set(pipeline))
    assert_native_success_node({"action": "StopTask"})
    assert not any(
        node.get("custom_action") == "FailTask" for node in pipeline.values()
    )


def test_r20_start_and_result_candidates_keep_order() -> None:
    nodes = load_task_nodes(RING)
    ring_nodes = _load_pipeline()

    assert nodes["0017-擂台挑战-任务入口"]["next"] == [
        "1077-擂台挑战-打开-对弈"
    ]
    assert nodes["1079-擂台挑战-点击-擂台"]["next"] == [
        "1180-擂台挑战-擂台-次数为0-已完成",
        "1093-擂台挑战-大师-点击开始",
        "1092-擂台挑战-打开-模式",
    ]
    assert nodes["1092-擂台挑战-打开-模式"]["next"] == [
        "1095-擂台挑战-擂台-券-耗尽-探测",
        "[JumpBack]1107-擂台挑战-战斗-循环",
    ]
    assert ring_nodes["1095-擂台挑战-擂台-券-耗尽-探测"]["next"] == [
        "1120-擂台挑战-关闭-对手",
    ]
    assert nodes["1107-擂台挑战-战斗-循环"]["next"] == [
        "[JumpBack]1110-擂台挑战-跳过",
        "1114-擂台挑战-战斗-关闭-结果",
    ]
    assert nodes["1110-擂台挑战-跳过"]["next"] == [
        "1111-擂台挑战-跳过-确定",
    ]
    assert "next" not in ring_nodes["1111-擂台挑战-跳过-确定"]
    assert "next" not in ring_nodes["1114-擂台挑战-战斗-关闭-结果"]


def test_r20_failtask_nodes_are_removed() -> None:
    pipeline = _load_pipeline()

    assert "1112-擂台挑战-战斗未知结果-结果" not in pipeline
    assert "1112-擂台挑战-战斗失败-结果" not in pipeline


def test_r20_confirmed_completion_uses_native_success_cleanup() -> None:
    nodes = load_task_nodes(RING)
    ring_nodes = _load_pipeline()

    assert "1116-擂台挑战-已完成-关闭-页面" not in ring_nodes
    assert "1103-擂台挑战-扫荡后-已完成-关闭-对手" not in ring_nodes
    assert ring_nodes["1094-擂台挑战-大师-点击扫荡"]["next"] == [
        "1095-擂台挑战-擂台-券-耗尽-探测",
        "1172-擂台挑战-扫荡-确认",
        "1113-擂台挑战-关闭-结果",
    ]
    confirm = ring_nodes["1172-擂台挑战-扫荡-确认"]
    assert confirm["recognition"]["param"] == {
        "all_of": [
            "1162-擂台挑战-擂台-扫荡-提示",
            "1163-擂台挑战-擂台-扫荡-确认",
        ],
        "box_index": 1,
    }
    assert confirm["custom_action_param"]["action_id"] == "confirm_ring_sweep"
    assert confirm["next"] == ["1113-擂台挑战-关闭-结果"]
    assert ring_nodes["1121-擂台挑战-关闭-页面"]["next"] == [
        "1122-擂台挑战-关闭-对弈"
    ]
    assert ring_nodes["1121-擂台挑战-关闭-页面"]["post_delay"] == 1500
    assert ring_nodes["1122-擂台挑战-关闭-对弈"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]


def test_r20_dueling_hub_cleanup_uses_guarded_ring_close() -> None:
    ring_nodes = _load_pipeline()
    close_hub = ring_nodes["1122-擂台挑战-关闭-对弈"]

    assert close_hub["recognition"]["param"] == {
        "all_of": ["1132-擂台挑战-对弈-入口"],
        "box_index": 0,
    }
    assert close_hub["custom_action"] == "GuardedInput"
    assert close_hub["custom_action_param"] == {
        "task_id": RING.task_id,
        "action_id": "close_dueling_menu",
        "kind": "click",
        "fixed_click_mode": "dueling_menu_close",
        "evidence": {
            "page_index": 0,
            "target_index": 0,
            "page_name": "1132-擂台挑战-对弈-入口",
            "target_name": "1132-擂台挑战-对弈-入口",
        },
    }
    assert close_hub["post_delay"] == 1500
    assert close_hub["next"] == ["1371-公共-原生成功-主页边界"]


def test_r20_battle_loops_are_bounded_and_resource_evidence_is_same_frame() -> None:
    nodes = load_task_nodes(RING)
    policy_caps = TASK_POLICIES[RING.task_id].action_caps

    for name in (
        "1107-擂台挑战-战斗-循环",
        "1110-擂台挑战-跳过",
    ):
        assert nodes[name]["max_hit"] == 12, name
        assert nodes[name]["retry_times"] == 0, name

    for name in ("1107-擂台挑战-战斗-循环",):
        node = nodes[name]
        params = node["custom_action_param"]
        all_of = node["recognition"]["param"]["all_of"]
        assert params["action_id"] in policy_caps
        assert all_of[params["resource_index"]] == "1150-擂台券"
        assert all_of[params["amount_index"]] == "1151-擂台挑战-擂台-券-数量"
        assert params["resource_evidence_name"] == "擂台券"
        assert params["budget_amount"] == 1
        assert "observed_amount" not in params

    assert nodes["1151-擂台挑战-擂台-券-数量"]["expected"] == [
        "^[1-9][0-9]?$",
        "^[1-9][0-9]?/12$",
    ]
    assert_all_cycles_bounded(nodes)
