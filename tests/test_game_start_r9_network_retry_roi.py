import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KNOWN_POPUPS = ROOT / "assets/resource/base/pipeline/common/known_popups.json"

# Archived r9 full-screen batch OCR boxes from 2026-08-13 16:36:23.
RETRY_BOX = (857, 375, 35, 77)
CANCEL_BOX = (929, 374, 39, 79)


def _contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    outer_x, outer_y, outer_width, outer_height = outer
    inner_x, inner_y, inner_width, inner_height = inner
    return (
        outer_x <= inner_x
        and outer_y <= inner_y
        and outer_x + outer_width >= inner_x + inner_width
        and outer_y + outer_height >= inner_y + inner_height
    )


def _intersects(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return (
        left_x < right_x + right_width
        and right_x < left_x + left_width
        and left_y < right_y + right_height
        and right_y < left_y + left_height
    )


def test_r9_network_retry_roi_contains_retry_and_excludes_cancel() -> None:
    nodes = json.loads(KNOWN_POPUPS.read_text())
    retry = nodes["MJA_KNOWN_NETWORK_CONFIRM"]
    roi = tuple(retry["roi"])

    assert retry["recognition"] == "OCR"
    assert "重试" in retry["expected"]
    assert "取消" not in retry["expected"]
    assert retry["action"] == "Click"
    assert retry["max_hit"] == 1
    assert _contains(roi, RETRY_BOX)
    assert not _intersects(roi, CANCEL_BOX)
