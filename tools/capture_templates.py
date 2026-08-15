from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

ANDROID_IMAGE_ROOT = Path("assets/resource_android/image")
_UNSAFE_CROP_TERMS = ("claim", "reward", "领取", "奖励")


@dataclass(frozen=True, slots=True)
class Crop:
    x: int
    y: int
    width: int
    height: int

    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass(frozen=True, slots=True)
class CaptureCalibration:
    """The logical window and the pixel size emitted by Maa's controller."""

    logical_window_size: tuple[int, int]
    maa_capture_size: tuple[int, int]
    display_short_side: int

    def __post_init__(self) -> None:
        _validate_size(self.logical_window_size, "logical_window_size")
        _validate_size(self.maa_capture_size, "maa_capture_size")
        if (
            isinstance(self.display_short_side, bool)
            or not isinstance(self.display_short_side, int)
            or self.display_short_side <= 0
        ):
            raise ValueError("display_short_side must be a positive integer")
        if min(self.maa_capture_size) != self.display_short_side:
            raise ValueError(
                "display_short_side must equal the short side of maa_capture_size"
            )
        logical_ratio = self.logical_window_size[0] / self.logical_window_size[1]
        maa_ratio = self.maa_capture_size[0] / self.maa_capture_size[1]
        if abs(logical_ratio / maa_ratio - 1.0) > 0.01:
            raise ValueError("logical and MAA capture aspect ratios drift by more than 1%")


def _validate_size(size: tuple[int, int], label: str) -> None:
    if (
        not isinstance(size, tuple)
        or len(size) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in size
        )
    ):
        raise ValueError(f"{label} must contain two positive integers")


def _size_from_json(value: Any, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a two-item JSON array")
    size = (value[0], value[1])
    _validate_size(size, label)
    return size


def calibration_from_mapping(payload: Mapping[str, Any]) -> CaptureCalibration:
    """Parse one strict calibration object from JSON-compatible data."""

    try:
        return CaptureCalibration(
            logical_window_size=_size_from_json(
                payload["logical_window_size"], "logical_window_size"
            ),
            maa_capture_size=_size_from_json(payload["maa_capture_size"], "maa_capture_size"),
            display_short_side=payload["display_short_side"],
        )
    except KeyError as exc:
        raise ValueError(f"missing calibration field: {exc.args[0]}") from exc


def load_calibration(path: str | Path, profile: str | None = None) -> CaptureCalibration:
    """Load the top-level calibration or one named profile from JSON."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid calibration JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("calibration JSON must be an object")
    if profile is not None:
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict) or profile not in profiles:
            raise ValueError(f"unknown calibration profile: {profile}")
        payload = profiles[profile]
        if not isinstance(payload, dict):
            raise ValueError(f"calibration profile must be an object: {profile}")
    return calibration_from_mapping(payload)


TRUE_1280_CALIBRATION = CaptureCalibration((1280, 720), (1280, 720), 720)


HOME_CROPS: dict[str, Crop] = {
    "home_marker": Crop(1040, 0, 240, 110),
    "panel_open": Crop(1200, 0, 80, 100),
}
PANEL_CROPS: dict[str, Crop] = {
    "panel_marker": Crop(840, 0, 280, 160),
    "mail_entry": Crop(1120, 115, 160, 210),
    "panel_close": Crop(1200, 0, 80, 100),
}
MAIL_CROPS: dict[str, Crop] = {
    "mail_marker": Crop(0, 0, 320, 140),
    "mail_close": Crop(1040, 80, 160, 160),
}

_PROFILES: dict[str, tuple[str, Mapping[str, Crop]]] = {
    "home": ("home", HOME_CROPS),
    "panel": ("panel", PANEL_CROPS),
    "mail": ("mail", MAIL_CROPS),
}


def validate_crop_names(crops: Mapping[str, Crop]) -> None:
    for name in crops:
        normalized = name.casefold()
        if any(term.casefold() in normalized for term in _UNSAFE_CROP_TERMS):
            raise ValueError(f"unsafe crop name: {name}")


def _validate_crop(crop: Crop, source_size: tuple[int, int]) -> None:
    if min(crop.x, crop.y, crop.width, crop.height) < 0:
        raise ValueError("crop coordinates and dimensions must be non-negative")
    if crop.width == 0 or crop.height == 0:
        raise ValueError("crop dimensions must be positive")
    source_width, source_height = source_size
    if crop.x + crop.width > source_width or crop.y + crop.height > source_height:
        raise ValueError("crop is outside source image")


def validate_crop_profile(
    crops: Mapping[str, Crop], calibration: CaptureCalibration
) -> None:
    """Validate crop names and bounds in one explicit MAA coordinate system."""

    validate_crop_names(crops)
    for crop in crops.values():
        _validate_crop(crop, calibration.maa_capture_size)


def crop_templates(
    source: str | Path,
    output_dir: str | Path,
    crops: Mapping[str, Crop],
    *,
    calibration: CaptureCalibration = TRUE_1280_CALIBRATION,
) -> dict[str, Path]:
    """Write named PNG crops from one calibrated Maa source frame."""

    validate_crop_profile(crops, calibration)
    source_path = Path(source)
    target_dir = Path(output_dir)
    with Image.open(source_path) as opened:
        if opened.size != calibration.maa_capture_size:
            width, height = calibration.maa_capture_size
            raise ValueError(
                f"source image must match calibrated MAA capture size {width}x{height}"
            )
        image = opened.convert("RGB")
        outputs: dict[str, Path] = {}
        target_dir.mkdir(parents=True, exist_ok=True)
        for name, crop in crops.items():
            output = target_dir / f"{name}.png"
            temporary = output.with_name(output.name + ".tmp")
            try:
                image.crop(crop.box()).save(temporary, format="PNG")
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
            outputs[name] = output
    return outputs


def capture_android_profile(
    profile: str,
    device: Any,
    output_root: str | Path = ANDROID_IMAGE_ROOT,
) -> dict[str, Path]:
    """Capture one safe profile from a ready 1280x720 ADB device."""

    try:
        directory, crops = _PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"profile must be one of: {', '.join(_PROFILES)}") from exc
    device.wait_ready()
    target_dir = Path(output_root) / directory
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = target_dir / ".capture-source.png"
    try:
        device.screencap(temporary)
        return crop_templates(
            temporary,
            target_dir,
            crops,
            calibration=TRUE_1280_CALIBRATION,
        )
    finally:
        temporary.unlink(missing_ok=True)
