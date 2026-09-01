from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    load_task_nodes,
)


BATTLE_PASS = TaskContract(
    "BATTLE_PASS_REWARD_DAILY",
    "daily/battle_pass_reward_daily.json",
)
ONE_CLICK_NODE = "0057-战令奖励-基础-一键领取"
ONE_CLICK_TARGET = "0089-战令奖励-战斗-战令-基础-一键领取"


def test_battle_pass_prefers_explicit_one_click_reward_button() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    open_rewards = nodes["0054-战令奖励-打开-奖励"]
    claim = nodes[ONE_CLICK_NODE]
    target = nodes[ONE_CLICK_TARGET]

    assert open_rewards["next"] == [
        ONE_CLICK_NODE,
        "0056-战令奖励-基础-领取",
        "0063-战令奖励-关闭-成功",
    ]
    assert claim["recognition"]["param"] == {
        "all_of": [
            "0085-战令奖励-战斗-战令-奖励",
            ONE_CLICK_TARGET,
        ],
        "box_index": 1,
    }
    assert claim["custom_action_param"] == {
        "task_id": "BATTLE_PASS_REWARD_DAILY",
        "action_id": "claim_basic_one_click_reward",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0085-战令奖励-战斗-战令-奖励",
            "target_name": ONE_CLICK_TARGET,
        },
    }
    assert claim["next"] == ["0060-战令奖励-基础-关闭-奖励"]
    assert claim["on_error"] == ["0063-战令奖励-关闭-成功"]
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0

    assert target == {
        "recognition": "OCR",
        "expected": [
            "^一键领取$",
            "^一键领$",
            "^键领取$",
            "^领取$",
        ],
        "roi": [600, 610, 280, 100],
        "action": "DoNothing",
    }
    assert (
        TASK_POLICIES[BATTLE_PASS.task_id].action_caps[
            "claim_basic_one_click_reward"
        ]
        == 1
    )
    assert_no_side_effect_retry(nodes, "claim_basic_one_click_reward")
