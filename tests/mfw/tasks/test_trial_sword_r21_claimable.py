from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_reachable,
    load_task_nodes,
)


TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")


def _assert_contains(roi: list[int], box: list[int]) -> None:
    roi_x, roi_y, roi_width, roi_height = roi
    box_x, box_y, box_width, box_height = box
    assert roi_x <= box_x
    assert roi_y <= box_y
    assert roi_x + roi_width >= box_x + box_width
    assert roi_y + roi_height >= box_y + box_height


def test_trial_r21_claimable_reward_uses_exact_same_frame_ocr_evidence() -> None:
    nodes = load_task_nodes(TRIAL)

    # Fresh r21 live evidence from 2026-08-09 18:43:16.220 at 1280x720.
    archived_page_box = [30, 267, 107, 27]
    archived_current_reward_box = [31, 462, 106, 25]
    archived_claim_box = [180, 632, 58, 34]

    _assert_contains(nodes["试剑-试炼-页面"]["roi"], archived_page_box)

    current_reward = nodes["trial.current_reward"]
    assert current_reward == {
        "recognition": "OCR",
        "expected": "^当前收益$",
        "roi": [20, 440, 140, 70],
        "action": "DoNothing",
    }
    _assert_contains(current_reward["roi"], archived_current_reward_box)

    claim_target = nodes["trial.current_reward_claim"]
    assert claim_target == {
        "recognition": "OCR",
        "expected": "^领取$",
        "roi": [160, 610, 100, 80],
        "action": "DoNothing",
    }
    _assert_contains(claim_target["roi"], archived_claim_box)

    # The separate purple 免费 control begins to the right of this boundary.
    # The ordinary reward target therefore cannot authorize the paid/free
    # confirmation route or any neighbouring control.
    assert claim_target["roi"][0] + claim_target["roi"][2] <= 270

    claim = nodes["试剑-领取-奖励"]
    assert claim["recognition"]["param"] == {
        "all_of": [
            "试剑-试炼-页面",
            "trial.current_reward",
            "trial.current_reward_claim",
        ],
        "box_index": 2,
    }
    assert claim["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 2,
        "page_name": "试剑-试炼-页面",
        "target_name": "trial.current_reward_claim",
    }
    assert claim["custom_action_param"]["action_id"] == "claim_trial_sword_reward"
    assert claim["retry_times"] == 0
    assert TASK_POLICIES[TRIAL.task_id].action_caps["claim_trial_sword_reward"] == 1
    assert_no_side_effect_retry(nodes, "claim_trial_sword_reward")


def test_trial_r21_page_routes_claimable_reward_as_a_bounded_sibling() -> None:
    nodes = load_task_nodes(TRIAL)

    page_probe = nodes["试剑-页面-探测"]
    assert page_probe["next"] == [
        "MJA_TRIAL_ALREADY_STATUS",
        "MJA_TRIAL_REWARD_STATUS",
        "试剑-领取-奖励",
    ]
    assert page_probe["timeout"] == 8000
    assert page_probe["retry_times"] == 0
    assert page_probe["on_error"] == ["试剑-记录-失败"]

    claim = nodes["试剑-领取-奖励"]
    assert claim["next"] == [
        "试剑-关闭-奖励",
        "MJA_TRIAL_REWARD_VERIFY",
    ]
    assert claim["timeout"] == 8000
    assert claim["on_error"] == ["试剑-记录-失败"]

    reward_popup = nodes["试剑-关闭-奖励"]
    assert reward_popup["recognition"]["param"] == {
        "all_of": ["试剑-试炼-奖励-弹窗", "试剑-试炼-弹窗-关闭"],
        "box_index": 1,
    }
    assert reward_popup["custom_action_param"]["action_id"] == "close_reward_popup"

    claimed_state = nodes["MJA_TRIAL_REWARD_VERIFY"]
    assert claimed_state["recognition"]["param"] == {
        "all_of": ["试剑-试炼-页面", "trial.reward_claimed"],
        "box_index": 1,
    }

    for node_name in (
        "试剑-恢复继续-结果-关闭",
        "试剑-关闭-奖励",
        "MJA_TRIAL_REWARD_VERIFY",
    ):
        node = nodes[node_name]
        assert node["next"] == [
            "MJA_TRIAL_POST_REWARD_FREE_STATUS",
            "试剑-领取-免费",
        ]
        assert node["timeout"] == 8000
        assert node["retry_times"] == 0
        assert node["on_error"] == ["试剑-记录-失败"]


def test_trial_r21_keeps_free_claim_already_complete_and_native_failure_contracts() -> None:
    nodes = load_task_nodes(TRIAL)

    free_claim = nodes["试剑-领取-免费"]
    assert free_claim["recognition"]["param"] == {
        "all_of": ["试剑-试炼-页面", "试剑-试炼-免费-领取"],
        "box_index": 1,
    }
    assert free_claim["custom_action_param"]["action_id"] == "claim_free_trial"
    assert TASK_POLICIES[TRIAL.task_id].action_caps["claim_free_trial"] == 1

    assert nodes["MJA_TRIAL_POST_REWARD_FREE_STATUS"]["next"] == [
        "试剑-关闭-成功"
    ]
    assert nodes["试剑-关闭-成功"]["next"] == [
        "试剑-成功-主页-探测"
    ]
    assert nodes["试剑-成功-主页-探测"]["next"] == [
        "试剑-成功"
    ]
    assert nodes["试剑-成功"]["custom_action_param"] == {
        "task_id": TRIAL.task_id,
        "status": "success",
        "postcondition": "trial.free_used",
    }

    assert nodes["MJA_TRIAL_ALREADY_STATUS"]["next"] == [
        "MJA_TRIAL_CLOSE_ALREADY"
    ]
    assert nodes["MJA_TRIAL_ALREADY_HOME_PROBE"]["next"] == [
        "MJA_TRIAL_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_TRIAL_ALREADY_COMPLETE"]["custom_action_param"]["status"] == (
        "success"
    )

    failure = nodes["试剑-记录-失败"]
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]

    assert_reachable(nodes, TRIAL.entry, "试剑-成功")
    assert_reachable(nodes, TRIAL.entry, "MJA_TRIAL_ALREADY_COMPLETE")
    assert_reachable(nodes, TRIAL.entry, "试剑-记录-失败")
