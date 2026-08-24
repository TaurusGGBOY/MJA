from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    guarded_nodes_for_action,
    load_task_nodes,
)


COLLECTION = TaskContract(
    "COLLECTION_DEPLOYMENT_DAILY",
    "daily/collection_deployment_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / COLLECTION.pipeline_file
CANONICAL_MAIN = ROOT
R22_FIXTURE = ROOT / "tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/r22_harvest_entry.json"


def _local_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_entry_initializes_native_task_lifecycle_before_first_click() -> None:
    nodes = _local_nodes()
    entry = nodes["0004-采集部署-打开-画卷"]
    click = nodes["0004-采集部署-打开-画卷-点击"]

    assert entry["is_entry"] is True
    assert entry["action"] == "Custom"
    assert entry["custom_action"] == "BeginTask"
    assert entry["custom_action_param"] == {"task_id": COLLECTION.task_id}
    assert entry["next"] == ["0004-采集部署-打开-画卷-点击"]
    assert entry["timeout"] == 5000
    assert entry["on_error"] == [
        "MJA-任务入口失败-COLLECTION_DEPLOYMENT_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]

    assert click["custom_action"] == "GuardedInput"
    assert click["custom_action_param"]["action_id"] == "open_painting_scroll"
    assert click["custom_action_param"]["task_id"] == COLLECTION.task_id
    assert click["custom_action_param"]["fixed_click_mode"] == "painting_scroll_button"


def test_collection_has_only_native_success_and_natural_failure_routes() -> None:
    local = _local_nodes()
    nodes = load_task_nodes(COLLECTION)

    assert_no_custom_outcome_nodes(local)
    assert_on_error_contract(
        local,
        local_nodes=set(local),
        shared_targets={"1365-公共-主页边界-失败", "1371-公共-原生成功-主页边界"},
    )
    assert all(
        "0237-采集部署-记录-失败" not in node.get("on_error", [])
        for node in local.values()
    )
    assert all(
        target not in {"1363-公共-主页边界", "1366-公共-通用中止"}
        for node in local.values()
        for target in node.get("next", [])
        if isinstance(node.get("next"), list)
    )

    assert local["0236-采集部署-关闭-画卷"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert local["0230-采集部署-打开-采集"]["on_error"] == [
        "0237-采集部署-失败-返回主页",
    ]
    cleanup = local["0237-采集部署-失败-返回主页"]
    assert cleanup["custom_action"] == "ReturnToWorldHome"
    assert cleanup["timeout"] == 30000
    assert cleanup["max_hit"] == 1
    assert cleanup["next"] == ["1365-公共-主页边界-失败"]
    assert cleanup["on_error"] == ["1365-公共-主页边界-失败"]
    assert_native_failure_node(nodes["1365-公共-主页边界-失败"])
    assert_native_success_node(nodes["1369-公共-通用停止"])


def test_collection_success_requires_deploy_before_harvest() -> None:
    local = _local_nodes()

    assert local["0231-采集部署-一键部署"]["next"] == [
        "0252-采集部署-确认-自动部署",
        "0232-采集部署-领取",
    ]
    assert local["0252-采集部署-确认-自动部署"]["next"] == [
        "0232-采集部署-领取"
    ]
    assert local["0246-采集部署-采集-部署-全部"]["expected"] == (
        "^(?:一键部署|键部署)$"
    )
    assert local["0232-采集部署-领取"]["next"] == [
        "0233-采集部署-收获-成功"
    ]
    assert local["0233-采集部署-收获-成功"]["next"] == [
        "0234-采集部署-关闭-奖励",
        "0235-采集部署-关闭",
    ]
    assert local["0230-采集部署-打开-采集"]["on_error"] != [
        "0235-采集部署-关闭",
        "0236-采集部署-关闭-画卷",
    ]


def test_every_deployment_and_harvest_input_remains_single_shot_and_guarded() -> None:
    local = _local_nodes()
    policy = TASK_POLICIES[COLLECTION.task_id]
    expected_actions = {
        "open_painting_scroll",
        "select_yanwu_world",
        "open_collection_deployment",
        "deploy_all_collection",
        "confirm_collection_deployment",
        "claim_all_collection",
        "close_reward_popup",
        "close_collection_deployment",
        "close_collection_painting",
    }
    guarded = {
        node["custom_action_param"]["action_id"]: node
        for node in local.values()
        if node.get("custom_action") == "GuardedInput"
    }

    assert set(guarded) == expected_actions
    for action_id, node in guarded.items():
        assert node["max_hit"] == 1
        assert node["retry_times"] == 0
        assert node["custom_action_param"]["kind"] == "click"
        assert policy.action_caps[action_id] == 1

    for action_id in ("open_painting_scroll", "deploy_all_collection", "claim_all_collection"):
        assert_no_side_effect_retry(local, action_id)
        assert len(guarded_nodes_for_action(local, action_id)) == 1


def test_r22_harvest_target_and_page_bounds_remain_unchanged() -> None:
    nodes = _local_nodes()
    fixture = json.loads(R22_FIXTURE.read_text(encoding="utf-8"))

    archived = CANONICAL_MAIN / fixture["source"]
    if archived.is_file():
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]

    page = nodes["0244-采集部署-采集-页面"]
    assert re.fullmatch(page["expected"], fixture["page"]["text"])
    assert _contains(page["roi"], fixture["page"]["box"])

    harvest = nodes["0245-采集部署-采集-收获-全部"]
    assert harvest["roi"] == [880, 610, 320, 85]
    assert _contains(harvest["roi"], fixture["harvest"]["button_box"])
    for text in (*fixture["harvest"]["accepted_texts"], "收获全部", "领取全部"):
        assert re.fullmatch(harvest["expected"], text)

    claim = nodes["0232-采集部署-领取"]
    assert claim["recognition"]["param"] == {
        "all_of": ["0244-采集部署-采集-页面", "0245-采集部署-采集-收获-全部"],
        "box_index": 1,
    }
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0
    assert TASK_POLICIES[COLLECTION.task_id].action_caps["claim_all_collection"] == 1
