from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    guarded_nodes_for_action,
    load_task_nodes,
)

HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_r19_home_archive_drives_narrow_exact_roi_contract() -> None:
    nodes = load_task_nodes(HERO)

    # Fresh r17 MFW OCR on the stable world-home renderer.  The painting
    # entry is the top-left 画卷 control; the old ROI [1095, 45, 85, 40]
    # pointed at the unrelated upper-right HUD and produced no match.
    observed = {
        "hero.home.dungeon": [1060, 60, 29, 11],
        "painting_scroll.entry": [91, 27, 46, 27],
        "hero.home.trial": [990, 643, 44, 22],
    }
    expected = {
        "hero.home.dungeon": "^副本$",
        "painting_scroll.entry": "^画卷$",
        "hero.home.trial": "^试剑$",
    }

    for name, box in observed.items():
        node = nodes[name]
        roi = node["roi"]
        assert node["recognition"] == "OCR"
        assert node["expected"] == expected[name]
        assert _contains(roi, box)
        if name != "painting_scroll.entry":
            assert roi[0] >= 900
        assert roi[2] * roi[3] < FRAME_WIDTH * FRAME_HEIGHT // 100

    assert nodes["painting_scroll.entry"]["roi"] == [70, 10, 95, 60]
    assert nodes["painting_scroll.entry"]["roi"] != [850, 0, 430, 180]


def test_home_entry_requires_same_frame_world_boundary_and_exact_target() -> None:
    nodes = load_task_nodes(HERO)

    home_page = nodes["hero.home.page"]
    assert home_page == {
        "recognition": {
            "type": "And",
            "param": {"all_of": ["MJA_GAME_HOME_PAGE"]},
        },
        "action": "DoNothing",
    }

    # The first route must be a cheap page probe.  OCR candidates are entered
    # one at a time through on_error, so a stale batch frame cannot decide the
    # page state before the home boundary is checked.
    assert nodes["MJA_HERO_DISPATCH_DAILY_START"]["next"] == [
        "MJA_HERO_HOME_PROBE"
    ]
    assert nodes["MJA_HERO_HOME_PROBE"]["next"] == [
        "MJA_HERO_OPEN_PAINTING",
        "MJA_HERO_OPEN_PAINTING_WORLD",
    ]
    assert nodes["MJA_HERO_HOME_PROBE"]["on_error"] == [
        "MJA_HERO_RESUME_REWARD_PROBE"
    ]

    for probe_name in ("MJA_HERO_HOME_PROBE", "MJA_HERO_HOME_BOUNDARY_PROBE"):
        probe = nodes[probe_name]
        assert probe["recognition"] == {
            "type": "And",
            "param": {"all_of": ["hero.home.page"]},
        }

    open_node = nodes["MJA_HERO_OPEN_PAINTING"]
    assert open_node["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["hero.home.page", "painting_scroll.entry"],
            "box_index": 1,
        },
    }
    assert open_node["action"] == "Custom"
    assert open_node["custom_action"] == "GuardedInput"
    assert open_node["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "hero.home.page",
        "target_name": "painting_scroll.entry",
    }
    assert open_node["max_hit"] == 1
    assert open_node["retry_times"] == 0
    assert TASK_POLICIES[HERO.task_id].action_caps["open_painting_scroll"] == 1

    world_open = nodes["MJA_HERO_OPEN_PAINTING_WORLD"]
    assert world_open["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["hero.home.page", "painting_scroll.entry.world"],
            "box_index": 1,
        },
    }
    assert world_open["custom_action_param"]["evidence"]["target_name"] == (
        "painting_scroll.entry.world"
    )
    assert nodes["painting_scroll.entry.world"] == {
        "recognition": "OCR",
        "expected": "^画卷$",
        "roi": [1080, 0, 200, 120],
        "action": "DoNothing",
    }


def test_start_routes_home_before_ocr_resume_states_and_fails_truthfully() -> None:
    nodes = load_task_nodes(HERO)
    start = nodes[HERO.entry]

    # The bounded game-start recovery is allowed once before the task fails
    # truthfully.  The home boundary is checked before any OCR candidate so
    # one stale batch frame cannot select a page route.
    assert start["next"] == ["MJA_HERO_HOME_PROBE"]
    assert start["on_error"] == [
        "MJA_HERO_GAME_START_RECOVERY",
        "MJA_HERO_RECORD_FAILURE",
    ]
    assert nodes["MJA_HERO_HOME_PROBE"]["on_error"] == [
        "MJA_HERO_RESUME_REWARD_PROBE"
    ]
    assert nodes["MJA_HERO_RESUME_REWARD_PROBE"]["on_error"] == [
        "MJA_HERO_DISPATCH_PAGE_PROBE"
    ]
    assert nodes["MJA_HERO_DISPATCH_PAGE_PROBE"]["on_error"] == [
        "MJA_HERO_OPEN_DISPATCH"
    ]

    failure_nodes = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id") == HERO.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert set(failure_nodes) == {
        "MJA_DISPATCH_FILL_LOOP_EXHAUSTED",
        "MJA_DISPATCH_CLAIM_LOOP_EXHAUSTED",
        "MJA_HERO_RECORD_FAILURE",
        "MJA_HERO_BOUNDARY_FAILURE",
    }
    for node in failure_nodes.values():
        assert node["custom_action_param"]["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["MJA_COMMON_ABORT"]


def test_empty_dispatch_state_requires_same_frame_zero_counters_and_blank_selection() -> None:
    nodes = load_task_nodes(HERO)

    marker = nodes["hero.no_dispatch_tasks"]
    assert marker["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "hero.dispatch.page",
                "hero.zero_dispatch_tasks",
                "hero.zero_completed_dispatches",
                "hero.no_selected_dispatch_task",
            ],
            "box_index": 1,
        },
    }
    assert nodes["hero.zero_dispatch_tasks"]["expected"] == r"^任务\s*[:：]?\s*0\s*/\s*9$"
    assert nodes["hero.zero_completed_dispatches"]["expected"] == r"^已完成\s*[:：]?\s*0$"
    assert nodes["hero.no_selected_dispatch_task"]["expected"] == "尚未选择派遣任务"
    assert nodes["hero.no_selected_dispatch_task"]["roi"] == [930, 250, 340, 220]

    for probe_name in ("MJA_HERO_INITIAL_NO_TASKS", "MJA_HERO_POST_NO_TASKS"):
        probe = nodes[probe_name]
        assert probe["recognition"]["param"]["all_of"] == [
            "hero.dispatch.page",
            "hero.no_dispatch_tasks",
        ]
        assert probe["next"] == ["MJA_HERO_SUCCESS_NO_TASKS"]

    outcome = nodes["MJA_HERO_SUCCESS_NO_TASKS"]
    assert outcome["custom_action_param"] == {
        "task_id": HERO.task_id,
        "status": "success",
        "postcondition": "hero.no_dispatch_tasks",
    }


def test_dispatch_side_effect_nodes_cannot_replay_one_observation() -> None:
    nodes = load_task_nodes(HERO)

    for action_id in (
        "claim_first_dispatch",
        "smart_configure_team",
        "dispatch_team",
    ):
        assert_no_side_effect_retry(nodes, action_id)
        matches = guarded_nodes_for_action(nodes, action_id)
        assert matches
        for node in matches:
            assert node.get("repeat", 1) == 1
            assert node.get("retry_times", 0) == 0
            assert node["on_error"] == ["MJA_HERO_RECORD_FAILURE"]


def test_success_and_already_complete_follow_fresh_visual_postconditions() -> None:
    nodes = load_task_nodes(HERO)
    contracts = {
        "MJA_HERO_ALREADY_ALL": (
            "already_complete",
            "hero.all_completed",
            "MJA_HERO_INITIAL_ALL",
        ),
        "MJA_HERO_ALREADY_PROGRESS": (
            "already_complete",
            "hero.first_task_in_progress",
            "MJA_HERO_INITIAL_PROGRESS",
        ),
        "MJA_HERO_SUCCESS_ALL": (
            "success",
            "hero.all_completed",
            "MJA_HERO_POST_ALL",
        ),
        "MJA_HERO_SUCCESS_PROGRESS": (
            "success",
            "hero.first_task_in_progress",
            "MJA_HERO_POST_PROGRESS",
        ),
        "MJA_HERO_SUCCESS_NO_TASKS": (
            "success",
            "hero.no_dispatch_tasks",
            "MJA_HERO_POST_NO_TASKS",
        ),
    }

    for outcome_name, (status, marker, visual_probe_name) in contracts.items():
        outcome = nodes[outcome_name]
        params = outcome["custom_action_param"]
        assert outcome["recognition"] == "DirectHit"
        assert outcome["custom_action"] == "RecordTaskOutcome"
        assert params["status"] == status
        assert params["postcondition"] == marker

        visual_probe = nodes[visual_probe_name]
        assert visual_probe["recognition"]["type"] == "And"
        assert marker in visual_probe["recognition"]["param"]["all_of"]
        assert visual_probe["next"] == [outcome_name]


def test_reward_popup_uses_live_blank_click_marker_for_probe_and_guarded_close() -> None:
    nodes = load_task_nodes(HERO)
    popup_roi = [350, 580, 600, 140]

    for name in ("MJA_HERO_CLAIM_REWARD_PROBE", "hero.reward_popup", "hero.reward_popup_close"):
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert node["expected"] == "点击空白处关闭"
        assert node["roi"] == popup_roi

    for name in ("MJA_HERO_CLOSE_REWARD", "MJA_HERO_RESUME_CLOSE_REWARD"):
        node = nodes[name]
        assert node["recognition"] == {
            "type": "And",
            "param": {
                "all_of": ["hero.reward_popup", "hero.reward_popup_close"],
                "box_index": 1,
            },
        }
        assert node["custom_action"] == "GuardedInput"
        assert node["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": "hero.reward_popup",
            "target_name": "hero.reward_popup_close",
        }

    assert nodes["MJA_HERO_CLOSE_REWARD"]["max_hit"] == 6
    assert nodes["MJA_HERO_RESUME_CLOSE_REWARD"]["max_hit"] == 1
    assert nodes["MJA_HERO_CLAIM_REWARD_PROBE"]["on_error"] == [
        "MJA_HERO_CLAIM_VERIFY",
        "MJA_HERO_RECORD_FAILURE",
    ]


def test_claim_postconditions_are_ordered_next_alternatives() -> None:
    nodes = load_task_nodes(HERO)

    assert nodes["MJA_HERO_CLAIM_VERIFY"]["next"] == [
        "MJA_DISPATCH_CLAIM_PROBE",
        "MJA_DISPATCH_FILL_LOOP",
    ]
    assert nodes["MJA_HERO_SEND"]["next"] == [
        "MJA_DISPATCH_CLAIM_PROBE",
        "MJA_DISPATCH_FILL_LOOP",
    ]
    assert nodes["MJA_DISPATCH_FILL_LOOP"]["next"] == [
        "MJA_HERO_POST_ALL",
        "MJA_HERO_POST_PROGRESS",
        "MJA_HERO_POST_NO_TASKS",
        "MJA_HERO_POST_SELECT",
    ]

    # The claim loop is a native MAA loop: its body nodes must be allowed to
    # recur.  A max_hit of one here would make the third claim wait until the
    # parent timeout and report HERO_CLAIM_LOOP_EXHAUSTED even though the page
    # remains visibly claimable.
    for name in (
        "MJA_HERO_POST_CLAIM_SELECT",
        "MJA_HERO_POST_CLAIM_BUTTON",
        "MJA_HERO_POST_CLAIM",
    ):
        assert nodes[name]["max_hit"] == 6

    assert nodes["hero.first_task_in_progress"]["expected"][-1] == (
        r"^\d{1,2}:\d{2}:\d{2}$"
    )
