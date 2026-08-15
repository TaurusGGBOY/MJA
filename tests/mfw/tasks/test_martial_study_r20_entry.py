from __future__ import annotations

from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, load_task_nodes

MARTIAL = TaskContract(
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "daily/martial_study_breakthrough_daily.json",
)
ROOT = Path(__file__).parents[3]
RECORD_FAILURE = "MJA_MARTIAL_RECORD_FAILURE"


def test_r20_start_routes_resume_and_launcher_recovery_as_siblings() -> None:
    nodes = load_task_nodes(MARTIAL)
    start = nodes["MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_START"]

    # In MaaFramework a child's on_error is not used when a next-list child
    # never matched. The final full regression therefore repeated the entry
    # Probes after SPEND can leave the game on another page. Recovery must be
    # visible from the entry next list, reuse shared startup, and fail closed.
    assert start["next"] == [
        "[JumpBack]MJA_KNOWN_TEA_DETAIL_CLOSE",
        "[JumpBack]MJA_KNOWN_TEA_SHOP_CLOSE",
        "MJA_MARTIAL_PAGE_PROBE",
        "MJA_MARTIAL_OPEN_STUDY",
        "MJA_MARTIAL_OPEN_PANEL",
        "MJA_MARTIAL_GAME_START_RECOVERY",
    ]
    assert start["timeout"] == 8000
    assert start["on_error"] == [
        "MJA_MARTIAL_GAME_START_RECOVERY",
        RECORD_FAILURE,
    ]
    assert start["retry_times"] == 0
    assert "MJA_MARTIAL_HOME_PROBE" not in nodes
    assert any(
        target == "[JumpBack]MJA_GAME_START"
        for name, node in nodes.items()
        if name.startswith("MJA_MARTIAL_")
        for target in node.get("next", [])
    )

    recovery = nodes["MJA_MARTIAL_GAME_START_RECOVERY"]
    assert recovery["max_hit"] == 1
    assert recovery["action"] == "DoNothing"
    assert recovery["retry_times"] == 0
    assert recovery["next"] == ["MJA_MARTIAL_RECOVERY_STATE_PROBE"]
    assert recovery["on_error"] == ["MJA_MARTIAL_GAME_START_RECOVERY_FAILED"]

    state_probe = nodes["MJA_MARTIAL_RECOVERY_STATE_PROBE"]
    assert state_probe["recognition"] == "DirectHit"
    assert state_probe["action"] == "DoNothing"
    assert state_probe["timeout"] == 30000
    assert state_probe["next"] == [
        "MJA_MARTIAL_PAGE_PROBE",
        "MJA_MARTIAL_OPEN_STUDY",
        "MJA_MARTIAL_OPEN_PANEL",
        "[JumpBack]MJA_GAME_START",
    ]
    assert state_probe["on_error"] == ["MJA_MARTIAL_GAME_START_RECOVERY_FAILED"]

    recovery_failed = nodes["MJA_MARTIAL_GAME_START_RECOVERY_FAILED"]
    assert recovery_failed["custom_action_param"] == {
        "task_id": "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "status": "failed",
        "error_code": "MARTIAL_GAME_START_RECOVERY_EXHAUSTED",
        "postcondition": "martial.game_foreground_or_recoverable_state",
        "native_fail_after_record": True,
    }
    assert recovery_failed["Abort"] is True
    assert recovery_failed["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in recovery_failed


def test_r20_function_panel_entry_uses_stable_text_not_background_color() -> None:
    nodes = load_task_nodes(MARTIAL)
    home = nodes["martial.home"]
    panel = nodes["martial.panel.open"]
    panel_entry = nodes["MJA_GAME_FUNCTION_PANEL_ENTRY"]

    # The home boundary remains template-backed, while the function-panel
    # entry is text-backed so its recognition does not depend on the changing
    # game background behind the icon.
    archived_home_score = 0.825888
    assert archived_home_score > home["threshold"] == 0.75
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
    assert panel_entry == {
        "recognition": "OCR",
        "expected": "^画[卷券]$",
        "roi": [1080, 0, 200, 120],
        "action": "DoNothing",
    }


def test_r20_panel_action_is_same_frame_guarded_and_capped_once() -> None:
    nodes = load_task_nodes(MARTIAL)
    open_panel = nodes["MJA_MARTIAL_OPEN_PANEL"]

    assert open_panel["recognition"]["param"] == {
        "all_of": ["martial.home", "martial.panel.open"],
        "box_index": 1,
    }
    assert open_panel["custom_action"] == "GuardedInput"
    assert open_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "martial.home",
        "target_name": "martial.panel.open",
    }
    assert open_panel["max_hit"] == 1
    assert open_panel["retry_times"] == 0
    assert open_panel["timeout"] == 8000
    assert TASK_POLICIES[MARTIAL.task_id].action_caps["open_function_panel"] == 1

    assert nodes["martial.entry"]["roi"] == [650, 120, 600, 560]
    # After closing the study result popup, the same page can render the
    # "武学研习" tab below y=220. Keep the ROI bounded but cover both layouts.
    assert nodes["martial.page"]["roi"] == [0, 0, 500, 420]
    assert nodes["martial.entry"]["roi"] != [0, 0, 1280, 720]
    assert nodes["martial.page"]["roi"] != [0, 0, 1280, 720]


def test_martial_probes_are_bounded_and_fail_closed() -> None:
    nodes = load_task_nodes(MARTIAL)
    bounded = (
        "MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_START",
        "MJA_MARTIAL_OPEN_PANEL",
        "MJA_MARTIAL_PANEL_PROBE",
        "MJA_MARTIAL_OPEN_STUDY",
        "MJA_MARTIAL_PAGE_PROBE",
        "MJA_MARTIAL_CLAIM_GATE",
        "MJA_MARTIAL_CLAIM_LOOP",
        "MJA_MARTIAL_CLAIM_RESULT",
        "MJA_MARTIAL_CLOSE_REWARD",
        "MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH",
        "MJA_MARTIAL_CLOSE_PAGE_FOR_SUCCESS",
        "MJA_MARTIAL_FINAL_PANEL_PROBE",
        "MJA_MARTIAL_SUCCESS_NO_CLAIM",
    )
    for name in bounded:
        node = nodes[name]
        assert node["timeout"] == 8000, name
        assert node["on_error"], name
        assert "MJA_MARTIAL_SUCCESS" not in node["on_error"], name

    page = nodes["MJA_MARTIAL_PAGE_PROBE"]
    assert page["next"] == [
        "MJA_MARTIAL_CLAIM_GATE",
        "MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH",
    ]
    assert nodes["MJA_MARTIAL_CLOSE_REWARD"]["next"] == [
        "MJA_MARTIAL_PAGE_PROBE"
    ]
    assert nodes["MJA_MARTIAL_NO_SUCCESSFUL_BREAKTHROUGH"]["next"] == [
        "MJA_MARTIAL_CLOSE_PAGE_FOR_SUCCESS"
    ]


def test_martial_slot_terminal_signals_match_the_live_card_surface() -> None:
    nodes = load_task_nodes(MARTIAL)

    success = nodes["martial.success_card"]
    assert success == {
        "recognition": "TemplateMatch",
        "template": "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success.png",
        "roi": [760, 350, 500, 330],
        "threshold": 0.36,
        "action": "DoNothing",
    }

    assert nodes["martial.result.close"]["expected"] == [
        "点击空白处关闭",
        "点击任意空白区域关闭",
    ]


def test_all_martial_failures_persist_then_fail_native() -> None:
    nodes = load_task_nodes(MARTIAL)
    failure_nodes = {
        name: node
        for name, node in nodes.items()
        if name.startswith("MJA_MARTIAL_")
        and node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert set(failure_nodes) == {
        "MJA_MARTIAL_GAME_START_RECOVERY_FAILED",
        "MJA_MARTIAL_CLAIM_LOOP_EXHAUSTED",
        RECORD_FAILURE,
    }
    for name, node in failure_nodes.items():
        assert node["custom_action_param"]["native_fail_after_record"] is True, name
        assert node["Abort"] is True, name
        assert node["next"] == ["MJA_COMMON_ABORT"], name
        assert "on_error" not in node, name

    successful_no_claim = nodes["MJA_MARTIAL_SUCCESS_NO_CLAIM"]
    assert successful_no_claim["custom_action_param"] == {
        "task_id": MARTIAL.task_id,
        "status": "success",
            "postcondition": "martial.successful_breakthroughs_claimed_or_none",
    }
    assert successful_no_claim["on_error"] == [RECORD_FAILURE]


def test_martial_side_effect_limits_are_claim_only() -> None:
    nodes = load_task_nodes(MARTIAL)
    policy = TASK_POLICIES[MARTIAL.task_id]
    expected_limits = {
        "open_function_panel": 1,
        "open_martial_study": 1,
        "claim_success_card": 3,
        "close_reward_popup": 3,
        "close_martial_page": 1,
    }
    assert dict(policy.action_caps) == expected_limits
    assert policy.risk_levels == frozenset({"stateful"})
    assert nodes["MJA_MARTIAL_CLAIM_LOOP"]["max_hit"] == 3
    assert nodes["MJA_MARTIAL_CLOSE_REWARD"]["custom_action_param"]["action_id"] == (
        "close_reward_popup"
    )
    assert nodes["MJA_MARTIAL_CLOSE_PAGE_FOR_SUCCESS"]["custom_action_param"][
        "action_id"
    ] == "close_martial_page"
    assert not any(
        "martial.success.result" in node.get("recognition", {}).get("param", {}).get(
            "all_of", []
        )
        for node in nodes.values()
        if isinstance(node.get("recognition"), dict)
    )
