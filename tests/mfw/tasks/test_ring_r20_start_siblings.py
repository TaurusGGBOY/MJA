from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, assert_outcome, load_task_nodes


RING = TaskContract("RING_CHALLENGE_DAILY", "daily/ring_challenge_daily.json")
FAILURE = "擂台挑战-记录-失败"
STARTUP_FAILURE = "擂台挑战-游戏启动恢复失败"


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
    start = nodes["擂台挑战-任务入口"]

    assert start["timeout"] == 8000
    assert start["next"] == [
        "擂台挑战-页面-探测",
        "擂台挑战-日常-页面",
        "擂台挑战-面板-探测",
        "擂台挑战-主页-探测",
    ]
    assert start["on_error"] == ["擂台挑战-游戏启动恢复", STARTUP_FAILURE]
    assert "JumpBack" not in str(start)

    recovery = nodes["擂台挑战-游戏启动恢复"]
    assert recovery["recognition"] == "DirectHit"
    assert recovery["action"] == "DoNothing"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["next"] == ["擂台挑战-恢复-状态-探测"]
    assert recovery["on_error"] == [STARTUP_FAILURE]

    state = nodes["擂台挑战-恢复-状态-探测"]
    assert state["recognition"] == "DirectHit"
    assert state["action"] == "DoNothing"
    assert state["timeout"] == 30000
    assert state["next"] == [
        "擂台挑战-页面-探测",
        "擂台挑战-日常-页面",
        "擂台挑战-面板-探测",
        "擂台挑战-主页-探测",
        "[JumpBack]启动-游戏启动",
    ]
    assert state["on_error"] == [STARTUP_FAILURE]
    assert "[JumpBack]启动-游戏启动" in state["next"]
    assert "[JumpBack]启动-游戏启动" not in recovery["next"]

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
    assert failed["next"] == ["公共-通用中止"]
    assert "on_error" not in failed

    assert not any(
        name.startswith("擂台挑战-") and node.get("action") == "StartApp"
        for name, node in nodes.items()
    )

    for name in (
        "擂台挑战-主页-探测",
        "擂台挑战-打开-面板",
        "擂台挑战-面板-探测",
        "擂台挑战-打开-日常",
        "擂台挑战-日常-页面",
        "擂台挑战-页面-探测",
    ):
        node = nodes[name]
        assert 0 < node["timeout"] <= 8000, name
        assert node["on_error"] == [FAILURE], name


def test_r20_panel_entry_uses_stable_shared_color_recognition() -> None:
    nodes = load_task_nodes(RING)
    target = nodes["擂台挑战-擂台-面板-打开"]

    assert target == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": ["公共-游戏功能面板-入口"],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }

    opener = nodes["擂台挑战-打开-面板"]
    assert opener["recognition"]["param"] == {
        "all_of": ["擂台挑战-擂台-主页", "擂台挑战-擂台-面板-打开"],
        "box_index": 1,
    }
    assert opener["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "擂台挑战-擂台-主页",
        "target_name": "擂台挑战-擂台-面板-打开",
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
        "擂台挑战-扫荡",
        "擂台挑战-确认-扫荡",
        "擂台挑战-开始-匹配中",
        "擂台挑战-战斗-循环",
    ):
        node = nodes[name]
        params = node["custom_action_param"]
        all_of = node["recognition"]["param"]["all_of"]
        assert all_of[params["resource_index"]] == "擂台券", name
        assert params["resource_evidence_name"] == "擂台券", name
        assert all_of[params["amount_index"]] == "擂台挑战-擂台-券-数量", name
        assert "observed_amount" not in params, name
        assert params["budget_amount"] == 1, name

    assert nodes["擂台挑战-擂台-券-数量"]["expected"] == [
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
    assert failure["next"] == ["公共-通用中止"]
    assert "on_error" not in failure

    # UI cleanup is not business evidence. A missing close target must never
    # manufacture a successful terminal result.
    assert nodes["擂台挑战-关闭-页面"]["on_error"] == [FAILURE]

    battle_unknown = nodes["擂台挑战-战斗未知结果-结果"]
    assert battle_unknown["custom_action_param"]["status"] == "failed"
    assert battle_unknown["custom_action_param"]["error_code"] == (
        "RING_BATTLE_RESULT_UNKNOWN"
    )
    assert battle_unknown["custom_action_param"]["native_fail_after_record"] is True
    assert battle_unknown["Abort"] is True
    assert battle_unknown["next"] == ["公共-通用中止"]
    assert "on_error" not in battle_unknown


def test_r20_allowed_terminals_keep_explicit_business_postconditions() -> None:
    nodes = load_task_nodes(RING)

    assert_outcome(nodes, "MJA_RING_NOT_OPEN", "not_eligible", "ring.not_open")
    assert_outcome(
        nodes,
        "擂台挑战-次数-耗尽",
        "success",
        "ring.attempts_exhausted",
    )
    assert nodes["MJA_RING_NOT_OPEN_PROBE"]["recognition"]["param"]["all_of"] == [
        "擂台挑战-擂台-页面",
        "ring.not.open",
    ]
    assert nodes["擂台挑战-次数-探测"]["recognition"]["param"][
        "all_of"
    ] == ["擂台挑战-擂台-页面", "擂台挑战-擂台-次数-耗尽"]
