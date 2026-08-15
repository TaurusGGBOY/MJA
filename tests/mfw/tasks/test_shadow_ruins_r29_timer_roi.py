from __future__ import annotations

import json
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


def test_r29_timer_roi_covers_digits_without_hourglass_contamination() -> None:
    nodes = _nodes()
    timer = nodes["影之遗迹-影-战斗-中-进度-计时器"]

    assert timer["roi"] == [190, 10, 85, 50]
    _assert_box_inside(timer["roi"], (194, 18, 73, 34))
    _assert_box_inside(timer["roi"], (199, 22, 68, 28))

    roi_x, _, _, _ = timer["roi"]
    hourglass_contamination_x = 180
    hourglass_contamination_width = 10
    assert roi_x >= hourglass_contamination_x + hourglass_contamination_width


def test_r29_battle_boundary_remains_strict_bounded_and_fail_closed() -> None:
    nodes = _nodes()

    assert nodes["影之遗迹-影-战斗-中-进度-计时器"]["expected"] == "^\\d{2}:\\d{2}$"
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

    wait = nodes["影之遗迹-战斗-中-进度-等待"]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["影之遗迹-影-战斗-中-进度"]},
    }
    assert wait["max_hit"] == 240
    assert wait["timeout"] == 240000
    assert wait["on_error"] == [
        "影之遗迹-战斗-结果-探测",
        "影之遗迹-战斗-循环-耗尽",
    ]
