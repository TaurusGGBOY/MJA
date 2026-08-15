from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, assert_outcome, load_task_nodes


APPRAISAL = TaskContract(
    "FREE_APPRAISAL_DAILY",
    "daily/free_appraisal_daily.json",
)
RECORD_FAILURE = "免费鉴定-记录-失败"
RUNTIME_RECOVERY = "免费鉴定-运行时-恢复-尝试"


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

    start = nodes["免费鉴定-任务入口"]
    assert start["next"] == [
        "[JumpBack]公共-已知-画卷-关闭",
        "[JumpBack]免费鉴定-额外-弹窗-关闭",
        "[JumpBack]免费鉴定-已知-茶-商店-关闭",
        "免费鉴定-奖励-探测",
        "免费鉴定-页面-探测",
        "免费鉴定-主页-探测",
        "免费鉴定-关闭-已恢复-面板",
    ]
    assert start["timeout"] == 8000
    assert start["retry_times"] == 0
    assert start["on_error"] == [RUNTIME_RECOVERY, RECORD_FAILURE]

    same_frame_home = ["免费鉴定-鉴定-主页-页面", "免费鉴定-鉴定-主页-入口"]
    home_probe = nodes["免费鉴定-主页-探测"]
    assert home_probe["recognition"]["param"] == {
        "all_of": same_frame_home,
        "box_index": 0,
    }
    assert home_probe["next"] == ["免费鉴定-打开-鉴定"]

    open_appraisal = nodes["免费鉴定-打开-鉴定"]
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
            "page_name": "免费鉴定-鉴定-主页-页面",
            "target_name": "免费鉴定-鉴定-主页-入口",
        },
    }
    assert open_appraisal["next"] == ["免费鉴定-页面-探测"]

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
        "免费鉴定-奖励-探测",
        "免费鉴定-页面-探测",
        "免费鉴定-主页-探测",
        "免费鉴定-关闭-已恢复-面板",
        "[JumpBack]启动-游戏启动",
    ]
    assert recovery["on_error"] == [RECORD_FAILURE]

    # The only startup escape is the shared, non-consuming game-start route;
    # this task must not add a launcher or replay the free claim here.
    assert "StartApp" not in str(recovery)
    assert "claim_free_appraisal_once" not in str(recovery)


def test_r21_ocr_boxes_are_covered_by_top_appraisal_target_variants() -> None:
    nodes = load_task_nodes(APPRAISAL)
    home = nodes["免费鉴定-鉴定-主页-页面"]
    appraisal = nodes["免费鉴定-鉴定-主页-入口"]

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
    panel = nodes["免费鉴定-鉴定-面板-页面"]
    assert "^秘宝$" in panel["expected"]
    assert "鉴宝" not in "".join(panel["expected"])
    assert appraisal["expected"] == ["^鉴宝$", "^宝$"]


def test_r21_open_panel_recovery_closes_once_then_reenters_home_route() -> None:
    nodes = load_task_nodes(APPRAISAL)
    recovery = nodes["免费鉴定-关闭-已恢复-面板"]

    assert recovery["recognition"]["param"] == {
        "all_of": ["免费鉴定-鉴定-面板-页面", "免费鉴定-鉴定-面板-关闭"],
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
            "page_name": "免费鉴定-鉴定-面板-页面",
            "target_name": "免费鉴定-鉴定-面板-关闭",
        },
    }
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["timeout"] == 8000
    assert recovery["next"] == ["免费鉴定-主页-探测"]
    assert recovery["on_error"] == [RECORD_FAILURE]

    close = nodes["免费鉴定-鉴定-面板-关闭"]
    assert close == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏侧边面板-打开"],
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

    page = nodes["免费鉴定-页面-探测"]
    assert page["next"] == ["免费鉴定-领取", "MJA_APPRAISAL_STATUS_PROBE"]
    claim = nodes["免费鉴定-领取"]
    assert claim["recognition"]["param"] == {
        "all_of": ["免费鉴定-鉴定-页面", "免费鉴定-鉴定-免费-一次"],
        "box_index": 1,
    }
    assert nodes["免费鉴定-鉴定-免费-一次"]["expected"] == "^免费鉴宝$"
    assert "付费" not in str(claim)

    assert nodes["MJA_APPRAISAL_STATUS_PROBE"]["next"] == [
        "MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE"
    ]
    assert nodes["MJA_APPRAISAL_VERIFY"]["next"] == [
        "免费鉴定-关闭-成功-页面"
    ]
    for close_name, home_name, outcome_name in (
        (
            "MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE",
            "MJA_APPRAISAL_HOME_AFTER_ALREADY_COMPLETE",
            "MJA_APPRAISAL_ALREADY_COMPLETE",
        ),
        (
            "免费鉴定-关闭-成功-页面",
            "免费鉴定-主页成功后",
            "免费鉴定-成功",
        ),
    ):
        close_node = nodes[close_name]
        assert close_node["recognition"]["param"] == {
            "all_of": ["免费鉴定-鉴定-页面", "免费鉴定-鉴定-页面-关闭"],
            "box_index": 1,
        }
        assert close_node["custom_action_param"]["action_id"] == "close_appraisal_page"
        assert close_node["next"] == [home_name]
        assert nodes[home_name]["recognition"]["param"] == {
            "all_of": ["免费鉴定-鉴定-主页-页面", "免费鉴定-鉴定-主页-入口"],
            "box_index": 0,
        }
        assert nodes[home_name]["next"] == [outcome_name]

    assert_outcome(
        nodes, "MJA_APPRAISAL_ALREADY_COMPLETE", "already_complete", "appraisal.used"
    )
    assert_outcome(nodes, "免费鉴定-成功", "success", "appraisal.used")


def test_r21_every_unknown_or_timeout_records_fresh_failure_then_native_fails() -> None:
    nodes = load_task_nodes(APPRAISAL)
    for name in (
        "免费鉴定-页面-探测",
        "MJA_APPRAISAL_STATUS_PROBE",
        "免费鉴定-领取",
        "免费鉴定-奖励-探测",
        "免费鉴定-关闭-奖励",
        "MJA_APPRAISAL_VERIFY",
        "MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE",
        "MJA_APPRAISAL_HOME_AFTER_ALREADY_COMPLETE",
        "免费鉴定-关闭-成功-页面",
        "免费鉴定-主页成功后",
        "免费鉴定-主页-之后-奖励",
        "免费鉴定-主页-探测",
        "免费鉴定-打开-鉴定",
        "免费鉴定-关闭-已恢复-面板",
    ):
        assert nodes[name]["on_error"] == [RECORD_FAILURE], name

    assert nodes["免费鉴定-任务入口"]["on_error"] == [
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
    assert failure["next"] == ["公共-通用中止"]
    assert "on_error" not in failure
