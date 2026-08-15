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
RECORD_FAILURE = "MJA_DAILY_RECORD_FAILURE"
SCAN_FAILURE = "MJA_DAILY_SCAN_EXHAUSTED"
HOME_FAILURE = "MJA_DAILY_HOME_BOUNDARY_FAILURE"


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
        "MJA_DAILY_RESUME_REWARD_PROBE",
        "MJA_DAILY_PAGE_PROBE",
        "MJA_DAILY_PANEL_PROBE",
        "MJA_DAILY_HOME_PROBE",
    ]
    assert start["on_error"] == [RECORD_FAILURE]
    assert nodes["MJA_DAILY_RESUME_REWARD_PROBE"]["on_error"] == [
        RECORD_FAILURE
    ]
    assert not any(
        "MJA_GAME_START" in target
        for name, node in nodes.items()
        if name.startswith("MJA_DAILY_")
        for target in node.get("on_error", [])
    )


def test_r20_world_home_uses_exact_same_frame_boundary_and_narrow_panel_target() -> None:
    nodes = load_task_nodes(DAILY)

    # Fresh r20 OCR boxes from the archived 1280x720 world-home screenshot.
    observed = {
        "daily.home.dungeon": [1057, 58, 36, 14],
        "daily.home.trial": [990, 643, 44, 22],
    }
    for name, box in observed.items():
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert _contains(node["roi"], box)
        assert node["roi"][2] * node["roi"][3] < 8_000

    assert nodes["daily.home.dungeon"]["expected"] == "^副本$"
    assert nodes["daily.home.trial"]["expected"] == [
        "^试剑$",
        "^击破：\\d+(?:层)?$",
    ]
    assert nodes["daily.home.page"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["daily.home.dungeon", "daily.home.trial"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    # The homepage entry is a shared color-recognition boundary. The open
    # panel itself is confirmed separately by OCR in the live function panel.
    panel = nodes["daily.home.panel_open"]
    assert panel == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_FUNCTION_PANEL_ENTRY"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    same_frame = ["daily.home.page", "daily.home.panel_open"]
    assert nodes["MJA_DAILY_HOME_PROBE"]["recognition"] == {
        "type": "And",
        "param": {"all_of": same_frame, "box_index": 0},
    }
    open_panel = nodes["MJA_DAILY_OPEN_PANEL"]
    assert open_panel["recognition"] == {
        "type": "And",
        "param": {"all_of": same_frame, "box_index": 1},
    }
    assert open_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "daily.home.page",
        "target_name": "daily.home.panel_open",
    }


def test_live_panel_and_daily_page_boxes_are_exact_and_same_frame_bounded() -> None:
    nodes = load_task_nodes(DAILY)

    # The live function-panel batch OCR observed 日常 at [1072,291,44,28],
    # 商城 at [954,294,42,23], and 武学研习 at [715,415,73,22].
    observed = {
        "daily.entry": [1072, 291, 44, 28],
        "daily.panel.shop": [954, 294, 42, 23],
        "daily.panel.study": [715, 415, 73, 22],
    }
    for name, box in observed.items():
        assert _contains(nodes[name]["roi"], box), name
    assert nodes["daily.entry"]["expected"] == "^日常$"
    assert nodes["daily.panel.page"]["recognition"]["param"]["all_of"] == [
        "daily.panel.shop",
        "daily.panel.study",
    ]
    assert nodes["MJA_DAILY_OPEN_DAILY"]["recognition"]["param"] == {
        "all_of": ["daily.panel.page", "daily.entry"],
        "box_index": 1,
    }

    # A prior live daily-page frame observed 日常任务 [93,29,81,23] and
    # vertical 活跃度 [329,98,29,64].  Require both, not OCR's OR-list form.
    assert _contains(nodes["daily.page.title"]["roi"], [93, 29, 81, 23])
    assert _contains(nodes["daily.page.activity"]["roi"], [329, 98, 29, 64])
    assert nodes["daily.page.title"]["expected"] == "^日常任务$"
    assert nodes["daily.page.activity"]["expected"] == "^活跃度$"
    assert nodes["daily.page"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["daily.page.title", "daily.page.activity"],
            "box_index": 0,
        },
    }


def test_page_decisions_are_explicit_siblings_and_scans_are_finite() -> None:
    nodes = load_task_nodes(DAILY)

    assert nodes["MJA_DAILY_PAGE_PROBE"]["next"] == [
        "MJA_DAILY_INITIAL_ROW_PROBE",
        "MJA_DAILY_INITIAL_CHEST_PROBE",
        "MJA_DAILY_INITIAL_NO_CLAIM_PROBE",
        "MJA_DAILY_REWARD_SCAN",
    ]
    assert nodes["MJA_DAILY_REWARD_PAGE_VERIFY"]["next"] == [
        "MJA_DAILY_MUTATION_ROW_PROBE",
        "MJA_DAILY_MUTATION_CHEST_PROBE",
        "MJA_DAILY_MUTATION_NO_CLAIM_PROBE",
        "MJA_DAILY_REWARD_SCAN_AFTER_MUTATION",
    ]

    scans = {
        "MJA_DAILY_REWARD_SCAN": (
            "MJA_DAILY_PAGE_PROBE",
            [
                "MJA_DAILY_INITIAL_SCAN_EXHAUSTED_PROBE",
                "MJA_DAILY_INITIAL_CLAIMED_EXHAUSTED_PROBE",
                SCAN_FAILURE,
            ],
        ),
        "MJA_DAILY_REWARD_SCAN_AFTER_MUTATION": (
            "MJA_DAILY_REWARD_PAGE_VERIFY",
            [
                "MJA_DAILY_MUTATION_SCAN_EXHAUSTED_PROBE",
                "MJA_DAILY_MUTATION_CLAIMED_EXHAUSTED_PROBE",
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

    for name in ("MJA_DAILY_CLAIM_ROW", "MJA_DAILY_CLAIM_CHEST"):
        assert nodes[name]["next"] == [
            "MJA_DAILY_REWARD_PROBE",
            "MJA_DAILY_REWARD_PAGE_VERIFY",
        ]
    assert not any(
        node.get("action") in {"Click", "Swipe", "MultiSwipe", "Key", "Input"}
        for name, node in nodes.items()
        if name.startswith("MJA_DAILY_")
    )


def test_success_outcomes_require_fresh_explicit_or_exhaustive_empty_state() -> None:
    nodes = load_task_nodes(DAILY)

    # A single visible 已领取 row is not enough for immediate completion.  It
    # becomes acceptable only after the bounded scan has exhausted the list.
    assert nodes["MJA_DAILY_INITIAL_NO_CLAIM_PROBE"]["recognition"]["param"] == {
        "all_of": ["daily.page", "daily.no_claimable_global"],
        "box_index": 1,
    }
    assert nodes["daily.no_claimable_global"]["expected"] == [
        "^暂无可领取$",
        "^前往$",
    ]
    assert nodes["daily.claimed_row"]["expected"] == "^已领取$"

    none_predecessors = {
        name
        for name, node in nodes.items()
        if "MJA_DAILY_REWARD_NONE" in node.get("next", [])
    }
    assert none_predecessors == {
        "MJA_DAILY_INITIAL_NO_CLAIM_PROBE",
        "MJA_DAILY_INITIAL_SCAN_EXHAUSTED_PROBE",
        "MJA_DAILY_INITIAL_CLAIMED_EXHAUSTED_PROBE",
    }
    done_predecessors = {
        name
        for name, node in nodes.items()
        if "MJA_DAILY_REWARD_DONE" in node.get("next", [])
    }
    assert done_predecessors == {
        "MJA_DAILY_MUTATION_NO_CLAIM_PROBE",
        "MJA_DAILY_MUTATION_SCAN_EXHAUSTED_PROBE",
        "MJA_DAILY_MUTATION_CLAIMED_EXHAUSTED_PROBE",
    }

    assert nodes["MJA_DAILY_REWARD_NONE"]["custom_action_param"] == {
        "task_id": DAILY.task_id,
        "status": "already_complete",
        "postcondition": "daily_reward.no_claimable",
    }
    assert nodes["MJA_DAILY_REWARD_DONE"]["custom_action_param"] == {
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
        assert node["next"] == ["MJA_COMMON_ABORT"]
        assert "on_error" not in node


def test_success_cleanup_requires_a_fresh_home_boundary() -> None:
    nodes = load_task_nodes(DAILY)
    close = nodes["MJA_DAILY_CLOSE"]
    assert close["next"] == [
        "MJA_DAILY_PANEL_AFTER_CLOSE",
        "MJA_DAILY_HOME_BOUNDARY_PROBE",
    ]
    assert close["on_error"] == [HOME_FAILURE]
    assert close["retry_times"] == 0
    panel_after_close = nodes["MJA_DAILY_PANEL_AFTER_CLOSE"]
    assert panel_after_close["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["daily.panel.page", "daily.panel.close"],
            "box_index": 0,
        },
    }
    assert panel_after_close["next"] == [
        "MJA_DAILY_CLOSE_PANEL",
        "MJA_DAILY_HOME_BOUNDARY_PROBE",
    ]
    close_panel = nodes["MJA_DAILY_CLOSE_PANEL"]
    assert close_panel["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["daily.panel.page", "daily.panel.close"],
            "box_index": 1,
        },
    }
    assert close_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "daily.panel.page",
        "target_name": "daily.panel.close",
    }
    assert close_panel["next"] == ["MJA_DAILY_HOME_BOUNDARY_PROBE"]
    assert close_panel["on_error"] == [HOME_FAILURE]
    assert close_panel["retry_times"] == 0
    assert nodes["MJA_DAILY_HOME_BOUNDARY_PROBE"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["daily.home.page"]},
    }
    assert nodes["MJA_DAILY_HOME_BOUNDARY_PROBE"]["next"] == [
        "MJA_COMMON_STOP",
        "[JumpBack]MJA_GAME_START",
    ]
    assert nodes["MJA_DAILY_HOME_BOUNDARY_PROBE"]["on_error"] == [HOME_FAILURE]
