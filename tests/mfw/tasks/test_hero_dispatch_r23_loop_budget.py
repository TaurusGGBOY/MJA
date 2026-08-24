from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, load_task_nodes


HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")


def test_dispatch_and_claim_loops_keep_declared_budgets() -> None:
    nodes = load_task_nodes(HERO)
    policy = TASK_POLICIES[HERO.task_id]

    assert nodes["0720-英雄派遣-初始-决策中"]["max_hit"] == 12
    assert nodes["0722-英雄派遣-初始-领取"]["max_hit"] == 12
    assert nodes["0724-英雄派遣-初始-选择"]["max_hit"] == 12
    assert nodes["0723-英雄派遣-初始-领取-动作"]["max_hit"] == 6
    assert nodes["0725-英雄派遣-领取-奖励-探测"]["max_hit"] == 6
    assert nodes["0726-英雄派遣-关闭-奖励"]["max_hit"] == 6
    assert nodes["0728-英雄派遣-配置"]["max_hit"] == 12
    assert nodes["0729-英雄派遣-发送"]["max_hit"] == 12

    assert policy.action_caps["select_first_visible_dispatch"] == 12
    assert policy.action_caps["claim_first_dispatch"] == 6
    assert policy.action_caps["close_reward_popup"] == 6
    assert policy.action_caps["smart_configure_team"] == 12
    assert policy.action_caps["dispatch_team"] == 12


def test_cleanup_and_native_terminal_nodes_are_single_shot() -> None:
    nodes = load_task_nodes(HERO)
    policy = TASK_POLICIES[HERO.task_id]
    for name, action_id in (
        ("0733-英雄派遣-关闭-派遣", "close_hero_dispatch"),
        ("0734-英雄派遣-关闭-画卷", "close_hero_dispatch_painting"),
    ):
        assert nodes[name]["max_hit"] == 1
        assert nodes[name]["retry_times"] == 0
        assert policy.action_caps[action_id] == 1
    assert nodes["0730-英雄派遣-成功-进度"]["max_hit"] == 1
    assert nodes["0731-英雄派遣-已完成-全部"]["max_hit"] == 1
    assert nodes["0727-英雄派遣-成功-领取"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
    }


def test_no_completion_or_elapsed_marker_uses_bounded_native_success_fallback() -> None:
    nodes = load_task_nodes(HERO)
    fallback = nodes["英雄派遣-之后-无-完成无耗时"]

    assert fallback["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0742-英雄派遣-英雄-派遣-页面",
                "0745-英雄派遣-英雄-首个-任务-无完成派遣",
                "0761-英雄派遣-英雄-首个-任务-无耗时",
            ],
            "box_index": 0,
        },
    }
    assert fallback["timeout"] == 5000
    assert fallback["next"] == ["0730-英雄派遣-成功-进度"]
    assert fallback["on_error"] == ["0730-英雄派遣-成功-进度"]
