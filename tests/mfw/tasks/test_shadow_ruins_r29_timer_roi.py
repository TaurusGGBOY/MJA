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
    timer = nodes["shadow.battle.in_progress.timer"]

    assert timer["roi"] == [190, 10, 85, 50]
    _assert_box_inside(timer["roi"], (194, 18, 73, 34))
    _assert_box_inside(timer["roi"], (199, 22, 68, 28))

    roi_x, _, _, _ = timer["roi"]
    hourglass_contamination_x = 180
    hourglass_contamination_width = 10
    assert roi_x >= hourglass_contamination_x + hourglass_contamination_width


def test_r29_battle_boundary_remains_strict_bounded_and_fail_closed() -> None:
    nodes = _nodes()

    assert nodes["shadow.battle.in_progress.timer"]["expected"] == "^\\d{2}:\\d{2}$"
    assert nodes["shadow.battle.in_progress"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "shadow.battle.in_progress.stats",
                "shadow.battle.in_progress.status",
                "shadow.battle.in_progress.timer",
            ]
        },
    }

    wait = nodes["MJA_SHADOW_BATTLE_IN_PROGRESS_WAIT"]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["shadow.battle.in_progress"]},
    }
    assert wait["max_hit"] == 240
    assert wait["timeout"] == 240000
    assert wait["on_error"] == [
        "MJA_SHADOW_BATTLE_RESULT_PROBE",
        "MJA_SHADOW_BATTLE_LOOP_EXHAUSTED",
    ]
