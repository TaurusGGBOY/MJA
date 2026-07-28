"""Run a read-only stability probe against one Maa macOS controller."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from agent.errors import ErrorCode, MJAError

DEFAULT_FRAMES = 50
SCREENSHOT_SHORT_SIDE = 720
FALLBACK_MARKER = "MJA screencap backend switched to CoreGraphicsRegion"
Backend = Literal["ScreenCaptureKit", "CoreGraphicsRegion"]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    window_id: int
    frames: int
    width: int
    height: int
    nonempty_frames: int
    backend: Backend


def _default_controller_factory(window_id: int) -> Any:
    try:
        from maa.controller import MacOSController
        from maa.define import MaaMacOSInputMethodEnum, MaaMacOSScreencapMethodEnum
    except Exception as exc:  # pragma: no cover - depends on the assembled runtime
        raise MJAError(
            ErrorCode.CONTROLLER_CONNECT_FAILED,
            "Maa macOS controller is unavailable",
        ) from exc

    return MacOSController(
        window_id,
        screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
        input_method=MaaMacOSInputMethodEnum.GlobalEvent,
    )


def _wait(value: Any) -> Any:
    waiter = getattr(value, "wait", None)
    return waiter() if callable(waiter) else value


def _connection_succeeded(connection: Any) -> bool:
    succeeded = getattr(connection, "succeeded", True)
    return bool(succeeded)


def _frame_shape_and_variance(frame: Any) -> tuple[int, int, bool]:
    if frame is None:
        return 0, 0, False

    # Maa returns a PIL image in the normal Python adapter path. Keep this
    # branch explicit so the probe does not require numpy just to validate a
    # frame returned by a fake controller.
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a project dependency
        Image = None  # type: ignore[assignment]

    if Image is not None and isinstance(frame, Image.Image):
        width, height = frame.size
        if width <= 0 or height <= 0:
            return width, height, False
        extrema = frame.convert("RGB").getextrema()
        return width, height, any(low != high for low, high in extrema)

    shape = getattr(frame, "shape", None)
    if shape is not None:
        try:
            dimensions = tuple(int(item) for item in shape)
            if len(dimensions) < 2:
                return 0, 0, False
            height, width = dimensions[:2]
            if width <= 0 or height <= 0 or getattr(frame, "size", 1) == 0:
                return width, height, False
            minimum = frame.min()
            maximum = frame.max()
            return width, height, bool(minimum != maximum)
        except (AttributeError, TypeError, ValueError):
            return 0, 0, False

    if isinstance(frame, (bytes, bytearray, memoryview)):
        data = bytes(frame)
        return (0, 0, False) if not data else (1, len(data), len(set(data)) > 1)

    size = getattr(frame, "size", None)
    if isinstance(size, tuple) and len(size) == 2:
        # A shape-only object does not expose enough pixels to prove that the
        # frame is nonempty; reject it instead of treating dimensions as data.
        return 0, 0, False

    return 0, 0, False


def _read_backend(log_path: Path | None) -> Backend:
    if log_path is None:
        raise MJAError(
            ErrorCode.CONTROLLER_PROBE_FAILED,
            "a Maa evidence log is required to identify the capture backend",
        )
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise MJAError(
            ErrorCode.CONTROLLER_PROBE_FAILED,
            f"could not read Maa evidence log: {log_path}",
        ) from exc

    transitions = log_text.count(FALLBACK_MARKER)
    if transitions > 1:
        raise MJAError(
            ErrorCode.CONTROLLER_PROBE_FAILED,
            "macOS capture backend switched more than once",
        )
    if transitions == 0:
        return "ScreenCaptureKit"

    marker_end = log_text.index(FALLBACK_MARKER) + len(FALLBACK_MARKER)
    if "ScreenCaptureKit" in log_text[marker_end:]:
        raise MJAError(
            ErrorCode.CONTROLLER_PROBE_FAILED,
            "ScreenCaptureKit was retried after the CoreGraphicsRegion fallback",
        )
    return "CoreGraphicsRegion"


def _validate_window_id(window_id: int) -> None:
    if isinstance(window_id, bool) or not isinstance(window_id, int) or window_id <= 0:
        raise MJAError(
            ErrorCode.WINDOW_NOT_FOUND,
            "window_id must be a positive integer",
        )


def probe_controller(
    window_id: int,
    *,
    frames: int = DEFAULT_FRAMES,
    controller_factory: Callable[[int], Any] | None = None,
    log_path: Path | None = None,
) -> ProbeResult:
    """Capture exactly ``frames`` read-only frames and validate their shape."""

    _validate_window_id(window_id)
    if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
        raise MJAError(
            ErrorCode.CONTROLLER_PROBE_FAILED,
            "frames must be a positive integer",
        )

    try:
        controller = (controller_factory or _default_controller_factory)(window_id)
        connection = _wait(controller.post_connection())
    except MJAError:
        raise
    except Exception as exc:
        raise MJAError(
            ErrorCode.CONTROLLER_CONNECT_FAILED,
            f"failed to connect macOS controller for window {window_id}",
        ) from exc

    if not _connection_succeeded(connection):
        raise MJAError(
            ErrorCode.CONTROLLER_CONNECT_FAILED,
            f"failed to connect macOS controller for window {window_id}",
        )

    try:
        if controller.set_screenshot_target_short_side(SCREENSHOT_SHORT_SIDE) is False:
            raise MJAError(
                ErrorCode.CONTROLLER_CONNECT_FAILED,
                "failed to set screenshot short side to 720",
            )
    except MJAError:
        raise
    except Exception as exc:
        raise MJAError(
            ErrorCode.CONTROLLER_CONNECT_FAILED,
            "failed to set screenshot short side to 720",
        ) from exc

    expected_size: tuple[int, int] | None = None
    nonempty_frames = 0
    for frame_number in range(frames):
        try:
            frame = _wait(controller.post_screencap()).get()
        except Exception as exc:
            raise MJAError(
                ErrorCode.CONTROLLER_PROBE_FAILED,
                f"screencap failed at frame {frame_number + 1}",
            ) from exc
        width, height, has_variance = _frame_shape_and_variance(frame)
        if width <= 0 or height <= 0 or not has_variance:
            raise MJAError(
                ErrorCode.CONTROLLER_PROBE_FAILED,
                f"frame {frame_number + 1} is empty or has no pixel variance",
            )
        if expected_size is None:
            expected_size = (width, height)
            if min(width, height) != SCREENSHOT_SHORT_SIDE:
                raise MJAError(
                    ErrorCode.CONTROLLER_PROBE_FAILED,
                    "captured frame short side is not 720 pixels",
                )
        elif expected_size != (width, height):
            raise MJAError(
                ErrorCode.CONTROLLER_PROBE_FAILED,
                "captured frame dimensions changed during probe",
            )
        nonempty_frames += 1

    backend = _read_backend(log_path)
    assert expected_size is not None
    return ProbeResult(
        window_id=window_id,
        frames=frames,
        width=expected_size[0],
        height=expected_size[1],
        nonempty_frames=nonempty_frames,
        backend=backend,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only Maa macOS controller probe")
    parser.add_argument("--window-id", required=True, type=int)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument(
        "--log-path",
        "--evidence-log-path",
        dest="log_path",
        type=Path,
        help="optional Maa log to inspect for the capture-backend transition",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help="directory for the probe JSON; its maafw.log is required for backend evidence",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.evidence_root is not None:
            args.evidence_root.mkdir(parents=True, exist_ok=True)
            if args.log_path is None:
                args.log_path = args.evidence_root / "maafw.log"
        result = probe_controller(
            args.window_id,
            frames=args.frames,
            log_path=args.log_path,
        )
    except MJAError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False, sort_keys=True))
        return 3
    output = json.dumps(asdict(result), ensure_ascii=False, sort_keys=True)
    if args.evidence_root is not None:
        (args.evidence_root / "probe-result.json").write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI.
    raise SystemExit(main())


__all__ = ["ProbeResult", "main", "probe_controller"]
