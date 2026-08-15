from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, assert_outcome, load_task_nodes


APPRAISAL = TaskContract(
    "FREE_APPRAISAL_DAILY",
    "daily/free_appraisal_daily.json",
)
RECORD_FAILURE = "MJA_APPRAISAL_RECORD_FAILURE"
RUNTIME_RECOVERY = "MJA_APPRAISAL_RUNTIME_RECOVERY_ATTEMPT"


def _contains(roi: list[int], box: list[int]) -> bool:
    x, y, width, height = roi
    box_x, box_y, box_width, box_height = box
    return (
        x <= box_x
        and y <= box_y
        and x + width >= box_x + box_width
        and y + height >= box_y + box_height
    )


def test_r21_start_uses_home_top_appraisal_and_panel_recovery_as_siblings() -> None:
    nodes = load_task_nodes(APPRAISAL)

    start = nodes["MJA_FREE_APPRAISAL_DAILY_START"]
    assert start["next"] == [
        "[JumpBack]MJA_KNOWN_PAINTING_CLOSE",
        "[JumpBack]MJA_APPRAISAL_EXTRA_POPUP_CLOSE",
        "[JumpBack]MJA_APPRAISAL_KNOWN_TEA_SHOP_CLOSE",
        "MJA_APPRAISAL_REWARD_PROBE",
        "MJA_APPRAISAL_PAGE_PROBE",
        "MJA_APPRAISAL_HOME_PROBE",
        "MJA_APPRAISAL_CLOSE_RECOVERED_PANEL",
    ]
    assert start["timeout"] == 8000
    assert start["retry_times"] == 0
    assert start["on_error"] == [RUNTIME_RECOVERY, RECORD_FAILURE]

    same_frame_home = ["appraisal.home.page", "appraisal.home.entry"]
    home_probe = nodes["MJA_APPRAISAL_HOME_PROBE"]
    assert home_probe["recognition"]["param"] == {
        "all_of": same_frame_home,
        "box_index": 0,
    }
    assert home_probe["next"] == ["MJA_APPRAISAL_OPEN_APPRAISAL"]

    open_appraisal = nodes["MJA_APPRAISAL_OPEN_APPRAISAL"]
    assert open_appraisal["recognition"]["param"] == {
        "all_of": same_frame_home,
        "box_index": 1,
    }
    assert open_appraisal["custom_action_param"] == {
        "task_id": APPRAISAL.task_id,
        "action_id": "open_appraisal",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "appraisal.home.page",
            "target_name": "appraisal.home.entry",
        },
    }
    assert open_appraisal["next"] == ["MJA_APPRAISAL_PAGE_PROBE"]

    # r21 proved that opening the function panel hides the real top-level
    # 鉴宝 entry. The old open-panel -> panel appraisal route must not return.
    assert "MJA_APPRAISAL_OPEN_PANEL" not in nodes
    assert "MJA_APPRAISAL_PANEL_PROBE" not in nodes
    assert "appraisal.entry" not in nodes


def test_r21_root_recovery_is_bounded_and_reuses_shared_startup_without_input() -> None:
    nodes = load_task_nodes(APPRAISAL)
    recovery = nodes[RUNTIME_RECOVERY]

    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "DoNothing"
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 30000
    assert recovery["retry_times"] == 0
    assert recovery["next"] == [
        "MJA_APPRAISAL_REWARD_PROBE",
        "MJA_APPRAISAL_PAGE_PROBE",
        "MJA_APPRAISAL_HOME_PROBE",
        "MJA_APPRAISAL_CLOSE_RECOVERED_PANEL",
        "[JumpBack]MJA_GAME_START",
    ]
    assert recovery["on_error"] == [RECORD_FAILURE]

    # The only startup escape is the shared, non-consuming game-start route;
    # this task must not add a launcher or replay the free claim here.
    assert "StartApp" not in str(recovery)
    assert "claim_free_appraisal_once" not in str(recovery)


def test_r21_ocr_boxes_are_covered_by_top_appraisal_target_variants() -> None:
    nodes = load_task_nodes(APPRAISAL)
    home = nodes["appraisal.home.page"]
    appraisal = nodes["appraisal.home.entry"]

    assert home == {
        "recognition": "OCR",
        "expected": ["^战令$", "^活动$", "^祈福$", "^副本$", "^画卷$"],
        "roi": [800, 40, 370, 50],
        "action": "DoNothing",
    }
    assert appraisal == {
        "recognition": "OCR",
        "expected": ["^鉴宝$", "^宝$"],
        "roi": [925, 45, 65, 40],
        "action": "DoNothing",
    }

    # Fresh r21 home OCR boxes from the failed live ticket.
    for box in (
        [824, 58, 30, 16],  # 战令
        [882, 58, 35, 14],  # 活动
        [1001, 58, 31, 14],  # 祈福
        [1057, 58, 36, 14],  # 副本
        [1116, 58, 32, 14],  # 画卷
    ):
        assert _contains(home["roi"], box)
    assert _contains(appraisal["roi"], [938, 58, 35, 14])
    assert _contains(appraisal["roi"], [953, 61, 15, 10])

    # 秘宝 is only a function-panel boundary anchor. It is never an appraisal
    # click target and is outside the fixed top-level 鉴宝 ROI.
    panel = nodes["appraisal.panel.page"]
    assert "^秘宝$" in panel["expected"]
    assert "鉴宝" not in "".join(panel["expected"])
    assert appraisal["expected"] == ["^鉴宝$", "^宝$"]


def test_r21_open_panel_recovery_closes_once_then_reenters_home_route() -> None:
    nodes = load_task_nodes(APPRAISAL)
    recovery = nodes["MJA_APPRAISAL_CLOSE_RECOVERED_PANEL"]

    assert recovery["recognition"]["param"] == {
        "all_of": ["appraisal.panel.page", "appraisal.panel.close"],
        "box_index": 1,
    }
    assert recovery["custom_action_param"] == {
        "task_id": APPRAISAL.task_id,
        "action_id": "close_function_panel",
        "kind": "click",
        "fixed_click_mode": "function_panel_close",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "appraisal.panel.page",
            "target_name": "appraisal.panel.close",
        },
    }
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["timeout"] == 8000
    assert recovery["next"] == ["MJA_APPRAISAL_HOME_PROBE"]
    assert recovery["on_error"] == [RECORD_FAILURE]

    close = nodes["appraisal.panel.close"]
    assert close == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }


def test_r21_free_claim_and_return_home_remain_bounded_and_truthful() -> None:
    nodes = load_task_nodes(APPRAISAL)
    guarded = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == APPRAISAL.task_id
    }
    assert {
        node["custom_action_param"]["action_id"] for node in guarded.values()
    } == {
        "close_function_panel",
        "close_extra_reward_popup",
        "open_appraisal",
        "claim_free_appraisal_once",
        "close_appraisal_popup",
        "close_appraisal_page",
    }

    policy = TASK_POLICIES[APPRAISAL.task_id]
    assert policy.max_steps == 16
    assert set(policy.action_caps) == {
        "close_function_panel",
        "close_extra_reward_popup",
        "open_appraisal",
        "claim_free_appraisal_once",
        "close_appraisal_popup",
        "close_appraisal_page",
    }
    assert policy.action_caps["close_extra_reward_popup"] == 2
    assert all(
        policy.action_caps[action_id] == 1
        for action_id in (
            "open_appraisal",
            "claim_free_appraisal_once",
            "close_appraisal_popup",
            "close_appraisal_page",
            "close_function_panel",
        )
    )
    for node in guarded.values():
        assert node["max_hit"] == 1
        assert node["retry_times"] == 0

    page = nodes["MJA_APPRAISAL_PAGE_PROBE"]
    assert page["next"] == ["MJA_APPRAISAL_CLAIM", "MJA_APPRAISAL_STATUS_PROBE"]
    claim = nodes["MJA_APPRAISAL_CLAIM"]
    assert claim["recognition"]["param"] == {
        "all_of": ["appraisal.page", "appraisal.free_once"],
        "box_index": 1,
    }
    assert nodes["appraisal.free_once"]["expected"] == "^免费鉴宝$"
    assert "付费" not in str(claim)

    assert nodes["MJA_APPRAISAL_STATUS_PROBE"]["next"] == [
        "MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE"
    ]
    assert nodes["MJA_APPRAISAL_VERIFY"]["next"] == [
        "MJA_APPRAISAL_CLOSE_SUCCESS_PAGE"
    ]
    for close_name, home_name, outcome_name in (
        (
            "MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE",
            "MJA_APPRAISAL_HOME_AFTER_ALREADY_COMPLETE",
            "MJA_APPRAISAL_ALREADY_COMPLETE",
        ),
        (
            "MJA_APPRAISAL_CLOSE_SUCCESS_PAGE",
            "MJA_APPRAISAL_HOME_AFTER_SUCCESS",
            "MJA_APPRAISAL_SUCCESS",
        ),
    ):
        close_node = nodes[close_name]
        assert close_node["recognition"]["param"] == {
            "all_of": ["appraisal.page", "appraisal.page.close"],
            "box_index": 1,
        }
        assert close_node["custom_action_param"]["action_id"] == "close_appraisal_page"
        assert close_node["next"] == [home_name]
        assert nodes[home_name]["recognition"]["param"] == {
            "all_of": ["appraisal.home.page", "appraisal.home.entry"],
            "box_index": 0,
        }
        assert nodes[home_name]["next"] == [outcome_name]

    assert_outcome(
        nodes, "MJA_APPRAISAL_ALREADY_COMPLETE", "already_complete", "appraisal.used"
    )
    assert_outcome(nodes, "MJA_APPRAISAL_SUCCESS", "success", "appraisal.used")


def test_r21_every_unknown_or_timeout_records_fresh_failure_then_native_fails() -> None:
    nodes = load_task_nodes(APPRAISAL)
    for name in (
        "MJA_APPRAISAL_PAGE_PROBE",
        "MJA_APPRAISAL_STATUS_PROBE",
        "MJA_APPRAISAL_CLAIM",
        "MJA_APPRAISAL_REWARD_PROBE",
        "MJA_APPRAISAL_CLOSE_REWARD",
        "MJA_APPRAISAL_VERIFY",
        "MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE",
        "MJA_APPRAISAL_HOME_AFTER_ALREADY_COMPLETE",
        "MJA_APPRAISAL_CLOSE_SUCCESS_PAGE",
        "MJA_APPRAISAL_HOME_AFTER_SUCCESS",
        "MJA_APPRAISAL_HOME_AFTER_REWARD",
        "MJA_APPRAISAL_HOME_PROBE",
        "MJA_APPRAISAL_OPEN_APPRAISAL",
        "MJA_APPRAISAL_CLOSE_RECOVERED_PANEL",
    ):
        assert nodes[name]["on_error"] == [RECORD_FAILURE], name

    assert nodes["MJA_FREE_APPRAISAL_DAILY_START"]["on_error"] == [
        RUNTIME_RECOVERY,
        RECORD_FAILURE,
    ]
    assert nodes[RUNTIME_RECOVERY]["on_error"] == [RECORD_FAILURE]

    assert_outcome(
        nodes,
        RECORD_FAILURE,
        "failed",
        "APPRAISAL_POSTCONDITION_MISSING",
    )
    failure = nodes[RECORD_FAILURE]
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
    assert "on_error" not in failure
