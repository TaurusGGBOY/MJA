from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    guarded_nodes_for_action,
    load_task_nodes,
)


DAILY = TaskContract(
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "daily/daily_task_reward_claim_daily.json",
)
RECORD_FAILURE = "日常任务奖励-记录-失败"
SCAN_FAILURE = "日常任务奖励-扫描-耗尽"
HOME_FAILURE = "日常任务奖励-主页边界-失败"


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_r20_home_failure_fans_out_all_resume_surfaces_as_siblings() -> None:
    nodes = load_task_nodes(DAILY)
    start = nodes[DAILY.entry]

    # r20 artifact:
    # mfw-android-all-20260809-r20-debug-daily-reward-r1
    # screenshot sha256:
    # 26f3978be2d6cd5d8b48c77791f5ebb5e0f6d1cfc7e64d1bdfe4a2a7bc99415a
    # The old graph exposed only MJA_DAILY_RESUME_REWARD_PROBE here, so Maa
    # retried that missing child for 20 seconds and never entered its on_error.
    assert start["next"] == [
        "日常任务奖励-恢复继续-奖励-探测",
        "日常任务奖励-页面-探测",
        "日常任务奖励-面板-探测",
        "日常任务奖励-主页-探测",
    ]
    assert start["on_error"] == [RECORD_FAILURE]
    assert nodes["日常任务奖励-恢复继续-奖励-探测"]["on_error"] == [
        RECORD_FAILURE
    ]
    assert not any(
        "启动-游戏启动" in target
        for name, node in nodes.items()
        if name.startswith("日常任务奖励-")
        for target in node.get("on_error", [])
    )


def test_r20_world_home_uses_exact_same_frame_boundary_and_narrow_panel_target() -> None:
    nodes = load_task_nodes(DAILY)

    # Fresh r20 OCR boxes from the archived 1280x720 world-home screenshot.
    observed = {
        "日常任务奖励-日常-主页-副本": [1057, 58, 36, 14],
        "日常任务奖励-日常-主页-试炼": [990, 643, 44, 22],
    }
    for name, box in observed.items():
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert _contains(node["roi"], box)
        assert node["roi"][2] * node["roi"][3] < 8_000

    assert nodes["日常任务奖励-日常-主页-副本"]["expected"] == "^副本$"
    assert nodes["日常任务奖励-日常-主页-试炼"]["expected"] == [
        "^试剑$",
        "^击破：\\d+(?:层)?$",
    ]
    assert nodes["日常任务奖励-日常-主页-页面"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["日常任务奖励-日常-主页-副本", "日常任务奖励-日常-主页-试炼"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    # The homepage entry is a shared color-recognition boundary. The open
    # panel itself is confirmed separately by OCR in the live function panel.
    panel = nodes["日常任务奖励-日常-主页-面板-打开"]
    assert panel == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏功能面板-入口"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    same_frame = ["日常任务奖励-日常-主页-页面", "日常任务奖励-日常-主页-面板-打开"]
    assert nodes["日常任务奖励-主页-探测"]["recognition"] == {
        "type": "And",
        "param": {"all_of": same_frame, "box_index": 0},
    }
    open_panel = nodes["日常任务奖励-打开-面板"]
    assert open_panel["recognition"] == {
        "type": "And",
        "param": {"all_of": same_frame, "box_index": 1},
    }
    assert open_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "日常任务奖励-日常-主页-页面",
        "target_name": "日常任务奖励-日常-主页-面板-打开",
    }


def test_live_panel_and_daily_page_boxes_are_exact_and_same_frame_bounded() -> None:
    nodes = load_task_nodes(DAILY)

    # The live function-panel batch OCR observed 日常 at [1072,291,44,28],
    # 商城 at [954,294,42,23], and 武学研习 at [715,415,73,22].
    observed = {
        "日常任务奖励-日常-入口": [1072, 291, 44, 28],
        "日常任务奖励-日常-面板-商店": [954, 294, 42, 23],
        "日常任务奖励-日常-面板-研习": [715, 415, 73, 22],
    }
    for name, box in observed.items():
        assert _contains(nodes[name]["roi"], box), name
    assert nodes["日常任务奖励-日常-入口"]["expected"] == "^日常$"
    assert nodes["日常任务奖励-日常-面板-页面"]["recognition"]["param"]["all_of"] == [
        "日常任务奖励-日常-面板-商店",
        "日常任务奖励-日常-面板-研习",
    ]
    assert nodes["日常任务奖励-打开-日常"]["recognition"]["param"] == {
        "all_of": ["日常任务奖励-日常-面板-页面", "日常任务奖励-日常-入口"],
        "box_index": 1,
    }

    # A prior live daily-page frame observed 日常任务 [93,29,81,23] and
    # vertical 活跃度 [329,98,29,64].  Require both, not OCR's OR-list form.
    assert _contains(nodes["日常任务奖励-日常-页面-标题"]["roi"], [93, 29, 81, 23])
    assert _contains(nodes["日常任务奖励-日常-页面-活动"]["roi"], [329, 98, 29, 64])
    assert nodes["日常任务奖励-日常-页面-标题"]["expected"] == "^日常任务$"
    assert nodes["日常任务奖励-日常-页面-活动"]["expected"] == "^活跃度$"
    assert nodes["日常任务奖励-日常-页面"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["日常任务奖励-日常-页面-标题", "日常任务奖励-日常-页面-活动"],
            "box_index": 0,
        },
    }


def test_page_decisions_are_explicit_siblings_and_scans_are_finite() -> None:
    nodes = load_task_nodes(DAILY)

    assert nodes["日常任务奖励-页面-探测"]["next"] == [
        "日常任务奖励-初始-行-探测",
        "日常任务奖励-初始-宝箱-探测",
        "日常任务奖励-初始-无-领取-探测",
        "日常任务奖励-奖励-扫描",
    ]
    assert nodes["日常任务奖励-奖励-页面-校验"]["next"] == [
        "日常任务奖励-变更-行-探测",
        "日常任务奖励-变更-宝箱-探测",
        "日常任务奖励-变更-无-领取-探测",
        "日常任务奖励-奖励-扫描-之后-变更",
    ]

    scans = {
        "日常任务奖励-奖励-扫描": (
            "日常任务奖励-页面-探测",
            [
                "日常任务奖励-初始-扫描-耗尽-探测",
                "日常任务奖励-初始-已领取-耗尽-探测",
                SCAN_FAILURE,
            ],
        ),
        "日常任务奖励-奖励-扫描-之后-变更": (
            "日常任务奖励-奖励-页面-校验",
            [
                "日常任务奖励-变更-扫描-耗尽-探测",
                "日常任务奖励-变更-已领取-耗尽-探测",
                SCAN_FAILURE,
            ],
        ),
    }
    for name, (next_node, exhausted) in scans.items():
        node = nodes[name]
        assert node["max_hit"] == 5
        assert node["retry_times"] == 0
        assert node["next"] == [next_node]
        assert node["on_error"] == exhausted


def test_claims_are_guarded_by_policy_caps_and_never_native_retried() -> None:
    nodes = load_task_nodes(DAILY)
    policy = TASK_POLICIES[DAILY.task_id]
    bounded = {
        "open_function_panel": 1,
        "open_daily_tasks": 1,
        "claim_completed_daily_row": 50,
        "scroll_daily_reward_rows": 5,
        "close_reward_popup": 60,
        "claim_unlocked_activity_chest": 10,
        "close_daily_tasks": 1,
        "close_function_panel": 1,
    }

    for action_id, cap in bounded.items():
        guarded = [
            node
            for node in guarded_nodes_for_action(nodes, action_id)
            if node["custom_action_param"].get("task_id") == DAILY.task_id
        ]
        assert guarded, action_id
        assert policy.action_caps[action_id] == cap
        assert all(node["max_hit"] == cap for node in guarded)
        assert all(node["retry_times"] == 0 for node in guarded)
        assert_no_side_effect_retry(nodes, action_id)

    for name in ("日常任务奖励-领取-行", "日常任务奖励-领取-宝箱"):
        assert nodes[name]["next"] == [
            "日常任务奖励-奖励-探测",
            "日常任务奖励-奖励-页面-校验",
        ]
    assert not any(
        node.get("action") in {"Click", "Swipe", "MultiSwipe", "Key", "Input"}
        for name, node in nodes.items()
        if name.startswith("日常任务奖励-")
    )


def test_success_outcomes_require_fresh_explicit_or_exhaustive_empty_state() -> None:
    nodes = load_task_nodes(DAILY)

    # A single visible 已领取 row is not enough for immediate completion.  It
    # becomes acceptable only after the bounded scan has exhausted the list.
    assert nodes["日常任务奖励-初始-无-领取-探测"]["recognition"]["param"] == {
        "all_of": ["日常任务奖励-日常-页面", "日常任务奖励-日常-无-可领取-全局"],
        "box_index": 1,
    }
    assert nodes["日常任务奖励-日常-无-可领取-全局"]["expected"] == [
        "^暂无可领取$",
        "^前往$",
    ]
    assert nodes["日常任务奖励-日常-已领取-行"]["expected"] == "^已领取$"

    none_predecessors = {
        name
        for name, node in nodes.items()
        if "日常任务奖励-奖励-无" in node.get("next", [])
    }
    assert none_predecessors == {
        "日常任务奖励-初始-无-领取-探测",
        "日常任务奖励-初始-扫描-耗尽-探测",
        "日常任务奖励-初始-已领取-耗尽-探测",
    }
    done_predecessors = {
        name
        for name, node in nodes.items()
        if "日常任务奖励-奖励-完成" in node.get("next", [])
    }
    assert done_predecessors == {
        "日常任务奖励-变更-无-领取-探测",
        "日常任务奖励-变更-扫描-耗尽-探测",
        "日常任务奖励-变更-已领取-耗尽-探测",
    }

    assert nodes["日常任务奖励-奖励-无"]["custom_action_param"] == {
        "task_id": DAILY.task_id,
        "status": "already_complete",
        "postcondition": "daily_reward.no_claimable",
    }
    assert nodes["日常任务奖励-奖励-完成"]["custom_action_param"] == {
        "task_id": DAILY.task_id,
        "status": "success",
        "postcondition": "daily_reward.no_claimable",
    }


def test_unknown_states_record_fresh_failed_then_native_abort() -> None:
    nodes = load_task_nodes(DAILY)
    expected = {
        RECORD_FAILURE: (
            "DAILY_REWARD_POSTCONDITION_MISSING",
            "DAILY_REWARD_POSTCONDITION_MISSING",
        ),
        SCAN_FAILURE: (
            "DAILY_REWARD_SCAN_EXHAUSTED",
            "DAILY_REWARD_SCAN_EXHAUSTED",
        ),
        HOME_FAILURE: ("home", "DAILY_REWARD_HOME_BOUNDARY_MISSING"),
    }
    for name, (postcondition, error_code) in expected.items():
        node = nodes[name]
        params = node["custom_action_param"]
        assert node["custom_action"] == "RecordTaskOutcome"
        assert params["task_id"] == DAILY.task_id
        assert params["status"] == "failed"
        assert params["postcondition"] == postcondition
        assert params["error_code"] == error_code
        assert params["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["公共-通用中止"]
        assert "on_error" not in node


def test_success_cleanup_requires_a_fresh_home_boundary() -> None:
    nodes = load_task_nodes(DAILY)
    close = nodes["日常任务奖励-关闭"]
    assert close["next"] == [
        "日常任务奖励-面板关闭后",
        "日常任务奖励-主页边界-探测",
    ]
    assert close["on_error"] == [HOME_FAILURE]
    assert close["retry_times"] == 0
    panel_after_close = nodes["日常任务奖励-面板关闭后"]
    assert panel_after_close["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["日常任务奖励-日常-面板-页面", "日常任务奖励-日常-面板-关闭"],
            "box_index": 0,
        },
    }
    assert panel_after_close["next"] == [
        "日常任务奖励-关闭-面板",
        "日常任务奖励-主页边界-探测",
    ]
    close_panel = nodes["日常任务奖励-关闭-面板"]
    assert close_panel["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["日常任务奖励-日常-面板-页面", "日常任务奖励-日常-面板-关闭"],
            "box_index": 1,
        },
    }
    assert close_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "日常任务奖励-日常-面板-页面",
        "target_name": "日常任务奖励-日常-面板-关闭",
    }
    assert close_panel["next"] == ["日常任务奖励-主页边界-探测"]
    assert close_panel["on_error"] == [HOME_FAILURE]
    assert close_panel["retry_times"] == 0
    assert nodes["日常任务奖励-主页边界-探测"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["日常任务奖励-日常-主页-页面"]},
    }
    assert nodes["日常任务奖励-主页边界-探测"]["next"] == [
        "公共-通用停止",
        "[JumpBack]启动-游戏启动",
    ]
    assert nodes["日常任务奖励-主页边界-探测"]["on_error"] == [HOME_FAILURE]
