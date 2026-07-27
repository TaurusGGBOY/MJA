from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image

SCREEN_SIZE = (1280, 720)
IMAGE_ROOT = Path("assets/resource/image")
_UNSAFE_CROP_TERMS = ("claim", "reward", "领取", "奖励")


@dataclass(frozen=True, slots=True)
class Crop:
    x: int
    y: int
    width: int
    height: int

    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


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


def crop_templates(
    source: str | Path,
    output_dir: str | Path,
    crops: Mapping[str, Crop],
) -> dict[str, Path]:
    """Write named PNG crops from one exact 1280x720 source frame."""

    validate_crop_names(crops)
    source_path = Path(source)
    target_dir = Path(output_dir)
    with Image.open(source_path) as opened:
        if opened.size != SCREEN_SIZE:
            raise ValueError(f"source image must be exactly {SCREEN_SIZE[0]}x{SCREEN_SIZE[1]}")
        image = opened.convert("RGB")
        outputs: dict[str, Path] = {}
        target_dir.mkdir(parents=True, exist_ok=True)
        for name, crop in crops.items():
            _validate_crop(crop, image.size)
            output = target_dir / f"{name}.png"
            image.crop(crop.box()).save(output, format="PNG")
            outputs[name] = output
    return outputs


def _default_controller_factory(window_id: int) -> Any:
    from maa.controller import MacOSController
    from maa.define import MaaMacOSInputMethodEnum, MaaMacOSScreencapMethodEnum

    return MacOSController(
        window_id,
        screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
        input_method=MaaMacOSInputMethodEnum.GlobalEvent,
    )


def capture_screen(
    window_id: int,
    controller_factory: Callable[[int], Any] | None = None,
) -> Image.Image:
    """Capture one 1280x720 frame through Maa's macOS ScreenCaptureKit controller."""

    if isinstance(window_id, bool) or not isinstance(window_id, int) or window_id <= 0:
        raise ValueError("window_id must be a positive integer")
    controller = (controller_factory or _default_controller_factory)(window_id)
    connection = controller.post_connection().wait()
    if hasattr(connection, "succeeded") and not connection.succeeded:
        raise RuntimeError(f"failed to connect macOS controller for window {window_id}")
    if not controller.set_screenshot_target_short_side(SCREEN_SIZE[1]):
        raise RuntimeError("failed to set screenshot short side to 720")
    frame = controller.post_screencap().wait().get()
    image = frame if isinstance(frame, Image.Image) else Image.fromarray(frame)
    if image.size != SCREEN_SIZE:
        raise ValueError(
            f"captured frame must be exactly {SCREEN_SIZE[0]}x{SCREEN_SIZE[1]}, got {image.size}"
        )
    return image.convert("RGB")


def capture_profile(
    profile: str,
    window_id: int,
    output_root: str | Path = IMAGE_ROOT,
    controller_factory: Callable[[int], Any] | None = None,
) -> dict[str, Path]:
    try:
        directory, crops = _PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"profile must be one of: {', '.join(_PROFILES)}") from exc
    image = capture_screen(window_id, controller_factory=controller_factory)
    target_dir = Path(output_root) / directory
    temporary = target_dir / ".capture-source.png"
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        image.save(temporary, format="PNG")
        outputs = crop_templates(temporary, target_dir, crops)
    finally:
        temporary.unlink(missing_ok=True)
    return outputs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture safe MJA template crops from a macOS window"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="capture one named screen profile")
    capture.add_argument("profile", choices=tuple(_PROFILES))
    capture.add_argument("--window-id", required=True, type=int)
    capture.add_argument("--output-root", type=Path, default=IMAGE_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "capture":
        outputs = capture_profile(args.profile, args.window_id, args.output_root)
        for output in outputs.values():
            print(output)
        return 0
    raise AssertionError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
