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


def test_dungeon_targets_fengxue_and_has_no_zero_assignment_success() -> None:
    nodes = _nodes()
    serialized = json.dumps(nodes, ensure_ascii=False)

    assert "数量为0-已完成" not in serialized
    assert "扫荡数量为0" not in serialized
    assert "燕王" not in serialized

    select = nodes["0317-副本扫荡-选择-风雪"]
    assert select["recognition"]["param"]["all_of"] == [
        "0344-副本扫荡-副本-页面",
        "0346-副本扫荡-副本-风雪-神道",
    ]
    assert select["custom_action_param"]["evidence"]["target_name"] == (
        "0346-副本扫荡-副本-风雪-神道"
    )
    assert nodes["0346-副本扫荡-副本-风雪-神道"]["expected"] == "风雪神道"
    assert nodes["0347-副本扫荡-副本-风雪-神道-标题"]["expected"] == "风雪神道"


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
        "0347-副本扫荡-副本-风雪-神道-标题",
        "0352-副本扫荡-副本-券-耗尽",
        "0349-副本扫荡-副本-扫荡-目标",
        "0374-副本扫荡-副本-关闭",
    ]
    assert "0350-副本扫荡-副本-扫荡-目标-视觉" not in close["recognition"]["param"]["all_of"]
    assert nodes["0321-副本扫荡-扫荡不可用-主页确认"]["next"] == ["1371-公共-原生成功-主页边界"]
    assert "0320-副本扫荡-扫荡-不可用" not in nodes


def test_dungeon_scrolls_to_fengxue_with_a_finite_native_swipe_loop() -> None:
    nodes = _nodes()
    open_dungeon = nodes["0316-副本扫荡-打开-副本"]
    scroll = nodes["0315-副本扫荡-滚动-寻找-风雪"]

    assert open_dungeon["next"] == [
        "0317-副本扫荡-选择-风雪",
        "0315-副本扫荡-滚动-寻找-风雪",
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
        "0317-副本扫荡-选择-风雪",
        "0315-副本扫荡-滚动-寻找-风雪",
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
    assert open_sweep["recognition"]["param"]["all_of"][0] == ("0347-副本扫荡-副本-风雪-神道-标题")
    assert open_sweep["next"] == ["0324-副本扫荡-选择-面板-风雪"]

    select_card = nodes["0324-副本扫荡-选择-面板-风雪"]
    assert select_card["next"] == ["0325-副本扫荡-选择-大师-80"]
    assert select_card["custom_action_param"]["evidence"]["target_name"] == (
        "0357-副本扫荡-副本-扫荡-风雪-神道-卡片"
    )

    select_master = nodes["0325-副本扫荡-选择-大师-80"]
    assert select_master["action"] == "DoNothing"
    assert select_master["next"] == ["0326-副本扫荡-分配-第一张券"]
    master = nodes["0358-副本扫荡-副本-宗师-80"]
    assert master["recognition"]["param"]["all_of"] == [
        "副本扫荡-风雪-大师文字",
        "副本扫荡-风雪-80级文字",
    ]
    assert nodes["副本扫荡-风雪-大师文字"]["expected"] == "大师"
    assert nodes["副本扫荡-风雪-80级文字"]["expected"] == "80级"

    for name, following in [
        ("0326-副本扫荡-分配-第一张券", "0327-副本扫荡-分配-第二张券"),
        ("0327-副本扫荡-分配-第二张券", "0328-副本扫荡-开始-扫荡"),
    ]:
        assign = nodes[name]
        assert assign["max_hit"] == 1
        assert assign["retry_times"] == 0
        assert assign["next"] == [following]
        assert (
            assign["custom_action_param"]["evidence"]["target_name"] == "0359-副本扫荡-副本-券-加号"
        )
        assert assign["recognition"]["param"]["all_of"] == [
            "0355-副本扫荡-副本-扫荡-面板",
            "0357-副本扫荡-副本-扫荡-风雪-神道-卡片",
            "0358-副本扫荡-副本-宗师-80",
            "0359-副本扫荡-副本-券-加号",
        ]
    assert "0326-副本扫荡-分配-券-循环" not in nodes
    start = nodes["0328-副本扫荡-开始-扫荡"]
    assert "0366-副本扫荡-副本-已分配-安全" in start["recognition"]["param"]["all_of"]
    assert nodes["0366-副本扫荡-副本-已分配-安全"]["expected"] == "^2$"
    assert start["next"] == ["0330-副本扫荡-确认-扫荡"]
    assert nodes["0330-副本扫荡-确认-扫荡"]["next"] == ["0332-副本扫荡-关闭-结果"]
    assert "风雪神道" in nodes["0368-副本扫荡-副本-确认-页面"]["expected"]

    result = nodes["0332-副本扫荡-关闭-结果"]
    assert result["recognition"]["param"]["all_of"] == [
        "0370-副本扫荡-副本-结果",
        "0373-副本扫荡-副本-结果-关闭",
    ]
    assert result["next"] == ["0337-副本扫荡-成功-关闭"]
    assert _predecessors(nodes, "0337-副本扫荡-成功-关闭") == {"0332-副本扫荡-关闭-结果"}
    assert nodes["0337-副本扫荡-成功-关闭"]["next"] == ["1371-公共-原生成功-主页边界"]
    assert "0338-副本扫荡-关闭后返回主页" not in nodes


def test_fengxue_master_controls_stay_in_the_same_column_and_third_row():
    nodes = _nodes()
    # 2026-09-11 live 1280x720 panel: 精英 is y=417; 大师 is y=477.
    # Quantity is x=737; the + is x=801. The former ROI clipped quantity 0.
    controls = [
        ("副本扫荡-风雪-大师文字", (510, 477)),
        ("副本扫荡-风雪-80级文字", (591, 477)),
        ("0359-副本扫荡-副本-券-加号", (801, 477)),
        ("0366-副本扫荡-副本-已分配-安全", (737, 477)),
    ]
    for name, (cx, cy) in controls:
        x, y, w, h = nodes[name]["roi"]
        assert x <= cx < x + w and y <= cy < y + h
        assert y > 431  # Never sample the elite row.
    x, _, w, _ = nodes["0359-副本扫荡-副本-券-加号"]["roi"]
    assert x > 750  # Excludes the zero quantity which previously matched.
    for name in (
        "0326-副本扫荡-分配-第一张券",
        "0327-副本扫荡-分配-第二张券",
        "0328-副本扫荡-开始-扫荡",
    ):
        assert nodes[name]["on_error"] == ["MJA-公共-原生失败-返回主页"]
