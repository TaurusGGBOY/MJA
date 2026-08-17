from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_abort_code,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_outcome,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

DONATION = TaskContract("GUILD_DONATION_DAILY", "daily/guild_donation_daily.json")
STATUS_LABELS = {"SUCCESS": "成功", "ALREADY_COMPLETE": "已完成"}


def _status_node(status: str, suffix: str = "") -> str:
    name = f"帮派捐献-{STATUS_LABELS[status]}"
    return f"{name}-{suffix}" if suffix else name


def test_guild_donation_is_an_independent_mfw_task_contract() -> None:
    assert_task_contract(DONATION, require_game_start_recovery=False)
    nodes = load_task_nodes(DONATION)

    assert_guarded_actions(
        nodes,
        DONATION.task_id,
        [
            "open_function_panel",
            "open_guild",
            "open_guild_donation",
            "open_android_function_panel",
            "open_android_guild",
            "open_android_guild_donation",
            "donate_guild_free_once",
            "donate_android_guild_free_once",
            "close_android_donation_reward",
            "close_guild_member",
            "close_guild_donation",
            "close_guild_home",
            "close_function_panel",
        ],
    )
    assert TASK_POLICIES[DONATION.task_id].action_caps == {
        "open_function_panel": 1,
        "open_guild": 1,
        "open_guild_donation": 1,
        "open_android_function_panel": 1,
        "open_android_guild": 1,
        "open_android_guild_donation": 1,
        "donate_guild_free_once": 1,
        "donate_android_guild_free_once": 1,
        "close_android_donation_reward": 1,
        "close_guild_member": 1,
        "close_guild_donation": 1,
        "close_guild_home": 1,
        "close_function_panel": 1,
    }
    assert_no_side_effect_retry(nodes, "donate_guild_free_once")


def test_guild_donation_recovers_once_without_reentering_shared_startup() -> None:
    nodes = load_task_nodes(DONATION)
    probes = [
        "帮派捐献-成员-关闭",
        "帮派捐献-开始-安全-探测",
        "帮派捐献-开始-付费-探测",
        "帮派捐献-开始-未知-弹窗-探测",
        "帮派捐献-安卓-页面-探测",
        "帮派捐献-安卓-帮派-页面-探测",
        "帮派捐献-安卓-面板-探测",
        "帮派捐献-安卓-主页-探测",
        "帮派捐献-页面-探测",
        "帮派捐献-帮派-页面-探测",
        "帮派捐献-主页-探测",
        "帮派捐献-面板-探测",
    ]
    start = nodes[DONATION.entry]
    assert start["timeout"] == 8000
    assert start["next"] == probes
    assert start["on_error"] == [
        "帮派捐献-游戏启动恢复",
        "帮派捐献-记录-失败",
    ]

    member_close = nodes["帮派捐献-成员-关闭"]
    assert member_close["recognition"]["param"] == {
        "all_of": [
            "帮派捐献-帮派-捐献-成员-页面",
            "帮派捐献-帮派-捐献-成员-关闭",
        ],
        "box_index": 1,
    }
    assert member_close["custom_action"] == "GuardedInput"
    assert member_close["custom_action_param"] == {
        "task_id": DONATION.task_id,
        "action_id": "close_guild_member",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "帮派捐献-帮派-捐献-成员-页面",
            "target_name": "帮派捐献-帮派-捐献-成员-关闭",
        },
    }
    assert member_close["max_hit"] == 1
    assert member_close["retry_times"] == 0
    assert member_close["next"] == [
        "帮派捐献-帮派-主页-打开-捐献",
        "帮派捐献-成员-帮派-主页-关闭"
    ]
    assert member_close["on_error"] == ["帮派捐献-记录-失败"]

    guild_home_open = nodes["帮派捐献-帮派-主页-打开-捐献"]
    assert guild_home_open["recognition"]["param"] == {
        "all_of": [
            "帮派捐献-帮派-捐献-帮派-主页-页面",
            "帮派捐献-帮派-捐献-帮派-主页-上下文",
            "帮派捐献-帮派-捐献-帮派-主页-捐献-入口",
        ],
        "box_index": 2,
    }
    assert guild_home_open["custom_action"] == "GuardedInput"
    assert guild_home_open["custom_action_param"] == {
        "task_id": DONATION.task_id,
        "action_id": "open_guild_donation",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 2,
            "page_name": "帮派捐献-帮派-捐献-帮派-主页-页面",
            "target_name": "帮派捐献-帮派-捐献-帮派-主页-捐献-入口",
        },
    }
    assert guild_home_open["max_hit"] == 1
    assert guild_home_open["retry_times"] == 0
    assert guild_home_open["next"] == ["帮派捐献-页面-探测"]
    assert guild_home_open["on_error"] == ["帮派捐献-记录-失败"]

    guild_home_close = nodes["帮派捐献-成员-帮派-主页-关闭"]
    assert guild_home_close["recognition"]["param"] == {
        "all_of": [
            "帮派捐献-帮派-捐献-帮派-主页-页面",
            "帮派捐献-帮派-捐献-帮派-主页-上下文",
            "帮派捐献-帮派-捐献-帮派-主页-关闭",
        ],
        "box_index": 2,
    }
    assert guild_home_close["custom_action"] == "GuardedInput"
    assert guild_home_close["custom_action_param"] == {
        "task_id": DONATION.task_id,
        "action_id": "close_guild_home",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 2,
            "page_name": "帮派捐献-帮派-捐献-帮派-主页-页面",
            "target_name": "帮派捐献-帮派-捐献-帮派-主页-关闭",
        },
    }
    assert guild_home_close["max_hit"] == 1
    assert guild_home_close["retry_times"] == 0
    assert guild_home_close["next"] == ["帮派捐献-面板-探测"]
    assert guild_home_close["on_error"] == ["帮派捐献-记录-失败"]

    recovery = nodes["帮派捐献-游戏启动恢复"]
    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "StartApp"
    assert recovery["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert recovery["post_delay"] == 5000
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 30000
    assert recovery["retry_times"] == 0
    assert recovery["next"] == probes
    assert recovery["on_error"] == ["帮派捐献-记录-失败"]

    assert nodes["帮派捐献-面板-探测"]["on_error"] == [
        "帮派捐献-记录-失败"
    ]
    assert nodes["帮派捐献-帮派-页面-探测"]["on_error"] == [
        "帮派捐献-记录-失败"
    ]


def test_guild_donation_requires_10_of_10_before_one_free_click() -> None:
    nodes = load_task_nodes(DONATION)

    remaining_10 = nodes["帮派捐献-帮派-捐献-剩余-10-共-10"]
    remaining_9 = nodes["帮派捐献-帮派-捐献-剩余-9-共-10"]
    invalid = nodes["帮派捐献-帮派-捐献-剩余-无效"]
    assert "10\\s*/\\s*10" in remaining_10["expected"]
    assert "9\\s*/\\s*10" in remaining_9["expected"]
    assert "[0-8]\\s*/\\s*10" in invalid["expected"]

    donation = nodes["帮派捐献-捐献-免费"]
    params = donation["custom_action_param"]
    assert params["action_id"] == "donate_guild_free_once"
    assert params["evidence"] == {
        "page_index": 0,
        "target_index": 3,
        "page_name": "帮派捐献-帮派-捐献-页面",
        "target_name": "帮派捐献-帮派-捐献-免费",
    }
    assert donation["retry_times"] == 0
    assert_reachable(
        nodes,
        "帮派捐献-剩余-10-探测",
        "帮派捐献-捐献-免费",
    )
    assert_reachable(
        nodes,
        "帮派捐献-捐献-免费",
        "帮派捐献-后置条件-探测",
    )
    android_donation = nodes["帮派捐献-安卓-捐献-免费"]
    assert android_donation["custom_action_param"]["action_id"] == (
        "donate_android_guild_free_once"
    )
    # The reward surface is animated and appears after the consumptive click;
    # let the first close-reward probe observe it before probing 9/10.
    assert android_donation["post_delay"] == 1500
    assert android_donation["retry_times"] == 0
    assert_reachable(
        nodes,
        "帮派捐献-安卓-剩余-10-探测",
        "帮派捐献-安卓-捐献-免费",
    )
    assert_reachable(
        nodes,
        "帮派捐献-安卓-捐献-免费",
        "帮派捐献-安卓-关闭-奖励",
    )
    assert_reachable(
        nodes,
        "帮派捐献-安卓-关闭-奖励",
        "帮派捐献-安卓-后置条件-探测",
    )

    close_reward = nodes["帮派捐献-安卓-关闭-奖励"]
    assert close_reward["custom_action_param"]["action_id"] == (
        "close_android_donation_reward"
    )
    assert close_reward["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "帮派捐献-帮派-捐献-安卓-奖励",
        "target_name": "帮派捐献-帮派-捐献-安卓-奖励-关闭",
    }


def test_guild_donation_success_is_strictly_9_of_10_and_known_surface() -> None:
    nodes = load_task_nodes(DONATION)

    post = nodes["帮派捐献-后置条件-探测"]
    assert post["recognition"]["param"]["all_of"] == [
        "帮派捐献-帮派-捐献-页面",
        "帮派捐献-帮派-捐献-上下文",
        "帮派捐献-帮派-捐献-剩余-9-共-10",
    ]
    assert_outcome(
        nodes,
        "帮派捐献-成功",
        "success",
        "guild.donation.remaining_9_of_10",
    )
    assert_outcome(
        nodes,
        "帮派捐献-已完成",
        "already_complete",
        "guild.donation.remaining_9_of_10",
    )
    assert nodes["帮派捐献-安卓-后置条件-探测"]["next"] == [
        "帮派捐献-成功-清理"
    ]
    assert nodes["帮派捐献-后置条件-探测"]["next"] == [
        "帮派捐献-成功-清理"
    ]
    assert nodes["帮派捐献-安卓-剩余-9-探测"]["next"] == [
        "帮派捐献-已完成-清理"
    ]
    assert nodes["帮派捐献-剩余-9-探测"]["next"] == [
        "帮派捐献-已完成-清理"
    ]
    assert nodes["帮派捐献-成功"]["next"] == ["公共-通用停止"]
    assert nodes["帮派捐献-已完成"]["next"] == [
        "公共-通用停止"
    ]
    assert_abort_code(
        nodes,
        "帮派捐献-记录-失败",
        "GUILD_DONATION_POSTCONDITION_MISSING",
    )
    assert_abort_code(
        nodes,
        "帮派捐献-付费-停止",
        "GUILD_DONATION_PAID_SURFACE",
    )
    assert_abort_code(
        nodes,
        "帮派捐献-未知-弹窗-停止",
        "GUILD_DONATION_UNKNOWN_POPUP",
    )


def test_guild_donation_terminal_outcomes_cleanup_and_verify_home() -> None:
    nodes = load_task_nodes(DONATION)

    for status in ("SUCCESS", "ALREADY_COMPLETE"):
        close = nodes[_status_node(status, "安卓-关闭")]
        assert close["recognition"]["param"] == {
            "all_of": [
                "帮派捐献-帮派-捐献-安卓-捐献-页面",
                "帮派捐献-帮派-捐献-安卓-捐献-关闭",
            ],
            "box_index": 1,
        }
        assert close["custom_action"] == "GuardedInput"
        assert close["custom_action_param"] == {
            "task_id": DONATION.task_id,
            "action_id": "close_guild_donation",
            "kind": "click",
            "evidence": {
                "page_index": 0,
                "target_index": 1,
                "page_name": "帮派捐献-帮派-捐献-安卓-捐献-页面",
                "target_name": "帮派捐献-帮派-捐献-安卓-捐献-关闭",
            },
        }
        assert close["max_hit"] == 1
        assert close["retry_times"] == 0
        assert close["next"] == [
            _status_node(status, "帮派-主页-关闭")
        ]
        assert close["on_error"] == [
            _status_node(status, "关闭"),
            "帮派捐献-主页-返回-失败",
        ]

        legacy_close = nodes[_status_node(status, "关闭")]
        assert legacy_close["next"] == [
            _status_node(status, "帮派-主页-关闭")
        ]
        assert legacy_close["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]

        guild_close = nodes[_status_node(status, "帮派-主页-关闭")]
        assert guild_close["recognition"]["param"] == {
            "all_of": [
                "帮派捐献-帮派-捐献-帮派-主页-页面",
                "帮派捐献-帮派-捐献-帮派-主页-上下文",
                "帮派捐献-帮派-捐献-帮派-主页-关闭",
            ],
            "box_index": 2,
        }
        assert guild_close["custom_action"] == "GuardedInput"
        assert guild_close["custom_action_param"] == {
            "task_id": DONATION.task_id,
            "action_id": "close_guild_home",
            "kind": "click",
            "evidence": {
                "page_index": 0,
                "target_index": 2,
                "page_name": "帮派捐献-帮派-捐献-帮派-主页-页面",
                "target_name": "帮派捐献-帮派-捐献-帮派-主页-关闭",
            },
        }
        assert guild_close["max_hit"] == 1
        assert guild_close["retry_times"] == 0
        panel_probe_name = _status_node(status, "功能-面板-探测")
        panel_close_name = _status_node(status, "功能-面板-关闭")
        assert guild_close["next"] == [panel_probe_name]
        assert guild_close["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]

        panel_probe = nodes[panel_probe_name]
        assert panel_probe == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": ["公共-游戏侧边面板-打开"],
                    "box_index": 0,
                },
            },
            "timeout": 5000,
            "max_hit": 1,
            "action": "DoNothing",
            "next": [panel_close_name],
            "on_error": ["帮派捐献-主页-返回-失败"],
            "retry_times": 0,
        }

        panel_close = nodes[panel_close_name]
        assert panel_close["recognition"]["param"] == {
            "all_of": [
                "帮派捐献-帮派-捐献-面板-页面",
                "帮派捐献-帮派-捐献-面板-关闭",
            ],
            "box_index": 1,
        }
        assert panel_close["custom_action"] == "GuardedInput"
        assert panel_close["custom_action_param"] == {
            "task_id": DONATION.task_id,
            "action_id": "close_function_panel",
            "kind": "click",
            "fixed_click_mode": "function_panel_close",
            "evidence": {
                "page_index": 0,
                "target_index": 1,
                "page_name": "帮派捐献-帮派-捐献-面板-页面",
                "target_name": "帮派捐献-帮派-捐献-面板-关闭",
            },
        }
        assert panel_close["max_hit"] == 1
        assert panel_close["retry_times"] == 0
        assert panel_close["next"] == [
            _status_node(status, "主页-探测")
        ]
        assert panel_close["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]

        home = nodes[_status_node(status, "主页-探测")]
        assert home["template"] == "home/home_marker.png"
        assert home["roi"] == [1040, 0, 240, 110]
        assert home["threshold"] == 0.75
        assert home["timeout"] == 5000
        assert home["max_hit"] == 1
        assert home["next"] == [_status_node(status)]
        assert home["on_error"] == ["帮派捐献-主页-返回-失败"]

    close_evidence = nodes["帮派捐献-帮派-捐献-安卓-捐献-关闭"]
    assert close_evidence == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [120, 120, 120],
        "roi": [980, 100, 60, 60],
        # The real X is split into 23/57/73/21-pixel components. Requiring one
        # connected component of 180 pixels made a visible X unrecognizable.
        "connected": False,
        "count": 120,
        "action": "DoNothing",
    }

    donation_close = nodes["帮派捐献-帮派-捐献-关闭"]
    assert donation_close == {
        "recognition": "TemplateMatch",
        "template": "home/modal_close.png",
        "roi": [1160, 0, 100, 100],
        # On the real donation page the close icon scores about 0.255. The
        # page-color marker is already part of the parent And recognizer, so
        # this lower threshold does not authorize a click on unrelated pages.
        "threshold": 0.2,
        "action": "DoNothing",
    }

    guild_home_page = nodes["帮派捐献-帮派-捐献-帮派-主页-页面"]
    assert guild_home_page == {
        "recognition": "OCR",
        "expected": "浮生城",
        "roi": [0, 0, 380, 100],
        "action": "DoNothing",
    }
    guild_home_context = nodes["帮派捐献-帮派-捐献-帮派-主页-上下文"]
    assert guild_home_context == {
        "recognition": "OCR",
        "expected": "帮会大厅",
        "roi": [780, 60, 380, 160],
        "action": "DoNothing",
    }
    guild_home_close = nodes["帮派捐献-帮派-捐献-帮派-主页-关闭"]
    assert guild_home_close == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [125, 125, 125],
        "roi": [1180, 0, 100, 100],
        "connected": True,
        "count": 180,
        "action": "DoNothing",
    }
    panel_page = nodes["帮派捐献-帮派-捐献-面板-页面"]
    assert panel_page == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏侧边面板-打开"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }
    panel_close = nodes["帮派捐献-帮派-捐献-面板-关闭"]
    assert panel_close == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏侧边面板-打开"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    assert nodes["启动-游戏主页-标记"]["template"] == "home/home_marker.png"
    assert nodes["启动-游戏主页-标记"]["threshold"] == 0.75

    assert_abort_code(
        nodes,
        "帮派捐献-主页-返回-失败",
        "GUILD_DONATION_HOME_RETURN_FAILED",
    )
    assert nodes["帮派捐献-主页-返回-失败"][
        "custom_action_param"
    ]["postcondition"] == "home.ready"

    for status in ("SUCCESS", "ALREADY_COMPLETE"):
        pending = _status_node(status, "清理")
        guild_close = _status_node(status, "帮派-主页-关闭")
        panel_probe = _status_node(status, "功能-面板-探测")
        panel_close = _status_node(status, "功能-面板-关闭")
        home = _status_node(status, "主页-探测")
        outcome = _status_node(status)
        assert_reachable(nodes, pending, guild_close)
        assert_reachable(nodes, guild_close, panel_probe)
        assert_reachable(nodes, panel_probe, panel_close)
        assert_reachable(nodes, panel_close, home)
        assert_reachable(nodes, pending, home)
        assert_reachable(nodes, home, outcome)


def test_guild_donation_cannot_fallback_to_success_when_cleanup_fails() -> None:
    nodes = load_task_nodes(DONATION)

    assert "MJA_GUILD_DONATION_EXIT_CLEANUP_STOP" not in nodes
    for status in ("SUCCESS", "ALREADY_COMPLETE"):
        pending = nodes[_status_node(status, "清理")]
        assert pending["next"][-1] == "帮派捐献-主页-返回-失败"

        android_close = nodes[_status_node(status, "安卓-关闭")]
        legacy_close = nodes[_status_node(status, "关闭")]
        guild_close = nodes[_status_node(status, "帮派-主页-关闭")]
        panel_probe = nodes[_status_node(status, "功能-面板-探测")]
        panel_close = nodes[_status_node(status, "功能-面板-关闭")]
        home = nodes[_status_node(status, "主页-探测")]
        assert android_close["on_error"][-1] == (
            "帮派捐献-主页-返回-失败"
        )
        assert legacy_close["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]
        assert guild_close["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]
        assert panel_probe["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]
        assert panel_close["on_error"] == [
            "帮派捐献-主页-返回-失败"
        ]
        assert home["on_error"] == ["帮派捐献-主页-返回-失败"]
        assert home["next"] == [_status_node(status)]

    failure = nodes["帮派捐献-主页-返回-失败"]
    assert failure["custom_action"] == "RecordTaskOutcome"
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
    assert "on_error" not in failure


def test_guild_donation_all_failure_outcomes_are_native_failures() -> None:
    nodes = load_task_nodes(DONATION)
    failure_names = {
        name
        for name, node in nodes.items()
        if node.get("custom_action") == "RecordTaskOutcome"
        and node.get("custom_action_param", {}).get("task_id") == DONATION.task_id
        and node.get("custom_action_param", {}).get("status") == "failed"
    }

    assert failure_names == {
        "帮派捐献-主页-返回-失败",
        "帮派捐献-计数-未知",
        "帮派捐献-安全-停止",
        "帮派捐献-付费-停止",
        "帮派捐献-未知-弹窗-停止",
        "帮派捐献-记录-失败",
    }
    for name in failure_names:
        node = nodes[name]
        assert node["custom_action_param"]["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["公共-通用中止"]
        assert "on_error" not in node


def test_guild_donation_has_no_paid_or_raw_input_branch() -> None:
    nodes = load_task_nodes(DONATION)
    scoped = {
        name: node
        for name, node in nodes.items()
        if name.startswith("帮派捐献-")
        or node.get("custom_action_param", {}).get("task_id") == DONATION.task_id
    }
    assert not any(
        node.get("action") in {"Click", "Swipe", "MultiSwipe", "Key", "Input"}
        for node in scoped.values()
    )
    guarded_targets = {
        node.get("custom_action_param", {}).get("evidence", {}).get("target_name")
        for node in scoped.values()
        if node.get("custom_action") == "GuardedInput"
    }
    assert "帮派捐献-帮派-捐献-免费" in guarded_targets
    assert "帮派捐献-帮派-捐献-面板-关闭" in guarded_targets
    assert not any(
        isinstance(target, str)
        and any(word in target for word in ("购买", "充值", "支付", "元宝", "价格"))
        for target in guarded_targets
    )
