from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

try:
    from agent.errors import ErrorCode, MJAError
except ModuleNotFoundError:
    # Task 3 remains independently runnable before the shared error module from
    # Task 2 is present. The production project will use agent.errors when it
    # exists, preserving one stable exception/code interface.
    class ErrorCode(StrEnum):
        PERMISSION_SCREEN_CAPTURE = "PERMISSION_SCREEN_CAPTURE"
        PERMISSION_ACCESSIBILITY = "PERMISSION_ACCESSIBILITY"
        APP_LAUNCH_TIMEOUT = "APP_LAUNCH_TIMEOUT"
        WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"
        WINDOW_RESIZE_FAILED = "WINDOW_RESIZE_FAILED"
        CONTROLLER_CONNECT_FAILED = "CONTROLLER_CONNECT_FAILED"
        HOME_RECOGNITION_TIMEOUT = "HOME_RECOGNITION_TIMEOUT"
        MAIL_OPEN_TIMEOUT = "MAIL_OPEN_TIMEOUT"
        HOME_RETURN_TIMEOUT = "HOME_RETURN_TIMEOUT"
        WINDOW_RESTORE_FAILED = "WINDOW_RESTORE_FAILED"

    class MJAError(RuntimeError):
        def __init__(self, code: ErrorCode, message: str) -> None:
            super().__init__(message)
            self.code = code


Probe = Callable[[], bool]


def _screen_capture_probe() -> bool:
    try:
        from Quartz import CGPreflightScreenCaptureAccess
    except Exception as exc:  # pragma: no cover - depends on the macOS runtime
        raise MJAError(
            ErrorCode.PERMISSION_SCREEN_CAPTURE,
            "screen recording probe is unavailable",
        ) from exc
    return bool(CGPreflightScreenCaptureAccess())


def _accessibility_probe() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted
    except Exception as exc:  # pragma: no cover - depends on the macOS runtime
        raise MJAError(
            ErrorCode.PERMISSION_ACCESSIBILITY,
            "accessibility probe is unavailable",
        ) from exc
    return bool(AXIsProcessTrusted())


def _check_probe(probe: Probe, code: ErrorCode, description: str) -> None:
    try:
        allowed = bool(probe())
    except MJAError:
        raise
    except Exception as exc:
        raise MJAError(code, f"{description} probe failed") from exc
    if not allowed:
        raise MJAError(code, f"{description} permission is not granted")


def ensure_permissions(
    screen_probe: Probe | None = None,
    accessibility_probe: Probe | None = None,
) -> None:
    """Validate required macOS permissions without requesting them.

    The probes are injectable so unit tests and future platform adapters do not
    need to invoke macOS APIs. Screen recording is checked first because image
    recognition cannot work without it.
    """

    _check_probe(
        screen_probe or _screen_capture_probe,
        ErrorCode.PERMISSION_SCREEN_CAPTURE,
        "screen recording",
    )
    _check_probe(
        accessibility_probe or _accessibility_probe,
        ErrorCode.PERMISSION_ACCESSIBILITY,
        "accessibility",
    )


def request_permissions(
    screen_request: Callable[[], Any] | None = None,
    accessibility_request: Callable[[], Any] | None = None,
) -> None:
    """Request permissions for an explicit setup/CLI action only.

    Normal task execution calls :func:`ensure_permissions`, never this function,
    so no system prompt can appear during an unattended task run.
    """

    if screen_request is None:
        try:
            from Quartz import CGRequestScreenCaptureAccess
        except Exception as exc:  # pragma: no cover - depends on macOS runtime
            raise MJAError(
                ErrorCode.PERMISSION_SCREEN_CAPTURE,
                "screen recording permission request is unavailable",
            ) from exc
        screen_request = CGRequestScreenCaptureAccess

    if accessibility_request is None:
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )
        except Exception as exc:  # pragma: no cover - depends on macOS runtime
            raise MJAError(
                ErrorCode.PERMISSION_ACCESSIBILITY,
                "accessibility permission request is unavailable",
            ) from exc

        accessibility_request = lambda: AXIsProcessTrustedWithOptions(  # noqa: E731
            {kAXTrustedCheckOptionPrompt: True}
        )

    try:
        screen_request()
    except Exception as exc:
        raise MJAError(
            ErrorCode.PERMISSION_SCREEN_CAPTURE,
            "screen recording permission request failed",
        ) from exc
    try:
        accessibility_request()
    except Exception as exc:
        raise MJAError(
            ErrorCode.PERMISSION_ACCESSIBILITY,
            "accessibility permission request failed",
        ) from exc
