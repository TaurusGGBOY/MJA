"""Small controller-input adapter with no device discovery or shell fallback."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def box_values(box: Any) -> tuple[int, int, int, int]:
    """Normalize a Maa rectangle while rejecting degenerate input."""

    if all(hasattr(box, name) for name in ("x", "y", "w", "h")):
        # MaaFramework's native ``Rect`` uses x/y/w/h.  Custom actions receive
        # this object directly, so accepting only width/height makes every
        # real controller input fail before it reaches AdbController.
        values = (box.x, box.y, box.w, box.h)
    elif all(hasattr(box, name) for name in ("x", "y", "width", "height")):
        values = (box.x, box.y, box.width, box.height)
    elif isinstance(box, Sequence) and not isinstance(box, (str, bytes, bytearray)):
        if len(box) != 4:
            raise ValueError("controller box must contain x, y, width, height")
        values = tuple(box)
    else:
        raise ValueError("controller box must contain x, y, width, height")

    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("controller box values must be integers")
    x, y, width, height = values
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("controller box must be on-screen and non-empty")
    return x, y, width, height


def resolution_values(resolution: Any) -> tuple[int, int] | None:
    if resolution is None:
        return None
    if all(hasattr(resolution, name) for name in ("width", "height")):
        values = (resolution.width, resolution.height)
    elif isinstance(resolution, Sequence) and not isinstance(
        resolution, (str, bytes, bytearray)
    ):
        if len(resolution) != 2:
            raise ValueError("controller resolution must contain width and height")
        values = tuple(resolution)
    else:
        raise ValueError("controller resolution must contain width and height")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("controller resolution values must be integers")
    width, height = values
    if width <= 0 or height <= 0:
        raise ValueError("controller resolution must be positive")
    return width, height


def _ensure_on_screen(box: tuple[int, int, int, int], resolution: Any) -> None:
    size = resolution_values(resolution)
    if size is None:
        return
    screen_width, screen_height = size
    x, y, width, height = box
    if x + width > screen_width or y + height > screen_height:
        raise ValueError("controller box is outside the controller resolution")


def wait_for_controller(job: Any, operation: str) -> bool:
    """Wait for a posted Maa job and propagate failures as infrastructure errors."""

    wait = getattr(job, "wait", None)
    if not callable(wait):
        raise RuntimeError(f"controller {operation} did not return a waitable job")
    if not wait():
        raise RuntimeError(f"controller {operation} failed")
    return True


def click_box(controller: Any, box: Any, *, resolution: Any = None) -> bool:
    normalized = box_values(box)
    _ensure_on_screen(normalized, resolution)
    x, y, width, height = normalized
    job = controller.post_click(x + width // 2, y + height // 2)
    return wait_for_controller(job, "click")


def swipe_box(
    controller: Any,
    box: Any,
    *,
    dx: int,
    dy: int,
    duration_ms: int,
    resolution: Any = None,
) -> bool:
    normalized = box_values(box)
    _ensure_on_screen(normalized, resolution)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (dx, dy)):
        raise ValueError("swipe vector must contain integers")
    if abs(dx) > 1000 or abs(dy) > 1000:
        raise ValueError("swipe vector is too large")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
        raise ValueError("swipe duration must be an integer")
    if not 50 <= duration_ms <= 5000:
        raise ValueError("swipe duration must be between 50 and 5000 milliseconds")

    x, y, width, height = normalized
    start_x, start_y = x + width // 2, y + height // 2
    end_x, end_y = start_x + dx, start_y + dy
    size = resolution_values(resolution)
    if size is not None:
        screen_width, screen_height = size
        if not 0 <= end_x < screen_width or not 0 <= end_y < screen_height:
            raise ValueError("swipe endpoint is outside the controller resolution")

    job = controller.post_swipe(start_x, start_y, end_x, end_y, duration_ms)
    return wait_for_controller(job, "swipe")


__all__ = [
    "box_values",
    "click_box",
    "resolution_values",
    "swipe_box",
    "wait_for_controller",
]
