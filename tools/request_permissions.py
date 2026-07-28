from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

from agent.errors import MJAError
from agent.macos.permissions import ensure_permissions, request_permissions

PERMISSION_FAILURE_EXIT = 2


def request_native_permissions(
    *,
    request: Callable[[], None] = request_permissions,
    verify: Callable[[], None] = ensure_permissions,
) -> None:
    """Request macOS permissions once, then verify them without prompting."""

    request()
    verify()


def _system_settings_guidance(error: BaseException) -> str:
    code = getattr(error, "code", None)
    if getattr(code, "value", code) == "PERMISSION_SCREEN_CAPTURE":
        return (
            "Enable the requesting host in System Settings > Privacy & Security "
            "> Screen Recording, then run this command again."
        )
    if getattr(code, "value", code) == "PERMISSION_ACCESSIBILITY":
        return (
            "Enable the requesting host in System Settings > Privacy & Security "
            "> Accessibility, then run this command again."
        )
    return (
        "Enable the requesting host in System Settings > Privacy & Security, "
        "then run this command again."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit, one-shot native permission setup command."""

    del argv
    try:
        request_native_permissions()
    except MJAError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        print(_system_settings_guidance(exc), file=sys.stderr)
        return PERMISSION_FAILURE_EXIT
    except Exception as exc:
        print(f"native permission request failed: {exc}", file=sys.stderr)
        print(_system_settings_guidance(exc), file=sys.stderr)
        return PERMISSION_FAILURE_EXIT

    print("native macOS permissions are granted")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised on the target Mac
    raise SystemExit(main())


__all__ = ["PERMISSION_FAILURE_EXIT", "main", "request_native_permissions"]
