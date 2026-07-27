from __future__ import annotations

import logging
import math
import subprocess
import time
from collections.abc import Callable
from numbers import Integral
from typing import Any

from agent.macos.window_lifecycle import WindowLifecycle, build_lifecycle

CLICLICK_PATH = "/opt/homebrew/bin/cliclick"
CLICK_SETTLE_SECONDS = 0.15
PREPARED_WINDOW_SIZE = (1280, 720)
LOGGER = logging.getLogger(__name__)


try:  # Maa is available in the assembled runtime, but not in bare test shells.
    from maa.agent.agent_server import AgentServer
    from maa.context import Context
    from maa.custom_action import CustomAction
except ImportError:  # pragma: no cover - exercised only without MaaFw installed.
    AgentServer = None  # type: ignore[assignment]
    Context = Any  # type: ignore[misc,assignment]

    class CustomAction:
        class RunResult:
            def __init__(self, success: bool) -> None:
                self.success = success


def _strict_values(value: Any, *, length: int, label: str) -> tuple[int, ...]:
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


def _window_values(window_bounds: Any) -> tuple[int, int, int, int]:
    if all(hasattr(window_bounds, name) for name in ("x", "y", "width", "height")):
        values = (
            window_bounds.x,
            window_bounds.y,
            window_bounds.width,
            window_bounds.height,
        )
    else:
        values = _strict_values(window_bounds, length=4, label="window bounds")
    if any(isinstance(item, bool) or not isinstance(item, Integral) for item in values):
        raise ValueError("window bounds must contain exactly 4 integers")
    x, y, width, height = (int(item) for item in values)
    if width <= 0 or height <= 0:
        raise ValueError("window bounds must have positive dimensions")
    if (width, height) != PREPARED_WINDOW_SIZE:
        raise ValueError("window bounds must be 1280x720")
    return x, y, width, height


def map_box_center(
    box: Any,
    capture_size: Any,
    window_bounds: Any,
) -> tuple[int, int]:
    """Map a recognition rectangle center into global screen coordinates."""

    x, y, width, height = _strict_values(box, length=4, label="recognition box")
    capture_width, capture_height = _strict_values(
        capture_size,
        length=2,
        label="capture size",
    )
    window_x, window_y, window_width, window_height = _window_values(window_bounds)

    if capture_width <= 0 or capture_height <= 0:
        raise ValueError("capture size must have positive dimensions")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("recognition box must have positive dimensions inside the capture")
    if x + width > capture_width or y + height > capture_height:
        raise ValueError("recognition box must be inside the capture")

    center_x = x + width / 2
    center_y = y + height / 2
    mapped_x = window_x + int(math.floor(center_x * window_width / capture_width + 0.5))
    mapped_y = window_y + int(math.floor(center_y * window_height / capture_height + 0.5))
    return mapped_x, mapped_y


def _default_pointer_position() -> tuple[int, int]:
    try:
        import Quartz

        point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return int(round(point.x)), int(round(point.y))
    except (ImportError, AttributeError, TypeError) as exc:  # pragma: no cover - macOS only.
        raise RuntimeError("Quartz mouse position API is unavailable") from exc


def _default_activate(pid: int) -> None:
    try:
        import AppKit

        application = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if application is None or not application.activateWithOptions_(
            AppKit.NSApplicationActivateIgnoringOtherApps
        ):
            raise RuntimeError(f"could not activate game process {pid}")
    except ImportError as exc:  # pragma: no cover - macOS only.
        raise RuntimeError("AppKit process activation API is unavailable") from exc


class ClickExecutor:
    def __init__(
        self,
        *,
        run: Callable[..., Any] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
        pointer_position: Callable[[], tuple[int, int]] = _default_pointer_position,
        activate: Callable[[int], None] = _default_activate,
    ) -> None:
        self.run = run
        self.sleep = sleep
        self.pointer_position = pointer_position
        self.activate = activate

    def click(self, box: Any, capture_size: Any, window_bounds: Any, pid: int) -> None:
        # Validate and map before activation or any subprocess call. This is the
        # safety gate that prevents a click when recognition did not produce a box.
        x, y = map_box_center(box, capture_size, window_bounds)
        if isinstance(pid, bool) or not isinstance(pid, Integral) or pid <= 0:
            raise ValueError("process id must be a positive integer")

        self.activate(int(pid))
        self.sleep(CLICK_SETTLE_SECONDS)
        original_pointer = self.pointer_position()
        try:
            self._run_cliclick(f"c:{x},{y}")
            LOGGER.info("clicked mapped recognition center (%s, %s)", x, y)
        finally:
            self._run_cliclick(f"m:{original_pointer[0]},{original_pointer[1]}")

    def _run_cliclick(self, command: str) -> None:
        argv = [CLICLICK_PATH, command]
        result = self.run(argv, check=False, capture_output=True, text=True)
        returncode = getattr(result, "returncode", None)
        if returncode != 0:
            stderr = str(getattr(result, "stderr", "") or "").strip()
            suffix = f": {stderr}" if stderr else ""
            raise RuntimeError(f"cliclick failed with exit code {returncode}{suffix}")


def build_executor(lifecycle: WindowLifecycle | None = None) -> ClickExecutor:
    lifecycle = lifecycle or build_lifecycle()
    return ClickExecutor(activate=lifecycle.backend.activate_pid)


class MacOSForegroundClick(CustomAction):
    def run(self, context: Context, argv: Any) -> Any:
        lifecycle = build_lifecycle()
        window = lifecycle.current_prepared_window()
        bounds = window.bounds
        capture_size = context.tasker.controller.resolution
        build_executor(lifecycle).click(
            argv.box,
            capture_size,
            (bounds.x, bounds.y, bounds.width, bounds.height),
            window.pid,
        )
        return CustomAction.RunResult(success=True)


if AgentServer is not None:  # Register only when the Maa agent runtime is present.
    MacOSForegroundClick = AgentServer.custom_action("MacOSForegroundClick")(
        MacOSForegroundClick
    )


__all__ = [
    "CLICLICK_PATH",
    "CLICK_SETTLE_SECONDS",
    "ClickExecutor",
    "MacOSForegroundClick",
    "build_executor",
    "map_box_center",
]
