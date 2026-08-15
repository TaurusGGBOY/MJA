"""Bounded Android gestures driven only by current-frame recognition boxes."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence
from numbers import Integral
from typing import Any

from .models import ActionIntent, InputKind

DEFAULT_CALIBRATION_SIZE = (1280, 720)
MIN_GESTURE_DURATION_MS = 50
MAX_GESTURE_DURATION_MS = 5_000
CONTROLLER_JOB_TIMEOUT_SECONDS = 30.0


def _values(value: Any, length: int, label: str) -> tuple[int, ...]:
    if value is None or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must contain exactly {length} integers")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{label} must contain exactly {length} integers") from exc
    if len(values) != length or any(
        isinstance(item, bool) or not isinstance(item, Integral) for item in values
    ):
        raise ValueError(f"{label} must contain exactly {length} integers")
    return tuple(int(item) for item in values)


def _duration_ms(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("duration_ms must be an integer")
    duration = int(value)
    if not MIN_GESTURE_DURATION_MS <= duration <= MAX_GESTURE_DURATION_MS:
        raise ValueError(
            f"duration_ms must be between {MIN_GESTURE_DURATION_MS} and "
            f"{MAX_GESTURE_DURATION_MS}"
        )
    return duration


def map_box_center(
    box: Sequence[int],
    frame_size: Sequence[int],
    calibration_size: Sequence[int] = DEFAULT_CALIBRATION_SIZE,
) -> tuple[int, int]:
    """Map a current-frame box to the bounded Android controller resolution."""

    x, y, width, height = _values(box, 4, "recognition box")
    frame_width, frame_height = _values(frame_size, 2, "frame size")
    target_width, target_height = _values(calibration_size, 2, "calibration size")
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame size must be positive")
    if target_width <= 0 or target_height <= 0:
        raise ValueError("calibration size must be positive")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("recognition box must have positive dimensions")
    if x + width > frame_width or y + height > frame_height:
        raise ValueError("recognition box must be inside the capture frame")
    return (
        math.floor((x + width / 2) * target_width / frame_width + 0.5),
        math.floor((y + height / 2) * target_height / frame_height + 0.5),
    )


def _wait_job(job: Any) -> None:
    wait = getattr(job, "wait", None)
    if not callable(wait):
        raise RuntimeError("Android controller gesture did not return a waitable job")

    # Maa jobs normally complete quickly, but a dead ADB transport can leave
    # the native wait blocked forever while the outer task supervisor keeps
    # waiting for the full business timeout. Keep the wait on a daemon thread
    # so the custom action can fail fast and let AndroidRun classify the task
    # locally; every actual input still goes through Maa's controller.
    completed = threading.Event()
    outcome: dict[str, Any] = {}

    def wait_for_native_job() -> None:
        try:
            outcome["result"] = wait()
        except BaseException as exc:  # propagate native/controller failures
            outcome["error"] = exc
        finally:
            completed.set()

    threading.Thread(target=wait_for_native_job, daemon=True).start()
    if not completed.wait(CONTROLLER_JOB_TIMEOUT_SECONDS):
        raise RuntimeError(
            "Android controller gesture wait timed out; ADB/Maa transport is unavailable"
        )
    error = outcome.get("error")
    if error is not None:
        raise error
    if outcome.get("result") is False:
        raise RuntimeError("Android controller gesture failed")
    if hasattr(job, "succeeded") and not job.succeeded:
        raise RuntimeError("Android controller gesture failed")


class AndroidWorkflowDriver:
    """Execute only bounded gestures mapped from current recognition boxes."""

    def __init__(
        self,
        controller: Any,
        *,
        frame_size: Sequence[int] = DEFAULT_CALIBRATION_SIZE,
        calibration_size: Sequence[int] = DEFAULT_CALIBRATION_SIZE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.controller = controller
        self.frame_size = _values(frame_size, 2, "frame size")
        self.calibration_size = _values(calibration_size, 2, "calibration size")
        self._sleep = sleep

    def _point(self, box: Sequence[int], frame_size: Sequence[int] | None) -> tuple[int, int]:
        return map_box_center(
            box,
            self.frame_size if frame_size is None else frame_size,
            self.calibration_size,
        )

    def click(
        self,
        box: Sequence[int],
        *,
        frame_size: Sequence[int] | None = None,
    ) -> None:
        x, y = self._point(box, frame_size)
        _wait_job(self.controller.post_click(x, y))

    def click_key(self, key: int) -> None:
        """Send one Android key event through Maa's Android controller."""

        if isinstance(key, bool) or not isinstance(key, Integral):
            raise ValueError("Android key must be an integer")
        post_click_key = getattr(self.controller, "post_click_key", None)
        if not callable(post_click_key):
            raise ValueError("Android controller does not support key events")
        _wait_job(post_click_key(int(key)))

    def drag_tap(
        self,
        box: Sequence[int],
        *,
        frame_size: Sequence[int] | None = None,
    ) -> None:
        """Tap a Unity button with a one-pixel Maa touch move.

        A few Unity UI controls on the Android build ignore Maa's synthesized
        ``post_click`` even though the same controller can deliver a real
        touch sequence.  Keep this path bounded to the current recognition
        box and make the smallest possible move before releasing the contact.
        """

        x, y = self._point(box, frame_size)
        # Unity's Android event bridge can report a queued one-pixel swipe as
        # successful while never delivering a Button pointer-up.  Emit the
        # complete Maa touch lifecycle explicitly: down, a tiny move, then
        # up.  Every event remains on Maa's Android ADB controller; this is
        # not a raw ``adb shell input`` fallback.
        post_down = getattr(self.controller, "post_touch_down", None)
        post_move = getattr(self.controller, "post_touch_move", None)
        post_up = getattr(self.controller, "post_touch_up", None)
        if post_down is None or post_move is None or post_up is None:
            # Keep compatibility with older/test controllers that expose
            # Maa's queued swipe but not the lower-level touch lifecycle.
            post_swipe = getattr(self.controller, "post_swipe", None)
            if post_swipe is None:
                raise ValueError("Android controller does not support drag tap")
            _wait_job(post_swipe(x, y, x + 1, y + 1, 100))
            return
        _wait_job(post_down(x, y, contact=0, pressure=1))
        try:
            self._sleep(0.1)
            _wait_job(post_move(x + 1, y + 1, contact=0, pressure=1))
            self._sleep(0.05)
        finally:
            _wait_job(post_up(contact=0))

    def swipe(
        self,
        start_box: Sequence[int],
        end_box: Sequence[int],
        *,
        duration_ms: int = 300,
        frame_size: Sequence[int] | None = None,
    ) -> None:
        duration = _duration_ms(duration_ms)
        start_x, start_y = self._point(start_box, frame_size)
        end_x, end_y = self._point(end_box, frame_size)
        post_swipe = getattr(self.controller, "post_swipe", None)
        if post_swipe is None:
            raise ValueError("Android controller does not support swipe")
        _wait_job(post_swipe(start_x, start_y, end_x, end_y, duration))

    def long_press(
        self,
        box: Sequence[int],
        *,
        duration_ms: int = 500,
        frame_size: Sequence[int] | None = None,
    ) -> None:
        duration = _duration_ms(duration_ms)
        x, y = self._point(box, frame_size)
        post_long_press = getattr(self.controller, "post_long_press", None)
        if post_long_press is not None:
            _wait_job(post_long_press(x, y, duration))
            return

        post_down = getattr(self.controller, "post_touch_down", None)
        post_up = getattr(self.controller, "post_touch_up", None)
        if post_down is None or post_up is None:
            raise ValueError("Android controller does not support long press")
        try:
            _wait_job(post_down(x, y))
            self._sleep(duration / 1000)
        finally:
            _wait_job(post_up(x, y))

    def execute(
        self,
        intent: ActionIntent,
        *,
        box: Sequence[int] | None = None,
        end_box: Sequence[int] | None = None,
        frame_size: Sequence[int] | None = None,
        duration_ms: int = 300,
    ) -> None:
        """Execute a previously authorized intent using fresh recognition boxes."""

        if not isinstance(intent, ActionIntent):
            raise TypeError("intent must be an ActionIntent")
        if intent.input_kind is InputKind.NONE:
            return
        if box is None:
            raise ValueError("a current-frame recognition box is required")
        if intent.input_kind is InputKind.CLICK:
            self.click(box, frame_size=frame_size)
        elif intent.input_kind is InputKind.SWIPE:
            if end_box is None:
                raise ValueError("swipe requires an end recognition box")
            self.swipe(box, end_box, duration_ms=duration_ms, frame_size=frame_size)
        elif intent.input_kind is InputKind.LONG_PRESS:
            self.long_press(box, duration_ms=duration_ms, frame_size=frame_size)
        else:  # pragma: no cover - InputKind is exhaustively validated by the model.
            raise ValueError("unsupported input kind")


__all__ = [
    "AndroidWorkflowDriver",
    "DEFAULT_CALIBRATION_SIZE",
    "MAX_GESTURE_DURATION_MS",
    "MIN_GESTURE_DURATION_MS",
    "map_box_center",
]
