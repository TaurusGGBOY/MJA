import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from agent.custom.recognition.home_panel import HomePanelGray

ROOT = Path(__file__).parents[2]
IMAGES = ROOT / "assets/resource/base/image"
FIXTURES = ROOT / "tests/fixtures/home_panel"


def parameters():
    pipeline = ROOT / "assets/resource/base/pipeline/common/home_recovery.json"
    nodes = json.loads(pipeline.read_text())
    entry = nodes["0030-公共-游戏功能面板-入口"]
    assert entry["custom_recognition"] == "HomePanelGray"
    return entry["custom_recognition_param"]


def analyze(crop, **overrides):
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[10:70, 1170:1230] = crop[:, :, ::-1]
    argv = SimpleNamespace(image=frame, node_name="panel", custom_recognition_param=json.dumps(
        parameters() | overrides))
    return HomePanelGray().analyze(None, argv)


def pixels(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


@pytest.mark.parametrize("path", [
    IMAGES / "home/panel_open.png", FIXTURES / "screen_badge.png",
    FIXTURES / "pink_button.png", FIXTURES / "pink_transition.png",
])
def test_callback_accepts_real_appearances_with_original_click_box(path):
    result = analyze(pixels(path))
    assert result is not None
    assert list(result.box) == [1170, 10, 60, 60]
    assert result.detail["score"] > 0.8


def test_pink_regression_was_rejected_by_rgb():
    a = pixels(IMAGES / "home/panel_open.png").astype(float)
    b = pixels(FIXTURES / "pink_button.png").astype(float)
    a -= a.mean(axis=(0, 1))
    b -= b.mean(axis=(0, 1))
    score = (a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum())
    assert score == pytest.approx(0.4068899)
    assert analyze(pixels(FIXTURES / "pink_button.png")).detail["score"] > 0.93


def test_callback_rejects_neighbor_and_uniform_render_failures():
    assert analyze(pixels(FIXTURES / "scroll_icon.png")) is None
    for color in [(0, 0, 0), (255, 0, 255), (255, 255, 255)]:
        assert analyze(np.full((60, 60, 3), color, dtype=np.uint8)) is None


@pytest.mark.parametrize("overrides", [
    {"templates": ["missing.png"]}, {"roi": [0, 0, 60, 60]},
    {"threshold": float("nan")}, {"threshold": True}, {"templates": []},
])
def test_invalid_assets_or_parameters_fail_closed(overrides):
    assert analyze(pixels(FIXTURES / "pink_button.png"), **overrides) is None


def test_callback_rejects_incompatible_frame_without_device_access():
    argv = SimpleNamespace(image=np.zeros((1280, 720, 3), dtype=np.uint8),
                           node_name="panel", custom_recognition_param=json.dumps(parameters()))
    assert HomePanelGray().analyze(None, argv) is None
