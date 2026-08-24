from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract, load_task_declaration
from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes

ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"
PIPELINE_PATH = PIPELINE_ROOT / "daily/break_array_martial_daily.json"
ENTRY_RECOVERY_PATH = PIPELINE_ROOT / "common/task_entry_recovery.json"
GAME_START_PATH = PIPELINE_ROOT / "startup/game_start.json"
TASK = TaskContract("BREAK_ARRAY_MARTIAL_DAILY", "daily/break_array_martial_daily.json")
FIXTURE_ROOT = ROOT / "tests/fixtures/BREAK_ARRAY_MARTIAL_DAILY"


def _load_pipeline() -> dict[str, dict]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_task_declaration_and_entry_are_native_mfw_contract() -> None:
    declaration = load_task_declaration(TASK.task_id)
    nodes = _load_pipeline()

    assert declaration["entry"] == "0002-破阵武学-任务入口"
    entry = nodes[declaration["entry"]]
    assert entry["action"] == "Custom"
    assert entry["custom_action"] == "BeginTask"
    assert entry["custom_action_param"] == {"task_id": TASK.task_id}
    assert "BreakArrayMartialDailyAction" not in json.dumps(nodes, ensure_ascii=False)


def test_entry_failure_uses_one_bounded_restart_before_native_failure() -> None:
    nodes = _load_pipeline()
    entry = nodes["0002-破阵武学-任务入口"]
    recovery_name = "MJA-任务入口失败-BREAK_ARRAY_MARTIAL_DAILY"

    assert entry["on_error"] == [
        recovery_name,
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert nodes[recovery_name] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "max_hit": 1,
        "timeout": 5000,
        "on_error": ["MJA-公共-任务入口-恢复耗尽"],
        "next": [
            "[JumpBack]MJA-公共-任务入口-重启游戏",
            "0002-破阵武学-任务入口",
        ],
    }

    shared = json.loads(ENTRY_RECOVERY_PATH.read_text(encoding="utf-8"))
    assert shared["MJA-公共-任务入口-重启游戏"] == {
        "recognition": "DirectHit",
        "action": "StopApp",
        "package": "com.hanjiasongshu.dr22",
        "max_hit": 1,
        "timeout": 5000,
        "next": ["0023-启动-游戏入口"],
    }
    assert shared["MJA-公共-任务入口-恢复耗尽"]["custom_action"] == "FailTask"
    assert shared["MJA-公共-任务入口-恢复耗尽"]["Abort"] is True

    startup = json.loads(GAME_START_PATH.read_text(encoding="utf-8"))
    assert startup["0023-启动-游戏入口"]["next"] == ["1356-启动-游戏启动"]
    assert startup["1356-启动-游戏启动"]["action"] == "StartApp"
    assert startup["1356-启动-游戏启动"]["repeat"] == 5
    assert startup["1356-启动-游戏启动"]["next"][-1] == "1362-启动-游戏就绪"


def test_pipeline_has_native_terminals_and_no_legacy_outcome_routes() -> None:
    nodes = _load_pipeline()

    assert_no_custom_outcome_nodes(nodes)
    assert_on_error_contract(
        nodes,
        local_nodes=set(nodes),
        shared_targets={"1365-公共-主页边界-失败"},
    )
    assert not validate_nodes(load_pipeline_nodes(PIPELINE_ROOT))

    for name in (
        "0126-破阵武学-不符合条件",
        "0131-破阵武学-战斗-失败",
        "0132-破阵武学-战斗-未知-结果",
        "0133-破阵武学-战斗-循环-耗尽",
        "0134-破阵武学-结果-循环-耗尽",
        "0135-破阵武学-安全-停止",
    ):
        assert_native_failure_node(nodes[name])

    assert nodes["0124-破阵武学-成功"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "next": ["0127-破阵武学-完成-收尾"],
    }
    assert nodes["0125-破阵武学-已完成"] == nodes["0124-破阵武学-成功"]
    assert nodes["0130-破阵武学-完成-主页-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]

    close_page = nodes["0128-破阵武学-完成-关闭-阵法"]
    assert close_page["recognition"]["param"] == {
        "all_of": ["0143-破阵武学-突破-阵法-页面"],
        "box_index": 0,
    }
    assert close_page["custom_action_param"]["fixed_click_mode"] == (
        "break_array_page_close"
    )
    assert close_page["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 0,
        "page_name": "0143-破阵武学-突破-阵法-页面",
        "target_name": "0143-破阵武学-突破-阵法-页面",
    }

    close_activity = nodes["0129-破阵武学-完成-关闭-活动"]
    assert close_activity["recognition"]["param"] == {
        "all_of": ["0139-破阵武学-活动-页面"],
        "box_index": 0,
    }
    assert close_activity["custom_action_param"]["fixed_click_mode"] == (
        "break_array_activity_close"
    )


def test_challenge_battle_and_result_loops_keep_explicit_bounds() -> None:
    nodes = _load_pipeline()

    assert nodes["0108-破阵武学-挑战-循环"]["max_hit"] == 9
    assert nodes["0114-破阵武学-战斗-加载-循环"]["max_hit"] == 360
    assert nodes["0115-破阵武学-战斗-循环"]["max_hit"] == 360
    assert nodes["0114-破阵武学-战斗-加载-循环"]["post_delay"] == 3000
    assert nodes["0115-破阵武学-战斗-循环"]["post_delay"] == 3000
    assert nodes["0119-破阵武学-结果-循环"]["max_hit"] == 9
    for name in (
        "0108-破阵武学-挑战-循环",
        "0114-破阵武学-战斗-加载-循环",
        "0115-破阵武学-战斗-循环",
        "0119-破阵武学-结果-循环",
    ):
        assert nodes[name]["retry_times"] == 0


def test_only_zero_of_nine_can_finish_the_task() -> None:
    nodes = _load_pipeline()

    assert "0106-破阵武学-已完成-探测" not in nodes
    assert "0122-破阵武学-已完成-之后-结果-探测" not in nodes
    assert "0158-破阵武学-突破-阵法-已完成" not in nodes
    assert nodes["0103-破阵武学-页面-探测"]["next"] == [
        "0104-破阵武学-安全-探测",
        "0105-破阵武学-不可用-探测",
        "0107-破阵武学-剩余-耗尽-探测",
        "0116-破阵武学-结果-探测",
        "0108-破阵武学-挑战-循环",
    ]
    assert nodes["0104-破阵武学-安全-探测"]["on_error"] == [
        "0105-破阵武学-不可用-探测",
        "0107-破阵武学-剩余-耗尽-探测",
        "0116-破阵武学-结果-探测",
        "0108-破阵武学-挑战-循环",
    ]
    assert nodes["0121-破阵武学-结果后-探测"]["next"] == [
        "0123-破阵武学-剩余-耗尽-之后-结果-探测",
        "0108-破阵武学-挑战-循环",
    ]
    assert nodes["0157-破阵武学-突破-阵法-剩余-耗尽"]["expected"] == [
        "(?:(?:今日)?剩余挑战次数|今日剩余|剩余|挑战次数)\\s*[:：]?\\s*0\\s*/\\s*9",
        "^0\\s*/\\s*9$",
    ]


def test_prepare_fixture_matches_native_pipeline_recognizers() -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "r20_prepare_page.json").read_text(encoding="utf-8")
    )
    nodes = _load_pipeline()

    for name in (
        "0160-破阵武学-突破-阵法-准备-阵容",
        "0161-破阵武学-突破-阵法-准备-首领",
        "0162-破阵武学-突破-阵法-准备-时长",
        "0163-破阵武学-突破-阵法-准备-战术",
    ):
        assert re.fullmatch(nodes[name]["expected"], fixture["recognitions"][name]["text"])

    start = fixture["recognitions"]["0164-破阵武学-突破-阵法-准备-开始"]
    assert start["color_count"] >= nodes["0164-破阵武学-突破-阵法-准备-开始"]["count"]
    assert not any(
        re.fullmatch(pattern, text)
        for pattern in nodes["0167-破阵武学-突破-阵法-战斗"]["expected"]
        for text in fixture["recognitions"]["0167-破阵武学-突破-阵法-战斗"]["texts"]
    )


def test_confirm_transition_fixture_is_diagnostic_only() -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "r21_confirm_transition.json").read_text(encoding="utf-8")
    )
    observations = fixture["observations"]
    assert observations["dark_field_count"] >= observations["dark_field_threshold"]
    assert max(observations["rumor_glyph_counts"]) < observations["rumor_glyph_threshold"]
    assert observations["prepare_page"] is False
    assert observations["battle"] is False
    assert observations["prepare_start"] is False
    assert fixture["action_trace"] == [
        "open_break_array_activity",
        "open_break_array",
        "start_break_array_challenge",
        "confirm_break_array_challenge",
    ]


def test_victory_fixture_keeps_same_frame_anchors_and_native_cleanup() -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "r22_victory.json").read_text(encoding="utf-8")
    )
    nodes = _load_pipeline()

    for name in (
        "0171-破阵武学-突破-阵法-结果-胜利-标题",
        "0172-破阵武学-突破-阵法-结果-标识",
    ):
        observed = fixture["recognitions"][name]
        assert re.fullmatch(nodes[name]["expected"], observed["text"])
        rx, ry, rw, rh = nodes[name]["roi"]
        bx, by, bw, bh = observed["box"]
        assert rx <= bx and ry <= by
        assert bx + bw <= rx + rw and by + bh <= ry + rh

    expected = [
        "0171-破阵武学-突破-阵法-结果-胜利-标题",
        "0172-破阵武学-突破-阵法-结果-标识",
    ]
    for name in ("0168-破阵武学-突破-阵法-结果", "0170-破阵武学-突破-阵法-成功"):
        assert nodes[name]["recognition"]["param"] == {
            "all_of": expected,
            "box_index": 0,
        }
    dismiss = nodes["0120-破阵武学-关闭-结果"]
    assert dismiss["recognition"]["param"] == {
        "all_of": ["0168-破阵武学-突破-阵法-结果"],
        "box_index": 0,
    }
    assert dismiss["custom_action_param"] == {
        "task_id": "BREAK_ARRAY_MARTIAL_DAILY",
        "action_id": "dismiss_break_array_result",
        "kind": "click",
        "fixed_click_mode": "break_array_victory_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 0,
            "page_name": "0168-破阵武学-突破-阵法-结果",
            "target_name": "0168-破阵武学-突破-阵法-结果",
        },
    }
    assert nodes["0130-破阵武学-完成-主页-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]


def test_selected_break_array_label_roi_covers_live_720p_position() -> None:
    """The selected label moved up after the activity-list layout changed."""
    node = _load_pipeline()["0142-破阵武学-突破-阵法-已选择-入口"]
    rx, ry, rw, rh = node["roi"]
    bx, by, bw, bh = (56, 346, 84, 23)

    assert rx <= bx and ry <= by
    assert bx + bw <= rx + rw and by + bh <= ry + rh


def test_victory_brand_anchor_accepts_live_short_ocr_without_leaving_brand_roi() -> None:
    node = _load_pipeline()["0172-破阵武学-突破-阵法-结果-标识"]
    assert re.fullmatch(node["expected"], "决·剑之川")
    assert node["roi"] == [160, 100, 960, 420]

    rx, ry, rw, rh = node["roi"]
    for bx, by, bw, bh in ((1004, 247, 111, 13), (1016, 247, 99, 13)):
        assert rx <= bx and ry <= by
        assert bx + bw <= rx + rw and by + bh <= ry + rh


def test_fixture_archive_hashes_remain_read_only_evidence() -> None:
    for filename in (
        "r20_prepare_page.json",
        "r21_confirm_transition.json",
        "r22_victory.json",
    ):
        fixture = json.loads((FIXTURE_ROOT / filename).read_text(encoding="utf-8"))
        archived = ROOT / fixture["source"]
        if archived.is_file():
            assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]
