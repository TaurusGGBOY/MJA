from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tools.capture_templates import (
    HOME_CROPS,
    MAIL_CROPS,
    PANEL_CROPS,
    Crop,
    crop_templates,
    validate_crop_names,
)


def test_named_crops_have_exact_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "screen.png"
    Image.new("RGB", (1280, 720), "navy").save(source)
    outputs = crop_templates(
        source,
        tmp_path / "out",
        {
            "home_marker": Crop(1040, 0, 240, 110),
            "panel_open": Crop(1200, 0, 80, 100),
        },
    )
    assert Image.open(outputs["home_marker"]).size == (240, 110)
    assert Image.open(outputs["panel_open"]).size == (80, 100)


def test_fixed_crop_profiles_are_1280x720_safe() -> None:
    for profile in (HOME_CROPS, PANEL_CROPS, MAIL_CROPS):
        for crop in profile.values():
            assert crop.x >= 0
            assert crop.y >= 0
            assert crop.x + crop.width <= 1280
            assert crop.y + crop.height <= 720


def test_crop_templates_refuse_non_1280x720_source(tmp_path: Path) -> None:
    source = tmp_path / "wrong-size.png"
    Image.new("RGB", (1279, 720), "navy").save(source)

    with pytest.raises(ValueError, match="1280x720"):
        crop_templates(source, tmp_path / "out", {"home_marker": HOME_CROPS["home_marker"]})


def test_crop_names_cannot_target_claim_or_reward_controls() -> None:
    with pytest.raises(ValueError, match="unsafe crop name"):
        validate_crop_names({"claim_button": Crop(0, 0, 1, 1)})

    with pytest.raises(ValueError, match="unsafe crop name"):
        validate_crop_names({"奖励区域": Crop(0, 0, 1, 1)})


def test_crop_templates_refuse_out_of_bounds_crop(tmp_path: Path) -> None:
    source = tmp_path / "screen.png"
    Image.new("RGB", (1280, 720), "navy").save(source)

    with pytest.raises(ValueError, match="outside source"):
        crop_templates(source, tmp_path / "out", {"home_marker": Crop(1279, 0, 2, 2)})


def test_capture_screen_uses_connection_short_side_and_screencap() -> None:
    class FakeJob:
        succeeded = True

        def __init__(self, result: Image.Image | None = None) -> None:
            self.result = result

        def wait(self) -> "FakeJob":
            return self

        def get(self) -> Image.Image:
            assert self.result is not None
            return self.result

    class FakeController:
        def __init__(self) -> None:
            self.short_side: int | None = None
            self.connected = False
            self.screencapped = False

        def post_connection(self) -> FakeJob:
            self.connected = True
            return FakeJob()

        def set_screenshot_target_short_side(self, short_side: int) -> bool:
            self.short_side = short_side
            return True

        def post_screencap(self) -> FakeJob:
            self.screencapped = True
            return FakeJob(Image.new("RGB", (1280, 720), "navy"))

    controller = FakeController()
    from tools.capture_templates import capture_screen

    image = capture_screen(42, controller_factory=lambda window_id: controller)

    assert image.size == (1280, 720)
    assert controller.connected is True
    assert controller.short_side == 720
    assert controller.screencapped is True
