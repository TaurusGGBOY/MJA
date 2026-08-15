from __future__ import annotations

import json
import re
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def _assert_box_inside(roi: list[int], box: tuple[int, int, int, int]) -> None:
    roi_x, roi_y, roi_width, roi_height = roi
    box_x, box_y, box_width, box_height = box
    assert roi_x <= box_x
    assert roi_y <= box_y
    assert box_x + box_width <= roi_x + roi_width
    assert box_y + box_height <= roi_y + roi_height


def test_r8_active_battle_has_a_distinct_exact_recognition_boundary() -> None:
    """r8 repeatedly saw 统计, 状态, and an mm:ss timer in one battle frame."""

    nodes = _nodes()

    assert nodes["影之遗迹-影-战斗-页面"]["expected"] == [
        "^阵容一$",
        "^推荐阵容$",
    ]
    assert nodes["影之遗迹-战斗-门禁"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-战斗-页面", "shadow.battle.target"]

    assert nodes["影之遗迹-影-战斗-中-进度"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "影之遗迹-影-战斗-中-进度-统计",
                "影之遗迹-影-战斗-中-进度-状态",
                "影之遗迹-影-战斗-中-进度-计时器",
            ]
        },
    }

    archived_hits = {
        "影之遗迹-影-战斗-中-进度-统计": ("统计", (52, 49, 33, 18)),
        "影之遗迹-影-战斗-中-进度-状态": ("状态", (117, 52, 29, 14)),
        "影之遗迹-影-战斗-中-进度-计时器": ("02:37", (194, 18, 73, 34)),
    }
    for name, (text, box) in archived_hits.items():
        node = nodes[name]
        assert re.fullmatch(node["expected"], text)
        _assert_box_inside(node["roi"], box)


def test_r8_battle_wait_is_result_first_repeatable_and_bounded() -> None:
    nodes = _nodes()
    result_then_wait = [
        "影之遗迹-战斗-结果-探测",
        "影之遗迹-战斗-中-进度-等待",
    ]

    for source in (
        "影之遗迹-探索-页面",
        "影之遗迹-前台-循环",
        "影之遗迹-战斗-循环",
    ):
        assert nodes[source]["next"][:2] == result_then_wait

    wait = nodes["影之遗迹-战斗-中-进度-等待"]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["影之遗迹-影-战斗-中-进度"]},
    }
    assert wait["action"] == "DoNothing"
    assert wait["post_delay"] == 1000
    assert wait["max_hit"] == 240
    assert wait["timeout"] == 240000
    assert wait["next"] == result_then_wait
    assert wait["on_error"] == [
        "影之遗迹-战斗-结果-探测",
        "影之遗迹-战斗-循环-耗尽",
    ]

    assert nodes["影之遗迹-页面-探测"]["next"] == [
        "影之遗迹-选择-进行中",
        "MJA_SHADOW_STATUS_PROBE",
    ]
