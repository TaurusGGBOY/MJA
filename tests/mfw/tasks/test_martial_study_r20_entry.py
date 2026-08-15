from __future__ import annotations

from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, load_task_nodes

MARTIAL = TaskContract(
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "daily/martial_study_breakthrough_daily.json",
)
ROOT = Path(__file__).parents[3]
RECORD_FAILURE = "武学突破-记录-失败"


def test_r20_start_routes_resume_and_launcher_recovery_as_siblings() -> None:
    nodes = load_task_nodes(MARTIAL)
    start = nodes["武学突破-任务入口"]

    # In MaaFramework a child's on_error is not used when a next-list child
    # never matched. The final full regression therefore repeated the entry
    # Probes after SPEND can leave the game on another page. Recovery must be
    # visible from the entry next list, reuse shared startup, and fail closed.
    assert start["next"] == [
        "[JumpBack]公共-已知-茶-详情-关闭",
        "[JumpBack]公共-已知-茶-商店-关闭",
        "武学突破-页面-探测",
        "武学突破-打开-研习",
        "武学突破-打开-面板",
        "武学突破-游戏启动恢复",
    ]
    assert start["timeout"] == 8000
    assert start["on_error"] == [
        "武学突破-游戏启动恢复",
        RECORD_FAILURE,
    ]
    assert start["retry_times"] == 0
    assert "MJA_MARTIAL_HOME_PROBE" not in nodes
    assert any(
        target == "[JumpBack]启动-游戏启动"
        for name, node in nodes.items()
        if name.startswith("武学突破-")
        for target in node.get("next", [])
    )

    recovery = nodes["武学突破-游戏启动恢复"]
    assert recovery["max_hit"] == 1
    assert recovery["action"] == "DoNothing"
    assert recovery["retry_times"] == 0
    assert recovery["next"] == ["武学突破-恢复-状态-探测"]
    assert recovery["on_error"] == ["武学突破-游戏启动恢复失败"]

    state_probe = nodes["武学突破-恢复-状态-探测"]
    assert state_probe["recognition"] == "DirectHit"
    assert state_probe["action"] == "DoNothing"
    assert state_probe["timeout"] == 30000
    assert state_probe["next"] == [
        "武学突破-页面-探测",
        "武学突破-打开-研习",
        "武学突破-打开-面板",
        "[JumpBack]启动-游戏启动",
    ]
    assert state_probe["on_error"] == ["武学突破-游戏启动恢复失败"]

    recovery_failed = nodes["武学突破-游戏启动恢复失败"]
    assert recovery_failed["custom_action_param"] == {
        "task_id": "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "status": "failed",
        "error_code": "MARTIAL_GAME_START_RECOVERY_EXHAUSTED",
        "postcondition": "martial.game_foreground_or_recoverable_state",
        "native_fail_after_record": True,
    }
    assert recovery_failed["Abort"] is True
    assert recovery_failed["next"] == ["公共-通用中止"]
    assert "on_error" not in recovery_failed


def test_r20_function_panel_entry_uses_stable_text_not_background_color() -> None:
    nodes = load_task_nodes(MARTIAL)
    home = nodes["武学突破-武学-主页"]
    panel = nodes["武学突破-武学-面板-打开"]
    panel_entry = nodes["公共-游戏功能面板-入口"]

    # The home boundary remains template-backed, while the function-panel
    # entry is text-backed so its recognition does not depend on the changing
    # game background behind the icon.
    archived_home_score = 0.825888
    assert archived_home_score > home["threshold"] == 0.75
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
    assert panel_entry == {
        "recognition": "OCR",
        "expected": "^画[卷券]$",
        "roi": [1080, 0, 200, 120],
        "action": "DoNothing",
    }


def test_r20_panel_action_is_same_frame_guarded_and_capped_once() -> None:
    nodes = load_task_nodes(MARTIAL)
    open_panel = nodes["武学突破-打开-面板"]

    assert open_panel["recognition"]["param"] == {
        "all_of": ["武学突破-武学-主页", "武学突破-武学-面板-打开"],
        "box_index": 1,
    }
    assert open_panel["custom_action"] == "GuardedInput"
    assert open_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "武学突破-武学-主页",
        "target_name": "武学突破-武学-面板-打开",
    }
    assert open_panel["max_hit"] == 1
    assert open_panel["retry_times"] == 0
    assert open_panel["timeout"] == 8000
    assert TASK_POLICIES[MARTIAL.task_id].action_caps["open_function_panel"] == 1

    assert nodes["武学突破-武学-入口"]["roi"] == [650, 120, 600, 560]
    # After closing the study result popup, the same page can render the
    # "武学研习" tab below y=220. Keep the ROI bounded but cover both layouts.
    assert nodes["武学突破-武学-页面"]["roi"] == [0, 0, 500, 420]
    assert nodes["武学突破-武学-入口"]["roi"] != [0, 0, 1280, 720]
    assert nodes["武学突破-武学-页面"]["roi"] != [0, 0, 1280, 720]


def test_martial_probes_are_bounded_and_fail_closed() -> None:
    nodes = load_task_nodes(MARTIAL)
    bounded = (
        "武学突破-任务入口",
        "武学突破-打开-面板",
        "武学突破-面板-探测",
        "武学突破-打开-研习",
        "武学突破-页面-探测",
        "武学突破-领取-门禁",
        "武学突破-领取-循环",
        "武学突破-领取-结果",
        "武学突破-关闭-奖励",
        "武学突破-无-成功-突破",
        "武学突破-关闭-页面-用于-成功",
        "武学突破-最终-面板-探测",
        "武学突破-成功-无-领取",
    )
    for name in bounded:
        node = nodes[name]
        assert node["timeout"] == 8000, name
        assert node["on_error"], name
        assert "MJA_MARTIAL_SUCCESS" not in node["on_error"], name

    page = nodes["武学突破-页面-探测"]
    assert page["next"] == [
        "武学突破-领取-门禁",
        "武学突破-无-成功-突破",
    ]
    assert nodes["武学突破-关闭-奖励"]["next"] == [
        "武学突破-页面-探测"
    ]
    assert nodes["武学突破-无-成功-突破"]["next"] == [
        "武学突破-关闭-页面-用于-成功"
    ]


def test_martial_slot_terminal_signals_match_the_live_card_surface() -> None:
    nodes = load_task_nodes(MARTIAL)

    success = nodes["武学突破-武学-成功-卡片"]
    assert success == {
        "recognition": "TemplateMatch",
        "template": "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success.png",
        "roi": [760, 350, 500, 330],
        "threshold": 0.36,
        "action": "DoNothing",
    }

    assert nodes["武学突破-武学-结果-关闭"]["expected"] == [
        "点击空白处关闭",
        "点击任意空白区域关闭",
    ]


def test_all_martial_failures_persist_then_fail_native() -> None:
    nodes = load_task_nodes(MARTIAL)
    failure_nodes = {
        name: node
        for name, node in nodes.items()
        if name.startswith("武学突破-")
        and node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert set(failure_nodes) == {
        "武学突破-游戏启动恢复失败",
        "武学突破-领取-循环-耗尽",
        RECORD_FAILURE,
    }
    for name, node in failure_nodes.items():
        assert node["custom_action_param"]["native_fail_after_record"] is True, name
        assert node["Abort"] is True, name
        assert node["next"] == ["公共-通用中止"], name
        assert "on_error" not in node, name

    successful_no_claim = nodes["武学突破-成功-无-领取"]
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
    assert nodes["武学突破-领取-循环"]["max_hit"] == 3
    assert nodes["武学突破-关闭-奖励"]["custom_action_param"]["action_id"] == (
        "close_reward_popup"
    )
    assert nodes["武学突破-关闭-页面-用于-成功"]["custom_action_param"][
        "action_id"
    ] == "close_martial_page"
    assert not any(
        "martial.success.result" in node.get("recognition", {}).get("param", {}).get(
            "all_of", []
        )
        for node in nodes.values()
        if isinstance(node.get("recognition"), dict)
    )
