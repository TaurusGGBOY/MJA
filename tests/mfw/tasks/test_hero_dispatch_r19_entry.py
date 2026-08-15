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
        "英雄派遣-英雄-主页-副本": [1060, 60, 29, 11],
        "英雄派遣-画卷-滚动-入口": [91, 27, 46, 27],
        "英雄派遣-英雄-主页-试炼": [990, 643, 44, 22],
    }
    expected = {
        "英雄派遣-英雄-主页-副本": "^副本$",
        "英雄派遣-画卷-滚动-入口": "^画卷$",
        "英雄派遣-英雄-主页-试炼": "^试剑$",
    }

    for name, box in observed.items():
        node = nodes[name]
        roi = node["roi"]
        assert node["recognition"] == "OCR"
        assert node["expected"] == expected[name]
        assert _contains(roi, box)
        if name != "英雄派遣-画卷-滚动-入口":
            assert roi[0] >= 900
        assert roi[2] * roi[3] < FRAME_WIDTH * FRAME_HEIGHT // 100

    assert nodes["英雄派遣-画卷-滚动-入口"]["roi"] == [70, 10, 95, 60]
    assert nodes["英雄派遣-画卷-滚动-入口"]["roi"] != [850, 0, 430, 180]


def test_home_entry_requires_same_frame_world_boundary_and_exact_target() -> None:
    nodes = load_task_nodes(HERO)

    home_page = nodes["英雄派遣-英雄-主页-页面"]
    assert home_page == {
        "recognition": {
            "type": "And",
            "param": {"all_of": ["公共-游戏主页-页面"]},
        },
        "action": "DoNothing",
    }

    # The first route must be a cheap page probe.  OCR candidates are entered
    # one at a time through on_error, so a stale batch frame cannot decide the
    # page state before the home boundary is checked.
    assert nodes["英雄派遣-任务入口"]["next"] == [
        "英雄派遣-主页-探测"
    ]
    assert nodes["英雄派遣-主页-探测"]["next"] == [
        "英雄派遣-打开-画卷",
        "英雄派遣-打开-画卷-世界",
    ]
    assert nodes["英雄派遣-主页-探测"]["on_error"] == [
        "英雄派遣-恢复继续-奖励-探测"
    ]

    for probe_name in ("英雄派遣-主页-探测", "英雄派遣-主页边界-探测"):
        probe = nodes[probe_name]
        assert probe["recognition"] == {
            "type": "And",
            "param": {"all_of": ["英雄派遣-英雄-主页-页面"]},
        }

    open_node = nodes["英雄派遣-打开-画卷"]
    assert open_node["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["英雄派遣-英雄-主页-页面", "英雄派遣-画卷-滚动-入口"],
            "box_index": 1,
        },
    }
    assert open_node["action"] == "Custom"
    assert open_node["custom_action"] == "GuardedInput"
    assert open_node["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "英雄派遣-英雄-主页-页面",
        "target_name": "英雄派遣-画卷-滚动-入口",
    }
    assert open_node["max_hit"] == 1
    assert open_node["retry_times"] == 0
    assert TASK_POLICIES[HERO.task_id].action_caps["open_painting_scroll"] == 1

    world_open = nodes["英雄派遣-打开-画卷-世界"]
    assert world_open["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["英雄派遣-英雄-主页-页面", "英雄派遣-画卷-滚动-入口-世界"],
            "box_index": 1,
        },
    }
    assert world_open["custom_action_param"]["evidence"]["target_name"] == (
        "英雄派遣-画卷-滚动-入口-世界"
    )
    assert nodes["英雄派遣-画卷-滚动-入口-世界"] == {
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
    assert start["next"] == ["英雄派遣-主页-探测"]
    assert start["on_error"] == [
        "英雄派遣-游戏启动恢复",
        "英雄派遣-记录-失败",
    ]
    assert nodes["英雄派遣-主页-探测"]["on_error"] == [
        "英雄派遣-恢复继续-奖励-探测"
    ]
    assert nodes["英雄派遣-恢复继续-奖励-探测"]["on_error"] == [
        "英雄派遣-派遣-页面-探测"
    ]
    assert nodes["英雄派遣-派遣-页面-探测"]["on_error"] == [
        "英雄派遣-打开-派遣"
    ]

    failure_nodes = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id") == HERO.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    }
    assert set(failure_nodes) == {
        "英雄派遣-填充-循环-耗尽",
        "英雄派遣-领取-循环-耗尽",
        "英雄派遣-记录-失败",
        "英雄派遣-边界-失败",
    }
    for node in failure_nodes.values():
        assert node["custom_action_param"]["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["公共-通用中止"]


def test_empty_dispatch_state_requires_same_frame_zero_counters_and_blank_selection() -> None:
    nodes = load_task_nodes(HERO)

    marker = nodes["英雄派遣-英雄-无-派遣-任务"]
    assert marker["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "英雄派遣-英雄-派遣-页面",
                "英雄派遣-英雄-零-派遣-任务",
                "英雄派遣-英雄-零-已完成-派遣任务",
                "英雄派遣-英雄-无-已选择-派遣-任务",
            ],
            "box_index": 1,
        },
    }
    assert nodes["英雄派遣-英雄-零-派遣-任务"]["expected"] == r"^任务\s*[:：]?\s*0\s*/\s*9$"
    assert nodes["英雄派遣-英雄-零-已完成-派遣任务"]["expected"] == r"^已完成\s*[:：]?\s*0$"
    assert nodes["英雄派遣-英雄-无-已选择-派遣-任务"]["expected"] == "尚未选择派遣任务"
    assert nodes["英雄派遣-英雄-无-已选择-派遣-任务"]["roi"] == [930, 250, 340, 220]

    for probe_name in ("英雄派遣-初始-无-任务", "英雄派遣-之后-无-任务"):
        probe = nodes[probe_name]
        assert probe["recognition"]["param"]["all_of"] == [
            "英雄派遣-英雄-派遣-页面",
            "英雄派遣-英雄-无-派遣-任务",
        ]
        assert probe["next"] == ["英雄派遣-成功-无-任务"]

    outcome = nodes["英雄派遣-成功-无-任务"]
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
            assert node["on_error"] == ["英雄派遣-记录-失败"]


def test_success_and_already_complete_follow_fresh_visual_postconditions() -> None:
    nodes = load_task_nodes(HERO)
    contracts = {
        "英雄派遣-已完成-全部": (
            "already_complete",
            "英雄派遣-英雄-全部-已完成",
            "英雄派遣-初始-全部",
        ),
        "英雄派遣-已完成-进度": (
            "already_complete",
            "英雄派遣-英雄-首个-任务-中-进度",
            "英雄派遣-初始-进度",
        ),
        "英雄派遣-成功-全部": (
            "success",
            "英雄派遣-英雄-全部-已完成",
            "英雄派遣-之后-全部",
        ),
        "英雄派遣-成功-进度": (
            "success",
            "英雄派遣-英雄-首个-任务-中-进度",
            "英雄派遣-之后-进度",
        ),
        "英雄派遣-成功-无-任务": (
            "success",
            "英雄派遣-英雄-无-派遣-任务",
            "英雄派遣-之后-无-任务",
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

    for name in ("英雄派遣-领取-奖励-探测", "英雄派遣-英雄-奖励-弹窗", "英雄派遣-英雄-奖励-弹窗-关闭"):
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert node["expected"] == "点击空白处关闭"
        assert node["roi"] == popup_roi

    for name in ("英雄派遣-关闭-奖励", "英雄派遣-恢复继续-关闭-奖励"):
        node = nodes[name]
        assert node["recognition"] == {
            "type": "And",
            "param": {
                "all_of": ["英雄派遣-英雄-奖励-弹窗", "英雄派遣-英雄-奖励-弹窗-关闭"],
                "box_index": 1,
            },
        }
        assert node["custom_action"] == "GuardedInput"
        assert node["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": "英雄派遣-英雄-奖励-弹窗",
            "target_name": "英雄派遣-英雄-奖励-弹窗-关闭",
        }

    assert nodes["英雄派遣-关闭-奖励"]["max_hit"] == 6
    assert nodes["英雄派遣-恢复继续-关闭-奖励"]["max_hit"] == 1
    assert nodes["英雄派遣-领取-奖励-探测"]["on_error"] == [
        "英雄派遣-领取-校验",
        "英雄派遣-记录-失败",
    ]


def test_claim_postconditions_are_ordered_next_alternatives() -> None:
    nodes = load_task_nodes(HERO)

    assert nodes["英雄派遣-领取-校验"]["next"] == [
        "英雄派遣-领取-探测",
        "英雄派遣-填充-循环",
    ]
    assert nodes["英雄派遣-发送"]["next"] == [
        "英雄派遣-领取-探测",
        "英雄派遣-填充-循环",
    ]
    assert nodes["英雄派遣-填充-循环"]["next"] == [
        "英雄派遣-之后-全部",
        "英雄派遣-之后-进度",
        "英雄派遣-之后-无-任务",
        "英雄派遣-之后-选择",
    ]

    # The claim loop is a native MAA loop: its body nodes must be allowed to
    # recur.  A max_hit of one here would make the third claim wait until the
    # parent timeout and report HERO_CLAIM_LOOP_EXHAUSTED even though the page
    # remains visibly claimable.
    for name in (
        "英雄派遣-领取后-选择",
        "英雄派遣-领取后-按钮",
        "英雄派遣-领取后",
    ):
        assert nodes[name]["max_hit"] == 6

    assert nodes["英雄派遣-英雄-首个-任务-中-进度"]["expected"][-1] == (
        r"^\d{1,2}:\d{2}:\d{2}$"
    )
