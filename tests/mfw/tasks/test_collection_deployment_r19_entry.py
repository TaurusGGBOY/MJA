from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
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
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
RECORD_FAILURE = "采集部署-记录-失败"
BOUNDARY_FAILURE = "采集部署-边界-失败"
ROOT = Path(__file__).parents[3]
CANONICAL_MAIN = Path("/Volumes/my_disk/project/MJA")
R22_FIXTURE = (
    ROOT
    / "tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/r22_harvest_entry.json"
)


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_live_world_home_toolbar_context_drives_painting_entry_roi() -> None:
    nodes = load_task_nodes(COLLECTION)

    # The current 1280x720 world-home frame keeps the top function row in this
    # bounded context.  Use the same broad toolbar OCR context that has
    # already recognized 画卷 in a fresh MFW frame, while excluding the
    # bottom-right regional 画卷 entry by height.
    observed = {
        "采集部署-采集-主页-副本": [1060, 60, 29, 11],
        "采集部署-采集-画卷-滚动-入口": [1116, 58, 32, 14],
        "采集部署-采集-主页-试炼": [990, 643, 44, 22],
    }
    expected = {
        "采集部署-采集-主页-副本": "^副本$",
        "采集部署-采集-画卷-滚动-入口": "^画卷$",
        "采集部署-采集-主页-试炼": "^试剑$",
    }

    for name, box in observed.items():
        node = nodes[name]
        roi = node["roi"]
        assert node["recognition"] == "OCR"
        assert node["expected"] == expected[name]
        assert _contains(roi, box)
        if name == "采集部署-采集-画卷-滚动-入口":
            assert roi[0] == 800
        else:
            assert roi[0] >= 900
        assert roi[2] * roi[3] < FRAME_WIDTH * FRAME_HEIGHT // 30

    assert nodes["采集部署-采集-画卷-滚动-入口"]["roi"] == [800, 40, 370, 50]
    assert nodes["采集部署-采集-画卷-滚动-入口"]["roi"][1] >= 40
    assert nodes["采集部署-采集-画卷-滚动-入口"]["roi"][1] + nodes[
        "采集部署-采集-画卷-滚动-入口"
    ]["roi"][3] <= 100


def test_start_fans_out_reward_collection_and_home_as_siblings() -> None:
    nodes = load_task_nodes(COLLECTION)
    start = nodes[COLLECTION.entry]

    # r19 listed only the reward probe.  MaaFramework therefore retried that
    # one candidate for 20 seconds and never selected its on_error route.
    assert start["next"] == [
        "[JumpBack]采集部署-已知-采集-过期-商店-关闭",
        "采集部署-恢复继续-奖励-探测",
        "采集部署-页面-探测",
        "采集部署-主页-探测",
    ]
    assert start["on_error"] == [RECORD_FAILURE]
    assert nodes["采集部署-恢复继续-奖励-探测"]["on_error"] == [
        RECORD_FAILURE
    ]
    assert nodes["采集部署-页面-探测"]["on_error"] == [RECORD_FAILURE]
    assert nodes["采集部署-主页-探测"]["on_error"] == [RECORD_FAILURE]


def test_reward_close_uses_live_blank_click_marker_without_stale_item_title() -> None:
    nodes = load_task_nodes(COLLECTION)
    expected = {
        "type": "And",
        "param": {
            "all_of": ["采集部署-采集-奖励-弹窗", "采集部署-采集-弹窗-关闭"],
            "box_index": 1,
        },
    }
    for name in ("采集部署-恢复继续-奖励-探测", "采集部署-关闭-奖励"):
        assert nodes[name]["recognition"] == expected

    close = nodes["采集部署-关闭-奖励"]
    assert close["next"] == ["采集部署-奖励-画卷-探测"]
    assert close["custom_action"] == "GuardedInput"
    assert close["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "采集部署-采集-奖励-弹窗",
        "target_name": "采集部署-采集-弹窗-关闭",
    }

    painting_probe = nodes["采集部署-奖励-画卷-探测"]
    assert painting_probe["recognition"] == {
        "type": "And",
        "param": {"all_of": ["采集部署-采集-画卷-页面"]},
    }
    assert painting_probe["next"] == ["MJA_COLLECTION_REWARD_RETURNED"]
    assert painting_probe["on_error"] == [RECORD_FAILURE]

    returned = nodes["MJA_COLLECTION_REWARD_RETURNED"]
    assert returned["custom_action"] == "RecordTaskOutcome"
    assert returned["custom_action_param"] == {
        "task_id": COLLECTION.task_id,
        "status": "success",
        "postcondition": "collection.reward_closed_to_painting",
    }
    assert returned["next"] == ["采集部署-关闭-画卷"]


def test_home_entry_uses_same_frame_world_boundary_and_exact_painting_target() -> None:
    nodes = load_task_nodes(COLLECTION)

    assert nodes["采集部署-采集-主页-页面"] == {
        "recognition": "TemplateMatch",
        "template": "home/home_marker.png",
        "roi": [1040, 0, 240, 110],
        "threshold": 0.375,
        "action": "DoNothing",
    }

    same_frame = ["采集部署-采集-主页-页面", "采集部署-采集-画卷-滚动-入口"]
    probe = nodes["采集部署-主页-探测"]
    assert probe["recognition"] == {
        "type": "And",
        "param": {"all_of": same_frame, "box_index": 0},
    }

    open_painting = nodes["采集部署-打开-画卷"]
    assert open_painting["recognition"] == {
        "type": "And",
        "param": {"all_of": same_frame, "box_index": 1},
    }
    assert open_painting["custom_action"] == "GuardedInput"
    assert open_painting["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "采集部署-采集-主页-页面",
        "target_name": "采集部署-采集-画卷-滚动-入口",
    }
    assert nodes["采集部署-采集-画卷-滚动-入口"]["expected"] == "^画卷$"
    assert "template" not in nodes["采集部署-采集-画卷-滚动-入口"]
    assert "画卷" not in nodes["采集部署-采集-画卷-页面"]["expected"]
    assert nodes["采集部署-画卷-探测"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["采集部署-采集-画卷-页面"]},
    }


def test_every_collection_input_is_guarded_once_and_business_effects_cannot_replay() -> None:
    nodes = load_task_nodes(COLLECTION)
    policy = TASK_POLICIES[COLLECTION.task_id]
    expected_actions = {
        "open_painting_scroll",
        "select_yanwu_world",
        "open_collection_deployment",
        "claim_all_collection",
        "close_reward_popup",
        "close_collection_deployment",
        "close_collection_painting",
    }
    guarded = {
        node["custom_action_param"]["action_id"]: node
        for name, node in nodes.items()
        if name.startswith("采集部署-")
        and node.get("custom_action") == "GuardedInput"
    }

    assert set(guarded) == expected_actions
    for action_id, node in guarded.items():
        assert node["max_hit"] == 1
        assert node["retry_times"] == 0
        assert policy.action_caps[action_id] == 1
        assert node["custom_action_param"]["kind"] == "click"

    for action_id in ("open_collection_deployment", "claim_all_collection"):
        assert_no_side_effect_retry(nodes, action_id)
        assert len(guarded_nodes_for_action(nodes, action_id)) == 1

    assert not any(
        node.get("action") in {"Click", "Swipe", "MultiSwipe", "Key", "Input"}
        for name, node in nodes.items()
        if name.startswith("采集部署-")
    )


def test_all_reachable_failures_record_terminal_failed_before_native_failure() -> None:
    nodes = load_task_nodes(COLLECTION)

    failure_nodes = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id") == COLLECTION.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert set(failure_nodes) == {RECORD_FAILURE, BOUNDARY_FAILURE}
    for node in failure_nodes.values():
        assert node["custom_action_param"]["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["公共-通用中止"]
        assert "on_error" not in node

    workflow_failures = (
        "采集部署-任务入口",
        "采集部署-恢复继续-奖励-探测",
        "采集部署-页面-探测",
        "采集部署-领取",
        "采集部署-关闭-奖励",
        "采集部署-奖励-画卷-探测",
        "MJA_COLLECTION_CLAIM_VERIFY",
        "MJA_COLLECTION_HARVEST_VERIFY",
        "采集部署-主页-探测",
        "采集部署-打开-画卷",
        "采集部署-画卷-探测",
        "采集部署-打开-偃武",
        "采集部署-偃武-探测",
        "采集部署-打开-采集",
        "采集部署-之后-打开-页面-探测",
    )
    for name in workflow_failures:
        assert nodes[name]["on_error"] == [RECORD_FAILURE], name

    for name in (
        "采集部署-关闭",
        "采集部署-画卷-之后-关闭-探测",
        "采集部署-关闭-画卷",
        "采集部署-主页边界-探测",
    ):
        assert nodes[name]["on_error"] == [BOUNDARY_FAILURE], name

    assert nodes["MJA_COLLECTION_INITIAL_HARVESTED"]["on_error"] == [RECORD_FAILURE]
    assert nodes["采集部署-奖励-探测"]["on_error"] == [
        "MJA_COLLECTION_CLAIM_VERIFY"
    ]
    assert not any(
        "启动-游戏启动" in target
        for name, node in nodes.items()
        if name.startswith("采集部署-")
        for target in node.get("on_error", [])
    )


def test_r22_page_exposes_harvest_as_parent_sibling_with_tight_target() -> None:
    nodes = load_task_nodes(COLLECTION)
    fixture = json.loads(R22_FIXTURE.read_text(encoding="utf-8"))

    archived = CANONICAL_MAIN / fixture["source"]
    if archived.is_file():
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]

    page = nodes["采集部署-采集-页面"]
    assert re.fullmatch(page["expected"], fixture["page"]["text"])
    assert _contains(page["roi"], fixture["page"]["box"])

    expected_siblings = [
        "MJA_COLLECTION_INITIAL_HARVESTED",
        "采集部署-领取",
    ]
    assert nodes["采集部署-页面-探测"]["next"] == expected_siblings
    assert nodes["采集部署-之后-打开-页面-探测"]["next"] == expected_siblings
    assert nodes["MJA_COLLECTION_INITIAL_HARVESTED"]["on_error"] == [RECORD_FAILURE]

    harvest = nodes["采集部署-采集-收获-全部"]
    assert harvest["roi"] == [880, 610, 320, 85]
    assert _contains(harvest["roi"], fixture["harvest"]["button_box"])
    for text in fixture["harvest"]["accepted_texts"]:
        assert re.fullmatch(harvest["expected"], text)

    claim = nodes["采集部署-领取"]
    assert claim["recognition"]["param"] == {
        "all_of": ["采集部署-采集-页面", "采集部署-采集-收获-全部"],
        "box_index": 1,
    }
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0
    assert TASK_POLICIES[COLLECTION.task_id].action_caps["claim_all_collection"] == 1


def test_terminal_outcomes_require_fresh_collection_state_then_restore_home() -> None:
    nodes = load_task_nodes(COLLECTION)

    contracts = {
        "MJA_COLLECTION_ALREADY_HARVESTED": (
            "success",
            "MJA_COLLECTION_INITIAL_HARVESTED",
        ),
        "MJA_COLLECTION_HARVEST_VERIFIED": (
            "success",
            "MJA_COLLECTION_HARVEST_VERIFY",
        ),
    }
    for outcome_name, (status, visual_probe_name) in contracts.items():
        outcome = nodes[outcome_name]
        params = outcome["custom_action_param"]
        assert params["status"] == status
        assert params["postcondition"] == "collection.harvested"
        assert outcome["next"] == ["采集部署-关闭"]

        visual_probe = nodes[visual_probe_name]
        assert visual_probe["recognition"] == {
            "type": "And",
            "param": {
                "all_of": ["采集部署-采集-页面", "collection.harvested"],
                "box_index": 1,
            },
        }
        assert visual_probe["next"] == [outcome_name]

    assert nodes["采集部署-关闭"]["next"] == [
        "采集部署-画卷-之后-关闭-探测",
        "采集部署-主页边界-探测",
    ]
    assert nodes["采集部署-画卷-之后-关闭-探测"]["next"] == [
        "采集部署-关闭-画卷"
    ]
    assert nodes["采集部署-关闭-画卷"]["next"] == [
        "采集部署-主页边界-探测"
    ]
    assert nodes["采集部署-采集-画卷-关闭"] == {
        "recognition": "TemplateMatch",
        "template": "daily/HERO_DISPATCH_DAILY/painting_close.png",
        "roi": [1175, 5, 75, 75],
        "threshold": 0.35,
        "green_mask": True,
        "action": "DoNothing",
    }
    assert nodes["采集部署-主页边界-探测"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["采集部署-采集-主页-页面"]},
    }
    assert nodes["采集部署-主页边界-探测"]["next"] == [
        "公共-通用停止",
        "[JumpBack]启动-游戏启动",
    ]
