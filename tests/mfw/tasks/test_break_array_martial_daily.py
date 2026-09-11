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
from agent.custom.support.policy import TASK_POLICIES
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


def test_zero_of_nine_or_defeat_threshold_can_finish_the_task() -> None:
    nodes = _load_pipeline()

    assert "0122-破阵武学-已完成-之后-结果-探测" not in nodes
    assert "0158-破阵武学-突破-阵法-已完成" not in nodes
    assert nodes["0103-破阵武学-页面-探测"]["next"] == [
        "0104-破阵武学-安全-探测",
        "0105-破阵武学-不可用-探测",
        "0190-破阵武学-当前击败人数-达到2500-探测",
        "0107-破阵武学-剩余-耗尽-探测",
        "0116-破阵武学-结果-探测",
        "0108-破阵武学-挑战-循环",
    ]
    assert nodes["0104-破阵武学-安全-探测"]["on_error"] == [
        "0105-破阵武学-不可用-探测",
        "0190-破阵武学-当前击败人数-达到2500-探测",
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


def test_2500_completion_marker_is_native_success() -> None:
    nodes = _load_pipeline()

    probe = nodes["0190-破阵武学-当前击败人数-达到2500-探测"]
    marker = nodes["0191-破阵武学-当前击败人数"]

    assert probe["next"] == ["0125-破阵武学-已完成"]
    assert probe["on_error"] == ["0107-破阵武学-剩余-耗尽-探测"]
    assert probe["recognition"] == {
        "type": "And",
        "param": {"all_of": ["0191-破阵武学-当前击败人数"]},
    }
    assert marker["recognition"] == "OCR"
    assert re.fullmatch(marker["expected"], "2500")
    assert re.fullmatch(marker["expected"], "2719")
    assert not re.fullmatch(marker["expected"], "2450")
    assert marker["roi"] == [160, 620, 200, 100]


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
    bx, by, bw, bh = (58, 467, 90, 24)

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


def test_activity_probe_scrolls_once_when_break_array_is_below_visible_list() -> None:
    nodes = _load_pipeline()
    policy = TASK_POLICIES["BREAK_ARRAY_MARTIAL_DAILY"]
    home_probe = nodes["0099-破阵武学-主页-探测"]
    open_activity = nodes["0100-破阵武学-打开-活动"]
    activity_probe = nodes["0101-破阵武学-活动-探测"]
    scroll = nodes["0106-破阵武学-活动-滚动-一次"]
    activity_page = nodes["0180-破阵武学-活动-列表-页面"]

    assert home_probe["on_error"] == ["0106-破阵武学-活动-滚动-一次"]
    assert open_activity["next"] == ["0106-破阵武学-活动-滚动-一次"]
    assert "on_error" not in activity_probe
    assert nodes["0138-破阵武学-活动-入口"]["roi"] == [780, 20, 180, 100]
    assert policy.action_caps["scroll_break_array_activity"] == 1
    assert activity_page["expected"] == ["成长基金", "成长", "装扮上新"]
    assert activity_page["roi"] == [0, 0, 400, 600]
    assert scroll["recognition"]["param"] == {
        "all_of": [
            "0180-破阵武学-活动-列表-页面",
            "0181-破阵武学-活动-列表-滚动-目标",
        ],
        "box_index": 1,
    }
    target = nodes["0181-破阵武学-活动-列表-滚动-目标"]
    assert target["expected"] == [
        "装扮上新",
        "武库臻选",
        "韬略演武",
        "累充有礼",
        "武道玄境",
    ]
    assert target["roi"] == [0, 320, 200, 280]
    rx, ry, rw, rh = target["roi"]
    for bx, by, bw, bh in (
        (61, 347, 78, 21),  # observed 武库臻选
        (61, 345, 79, 24),  # observed 韬略演武
        (61, 424, 79, 27),  # observed 累充有礼
        (63, 509, 75, 18),  # observed 武道玄境
    ):
        assert rx <= bx and ry <= by
        assert bx + bw <= rx + rw and by + bh <= ry + rh
        assert by + bh // 2 - 300 >= 0

    assert scroll["custom_action_param"]["evidence"]["dy"] == -300
    assert scroll["custom_action_param"]["evidence"]["duration_ms"] == 500
    assert scroll["next"] == ["0192-破阵武学-活动-列表-打开-破阵演武"]
    assert scroll["on_error"] == [
        "0194-破阵武学-活动-列表-滚动-二次",
        "0135-破阵武学-安全-停止",
    ]

    open_item = nodes["0192-破阵武学-活动-列表-打开-破阵演武"]
    assert open_item["recognition"]["param"] == {
        "all_of": [
            "0180-破阵武学-活动-列表-页面",
            "0193-破阵武学-活动-列表-破阵演武-入口",
        ],
        "box_index": 1,
    }
    assert open_item["custom_action_param"] == {
        "task_id": "BREAK_ARRAY_MARTIAL_DAILY",
        "action_id": "open_break_array_activity_item",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0180-破阵武学-活动-列表-页面",
            "target_name": "0193-破阵武学-活动-列表-破阵演武-入口",
        },
    }
    assert open_item["next"] == ["0101-破阵武学-活动-探测"]
    assert "on_error" not in open_item

    activity_item = nodes["0193-破阵武学-活动-列表-破阵演武-入口"]
    assert activity_item["expected"] == ["破阵演武", "破阵"]
    assert activity_item["roi"] == [0, 0, 200, 600]

    second_scroll = nodes["0194-破阵武学-活动-列表-滚动-二次"]
    assert second_scroll["recognition"]["param"] == {
        "all_of": [
            "0180-破阵武学-活动-列表-页面",
            "0195-破阵武学-活动-列表-二次滚动-底部锚点",
        ],
        "box_index": 1,
    }
    assert second_scroll["custom_action_param"]["action_id"] == (
        "scroll_break_array_activity_second"
    )
    assert second_scroll["custom_action_param"]["evidence"]["target_name"] == (
        "0195-破阵武学-活动-列表-二次滚动-底部锚点"
    )
    assert second_scroll["custom_action_param"]["evidence"]["dy"] == -300
    assert second_scroll["next"] == ["0192-破阵武学-活动-列表-打开-破阵演武"]
    assert second_scroll["on_error"] == [
        "0197-破阵武学-活动-列表-反向滚动-一次",
        "0135-破阵武学-安全-停止",
    ]
    assert policy.action_caps["open_break_array_activity_item"] == 1
    assert policy.action_caps["scroll_break_array_activity_second"] == 1
    assert policy.action_caps["scroll_break_array_activity_reverse"] == 1

    bottom_anchor = nodes["0195-破阵武学-活动-列表-二次滚动-底部锚点"]
    assert bottom_anchor["expected"] == "装扮上新"
    assert bottom_anchor["roi"] == [0, 500, 200, 100]

    reverse_scroll = nodes["0197-破阵武学-活动-列表-反向滚动-一次"]
    assert reverse_scroll["recognition"]["param"] == {
        "all_of": [
            "0180-破阵武学-活动-列表-页面",
            "0198-破阵武学-活动-列表-反向滚动-顶部锚点",
        ],
        "box_index": 1,
    }
    assert reverse_scroll["custom_action_param"]["evidence"]["dy"] == 300
    assert reverse_scroll["next"] == ["0192-破阵武学-活动-列表-打开-破阵演武"]
    assert reverse_scroll["on_error"] == ["0135-破阵武学-安全-停止"]

    top_anchor = nodes["0198-破阵武学-活动-列表-反向滚动-顶部锚点"]
    assert top_anchor["expected"] == ["江湖试炼", "启程基金", "江湖棋摊"]
    assert top_anchor["roi"] == [0, 120, 200, 180]
