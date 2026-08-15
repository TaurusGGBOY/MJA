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
        "MJA_GUILD_DONATION_MEMBER_CLOSE",
        "MJA_GUILD_DONATION_START_SAFETY_PROBE",
        "MJA_GUILD_DONATION_START_PAID_PROBE",
        "MJA_GUILD_DONATION_START_UNKNOWN_POPUP_PROBE",
        "MJA_GUILD_DONATION_ANDROID_PAGE_PROBE",
        "MJA_GUILD_DONATION_ANDROID_GUILD_PAGE_PROBE",
        "MJA_GUILD_DONATION_ANDROID_PANEL_PROBE",
        "MJA_GUILD_DONATION_ANDROID_HOME_PROBE",
        "MJA_GUILD_DONATION_PAGE_PROBE",
        "MJA_GUILD_DONATION_GUILD_PAGE_PROBE",
        "MJA_GUILD_DONATION_HOME_PROBE",
        "MJA_GUILD_DONATION_PANEL_PROBE",
    ]
    start = nodes[DONATION.entry]
    assert start["timeout"] == 8000
    assert start["next"] == probes
    assert start["on_error"] == [
        "MJA_GUILD_DONATION_GAME_START_RECOVERY",
        "MJA_GUILD_DONATION_RECORD_FAILURE",
    ]

    member_close = nodes["MJA_GUILD_DONATION_MEMBER_CLOSE"]
    assert member_close["recognition"]["param"] == {
        "all_of": [
            "guild.donation.member.page",
            "guild.donation.member.close",
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
            "page_name": "guild.donation.member.page",
            "target_name": "guild.donation.member.close",
        },
    }
    assert member_close["max_hit"] == 1
    assert member_close["retry_times"] == 0
    assert member_close["next"] == [
        "MJA_GUILD_DONATION_GUILD_HOME_OPEN_DONATION",
        "MJA_GUILD_DONATION_MEMBER_GUILD_HOME_CLOSE"
    ]
    assert member_close["on_error"] == ["MJA_GUILD_DONATION_RECORD_FAILURE"]

    guild_home_open = nodes["MJA_GUILD_DONATION_GUILD_HOME_OPEN_DONATION"]
    assert guild_home_open["recognition"]["param"] == {
        "all_of": [
            "guild.donation.guild.home.page",
            "guild.donation.guild.home.context",
            "guild.donation.guild.home.donation.entry",
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
            "page_name": "guild.donation.guild.home.page",
            "target_name": "guild.donation.guild.home.donation.entry",
        },
    }
    assert guild_home_open["max_hit"] == 1
    assert guild_home_open["retry_times"] == 0
    assert guild_home_open["next"] == ["MJA_GUILD_DONATION_PAGE_PROBE"]
    assert guild_home_open["on_error"] == ["MJA_GUILD_DONATION_RECORD_FAILURE"]

    guild_home_close = nodes["MJA_GUILD_DONATION_MEMBER_GUILD_HOME_CLOSE"]
    assert guild_home_close["recognition"]["param"] == {
        "all_of": [
            "guild.donation.guild.home.page",
            "guild.donation.guild.home.context",
            "guild.donation.guild.home.close",
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
            "page_name": "guild.donation.guild.home.page",
            "target_name": "guild.donation.guild.home.close",
        },
    }
    assert guild_home_close["max_hit"] == 1
    assert guild_home_close["retry_times"] == 0
    assert guild_home_close["next"] == ["MJA_GUILD_DONATION_PANEL_PROBE"]
    assert guild_home_close["on_error"] == ["MJA_GUILD_DONATION_RECORD_FAILURE"]

    recovery = nodes["MJA_GUILD_DONATION_GAME_START_RECOVERY"]
    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "StartApp"
    assert recovery["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert recovery["post_delay"] == 5000
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 30000
    assert recovery["retry_times"] == 0
    assert recovery["next"] == probes
    assert recovery["on_error"] == ["MJA_GUILD_DONATION_RECORD_FAILURE"]

    assert nodes["MJA_GUILD_DONATION_PANEL_PROBE"]["on_error"] == [
        "MJA_GUILD_DONATION_RECORD_FAILURE"
    ]
    assert nodes["MJA_GUILD_DONATION_GUILD_PAGE_PROBE"]["on_error"] == [
        "MJA_GUILD_DONATION_RECORD_FAILURE"
    ]


def test_guild_donation_requires_10_of_10_before_one_free_click() -> None:
    nodes = load_task_nodes(DONATION)

    remaining_10 = nodes["guild.donation.remaining_10_of_10"]
    remaining_9 = nodes["guild.donation.remaining_9_of_10"]
    invalid = nodes["guild.donation.remaining_invalid"]
    assert "10\\s*/\\s*10" in remaining_10["expected"]
    assert "9\\s*/\\s*10" in remaining_9["expected"]
    assert "[0-8]\\s*/\\s*10" in invalid["expected"]

    donation = nodes["MJA_GUILD_DONATION_DONATE_FREE"]
    params = donation["custom_action_param"]
    assert params["action_id"] == "donate_guild_free_once"
    assert params["evidence"] == {
        "page_index": 0,
        "target_index": 3,
        "page_name": "guild.donation.page",
        "target_name": "guild.donation.free",
    }
    assert donation["retry_times"] == 0
    assert_reachable(
        nodes,
        "MJA_GUILD_DONATION_REMAINING_10_PROBE",
        "MJA_GUILD_DONATION_DONATE_FREE",
    )
    assert_reachable(
        nodes,
        "MJA_GUILD_DONATION_DONATE_FREE",
        "MJA_GUILD_DONATION_POSTCONDITION_PROBE",
    )
    android_donation = nodes["MJA_GUILD_DONATION_ANDROID_DONATE_FREE"]
    assert android_donation["custom_action_param"]["action_id"] == (
        "donate_android_guild_free_once"
    )
    # The reward surface is animated and appears after the consumptive click;
    # let the first close-reward probe observe it before probing 9/10.
    assert android_donation["post_delay"] == 1500
    assert android_donation["retry_times"] == 0
    assert_reachable(
        nodes,
        "MJA_GUILD_DONATION_ANDROID_REMAINING_10_PROBE",
        "MJA_GUILD_DONATION_ANDROID_DONATE_FREE",
    )
    assert_reachable(
        nodes,
        "MJA_GUILD_DONATION_ANDROID_DONATE_FREE",
        "MJA_GUILD_DONATION_ANDROID_CLOSE_REWARD",
    )
    assert_reachable(
        nodes,
        "MJA_GUILD_DONATION_ANDROID_CLOSE_REWARD",
        "MJA_GUILD_DONATION_ANDROID_POSTCONDITION_PROBE",
    )

    close_reward = nodes["MJA_GUILD_DONATION_ANDROID_CLOSE_REWARD"]
    assert close_reward["custom_action_param"]["action_id"] == (
        "close_android_donation_reward"
    )
    assert close_reward["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "guild.donation.android.reward",
        "target_name": "guild.donation.android.reward.close",
    }


def test_guild_donation_success_is_strictly_9_of_10_and_known_surface() -> None:
    nodes = load_task_nodes(DONATION)

    post = nodes["MJA_GUILD_DONATION_POSTCONDITION_PROBE"]
    assert post["recognition"]["param"]["all_of"] == [
        "guild.donation.page",
        "guild.donation.context",
        "guild.donation.remaining_9_of_10",
    ]
    assert_outcome(
        nodes,
        "MJA_GUILD_DONATION_SUCCESS",
        "success",
        "guild.donation.remaining_9_of_10",
    )
    assert_outcome(
        nodes,
        "MJA_GUILD_DONATION_ALREADY_COMPLETE",
        "already_complete",
        "guild.donation.remaining_9_of_10",
    )
    assert nodes["MJA_GUILD_DONATION_ANDROID_POSTCONDITION_PROBE"]["next"] == [
        "MJA_GUILD_DONATION_SUCCESS_CLEANUP"
    ]
    assert nodes["MJA_GUILD_DONATION_POSTCONDITION_PROBE"]["next"] == [
        "MJA_GUILD_DONATION_SUCCESS_CLEANUP"
    ]
    assert nodes["MJA_GUILD_DONATION_ANDROID_REMAINING_9_PROBE"]["next"] == [
        "MJA_GUILD_DONATION_ALREADY_COMPLETE_CLEANUP"
    ]
    assert nodes["MJA_GUILD_DONATION_REMAINING_9_PROBE"]["next"] == [
        "MJA_GUILD_DONATION_ALREADY_COMPLETE_CLEANUP"
    ]
    assert nodes["MJA_GUILD_DONATION_SUCCESS"]["next"] == ["MJA_COMMON_STOP"]
    assert nodes["MJA_GUILD_DONATION_ALREADY_COMPLETE"]["next"] == [
        "MJA_COMMON_STOP"
    ]
    assert_abort_code(
        nodes,
        "MJA_GUILD_DONATION_RECORD_FAILURE",
        "GUILD_DONATION_POSTCONDITION_MISSING",
    )
    assert_abort_code(
        nodes,
        "MJA_GUILD_DONATION_PAID_STOP",
        "GUILD_DONATION_PAID_SURFACE",
    )
    assert_abort_code(
        nodes,
        "MJA_GUILD_DONATION_UNKNOWN_POPUP_STOP",
        "GUILD_DONATION_UNKNOWN_POPUP",
    )


def test_guild_donation_terminal_outcomes_cleanup_and_verify_home() -> None:
    nodes = load_task_nodes(DONATION)

    for status in ("SUCCESS", "ALREADY_COMPLETE"):
        close = nodes[f"MJA_GUILD_DONATION_{status}_ANDROID_CLOSE"]
        assert close["recognition"]["param"] == {
            "all_of": [
                "guild.donation.android.donation.page",
                "guild.donation.android.donation.close",
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
                "page_name": "guild.donation.android.donation.page",
                "target_name": "guild.donation.android.donation.close",
            },
        }
        assert close["max_hit"] == 1
        assert close["retry_times"] == 0
        assert close["next"] == [
            f"MJA_GUILD_DONATION_{status}_GUILD_HOME_CLOSE"
        ]
        assert close["on_error"] == [
            f"MJA_GUILD_DONATION_{status}_CLOSE",
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED",
        ]

        legacy_close = nodes[f"MJA_GUILD_DONATION_{status}_CLOSE"]
        assert legacy_close["next"] == [
            f"MJA_GUILD_DONATION_{status}_GUILD_HOME_CLOSE"
        ]
        assert legacy_close["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]

        guild_close = nodes[f"MJA_GUILD_DONATION_{status}_GUILD_HOME_CLOSE"]
        assert guild_close["recognition"]["param"] == {
            "all_of": [
                "guild.donation.guild.home.page",
                "guild.donation.guild.home.context",
                "guild.donation.guild.home.close",
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
                "page_name": "guild.donation.guild.home.page",
                "target_name": "guild.donation.guild.home.close",
            },
        }
        assert guild_close["max_hit"] == 1
        assert guild_close["retry_times"] == 0
        panel_probe_name = f"MJA_GUILD_DONATION_{status}_FUNCTION_PANEL_PROBE"
        panel_close_name = f"MJA_GUILD_DONATION_{status}_FUNCTION_PANEL_CLOSE"
        assert guild_close["next"] == [panel_probe_name]
        assert guild_close["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]

        panel_probe = nodes[panel_probe_name]
        assert panel_probe == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                    "box_index": 0,
                },
            },
            "timeout": 5000,
            "max_hit": 1,
            "action": "DoNothing",
            "next": [panel_close_name],
            "on_error": ["MJA_GUILD_DONATION_HOME_RETURN_FAILED"],
            "retry_times": 0,
        }

        panel_close = nodes[panel_close_name]
        assert panel_close["recognition"]["param"] == {
            "all_of": [
                "guild.donation.panel.page",
                "guild.donation.panel.close",
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
                "page_name": "guild.donation.panel.page",
                "target_name": "guild.donation.panel.close",
            },
        }
        assert panel_close["max_hit"] == 1
        assert panel_close["retry_times"] == 0
        assert panel_close["next"] == [
            f"MJA_GUILD_DONATION_{status}_HOME_PROBE"
        ]
        assert panel_close["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]

        home = nodes[f"MJA_GUILD_DONATION_{status}_HOME_PROBE"]
        assert home["template"] == "home/home_marker.png"
        assert home["roi"] == [1040, 0, 240, 110]
        assert home["threshold"] == 0.75
        assert home["timeout"] == 5000
        assert home["max_hit"] == 1
        assert home["next"] == [f"MJA_GUILD_DONATION_{status}"]
        assert home["on_error"] == ["MJA_GUILD_DONATION_HOME_RETURN_FAILED"]

    close_evidence = nodes["guild.donation.android.donation.close"]
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

    guild_home_page = nodes["guild.donation.guild.home.page"]
    assert guild_home_page == {
        "recognition": "OCR",
        "expected": "浮生城",
        "roi": [0, 0, 380, 100],
        "action": "DoNothing",
    }
    guild_home_context = nodes["guild.donation.guild.home.context"]
    assert guild_home_context == {
        "recognition": "OCR",
        "expected": "帮会大厅",
        "roi": [780, 60, 380, 160],
        "action": "DoNothing",
    }
    guild_home_close = nodes["guild.donation.guild.home.close"]
    assert guild_home_close == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [125, 125, 125],
        "roi": [1180, 0, 100, 100],
        "connected": True,
        "count": 180,
        "action": "DoNothing",
    }
    panel_page = nodes["guild.donation.panel.page"]
    assert panel_page == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }
    panel_close = nodes["guild.donation.panel.close"]
    assert panel_close == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["MJA_GAME_SIDE_PANEL_OPEN"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    assert nodes["MJA_GAME_HOME_MARKER"]["template"] == "home/home_marker.png"
    assert nodes["MJA_GAME_HOME_MARKER"]["threshold"] == 0.75

    assert_abort_code(
        nodes,
        "MJA_GUILD_DONATION_HOME_RETURN_FAILED",
        "GUILD_DONATION_HOME_RETURN_FAILED",
    )
    assert nodes["MJA_GUILD_DONATION_HOME_RETURN_FAILED"][
        "custom_action_param"
    ]["postcondition"] == "home.ready"

    for status in ("SUCCESS", "ALREADY_COMPLETE"):
        pending = f"MJA_GUILD_DONATION_{status}_CLEANUP"
        guild_close = f"MJA_GUILD_DONATION_{status}_GUILD_HOME_CLOSE"
        panel_probe = f"MJA_GUILD_DONATION_{status}_FUNCTION_PANEL_PROBE"
        panel_close = f"MJA_GUILD_DONATION_{status}_FUNCTION_PANEL_CLOSE"
        home = f"MJA_GUILD_DONATION_{status}_HOME_PROBE"
        outcome = f"MJA_GUILD_DONATION_{status}"
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
        pending = nodes[f"MJA_GUILD_DONATION_{status}_CLEANUP"]
        assert pending["next"][-1] == "MJA_GUILD_DONATION_HOME_RETURN_FAILED"

        android_close = nodes[f"MJA_GUILD_DONATION_{status}_ANDROID_CLOSE"]
        legacy_close = nodes[f"MJA_GUILD_DONATION_{status}_CLOSE"]
        guild_close = nodes[f"MJA_GUILD_DONATION_{status}_GUILD_HOME_CLOSE"]
        panel_probe = nodes[f"MJA_GUILD_DONATION_{status}_FUNCTION_PANEL_PROBE"]
        panel_close = nodes[f"MJA_GUILD_DONATION_{status}_FUNCTION_PANEL_CLOSE"]
        home = nodes[f"MJA_GUILD_DONATION_{status}_HOME_PROBE"]
        assert android_close["on_error"][-1] == (
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        )
        assert legacy_close["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]
        assert guild_close["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]
        assert panel_probe["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]
        assert panel_close["on_error"] == [
            "MJA_GUILD_DONATION_HOME_RETURN_FAILED"
        ]
        assert home["on_error"] == ["MJA_GUILD_DONATION_HOME_RETURN_FAILED"]
        assert home["next"] == [f"MJA_GUILD_DONATION_{status}"]

    failure = nodes["MJA_GUILD_DONATION_HOME_RETURN_FAILED"]
    assert failure["custom_action"] == "RecordTaskOutcome"
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
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
        "MJA_GUILD_DONATION_HOME_RETURN_FAILED",
        "MJA_GUILD_DONATION_COUNTER_UNKNOWN",
        "MJA_GUILD_DONATION_SAFETY_STOP",
        "MJA_GUILD_DONATION_PAID_STOP",
        "MJA_GUILD_DONATION_UNKNOWN_POPUP_STOP",
        "MJA_GUILD_DONATION_RECORD_FAILURE",
    }
    for name in failure_names:
        node = nodes[name]
        assert node["custom_action_param"]["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["MJA_COMMON_ABORT"]
        assert "on_error" not in node


def test_guild_donation_has_no_paid_or_raw_input_branch() -> None:
    nodes = load_task_nodes(DONATION)
    scoped = {
        name: node
        for name, node in nodes.items()
        if name.startswith("MJA_GUILD_DONATION_DAILY_")
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
    assert "guild.donation.free" in guarded_targets
    assert "guild.donation.panel.close" in guarded_targets
    assert not any(
        isinstance(target, str)
        and any(word in target for word in ("购买", "充值", "支付", "元宝", "价格"))
        for target in guarded_targets
    )
