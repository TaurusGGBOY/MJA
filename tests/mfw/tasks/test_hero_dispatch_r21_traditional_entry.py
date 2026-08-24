from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract, load_task_nodes


ROOT = Path(__file__).parents[3]
HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / HERO.pipeline_file


def _hero_edges(node: dict[str, Any]) -> tuple[str, ...]:
    edges: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, ())
        if isinstance(value, list):
            edges.extend(
                item
                for item in value
                if isinstance(item, str) and item.startswith("英雄派遣-")
            )
    return tuple(edges)


def test_r21_painting_ocr_uses_tight_same_frame_markers() -> None:
    nodes = load_task_nodes(HERO)
    assert nodes["0738-英雄派遣-画卷-页面"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0739-英雄派遣-画卷-页面-标题",
                "0740-英雄派遣-画卷-页面-偃武-世界",
            ],
            "box_index": 0,
        },
    }
    assert nodes["0739-英雄派遣-画卷-页面-标题"]["expected"] == "画卷"
    assert nodes["0740-英雄派遣-画卷-页面-偃武-世界"]["expected"] == "偃武世界"
    assert nodes["0741-英雄派遣-英雄-派遣-入口"]["expected"] == (
        "(?:侠客派遣|俠客派遣)"
    )


def test_r21_dispatch_entry_is_page_bounded_and_single_shot() -> None:
    nodes = load_task_nodes(HERO)
    entry = nodes["0716-英雄派遣-打开-派遣"]

    assert entry["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["0738-英雄派遣-画卷-页面", "0741-英雄派遣-英雄-派遣-入口"],
            "box_index": 1,
        },
    }
    assert entry["custom_action"] == "GuardedInput"
    assert entry["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0738-英雄派遣-画卷-页面",
        "target_name": "0741-英雄派遣-英雄-派遣-入口",
    }
    assert entry["timeout"] == 8000
    assert entry["max_hit"] == 1
    assert entry["retry_times"] == 0
    assert TASK_POLICIES[HERO.task_id].action_caps["open_hero_dispatch"] == 1


def test_r21_startup_and_page_recovery_have_no_recorder_cycle() -> None:
    nodes = load_task_nodes(HERO)
    start = nodes[HERO.entry]
    assert start["next"] == ["0714-英雄派遣-主页-探测"]
    assert start["timeout"] == 5000
    assert start["on_error"] == [
        "MJA-任务入口失败-HERO_DISPATCH_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert all("0732-英雄派遣-记录-失败" not in _hero_edges(node) for node in nodes.values())
    assert nodes["0714-英雄派遣-主页-探测"]["next"] == [
        "0715-英雄派遣-打开-画卷-世界",
        "英雄派遣-打开-画卷",
    ]
    assert nodes["0715-英雄派遣-打开-画卷-世界"]["next"] == [
        "0716-英雄派遣-打开-派遣"
    ]
    assert nodes["英雄派遣-打开-画卷"]["next"] == [
        "0716-英雄派遣-打开-派遣"
    ]


def test_r21_native_success_cleanup_is_best_effort_and_bounded() -> None:
    nodes = load_task_nodes(HERO)
    for node_name, action_id in (
        ("0733-英雄派遣-关闭-派遣", "close_hero_dispatch"),
        ("0734-英雄派遣-关闭-画卷", "close_hero_dispatch_painting"),
    ):
        node = nodes[node_name]
        assert node["custom_action"] == "GuardedInput"
        assert node["custom_action_param"]["action_id"] == action_id
        assert node["max_hit"] == 1
        assert node["retry_times"] == 0
    assert nodes["0733-英雄派遣-关闭-派遣"]["on_error"] == [
        "0734-英雄派遣-关闭-画卷",
        "0735-英雄派遣-主页边界-探测",
    ]
    assert nodes["0734-英雄派遣-关闭-画卷"]["on_error"] == [
        "0735-英雄派遣-主页边界-探测"
    ]
    assert nodes["0735-英雄派遣-主页边界-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert nodes["0735-英雄派遣-主页边界-探测"]["on_error"] == [
        "1372-公共-原生成功-尝试返回"
    ]


def test_r21_pipeline_uses_native_terminal_contract() -> None:
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert_no_custom_outcome_nodes(pipeline)
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={"1372-公共-原生成功-尝试返回"},
    )
    assert pipeline["0727-英雄派遣-成功-领取"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
    }
    assert pipeline["0730-英雄派遣-成功-进度"]["action"] == "DoNothing"
    assert pipeline["0731-英雄派遣-已完成-全部"]["action"] == "DoNothing"
