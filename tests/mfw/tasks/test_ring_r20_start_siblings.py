from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, assert_outcome, load_task_nodes


RING = TaskContract("RING_CHALLENGE_DAILY", "daily/ring_challenge_daily.json")
FAILURE = "MJA_RING_RECORD_FAILURE"
STARTUP_FAILURE = "MJA_RING_GAME_START_RECOVERY_FAILED"


def _contains(roi: list[int], box: list[int]) -> bool:
    x, y, width, height = roi
    box_x, box_y, box_width, box_height = box
    return (
        x <= box_x
        and y <= box_y
        and x + width >= box_x + box_width
        and y + height >= box_y + box_height
    )


def test_r20_start_recovers_once_through_shared_startup() -> None:
    nodes = load_task_nodes(RING)
    start = nodes["MJA_RING_CHALLENGE_DAILY_START"]

    assert start["timeout"] == 8000
    assert start["next"] == [
        "MJA_RING_PAGE_PROBE",
        "MJA_RING_DAILY_PAGE",
        "MJA_RING_PANEL_PROBE",
        "MJA_RING_HOME_PROBE",
    ]
    assert start["on_error"] == ["MJA_RING_GAME_START_RECOVERY", STARTUP_FAILURE]
    assert "JumpBack" not in str(start)

    recovery = nodes["MJA_RING_GAME_START_RECOVERY"]
    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "DoNothing"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["next"] == ["MJA_RING_RECOVERY_STATE_PROBE"]
    assert recovery["on_error"] == [STARTUP_FAILURE]

    state = nodes["MJA_RING_RECOVERY_STATE_PROBE"]
    assert state["recognition"] == "DirectHit"
    assert state["action"] == "DoNothing"
    assert state["timeout"] == 30000
    assert state["next"] == [
        "MJA_RING_PAGE_PROBE",
        "MJA_RING_DAILY_PAGE",
        "MJA_RING_PANEL_PROBE",
        "MJA_RING_HOME_PROBE",
        "[JumpBack]MJA_GAME_START",
    ]
    assert state["on_error"] == [STARTUP_FAILURE]
    assert "[JumpBack]MJA_GAME_START" in state["next"]
    assert "[JumpBack]MJA_GAME_START" not in recovery["next"]

    assert_outcome(
        nodes,
        STARTUP_FAILURE,
        "failed",
        "ring.game_foreground_or_recoverable_state",
    )
    failed = nodes[STARTUP_FAILURE]
    assert failed["custom_action_param"]["error_code"] == (
        "RING_GAME_START_RECOVERY_EXHAUSTED"
    )
    assert failed["custom_action_param"]["native_fail_after_record"] is True
    assert failed["Abort"] is True
    assert failed["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failed

    assert not any(
        name.startswith("MJA_RING_") and node.get("action") == "StartApp"
        for name, node in nodes.items()
    )

    for name in (
        "MJA_RING_HOME_PROBE",
        "MJA_RING_OPEN_PANEL",
        "MJA_RING_PANEL_PROBE",
        "MJA_RING_OPEN_DAILY",
        "MJA_RING_DAILY_PAGE",
        "MJA_RING_PAGE_PROBE",
    ):
        node = nodes[name]
        assert 0 < node["timeout"] <= 8000, name
        assert node["on_error"] == [FAILURE], name


def test_r20_panel_entry_uses_stable_shared_color_recognition() -> None:
    nodes = load_task_nodes(RING)
    target = nodes["ring.panel.open"]

    assert target == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_FUNCTION_PANEL_ENTRY"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    opener = nodes["MJA_RING_OPEN_PANEL"]
    assert opener["recognition"]["param"] == {
        "all_of": ["ring.home", "ring.panel.open"],
        "box_index": 1,
    }
    assert opener["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "ring.home",
        "target_name": "ring.panel.open",
    }
    assert opener["max_hit"] == 1
    assert opener["retry_times"] == 0


def test_r20_every_guarded_action_has_pipeline_and_policy_caps() -> None:
    nodes = load_task_nodes(RING)
    policy_caps = TASK_POLICIES[RING.task_id].action_caps
    guarded = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == RING.task_id
    }

    assert guarded
    for name, node in guarded.items():
        action_id = node["custom_action_param"]["action_id"]
        assert action_id in policy_caps, name
        assert node["retry_times"] == 0, name
        assert 0 < node["max_hit"] <= policy_caps[action_id], name
        assert node["on_error"], name


def test_r20_resource_indices_are_same_frame_and_dynamic_positive() -> None:
    nodes = load_task_nodes(RING)

    for name in (
        "MJA_RING_SWEEP",
        "MJA_RING_CONFIRM_SWEEP",
        "MJA_RING_START_MATCHING",
        "MJA_RING_FIGHT_LOOP",
    ):
        node = nodes[name]
        params = node["custom_action_param"]
        all_of = node["recognition"]["param"]["all_of"]
        assert all_of[params["resource_index"]] == "擂台券", name
        assert params["resource_evidence_name"] == "擂台券", name
        assert all_of[params["amount_index"]] == "ring.ticket.amount", name
        assert "observed_amount" not in params, name
        assert params["budget_amount"] == 1, name

    assert nodes["ring.ticket.amount"]["expected"] == [
        "^[1-9][0-9]?$",
        "^[1-9][0-9]?/12$",
    ]


def test_r20_unknown_state_records_fresh_failed_then_native_failed() -> None:
    nodes = load_task_nodes(RING)
    failure = nodes[FAILURE]

    assert_outcome(nodes, FAILURE, "failed", "ring.state_known")
    assert failure["custom_action_param"]["error_code"] == (
        "RING_POSTCONDITION_MISSING"
    )
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failure

    # UI cleanup is not business evidence. A missing close target must never
    # manufacture a successful terminal result.
    assert nodes["MJA_RING_CLOSE_PAGE"]["on_error"] == [FAILURE]

    battle_unknown = nodes["MJA_RING_BATTLE_RESULT_UNKNOWN_RESULT"]
    assert battle_unknown["custom_action_param"]["status"] == "failed"
    assert battle_unknown["custom_action_param"]["error_code"] == (
        "RING_BATTLE_RESULT_UNKNOWN"
    )
    assert battle_unknown["custom_action_param"]["native_fail_after_record"] is True
    assert battle_unknown["Abort"] is True
    assert battle_unknown["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in battle_unknown


def test_r20_allowed_terminals_keep_explicit_business_postconditions() -> None:
    nodes = load_task_nodes(RING)

    assert_outcome(nodes, "MJA_RING_NOT_OPEN", "not_eligible", "ring.not_open")
    assert_outcome(
        nodes,
        "MJA_RING_ATTEMPTS_EXHAUSTED",
        "success",
        "ring.attempts_exhausted",
    )
    assert nodes["MJA_RING_NOT_OPEN_PROBE"]["recognition"]["param"]["all_of"] == [
        "ring.page",
        "ring.not.open",
    ]
    assert nodes["MJA_RING_ATTEMPTS_PROBE"]["recognition"]["param"][
        "all_of"
    ] == ["ring.page", "ring.attempts.exhausted"]
