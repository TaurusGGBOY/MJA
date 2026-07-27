from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agent.errors import ErrorCode, MJAError
from agent.macos.window_state import Bounds, WindowSnapshot, WindowStateStore

GAME_WINDOW_TITLE = "对决！剑之川"
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720


@dataclass(frozen=True)
class GameWindow:
    window_id: int
    pid: int
    title: str
    bounds: Bounds


class WindowBackend(Protocol):
    def find_window(self, title: str, deadline: float) -> GameWindow | None: ...

    def frontmost_bundle_id(self) -> str | None: ...

    def game_process_running(self) -> bool: ...

    def activate_pid(self, pid: int) -> None: ...

    def set_bounds(self, window: GameWindow, bounds: Bounds) -> None: ...

    def read_window(self, window_id: int, pid: int) -> GameWindow | None: ...

    def activate_bundle(self, bundle_id: str) -> None: ...


class WindowLifecycle:
    """Pure orchestration for preparing and restoring the game window.

    The backend owns all macOS framework calls. This class only controls the
    order of discovery, state persistence, activation, resize, verification,
    and restoration, which keeps the safety-critical behavior unit-testable.
    """

    def __init__(
        self,
        backend: WindowBackend,
        store: WindowStateStore,
        *,
        title: str = GAME_WINDOW_TITLE,
        clock: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self.backend = backend
        self.store = store
        self.title = title
        self._clock = clock
        self._sleep = sleep
        self._prepared: GameWindow | None = None

    def prepare(self, timeout_seconds: float = 60) -> GameWindow:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")

        deadline = self._clock() + timeout_seconds
        window = self._discover(deadline)
        if window is None:
            code = (
                ErrorCode.APP_LAUNCH_TIMEOUT
                if not self.backend.game_process_running()
                else ErrorCode.WINDOW_NOT_FOUND
            )
            message = (
                "game process did not become available before the deadline"
                if code is ErrorCode.APP_LAUNCH_TIMEOUT
                else f"exact game window not found: {self.title}"
            )
            raise MJAError(code, message)

        snapshot = WindowSnapshot(
            window_id=window.window_id,
            pid=window.pid,
            bounds=window.bounds,
            previous_frontmost_bundle_id=self.backend.frontmost_bundle_id(),
        )
        # Persist before any activation or geometry mutation. A process crash
        # after this point therefore leaves enough information for recovery.
        self.store.save(snapshot)

        target = Bounds(window.bounds.x, window.bounds.y, TARGET_WIDTH, TARGET_HEIGHT)
        self.backend.activate_pid(window.pid)
        try:
            self.backend.set_bounds(window, target)
            actual = self.backend.read_window(window.window_id, window.pid)
        except Exception as exc:
            if isinstance(exc, MJAError):
                raise
            raise MJAError(
                ErrorCode.WINDOW_RESIZE_FAILED,
                f"failed to resize game window: {exc}",
            ) from exc

        if actual is None or actual.window_id != window.window_id or actual.pid != window.pid:
            raise MJAError(
                ErrorCode.WINDOW_RESIZE_FAILED,
                "window identity changed while resizing",
            )
        if actual.bounds != target:
            raise MJAError(
                ErrorCode.WINDOW_RESIZE_FAILED,
                f"window bounds read back as {actual.bounds!r}, expected {target!r}",
            )

        self._prepared = actual
        return actual

    def restore(self) -> None:
        snapshot = self.store.load_pending()
        if snapshot is None:
            self._prepared = None
            return

        try:
            current = self.backend.read_window(snapshot.window_id, snapshot.pid)
            if (
                current is None
                or current.window_id != snapshot.window_id
                or current.pid != snapshot.pid
            ):
                raise MJAError(
                    ErrorCode.WINDOW_RESTORE_FAILED,
                    "the original game window is no longer available",
                )

            self.backend.set_bounds(current, snapshot.bounds)
            restored = self.backend.read_window(snapshot.window_id, snapshot.pid)
            if (
                restored is None
                or restored.window_id != snapshot.window_id
                or restored.pid != snapshot.pid
            ):
                raise MJAError(
                    ErrorCode.WINDOW_RESTORE_FAILED,
                    "window identity changed during restoration",
                )
            if restored.bounds != snapshot.bounds:
                raise MJAError(
                    ErrorCode.WINDOW_RESTORE_FAILED,
                    f"window bounds read back as {restored.bounds!r}, expected {snapshot.bounds!r}",
                )
            if snapshot.previous_frontmost_bundle_id:
                self.backend.activate_bundle(snapshot.previous_frontmost_bundle_id)
            # Mark consumed only after geometry and frontmost-app restoration
            # have both completed successfully. A repeated call is a no-op.
            self.store.mark_restored()
            self._prepared = None
        except MJAError:
            raise
        except Exception as exc:
            raise MJAError(
                ErrorCode.WINDOW_RESTORE_FAILED,
                f"failed to restore game window: {exc}",
            ) from exc

    def has_pending_restore(self) -> bool:
        return self.store.load_pending() is not None

    def current_prepared_window(self) -> GameWindow:
        if self._prepared is None:
            raise MJAError(
                ErrorCode.WINDOW_NOT_FOUND,
                "game window has not been prepared",
            )
        return self._prepared

    def _discover(self, deadline: float) -> GameWindow | None:
        while True:
            window = self.backend.find_window(self.title, deadline)
            if window is not None:
                return window
            now = self._clock()
            if now >= deadline:
                return None
            self._sleep(min(0.1, deadline - now))


class PyObjCWindowBackend:
    """macOS implementation kept behind a runtime-only PyObjC boundary."""

    def __init__(self, title: str = GAME_WINDOW_TITLE) -> None:
        self.title = title
        self._quartz, self._appkit, self._ax = self._load_frameworks()

    @staticmethod
    def _load_frameworks() -> tuple[Any, Any, Any]:
        try:
            import AppKit as appkit
            import ApplicationServices as ax
            import Quartz as quartz
        except ImportError as exc:  # pragma: no cover - platform/runtime dependent
            raise RuntimeError("PyObjC macOS frameworks are unavailable") from exc
        return quartz, appkit, ax

    def find_window(self, title: str, deadline: float) -> GameWindow | None:
        del deadline
        quartz = self._quartz
        options = (
            quartz.kCGWindowListOptionOnScreenOnly
            | quartz.kCGWindowListExcludeDesktopElements
        )
        windows = quartz.CGWindowListCopyWindowInfo(options, quartz.kCGNullWindowID) or []
        for info in windows:
            if self._value(info, quartz.kCGWindowName) != title:
                continue
            if self._value(info, quartz.kCGWindowLayer) != 0:
                continue
            pid = int(self._value(info, quartz.kCGWindowOwnerPID))
            window_id = int(self._value(info, quartz.kCGWindowNumber))
            bounds = self._bounds_from_cg(self._value(info, quartz.kCGWindowBounds))
            return GameWindow(window_id, pid, title, bounds)
        return None

    def game_process_running(self) -> bool:
        workspace = self._appkit.NSWorkspace.sharedWorkspace()
        for application in workspace.runningApplications():
            name = application.localizedName() or application.processName()
            if name == self.title:
                return True
        return False

    def frontmost_bundle_id(self) -> str | None:
        application = self._appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        return application.bundleIdentifier() if application is not None else None

    def activate_pid(self, pid: int) -> None:
        application = (
            self._appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        )
        if application is None or not application.activateWithOptions_(
            self._appkit.NSApplicationActivateIgnoringOtherApps
        ):
            raise RuntimeError(f"could not activate process {pid}")

    def set_bounds(self, window: GameWindow, bounds: Bounds) -> None:
        ax_window = self._find_ax_window(window.pid, window.title)
        if ax_window is None:
            raise RuntimeError("Accessibility window was not found")
        point = self._ax.AXValueCreate(self._ax.kAXValueCGPointType, (bounds.x, bounds.y))
        size = self._ax.AXValueCreate(
            self._ax.kAXValueCGSizeType, (bounds.width, bounds.height)
        )
        if self._ax.AXUIElementSetAttributeValue(
            ax_window, self._ax.kAXPositionAttribute, point
        ) != 0:
            raise RuntimeError("could not set Accessibility window position")
        if self._ax.AXUIElementSetAttributeValue(
            ax_window, self._ax.kAXSizeAttribute, size
        ) != 0:
            raise RuntimeError("could not set Accessibility window size")

    def read_window(self, window_id: int, pid: int) -> GameWindow | None:
        found = self.find_window(self.title, time.monotonic())
        if found is None or found.window_id != window_id or found.pid != pid:
            return None
        return found

    def activate_bundle(self, bundle_id: str) -> None:
        applications = self._appkit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            bundle_id
        )
        if not applications or not applications[0].activateWithOptions_(
            self._appkit.NSApplicationActivateIgnoringOtherApps
        ):
            raise RuntimeError(f"could not restore frontmost application {bundle_id}")

    def _find_ax_window(self, pid: int, title: str) -> Any | None:
        ax = self._ax
        application = ax.AXUIElementCreateApplication(pid)
        result = ax.AXUIElementCopyAttributeValue(application, ax.kAXWindowsAttribute, None)
        windows = self._unwrap_ax(result) or []
        for window in windows:
            title_result = ax.AXUIElementCopyAttributeValue(window, ax.kAXTitleAttribute, None)
            if self._unwrap_ax(title_result) == title:
                return window
        return None

    @staticmethod
    def _unwrap_ax(result: Any) -> Any:
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
            error, value = result
            if error != 0:
                return None
            return value
        return result

    @staticmethod
    def _value(mapping: Any, key: Any) -> Any:
        try:
            return mapping[key]
        except (KeyError, TypeError):
            return mapping.get(str(key))

    @staticmethod
    def _bounds_from_cg(value: Any) -> Bounds:
        if value is None:
            raise RuntimeError("window has no screen bounds")
        return Bounds(
            int(value["X"] if "X" in value else value["x"]),
            int(value["Y"] if "Y" in value else value["y"]),
            int(value["Width"] if "Width" in value else value["width"]),
            int(value["Height"] if "Height" in value else value["height"]),
        )


def build_window_backend() -> PyObjCWindowBackend:
    return PyObjCWindowBackend()


def build_lifecycle(
    *,
    state_path: str | os.PathLike[str] | None = None,
    backend: WindowBackend | None = None,
) -> WindowLifecycle:
    path = Path(state_path or os.environ.get("MJA_WINDOW_STATE", ".mja-state/window.json"))
    return WindowLifecycle(backend or build_window_backend(), WindowStateStore(path))


__all__ = [
    "Bounds",
    "GameWindow",
    "PyObjCWindowBackend",
    "WindowBackend",
    "WindowLifecycle",
    "WindowSnapshot",
    "WindowStateStore",
    "build_lifecycle",
    "build_window_backend",
]
