from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tools.capture_templates import (
    HOME_CROPS,
    MAIL_CROPS,
    OBSERVED_IOS_CALIBRATION,
    PANEL_CROPS,
    TRUE_1280_CALIBRATION,
    CaptureCalibration,
    Crop,
    _crops_for_calibration,
    calibration_from_mapping,
    capture_screen,
    crop_templates,
    load_calibration,
    validate_crop_names,
    validate_crop_profile,
)


def test_named_crops_have_exact_dimensions_in_true_1280_profile(tmp_path: Path) -> None:
    source = tmp_path / "screen.png"
    Image.new("RGB", TRUE_1280_CALIBRATION.maa_capture_size, "navy").save(source)
    outputs = crop_templates(
        source,
        tmp_path / "out",
        {
            "home_marker": Crop(1040, 0, 240, 110),
            "panel_open": Crop(1200, 0, 80, 100),
        },
        calibration=TRUE_1280_CALIBRATION,
    )
    assert Image.open(outputs["home_marker"]).size == (240, 110)
    assert Image.open(outputs["panel_open"]).size == (80, 100)


def test_observed_logical_window_scales_to_923x720() -> None:
    assert OBSERVED_IOS_CALIBRATION.logical_window_size == (1051, 820)
    assert OBSERVED_IOS_CALIBRATION.maa_capture_size == (923, 720)
    assert OBSERVED_IOS_CALIBRATION.display_short_side == 720


def test_true_1280x720_resizable_window_remains_supported() -> None:
    calibration = CaptureCalibration((1280, 720), (1280, 720), 720)
    assert calibration == TRUE_1280_CALIBRATION


def test_calibration_rejects_aspect_ratio_drift_over_one_percent() -> None:
    with pytest.raises(ValueError, match="aspect ratios drift"):
        CaptureCalibration((1000, 800), (923, 720), 720)


def test_calibration_json_round_trips_strict_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(
            {
                "logical_window_size": [1051, 820],
                "maa_capture_size": [923, 720],
                "display_short_side": 720,
            }
        ),
        encoding="utf-8",
    )
    assert load_calibration(path) == OBSERVED_IOS_CALIBRATION
    assert calibration_from_mapping(
        {
            "logical_window_size": [1280, 720],
            "maa_capture_size": [1280, 720],
            "display_short_side": 720,
        }
    ) == TRUE_1280_CALIBRATION


def test_committed_calibration_profiles_are_runtime_loadable() -> None:
    path = Path(__file__).resolve().parents[1] / "assets/resource/calibration.json"
    assert load_calibration(path, "observed_ios_window") == OBSERVED_IOS_CALIBRATION
    assert load_calibration(path, "true_1280_legacy_assets") == TRUE_1280_CALIBRATION


def test_crop_profiles_are_validated_against_their_calibrated_dimensions() -> None:
    for profile in (HOME_CROPS, PANEL_CROPS, MAIL_CROPS):
        validate_crop_profile(profile, TRUE_1280_CALIBRATION)

    with pytest.raises(ValueError, match="outside source"):
        validate_crop_profile(HOME_CROPS, OBSERVED_IOS_CALIBRATION)


def test_crop_templates_accept_non_1280_calibrated_source(tmp_path: Path) -> None:
    source = tmp_path / "screen.png"
    Image.new("RGB", OBSERVED_IOS_CALIBRATION.maa_capture_size, "navy").save(source)
    outputs = crop_templates(
        source,
        tmp_path / "out",
        {"observed_marker": Crop(700, 10, 200, 100)},
        calibration=OBSERVED_IOS_CALIBRATION,
    )
    assert Image.open(outputs["observed_marker"]).size == (200, 100)


def test_legacy_crops_project_into_observed_capture_size() -> None:
    crops = _crops_for_calibration(
        {"home_marker": Crop(1040, 0, 240, 110)}, OBSERVED_IOS_CALIBRATION
    )
    assert crops["home_marker"] == Crop(750, 0, 173, 110)


def test_crop_templates_refuse_live_size_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "wrong-size.png"
    Image.new("RGB", (924, 720), "navy").save(source)

    with pytest.raises(ValueError, match="calibrated MAA capture size 923x720"):
        crop_templates(
            source,
            tmp_path / "out",
            {"marker": Crop(0, 0, 1, 1)},
            calibration=OBSERVED_IOS_CALIBRATION,
        )


def test_crop_templates_refuse_out_of_bounds_crop(tmp_path: Path) -> None:
    source = tmp_path / "screen.png"
    Image.new("RGB", TRUE_1280_CALIBRATION.maa_capture_size, "navy").save(source)

    with pytest.raises(ValueError, match="outside source"):
        crop_templates(
            source,
            tmp_path / "out",
            {"home_marker": Crop(1279, 0, 2, 2)},
            calibration=TRUE_1280_CALIBRATION,
        )


def test_crop_names_cannot_target_claim_or_reward_controls() -> None:
    with pytest.raises(ValueError, match="unsafe crop name"):
        validate_crop_names({"claim_button": Crop(0, 0, 1, 1)})

    with pytest.raises(ValueError, match="unsafe crop name"):
        validate_crop_names({"奖励区域": Crop(0, 0, 1, 1)})


class _FakeJob:
    succeeded = True

    def __init__(self, result: Image.Image | None = None) -> None:
        self.result = result

    def wait(self) -> "_FakeJob":
        return self

    def get(self) -> Image.Image:
        assert self.result is not None
        return self.result


class _ReadOnlyController:
    def __init__(self, frame_size: tuple[int, int]) -> None:
        self.frame_size = frame_size
        self.short_side: int | None = None
        self.connected = False
        self.screencapped = False
        self.input_calls = 0

    def post_connection(self) -> _FakeJob:
        self.connected = True
        return _FakeJob()

    def set_screenshot_target_short_side(self, short_side: int) -> bool:
        self.short_side = short_side
        return True

    def post_screencap(self) -> _FakeJob:
        self.screencapped = True
        return _FakeJob(Image.new("RGB", self.frame_size, "navy"))

    def click(self, *_args: object) -> None:
        self.input_calls += 1
        raise AssertionError("capture helper must not invoke input actions")


@pytest.mark.parametrize(
    ("calibration", "frame_size"),
    [
        (OBSERVED_IOS_CALIBRATION, (923, 720)),
        (TRUE_1280_CALIBRATION, (1280, 720)),
    ],
)
def test_capture_screen_accepts_calibrated_maa_sizes(
    calibration: CaptureCalibration, frame_size: tuple[int, int]
) -> None:
    controller = _ReadOnlyController(frame_size)

    image = capture_screen(
        42,
        expected_short_side=720,
        calibration=calibration,
        controller_factory=lambda window_id: controller,
    )

    assert image.size == frame_size
    assert controller.connected is True
    assert controller.short_side == 720
    assert controller.screencapped is True
    assert controller.input_calls == 0


def test_capture_screen_keeps_legacy_controller_factory_position() -> None:
    controller = _ReadOnlyController((1280, 720))
    image = capture_screen(42, lambda window_id: controller)
    assert image.size == (1280, 720)


def test_capture_screen_rejects_dimension_mismatch() -> None:
    controller = _ReadOnlyController((924, 720))
    with pytest.raises(ValueError, match="does not match calibrated MAA capture size"):
        capture_screen(
            42,
            calibration=OBSERVED_IOS_CALIBRATION,
            controller_factory=lambda window_id: controller,
        )


def test_capture_screen_rejects_short_side_mismatch() -> None:
    controller = _ReadOnlyController((923, 719))
    with pytest.raises(ValueError, match="short side must be 720"):
        capture_screen(42, controller_factory=lambda window_id: controller)


def test_capture_screen_rejects_invalid_window_id() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        capture_screen(0)
