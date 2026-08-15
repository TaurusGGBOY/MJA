from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, load_task_nodes


HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")


def test_dispatch_fill_loop_body_can_repeat_to_its_declared_cap() -> None:
    nodes = load_task_nodes(HERO)
    policy = TASK_POLICIES[HERO.task_id]
    loop_cap = nodes["英雄派遣-填充-循环"]["max_hit"]

    assert loop_cap == 6
    assert policy.action_caps["smart_configure_team"] == loop_cap
    assert policy.action_caps["dispatch_team"] == loop_cap

    for name in (
        "英雄派遣-之后-选择",
        "英雄派遣-配置",
        "英雄派遣-发送",
    ):
        assert nodes[name]["max_hit"] == loop_cap, name
