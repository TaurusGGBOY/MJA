"""Small controller-input adapter with no device discovery or shell fallback."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from time import sleep
from typing import Any

CONTROLLER_JOB_TIMEOUT_SECONDS = 30.0


def _wait_job(
    job: Any, *, timeout_seconds: float = CONTROLLER_JOB_TIMEOUT_SECONDS
) -> None:
    """Wait for a Maa controller job without blocking forever on a dead transport."""

    wait = getattr(job, "wait", None)
    if not callable(wait):
        raise RuntimeError("Maa controller job did not return a waitable job")
    if timeout_seconds <= 0:
        raise ValueError("Maa controller job timeout must be positive")

    completed = threading.Event()
    outcome: dict[str, Any] = {}

    def wait_for_native_job() -> None:
        try:
            outcome["result"] = wait()
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            completed.set()

    threading.Thread(target=wait_for_native_job, daemon=True).start()
    if not completed.wait(timeout_seconds):
        raise RuntimeError("Maa controller job wait timed out")
    error = outcome.get("error")
    if error is not None:
        raise error
    if outcome.get("result") is False:
        raise RuntimeError("Maa controller job failed")
    if hasattr(job, "succeeded") and not job.succeeded:
        raise RuntimeError("Maa controller job failed")


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


def drag_tap_box(controller: Any, box: Any, *, resolution: Any = None) -> bool:
    """Deliver a one-pixel touch tap for Unity controls that ignore post_click."""

    normalized = box_values(box)
    _ensure_on_screen(normalized, resolution)
    x, y, width, height = normalized
    start_x, start_y = x + width // 2, y + height // 2
    post_down = getattr(controller, "post_touch_down", None)
    post_move = getattr(controller, "post_touch_move", None)
    post_up = getattr(controller, "post_touch_up", None)
    if not all(callable(method) for method in (post_down, post_move, post_up)):
        post_swipe = getattr(controller, "post_swipe", None)
        if not callable(post_swipe):
            raise RuntimeError("controller does not support drag tap")
        job = post_swipe(start_x, start_y, start_x + 1, start_y + 1, 100)
        return wait_for_controller(job, "drag tap")

    wait_for_controller(post_down(start_x, start_y, contact=0, pressure=1), "touch down")
    try:
        sleep(0.1)
        wait_for_controller(
            post_move(start_x + 1, start_y + 1, contact=0, pressure=1),
            "touch move",
        )
        sleep(0.05)
    finally:
        wait_for_controller(post_up(contact=0), "touch up")
    return True


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
    "drag_tap_box",
    "resolution_values",
    "swipe_box",
    "_wait_job",
    "wait_for_controller",
]
