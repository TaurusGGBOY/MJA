from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tools.capture_templates import (
    HOME_CROPS,
    MAIL_CROPS,
    PANEL_CROPS,
    TRUE_1280_CALIBRATION,
    CaptureCalibration,
    Crop,
    calibration_from_mapping,
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
                "logical_window_size": [1280, 720],
                "maa_capture_size": [1280, 720],
                "display_short_side": 720,
            }
        ),
        encoding="utf-8",
    )
    assert load_calibration(path) == TRUE_1280_CALIBRATION
    assert calibration_from_mapping(
        {
            "logical_window_size": [1280, 720],
            "maa_capture_size": [1280, 720],
            "display_short_side": 720,
        }
    ) == TRUE_1280_CALIBRATION


def test_crop_profiles_are_validated_against_their_calibrated_dimensions() -> None:
    for profile in (HOME_CROPS, PANEL_CROPS, MAIL_CROPS):
        validate_crop_profile(profile, TRUE_1280_CALIBRATION)


def test_crop_templates_refuse_live_size_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "wrong-size.png"
    Image.new("RGB", (1279, 720), "navy").save(source)

    with pytest.raises(ValueError, match="calibrated MAA capture size 1280x720"):
        crop_templates(
            source,
            tmp_path / "out",
            {"marker": Crop(0, 0, 1, 1)},
            calibration=TRUE_1280_CALIBRATION,
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
