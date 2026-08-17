from __future__ import annotations

from tests.mfw.task_contract import TaskContract, load_task_nodes


HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")


def test_claim_branch_uses_the_visible_bottom_right_claim_button() -> None:
    nodes = load_task_nodes(HERO)
    claim = nodes["英雄派遣-初始-领取"]

    assert claim["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "英雄派遣-英雄-派遣-页面",
                "英雄派遣-英雄-首个-任务-可领取",
            ],
            "box_index": 1,
        },
    }
    assert claim["custom_action_param"] == {
        "task_id": HERO.task_id,
        "action_id": "select_first_visible_dispatch",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "英雄派遣-英雄-派遣-页面",
            "target_name": "英雄派遣-英雄-首个-任务-可领取",
        },
    }
    assert claim["next"] == ["英雄派遣-初始-领取-动作"]
    claim_button = nodes["英雄派遣-初始-领取-动作"]
    assert claim_button["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "英雄派遣-英雄-派遣-页面",
                "英雄派遣-英雄-领取-按钮",
            ],
            "box_index": 1,
        },
    }
    assert claim_button["custom_action_param"]["action_id"] == (
        "claim_first_dispatch"
    )
    assert claim_button["next"] == ["英雄派遣-领取-奖励-探测"]
    assert nodes["英雄派遣-英雄-首个-任务-可领取"]["expected"] == "完成派遣"
    assert nodes["英雄派遣-英雄-首个-任务-可派遣"]["expected"] == [
        "耗时",
        "派遣(?!中)",
    ]


def test_claim_records_success_and_closes_the_dispatch_surface() -> None:
    nodes = load_task_nodes(HERO)

    success = nodes["英雄派遣-成功-领取"]
    assert success["action"] == "Custom"
    assert success["custom_action"] == "RecordTaskOutcome"
    assert success["custom_action_param"] == {
        "task_id": HERO.task_id,
        "status": "success",
        "postcondition": "hero.claim_state_known",
        "defer_home_boundary": True,
    }
    assert success["next"] == ["英雄派遣-关闭-派遣"]
    assert nodes["英雄派遣-关闭-派遣"]["next"] == ["英雄派遣-关闭-画卷"]
    assert nodes["英雄派遣-关闭-画卷"]["next"] == ["英雄派遣-主页边界-探测"]
    assert nodes["英雄派遣-主页边界-探测"]["next"] == ["公共-主页边界"]
