from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_reachable,
    load_task_nodes,
)


ROOT = Path(__file__).parents[3]
TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")


def _assert_contains(roi: list[int], box: list[int]) -> None:
    roi_x, roi_y, roi_width, roi_height = roi
    box_x, box_y, box_width, box_height = box
    assert roi_x <= box_x
    assert roi_y <= box_y
    assert roi_x + roi_width >= box_x + box_width
    assert roi_y + roi_height >= box_y + box_height


def test_trial_r22_archive_defines_the_strict_same_frame_completion_proof() -> None:
    nodes = load_task_nodes(TRIAL)

    # Fresh formal failure ticket 20260809T111257556279Z, final frame
    # 2026.08.09-19.14.22.367 at 1280x720. The page OCR box is copied from
    # the archived Maa trace; the other boxes bound the two explicit controls
    # visible in that archived screenshot.
    archived_page_box = [30, 267, 106, 27]
    archived_waiting_box = [1000, 638, 188, 29]
    archived_first_zero_box = [75, 547, 18, 18]

    _assert_contains(nodes["trial.page"]["roi"], archived_page_box)

    waiting = nodes["trial.free_waiting"]
    assert waiting == {
        "recognition": "OCR",
        "expected": r"^敬\s*请\s*期\s*待$",
        "roi": [930, 600, 320, 100],
        "action": "DoNothing",
    }
    _assert_contains(waiting["roi"], archived_waiting_box)

    zero = nodes["trial.current_reward_zero"]
    assert zero == {
        "recognition": "OCR",
        "expected": "^0$",
        "roi": [30, 495, 120, 105],
        "action": "DoNothing",
    }
    _assert_contains(zero["roi"], archived_first_zero_box)

    assert nodes["trial.free_used"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": [
                    "trial.page",
                    "trial.free_waiting",
                ],
                "box_index": 1,
            },
        },
        "action": "DoNothing",
    }


def test_trial_r22_completion_precedes_claims_and_reaches_success() -> None:
    nodes = load_task_nodes(TRIAL)

    already = nodes["MJA_TRIAL_ALREADY_STATUS"]
    assert already["recognition"]["param"] == {
        "all_of": ["trial.page", "trial.free_used"],
        "box_index": 1,
    }
    assert already["next"] == ["MJA_TRIAL_CLOSE_ALREADY"]

    page_candidates = nodes["MJA_TRIAL_PAGE_PROBE"]["next"]
    assert page_candidates.index("MJA_TRIAL_ALREADY_STATUS") < page_candidates.index(
        "MJA_TRIAL_CLAIM_REWARD"
    )

    final_verify = nodes["MJA_TRIAL_FREE_VERIFY"]
    assert final_verify["recognition"]["param"] == {
        "all_of": ["trial.page", "trial.free_used"],
        "box_index": 1,
    }
    assert final_verify["next"] == ["MJA_TRIAL_CLOSE_SUCCESS"]
    assert_reachable(nodes, "MJA_TRIAL_FREE_VERIFY", "MJA_TRIAL_SUCCESS")
    assert nodes["MJA_TRIAL_SUCCESS"]["custom_action_param"]["status"] == "success"


def test_trial_r22_keeps_single_claim_caps_and_native_unknown_failure() -> None:
    nodes = load_task_nodes(TRIAL)
    policy = TASK_POLICIES[TRIAL.task_id]

    assert policy.action_caps["claim_trial_sword_reward"] == 1
    assert policy.action_caps["claim_free_trial"] == 1
    assert_no_side_effect_retry(nodes, "claim_trial_sword_reward")
    assert_no_side_effect_retry(nodes, "claim_free_trial")

    failure = nodes["MJA_TRIAL_RECORD_FAILURE"]
    assert failure["custom_action_param"] == {
        "task_id": TRIAL.task_id,
        "status": "failed",
        "postcondition": "TRIAL_POSTCONDITION_MISSING",
        "error_code": "TRIAL_POSTCONDITION_MISSING",
        "native_fail_after_record": True,
    }
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]


def test_trial_r22_android_override_matches_the_proven_completion_contract() -> None:
    android_nodes = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )

    assert android_nodes["trial.free_waiting"] == {
        "recognition": "OCR",
        "expected": r"^敬\s*请\s*期\s*待$",
        "roi": [930, 600, 320, 100],
        "action": "DoNothing",
    }
    assert android_nodes["trial.current_reward_zero"]["expected"] == "^0$"
    assert android_nodes["trial.free_used"] == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": [
                    "trial.page",
                    "trial.free_waiting",
                ],
                "box_index": 1,
            },
        },
        "action": "DoNothing",
    }
