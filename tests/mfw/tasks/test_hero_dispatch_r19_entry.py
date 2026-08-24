from __future__ import annotations

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    load_task_nodes,
)


ROOT = Path(__file__).parents[3]
HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / HERO.pipeline_file
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_r19_home_entry_keeps_both_painting_entry_modes() -> None:
    nodes = load_task_nodes(HERO)
    assert nodes["0714-英雄派遣-主页-探测"]["next"] == [
        "0715-英雄派遣-打开-画卷-世界",
        "英雄派遣-打开-画卷",
    ]

    world_entry = nodes["0715-英雄派遣-打开-画卷-世界"]
    traditional_entry = nodes["英雄派遣-打开-画卷"]
    assert world_entry["custom_action_param"]["action_id"] == (
        "open_painting_scroll"
    )
    assert traditional_entry["custom_action_param"]["action_id"] == (
        "open_painting_scroll"
    )
    assert traditional_entry["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "0736-英雄派遣-英雄-主页-页面",
        "target_name": "英雄派遣-画卷-滚动-入口",
    }
    assert traditional_entry["max_hit"] == 1
    assert traditional_entry["retry_times"] == 0
    assert nodes["英雄派遣-画卷-滚动-入口"] == {
        "recognition": "OCR",
        "expected": "^画卷$",
        "roi": [70, 10, 95, 60],
        "action": "DoNothing",
    }

    for name, observed in {
        "0737-英雄派遣-画卷-滚动-入口-世界": [1080, 0, 40, 20],
        "英雄派遣-画卷-滚动-入口": [91, 27, 46, 27],
        "0741-英雄派遣-英雄-派遣-入口": [1006, 648, 86, 28],
    }.items():
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert _contains(node["roi"], observed)
        if name != "0737-英雄派遣-画卷-滚动-入口-世界":
            assert node["roi"][2] * node["roi"][3] < FRAME_WIDTH * FRAME_HEIGHT // 50


def test_initial_complete_and_actionable_entries_remain_distinct() -> None:
    nodes = load_task_nodes(HERO)
    assert nodes["0718-英雄派遣-初始-已完成决策"]["next"] == [
        "0719-英雄派遣-初始-就已完成",
        "0720-英雄派遣-初始-决策中",
    ]
    assert nodes["0720-英雄派遣-初始-决策中"]["next"] == [
        "[JumpBack]0722-英雄派遣-初始-领取",
        "[JumpBack]0724-英雄派遣-初始-选择",
        "英雄派遣-初始-无-任务",
        "0721-英雄派遣-非初始-已完成",
        "英雄派遣-之后-无-完成无耗时",
    ]
    assert nodes["0719-英雄派遣-初始-就已完成"]["next"] == [
        "0731-英雄派遣-已完成-全部"
    ]
    assert nodes["0721-英雄派遣-非初始-已完成"]["next"] == [
        "0730-英雄派遣-成功-进度"
    ]


def test_no_dispatch_markers_are_same_frame_and_converge_on_native_cleanup() -> None:
    nodes = load_task_nodes(HERO)
    marker = nodes["0753-英雄派遣-英雄-无-派遣-任务"]
    assert marker["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0742-英雄派遣-英雄-派遣-页面",
                "0748-英雄派遣-英雄-零-派遣-任务",
                "0749-英雄派遣-英雄-零-已完成-派遣任务",
                "0752-英雄派遣-英雄-无-已选择-派遣-任务",
            ],
            "box_index": 1,
        },
    }
    assert nodes["0748-英雄派遣-英雄-零-派遣-任务"]["expected"] == (
        r"任务\s*[:：]?\s*0\s*/\s*12"
    )
    assert nodes["0749-英雄派遣-英雄-零-已完成-派遣任务"]["expected"] == (
        r"已完成\s*[:：]?\s*0"
    )
    assert nodes["0752-英雄派遣-英雄-无-已选择-派遣-任务"]["expected"] == (
        "尚未选择派遣任务"
    )
    for name in ("英雄派遣-初始-无-任务", "英雄派遣-之后-无-任务"):
        assert nodes[name]["next"] == ["英雄派遣-成功-无-任务"]
    assert nodes["英雄派遣-成功-无-任务"]["next"] == [
        "0733-英雄派遣-关闭-派遣"
    ]


def test_dispatch_inputs_have_no_recorder_retry_and_keep_policy_caps() -> None:
    nodes = load_task_nodes(HERO)
    policy = TASK_POLICIES[HERO.task_id]
    for action_id in (
        "select_first_visible_dispatch",
        "claim_first_dispatch",
        "smart_configure_team",
        "dispatch_team",
    ):
        assert_no_side_effect_retry(nodes, action_id)
    assert nodes["0722-英雄派遣-初始-领取"]["max_hit"] == 12
    assert nodes["0724-英雄派遣-初始-选择"]["max_hit"] == 12
    assert nodes["0723-英雄派遣-初始-领取-动作"]["max_hit"] == 6
    assert nodes["0728-英雄派遣-配置"]["max_hit"] == 12
    assert nodes["0729-英雄派遣-发送"]["max_hit"] == 12
    assert nodes["0728-英雄派遣-配置"]["on_error"] == ["0729-英雄派遣-发送"]
    assert policy.action_caps["select_first_visible_dispatch"] == 12
    assert policy.action_caps["claim_first_dispatch"] == 6
    assert policy.action_caps["smart_configure_team"] == 12
    assert policy.action_caps["dispatch_team"] == 12


def test_r19_pipeline_has_no_custom_outcome_or_legacy_abort_route() -> None:
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert_no_custom_outcome_nodes(pipeline)
    assert_on_error_contract(
        pipeline,
        local_nodes=set(pipeline),
        shared_targets={"1372-公共-原生成功-尝试返回"},
    )
    encoded = json.dumps(pipeline, ensure_ascii=False)
    assert "RecordTaskOutcome" not in encoded
    assert "1363-公共-主页边界" not in encoded
    assert "1366-公共-通用中止" not in encoded
