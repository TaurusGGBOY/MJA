from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline/daily/dungeon_sweep_daily.json"
AVAILABLE_PAGE = ROOT / "tests/fixtures/DUNGEON_SWEEP_DAILY/archived_available_page.png"


def _nodes() -> dict[str, dict[str, Any]]:
    payload = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _predecessors(nodes: dict[str, dict[str, Any]], target: str) -> set[str]:
    return {
        name
        for name, node in nodes.items()
        for edge in (*node.get("next", []), *node.get("on_error", []))
        if edge.removeprefix("[JumpBack]") == target
    }


def _component_sizes(points: set[tuple[int, int]]) -> list[int]:
    remaining = set(points)
    sizes: list[int] = []
    while remaining:
        stack = [remaining.pop()]
        size = 0
        while stack:
            x, y = stack.pop()
            size += 1
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def test_dungeon_targets_yanwang_and_has_no_zero_assignment_success() -> None:
    nodes = _nodes()
    serialized = json.dumps(nodes, ensure_ascii=False)

    assert "数量为0-已完成" not in serialized
    assert "扫荡数量为0" not in serialized
    wind_mentions = {
        name
        for name, node in nodes.items()
        if "风雪神道" in json.dumps(node, ensure_ascii=False)
    }
    assert wind_mentions == {"0345-副本扫荡-副本-滚动-探测"}

    select = nodes["0317-副本扫荡-选择-燕王"]
    assert select["recognition"]["param"]["all_of"] == [
        "0344-副本扫荡-副本-页面",
        "0346-副本扫荡-副本-燕王-秘陵",
    ]
    assert select["custom_action_param"]["evidence"]["target_name"] == (
        "0346-副本扫荡-副本-燕王-秘陵"
    )
    assert nodes["0346-副本扫荡-副本-燕王-秘陵"]["expected"] == "燕王秘陵"
    assert nodes["0347-副本扫荡-副本-燕王-秘陵-标题"]["expected"] == "燕王秘陵"


def test_dungeon_sweep_requires_text_and_enabled_button_color() -> None:
    nodes = _nodes()
    text = nodes["0349-副本扫荡-副本-扫荡-目标"]
    visual = nodes["0350-副本扫荡-副本-扫荡-目标-视觉"]
    actionable = nodes["0351-副本扫荡-副本-扫荡-可操作"]

    assert text["expected"] == "扫荡"
    assert "未解锁扫荡" not in json.dumps(text, ensure_ascii=False)
    assert actionable["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "0349-副本扫荡-副本-扫荡-目标",
                "0350-副本扫荡-副本-扫荡-目标-视觉",
            ],
            "box_index": 1,
        },
    }

    x, y, width, height = visual["roi"]
    assert visual["roi"] == [860, 560, 220, 120]
    lower = visual["lower"]
    upper = visual["upper"]
    with Image.open(AVAILABLE_PAGE) as image:
        pixels = image.convert("RGB").crop((x, y, x + width, y + height)).load()
        matches = {
            (column, row)
            for row in range(height)
            for column in range(width)
            if all(
                low <= channel <= high
                for channel, low, high in zip(pixels[column, row], lower, upper)
            )
        }
    components = _component_sizes(matches)
    assert components[0] == 2774
    assert components[0] >= visual["count"]


def test_dungeon_unavailable_gate_requires_fresh_zero_ticket_evidence() -> None:
    nodes = _nodes()
    exhausted = nodes["0352-副本扫荡-副本-券-耗尽"]
    close = nodes["0319-副本扫荡-扫荡不可用-关闭"]

    assert exhausted == {
        "recognition": "OCR",
        "expected": "^0\\s*/\\s*7$",
        "roi": [1040, 0, 130, 90],
        "action": "DoNothing",
    }
    assert close["recognition"]["type"] == "And"
    assert close["recognition"]["param"]["all_of"] == [
        "0347-副本扫荡-副本-燕王-秘陵-标题",
        "0352-副本扫荡-副本-券-耗尽",
        "0349-副本扫荡-副本-扫荡-目标",
        "0374-副本扫荡-副本-关闭",
    ]
    assert "0350-副本扫荡-副本-扫荡-目标-视觉" not in close[
        "recognition"
    ]["param"]["all_of"]
    assert nodes["0321-副本扫荡-扫荡不可用-主页确认"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert "0320-副本扫荡-扫荡-不可用" not in nodes


def test_dungeon_scrolls_to_yanwang_with_a_finite_native_swipe_loop() -> None:
    nodes = _nodes()
    open_dungeon = nodes["0316-副本扫荡-打开-副本"]
    scroll = nodes["0315-副本扫荡-滚动-寻找-燕王"]

    assert open_dungeon["next"] == [
        "0317-副本扫荡-选择-燕王",
        "0315-副本扫荡-滚动-寻找-燕王",
    ]
    assert scroll["recognition"]["param"] == {
        "all_of": [
            "0344-副本扫荡-副本-页面",
            "0345-副本扫荡-副本-滚动-探测",
        ],
        "box_index": 1,
    }
    assert scroll["action"] == "Swipe"
    assert scroll["begin"] is True
    assert scroll["end"] is True
    assert scroll["end_offset"] == [0, -260, 0, 0]
    assert scroll["duration"] == 350
    assert 1 <= scroll["max_hit"] <= 4
    assert scroll["next"] == [
        "0317-副本扫荡-选择-燕王",
        "0315-副本扫荡-滚动-寻找-燕王",
        "0314-副本扫荡-滚动-耗尽",
    ]
    assert nodes["0314-副本扫荡-滚动-耗尽"] == {
        "recognition": "DirectHit",
        "action": "Custom",
        "custom_action": "FailTask",
        "Abort": True,
    }


def test_dungeon_success_requires_master_assignment_start_confirm_and_result() -> None:
    nodes = _nodes()

    open_sweep = nodes["0318-副本扫荡-打开-扫荡"]
    assert open_sweep["recognition"]["param"]["all_of"][0] == (
        "0347-副本扫荡-副本-燕王-秘陵-标题"
    )
    assert open_sweep["next"] == ["0324-副本扫荡-选择-面板-燕王"]

    select_card = nodes["0324-副本扫荡-选择-面板-燕王"]
    assert select_card["next"] == ["0325-副本扫荡-选择-大师-80"]
    assert select_card["custom_action_param"]["evidence"]["target_name"] == (
        "0357-副本扫荡-副本-扫荡-燕王-秘陵-卡片"
    )

    select_master = nodes["0325-副本扫荡-选择-大师-80"]
    assert select_master["action"] == "Click"
    assert select_master["target"] is True
    assert select_master["recognition"]["param"]["box_index"] == 2
    assert select_master["next"] == ["0326-副本扫荡-分配-券-循环"]
    assert nodes["0358-副本扫荡-副本-宗师-80"]["roi"] == [900, 380, 260, 100]

    assign = nodes["0326-副本扫荡-分配-券-循环"]
    assert assign["max_hit"] == 20
    assert assign["recognition"]["param"] == {
        "all_of": [
            "0355-副本扫荡-副本-扫荡-面板",
            "0357-副本扫荡-副本-扫荡-燕王-秘陵-卡片",
            "0358-副本扫荡-副本-宗师-80",
        ],
        "box_index": 2,
    }
    assert assign["custom_action_param"]["fixed_click_mode"] == (
        "dungeon_yanwang_master_plus"
    )
    assert assign["next"] == [
        "0326-副本扫荡-分配-券-循环",
        "0328-副本扫荡-开始-扫荡",
    ]
    assert "on_error" not in assign
    assert "resource_id" not in assign["custom_action_param"]
    assert "0327-副本扫荡-已分配-券-探测" not in nodes

    start = nodes["0328-副本扫荡-开始-扫荡"]
    assert start["recognition"]["param"]["all_of"] == [
        "0355-副本扫荡-副本-扫荡-面板",
        "0357-副本扫荡-副本-扫荡-燕王-秘陵-卡片",
        "0358-副本扫荡-副本-宗师-80",
        "0367-副本扫荡-副本-开始",
    ]
    assert start["next"] == ["0330-副本扫荡-确认-扫荡"]

    confirm = nodes["0330-副本扫荡-确认-扫荡"]
    assert confirm["next"] == ["0332-副本扫荡-关闭-结果"]
    assert "燕王秘陵" in nodes["0368-副本扫荡-副本-确认-页面"]["expected"]

    result = nodes["0332-副本扫荡-关闭-结果"]
    assert result["recognition"]["param"]["all_of"] == [
        "0370-副本扫荡-副本-结果",
        "0373-副本扫荡-副本-结果-关闭",
    ]
    assert result["next"] == ["0337-副本扫荡-成功-关闭"]
    assert _predecessors(nodes, "0337-副本扫荡-成功-关闭") == {
        "0332-副本扫荡-关闭-结果"
    }
    assert nodes["0337-副本扫荡-成功-关闭"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert "0338-副本扫荡-关闭后返回主页" not in nodes
