from __future__ import annotations

from tests.mfw.task_contract import TaskContract, assert_reachable, load_task_nodes


CONDENSATE = TaskContract(
    "SPEND_CONDENSATE_DAILY",
    "daily/spend_condensate_daily.json",
)


def test_shadow_world_surface_fails_closed_without_recovery_or_paid_input() -> None:
    nodes = load_task_nodes(CONDENSATE)

    painting = nodes["MJA_CONDENSATE_PAINTING_PAGE_PROBE"]
    assert painting["next"] == ["MJA_CONDENSATE_SELECT_YANWU"]
    assert painting["on_error"] == [
        "MJA_CONDENSATE_SHADOW_PAGE_PROBE",
        "MJA_CONDENSATE_RECORD_FAILURE",
    ]
    assert painting["retry_times"] == 0

    shadow = nodes["MJA_CONDENSATE_SHADOW_PAGE_PROBE"]
    assert shadow == {
        "recognition": "OCR",
        "expected": "蜃影武墟",
        "roi": [250, 350, 450, 160],
        "timeout": 8000,
        "action": "DoNothing",
        "next": ["MJA_CONDENSATE_RECORD_FAILURE"],
        "on_error": ["MJA_CONDENSATE_RECORD_FAILURE"],
        "retry_times": 0,
    }

    x, y, width, height = shadow["roi"]
    box_x, box_y, box_width, box_height = [326, 389, 282, 83]
    assert x <= box_x and y <= box_y
    assert box_x + box_width <= x + width
    assert box_y + box_height <= y + height

    assert shadow["action"] == "DoNothing"
    assert_reachable(
        nodes,
        "MJA_CONDENSATE_SHADOW_PAGE_PROBE",
        "MJA_CONDENSATE_RECORD_FAILURE",
    )
    assert_reachable(nodes, "MJA_CONDENSATE_SHADOW_PAGE_PROBE", "MJA_COMMON_ABORT")
    assert nodes["MJA_CONDENSATE_RECORD_FAILURE"]["custom_action"] == "RecordTaskOutcome"
    assert nodes["MJA_COMMON_ABORT"]["Abort"] is True


def test_painting_probe_no_longer_jumps_to_unverified_world_or_game_start() -> None:
    nodes = load_task_nodes(CONDENSATE)
    on_error = nodes["MJA_CONDENSATE_PAINTING_PAGE_PROBE"]["on_error"]

    assert "MJA_CONDENSATE_YANWU_PAGE_PROBE" not in on_error
    assert "[JumpBack]MJA_GAME_START" not in on_error
    assert "MJA_CONDENSATE_RECORD_FAILURE" in on_error
