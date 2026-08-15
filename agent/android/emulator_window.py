"""Bring the Android Emulator's host window to the foreground when needed."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

EMULATOR_PROCESS_NAME = "qemu-system-aarch64"
EMULATOR_WINDOW_PREFIX = "Android Emulator - "


@dataclass(frozen=True)
class EmulatorWindow:
    pid: int
    title: str


class EmulatorWindowBackend(Protocol):
    def find_standard_window(self, avd_name: str) -> EmulatorWindow | None: ...

    def activate_pid(self, pid: int) -> bool: ...


class PyObjCEmulatorWindowBackend:
    """Find and activate the Android Emulator's macOS host window."""

    def __init__(self) -> None:
        try:
            import AppKit as appkit
            import ApplicationServices as ax
        except ImportError as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("PyObjC macOS frameworks are unavailable") from exc
        self._appkit = appkit
        self._ax = ax

    def find_standard_window(self, avd_name: str) -> EmulatorWindow | None:
        expected_prefix = f"{EMULATOR_WINDOW_PREFIX}{avd_name}:"
        workspace = self._appkit.NSWorkspace.sharedWorkspace()
        for application in workspace.runningApplications():
            process_name = application.localizedName()
            if not process_name:
                executable_url = application.executableURL()
                process_name = (
                    executable_url.lastPathComponent()
                    if executable_url is not None
                    else None
                )
            if process_name != EMULATOR_PROCESS_NAME:
                continue
            pid = int(application.processIdentifier())
            root = self._ax.AXUIElementCreateApplication(pid)
            result = self._ax.AXUIElementCopyAttributeValue(
                root, self._ax.kAXWindowsAttribute, None
            )
            for window in self._unwrap(result) or []:
                title = self._attribute(window, self._ax.kAXTitleAttribute)
                subrole = self._attribute(window, self._ax.kAXSubroleAttribute)
                # qemu also exposes an untitled, narrow emulator toolbar. It
                # must never be mistaken for the Stage Manager app window.
                if (
                    isinstance(title, str)
                    and title.startswith(expected_prefix)
                    and subrole == "AXStandardWindow"
                ):
                    return EmulatorWindow(pid=pid, title=title)
        return None

    def activate_pid(self, pid: int) -> bool:
        application = self._ax.AXUIElementCreateApplication(pid)
        error = self._ax.AXUIElementSetAttributeValue(
            application,
            self._ax.kAXFrontmostAttribute,
            True,
        )
        if error != 0:
            return False
        result = self._ax.AXUIElementCopyAttributeValue(
            application, self._ax.kAXFrontmostAttribute, None
        )
        return self._unwrap(result) is True

    def _attribute(self, element: Any, attribute: Any) -> Any:
        return self._unwrap(
            self._ax.AXUIElementCopyAttributeValue(element, attribute, None)
        )

    @staticmethod
    def _unwrap(result: Any) -> Any:
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
            error, value = result
            return value if error == 0 else None
        return result


def ensure_emulator_foreground(
    avd_name: str,
    *,
    backend: EmulatorWindowBackend | None = None,
    timeout_seconds: float = 5.0,
    clock: Any = time.monotonic,
    sleep: Any = time.sleep,
) -> bool:
    """Bring a Stage-Manager-hidden Android emulator to the foreground."""

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must not be negative")
    selected_backend = backend or PyObjCEmulatorWindowBackend()
    deadline = clock() + timeout_seconds
    while True:
        window = selected_backend.find_standard_window(avd_name)
        if window is not None:
            return selected_backend.activate_pid(window.pid)
        now = clock()
        if now >= deadline:
            return False
        sleep(min(0.1, deadline - now))


__all__ = [
    "EMULATOR_PROCESS_NAME",
    "EMULATOR_WINDOW_PREFIX",
    "EmulatorWindow",
    "EmulatorWindowBackend",
    "PyObjCEmulatorWindowBackend",
    "ensure_emulator_foreground",
]
