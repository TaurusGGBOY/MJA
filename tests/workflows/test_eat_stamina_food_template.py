"""Offline contract tests for the food-grid template recognizer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).parents[2]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline/daily/eat_stamina_food_daily.json"
TEMPLATE_PATH = ROOT / "assets/resource/base/image/daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp.png"
GRID_FIXTURE = ROOT / "tests/fixtures/EAT_STAMINA_FOOD_DAILY/grid_food_tab_shrimp_first_row.png"


def _load_pipeline() -> dict[str, dict[str, Any]]:
    payload = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _gray(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def _ncc(left: np.ndarray, right: np.ndarray) -> float:
    left = left - left.mean()
    right = right - right.mean()
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0:
        return -1.0
    return float(np.sum(left * right) / denominator)


def _best_template_match(
    frame: np.ndarray, template: np.ndarray, roi: list[int]
) -> tuple[float, tuple[int, int]]:
    """Scan the configured ROI without a fixed row/column prior."""

    x0, y0, width, height = roi
    template_height, template_width = template.shape
    stride = 4
    sampled_template = template[::stride, ::stride]
    best_score = -1.0
    best_box = (x0, y0)
    for y in range(y0, y0 + height - template_height + 1, stride):
        for x in range(x0, x0 + width - template_width + 1, stride):
            patch = frame[y : y + template_height : stride, x : x + template_width : stride]
            score = _ncc(patch, sampled_template)
            if score > best_score:
                best_score = score
                best_box = (x, y)

    refined_score = best_score
    refined_box = best_box
    for y in range(max(y0, best_box[1] - stride), best_box[1] + stride + 1):
        for x in range(max(x0, best_box[0] - stride), best_box[0] + stride + 1):
            patch = frame[y : y + template_height, x : x + template_width]
            score = _ncc(patch, template)
            if score > refined_score:
                refined_score = score
                refined_box = (x, y)
    return refined_score, refined_box


def test_food_template_scans_the_whole_grid_and_finds_first_row_card() -> None:
    pipeline = _load_pipeline()
    candidate = pipeline["吃体力食物-食物-候选"]
    assert candidate["recognition"] == "TemplateMatch"
    assert candidate["template"] == "daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp.png"
    roi = candidate["roi"]
    assert roi == [120, 80, 680, 540]
    assert roi[0] <= 540 and roi[1] <= 114
    assert roi[0] + roi[2] >= 620 and roi[1] + roi[3] >= 194

    frame = _gray(GRID_FIXTURE)
    template = _gray(TEMPLATE_PATH)
    score, (match_x, match_y) = _best_template_match(frame, template, roi)
    assert score >= candidate["threshold"]

    template_width = template.shape[1]
    template_height = template.shape[0]
    assert roi[0] <= match_x < roi[0] + roi[2]
    assert roi[1] <= match_y < roi[1] + roi[3]
    assert match_x + template_width <= roi[0] + roi[2]
    assert match_y + template_height <= roi[1] + roi[3]

    legacy_roi = [500, 370, 160, 170]
    assert not (
        legacy_roi[0] <= match_x < legacy_roi[0] + legacy_roi[2]
        and legacy_roi[1] <= match_y < legacy_roi[1] + legacy_roi[3]
    )


def test_food_candidate_click_uses_match_box_and_requires_after_probe() -> None:
    pipeline = _load_pipeline()
    loop = pipeline["吃体力食物-候选-循环"]
    recognition = loop["recognition"]
    assert recognition["type"] == "And"
    assert recognition["param"] == {
        "all_of": ["吃体力食物-食物-食物-页面", "吃体力食物-食物-候选"],
        "box_index": 1,
    }
    assert loop["max_hit"] == 6
    assert loop["action"] == "Custom"
    assert loop["custom_action"] == "GuardedInput"
    assert loop["custom_action_param"]["action_id"] == "inspect_food_candidate"
    assert loop["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "吃体力食物-食物-食物-页面",
        "target_name": "吃体力食物-食物-候选",
    }
    assert loop["next"] == ["吃体力食物-详情-探测"]

    after_probe = pipeline["吃体力食物-详情-探测"]
    assert after_probe["recognition"] == "OCR"
    assert "龙井虾仁" in after_probe["expected"]
    assert after_probe["on_error"] == ["吃体力食物-无安全卡-关闭-背包"]

    unknown_failure = pipeline["吃体力食物-记录-失败"]
    assert unknown_failure["custom_action_param"]["status"] == "failed"
    assert "Abort" not in unknown_failure
    assert unknown_failure["next"] == ["公共-通用中止"]


def test_food_replacement_confirm_accepts_the_live_button_match_margin() -> None:
    pipeline = _load_pipeline()
    confirm = pipeline["吃体力食物-食物-替换-确认"]

    assert confirm["recognition"] == "TemplateMatch"
    assert confirm["template"] == (
        "daily/EAT_STAMINA_FOOD_DAILY/food_buff_replace_confirm.png"
    )
    assert confirm["roi"] == [780, 450, 250, 100]
    # The live popup matched the confirm button at 0.341823. Keep the
    # threshold below that observed score while the prompt remains mandatory.
    assert confirm["threshold"] <= 0.34


def test_food_replacement_confirmation_does_not_require_the_covered_item_name() -> None:
    pipeline = _load_pipeline()
    loop = pipeline["吃体力食物-替换-确认-循环"]
    recognition = loop["recognition"]

    assert recognition["type"] == "And"
    assert recognition["param"] == {
        "all_of": [
            "吃体力食物-食物-替换-提示",
            "吃体力食物-食物-替换-确认",
        ],
        "box_index": 1,
    }


def test_food_full_branch_closes_the_bag_before_recording_success() -> None:
    pipeline = _load_pipeline()
    full_probe = pipeline["吃体力食物-已超上限-之后-食用-探测"]

    assert full_probe["next"] == ["吃体力食物-体力-已满-关闭-背包"]
