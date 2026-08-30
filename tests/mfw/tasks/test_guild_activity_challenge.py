from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_all_cycles_bounded, assert_native_failure_node
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

GUILD_ACTIVITY = TaskContract(
    "GUILD_ACTIVITY_CHALLENGE_DAILY",
    "daily/guild_activity_challenge_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / GUILD_ACTIVITY.pipeline_file


def _nodes() -> dict[str, dict]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_guild_activity_keeps_the_native_entry_and_cleanup_route() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    scoped = _nodes()
    entry = scoped[GUILD_ACTIVITY.entry]

    assert_task_contract(GUILD_ACTIVITY, require_game_start_recovery=False)
    assert entry["timeout"] == 5_000
    assert entry["on_error"] == [
        "MJA-任务入口失败-GUILD_ACTIVITY_CHALLENGE_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert_reachable(nodes, GUILD_ACTIVITY.entry, "1371-公共-原生成功-主页边界")
    assert_reachable(nodes, GUILD_ACTIVITY.entry, "1369-公共-通用停止")


def test_guild_activity_clicks_challenge_then_start_and_waits_for_battle() -> None:
    nodes = _nodes()
    title = nodes["0574-帮派活动挑战-帮派-挑战-准备-世界-首领-标题"]
    challenge = nodes["0533-帮派活动挑战-帮派-挑战-循环"]
    start = nodes["0537-帮派活动挑战-帮派-挑战-开始"]

    assert title["expected"] == ["世界首领", "公会讨伐", "幻境征讨", "幻境行"]
    assert challenge["next"] == ["0537-帮派活动挑战-帮派-挑战-开始"]
    assert challenge["custom_action_param"]["action_id"] == "challenge_guild_activity"
    assert start["custom_action_param"]["action_id"] == "start_guild_challenge"
    assert start["timeout"] == 300_000
    assert start["next"] == [
        "0583-帮派活动挑战-帮派-结果-胜利",
        "0584-帮派活动挑战-帮派-结果-失败-2",
    ]
    assert start["on_error"] == [
        "0590-帮派活动挑战-战斗结果-未知-失败"
    ]


def test_guild_activity_uses_only_zero_in_the_scoped_remaining_counter_as_completion() -> None:
    nodes = _nodes()
    available = nodes["0569-帮派活动挑战-帮派-剩余-可用"]
    zero = nodes["0570-帮派活动挑战-帮派-剩余-耗尽"]
    already_done = nodes["0527-帮派活动挑战-帮派-已完成-退出-活动"]

    assert available["expected"] == r"今日剩余征讨次数\s*[：:]\s*[12]\s*/\s*2"
    assert available["roi"] == [1000, 560, 280, 80]
    assert zero["expected"] == r"今日剩余征讨次数\s*[：:]\s*0\s*/\s*2"
    assert zero["roi"] == available["roi"]
    assert "0569-帮派活动挑战-帮派-剩余-可用" in nodes[
        "0533-帮派活动挑战-帮派-挑战-循环"
    ]["recognition"]["param"]["all_of"]
    assert "0570-帮派活动挑战-帮派-剩余-耗尽" in already_done[
        "recognition"
    ]["param"]["all_of"]
    assert already_done["next"] == ["0529-帮派活动挑战-帮派-已完成-退出-帮派-主页"]
    assert already_done["max_hit"] == 2
    assert already_done["custom_action_param"]["fixed_click_mode"] == (
        "guild_activity_close"
    )


def test_guild_activity_checks_zero_after_battle_cleanup_and_retries_only_bounded_challenge() -> None:
    nodes = _nodes()
    for name in (
        "0583-帮派活动挑战-帮派-结果-胜利",
        "0584-帮派活动挑战-帮派-结果-失败-2",
    ):
        assert nodes[name]["next"] == [
            "0547-帮派活动挑战-帮派-恭喜获得-关闭"
        ]
    close_reward = nodes["0547-帮派活动挑战-帮派-恭喜获得-关闭"]
    assert close_reward["max_hit"] == 3
    assert close_reward["next"] == [
        "0547-帮派活动挑战-帮派-恭喜获得-关闭",
        "0519-帮派活动挑战-零次-奖励检查",
        "[JumpBack]0533-帮派活动挑战-帮派-挑战-循环",
    ]
    assert close_reward["on_error"] == [
        "0519-帮派活动挑战-零次-奖励检查",
        "[JumpBack]0533-帮派活动挑战-帮派-挑战-循环",
    ]
    assert nodes["0533-帮派活动挑战-帮派-挑战-循环"]["max_hit"] == 2


def test_guild_activity_accepts_split_reward_popup_ocr() -> None:
    nodes = _nodes()
    assert nodes["0518-帮派活动挑战-帮派-恭喜获得-文案"]["expected"] == [
        "^恭喜获得$",
        "^喜获得$",
        "^战斗胜利$",
    ]

    defeat_reward = nodes["0591-帮派活动挑战-打开-击破奖励"]
    assert defeat_reward["next"] == [
        "0547-帮派活动挑战-帮派-恭喜获得-关闭",
        "0592-帮派活动挑战-关闭-击破奖励",
        "0519-帮派活动挑战-零次-奖励检查",
    ]
    assert defeat_reward["on_error"] == [
        "0610-帮派活动挑战-失败-返回主页",
    ]
    assert nodes["0592-帮派活动挑战-关闭-击破奖励"]["on_error"] == [
        "0610-帮派活动挑战-失败-返回主页",
    ]
    assert nodes["0519-帮派活动挑战-零次-奖励检查"]["on_error"] == [
        "0610-帮派活动挑战-失败-返回主页",
    ]
    assert nodes["0595-帮派活动挑战-关闭-征讨领取结果"]["post_delay"] >= 1000
    failure_cleanup = nodes["0610-帮派活动挑战-失败-返回主页"]
    assert failure_cleanup["custom_action"] == "ReturnToWorldHome"
    assert failure_cleanup["next"] == ["1365-公共-主页边界-失败"]
    assert failure_cleanup["on_error"] == ["1365-公共-主页边界-失败"]


def test_guild_activity_unknown_battle_result_is_native_failure() -> None:
    nodes = _nodes()
    assert_native_failure_node(nodes["0590-帮派活动挑战-战斗结果-未知-失败"])
    assert nodes["0582-帮派活动挑战-帮派-结果-页面"]["timeout"] == 30_000


def test_guild_activity_actions_are_guarded_and_cycles_are_bounded() -> None:
    nodes = load_task_nodes(GUILD_ACTIVITY)
    assert_guarded_actions(
        nodes,
        GUILD_ACTIVITY.task_id,
        [
            "open_function_panel",
            "open_guild",
            "open_guild_activity",
            "challenge_guild_activity",
            "start_guild_challenge",
            "dismiss_guild_activity_reward_popup",
            "open_guild_defeat_reward",
            "dismiss_guild_defeat_reward",
            "open_guild_conquest_reward",
            "claim_guild_conquest_reward",
            "dismiss_guild_conquest_reward",
            "close_guild_conquest_reward",
            "exit_guild_activity",
            "exit_guild_home",
            "close_function_panel",
        ],
    )
    for action_id in (
        "challenge_guild_activity",
        "start_guild_challenge",
        "dismiss_guild_activity_reward_popup",
        "open_guild_defeat_reward",
        "dismiss_guild_defeat_reward",
        "open_guild_conquest_reward",
        "claim_guild_conquest_reward",
        "dismiss_guild_conquest_reward",
        "close_guild_conquest_reward",
    ):
        assert_no_side_effect_retry(nodes, action_id)
    assert_all_cycles_bounded(nodes)


def test_guild_zero_counter_claims_defeat_then_conquest_rewards_when_red_dots_exist() -> None:
    nodes = _nodes()
    selector = nodes["0519-帮派活动挑战-零次-奖励检查"]
    assert selector["recognition"]["param"] == {
        "all_of": [
            "0566-帮派活动挑战-帮派-活动-页面",
            "0570-帮派活动挑战-帮派-剩余-耗尽",
        ],
        "box_index": 0,
    }
    assert selector["next"] == [
        "0591-帮派活动挑战-打开-击破奖励",
        "0593-帮派活动挑战-打开-征讨奖励",
        "0527-帮派活动挑战-帮派-已完成-退出-活动",
    ]
    assert nodes["0523-帮派活动挑战-帮派-打开-活动"]["next"][0] == (
        "0519-帮派活动挑战-零次-奖励检查"
    )

    for action_name, label_name, dot_name, action_id in (
        (
            "0591-帮派活动挑战-打开-击破奖励",
            "0598-帮派活动挑战-击破奖励-入口",
            "0599-帮派活动挑战-击破奖励-红点",
            "open_guild_defeat_reward",
        ),
        (
            "0593-帮派活动挑战-打开-征讨奖励",
            "0600-帮派活动挑战-征讨奖励-入口",
            "0601-帮派活动挑战-征讨奖励-红点",
            "open_guild_conquest_reward",
        ),
    ):
        action = nodes[action_name]
        assert action["recognition"]["param"] == {
            "all_of": [
                "0566-帮派活动挑战-帮派-活动-页面",
                "0570-帮派活动挑战-帮派-剩余-耗尽",
                label_name,
                dot_name,
            ],
            "box_index": 2,
        }
        assert action["custom_action_param"]["action_id"] == action_id
        assert action["max_hit"] == 1
        assert action["retry_times"] == 0

    for result_name in (
        "0592-帮派活动挑战-关闭-击破奖励",
        "0595-帮派活动挑战-关闭-征讨领取结果",
    ):
        result = nodes[result_name]
        assert result["recognition"]["param"] == {
            "all_of": ["0038-公共-已知-点击空白关闭"],
            "box_index": 0,
        }
        assert result["custom_action_param"]["evidence"]["page_name"] == (
            "0038-公共-已知-点击空白关闭"
        )

    claim = nodes["0594-帮派活动挑战-领取-征讨宝箱"]
    assert claim["recognition"]["param"] == {
        "all_of": [
            "0602-帮派活动挑战-征讨奖励-页面",
            "0603-帮派活动挑战-征讨奖励-第一排宝箱",
        ],
        "box_index": 1,
    }
    assert claim["custom_action_param"]["action_id"] == "claim_guild_conquest_reward"
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0
    assert nodes["0602-帮派活动挑战-征讨奖励-页面"] == {
        "recognition": "OCR",
        "expected": r"累计征讨\s*\d+\s*次",
        "roi": [300, 150, 450, 450],
        "action": "DoNothing",
    }
    assert nodes["0603-帮派活动挑战-征讨奖励-第一排宝箱"] == {
        "recognition": "ColorMatch",
        "lower": [180, 0, 0],
        "upper": [255, 120, 120],
        "roi": [940, 190, 70, 80],
        "connected": True,
        "count": 8,
        "order_by": "Area",
        "index": 0,
        "action": "DoNothing",
    }
    assert_reachable(nodes, "0519-帮派活动挑战-零次-奖励检查", "1371-公共-原生成功-主页边界")
