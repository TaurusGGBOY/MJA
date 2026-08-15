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

    assert nodes["shadow.battle.page"]["expected"] == [
        "^阵容一$",
        "^推荐阵容$",
    ]
    assert nodes["MJA_SHADOW_BATTLE_GATE"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.battle.page", "shadow.battle.target"]

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

    archived_hits = {
        "shadow.battle.in_progress.stats": ("统计", (52, 49, 33, 18)),
        "shadow.battle.in_progress.status": ("状态", (117, 52, 29, 14)),
        "shadow.battle.in_progress.timer": ("02:37", (194, 18, 73, 34)),
    }
    for name, (text, box) in archived_hits.items():
        node = nodes[name]
        assert re.fullmatch(node["expected"], text)
        _assert_box_inside(node["roi"], box)


def test_r8_battle_wait_is_result_first_repeatable_and_bounded() -> None:
    nodes = _nodes()
    result_then_wait = [
        "MJA_SHADOW_BATTLE_RESULT_PROBE",
        "MJA_SHADOW_BATTLE_IN_PROGRESS_WAIT",
    ]

    for source in (
        "MJA_SHADOW_EXPLORATION_PAGE",
        "MJA_SHADOW_FOREGROUND_LOOP",
        "MJA_SHADOW_BATTLE_LOOP",
    ):
        assert nodes[source]["next"][:2] == result_then_wait

    wait = nodes["MJA_SHADOW_BATTLE_IN_PROGRESS_WAIT"]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["shadow.battle.in_progress"]},
    }
    assert wait["action"] == "DoNothing"
    assert wait["post_delay"] == 1000
    assert wait["max_hit"] == 240
    assert wait["timeout"] == 240000
    assert wait["next"] == result_then_wait
    assert wait["on_error"] == [
        "MJA_SHADOW_BATTLE_RESULT_PROBE",
        "MJA_SHADOW_BATTLE_LOOP_EXHAUSTED",
    ]

    assert nodes["MJA_SHADOW_PAGE_PROBE"]["next"] == [
        "MJA_SHADOW_SELECT_ACTIVE",
        "MJA_SHADOW_STATUS_PROBE",
    ]
