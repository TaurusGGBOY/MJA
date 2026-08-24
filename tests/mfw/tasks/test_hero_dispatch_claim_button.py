from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract, load_task_nodes


ROOT = Path(__file__).parents[3]
HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / HERO.pipeline_file


def test_claim_branch_uses_the_visible_bottom_right_claim_button() -> None:
    nodes = load_task_nodes(HERO)
    claim = nodes["0722-英雄派遣-初始-领取"]

    assert claim["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0742-英雄派遣-英雄-派遣-页面",
                "0743-英雄派遣-英雄-首个-任务-可领取",
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
            "page_name": "0742-英雄派遣-英雄-派遣-页面",
            "target_name": "0743-英雄派遣-英雄-首个-任务-可领取",
        },
    }
    assert claim["next"] == ["0723-英雄派遣-初始-领取-动作"]

    claim_button = nodes["0723-英雄派遣-初始-领取-动作"]
    assert claim_button["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0742-英雄派遣-英雄-派遣-页面",
                "0754-英雄派遣-英雄-领取-按钮",
            ],
            "box_index": 1,
        },
    }
    assert claim_button["custom_action_param"]["action_id"] == (
        "claim_first_dispatch"
    )
    assert claim_button["next"] == ["0725-英雄派遣-领取-奖励-探测"]
    assert "on_error" not in claim_button
    assert nodes["0743-英雄派遣-英雄-首个-任务-可领取"]["expected"] == "完成"
    assert nodes["0746-英雄派遣-英雄-首个-任务-可派遣"]["expected"] == "耗时"


def test_claim_success_closes_dispatch_before_native_success() -> None:
    nodes = load_task_nodes(HERO)
    success = nodes["0727-英雄派遣-成功-领取"]

    assert success == {
        "recognition": "DirectHit",
        "action": "DoNothing",
    }


def test_each_row_action_returns_to_the_dispatch_decision_loop() -> None:
    nodes = load_task_nodes(HERO)

    assert "next" not in nodes["0727-英雄派遣-成功-领取"]
    assert "next" not in nodes["0729-英雄派遣-发送"]


def test_hero_pipeline_has_only_native_terminals_and_cleanup_on_error() -> None:
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    assert_no_custom_outcome_nodes(pipeline)
    assert "0732-英雄派遣-记录-失败" not in pipeline
    assert "1363-公共-主页边界" not in json.dumps(pipeline, ensure_ascii=False)
    assert "1366-公共-通用中止" not in json.dumps(pipeline, ensure_ascii=False)
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={"1372-公共-原生成功-尝试返回"},
    )

    assert pipeline["0730-英雄派遣-成功-进度"]["action"] == "DoNothing"
    assert pipeline["0731-英雄派遣-已完成-全部"]["action"] == "DoNothing"
    assert pipeline["0730-英雄派遣-成功-进度"]["next"] == [
        "0733-英雄派遣-关闭-派遣"
    ]
    assert pipeline["0731-英雄派遣-已完成-全部"]["next"] == [
        "0733-英雄派遣-关闭-派遣"
    ]
    assert pipeline["0735-英雄派遣-主页边界-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert pipeline["0735-英雄派遣-主页边界-探测"]["on_error"] == [
        "1372-公共-原生成功-尝试返回"
    ]
