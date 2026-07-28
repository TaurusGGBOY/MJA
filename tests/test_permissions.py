import pytest

from agent.macos.permissions import (
    ErrorCode,
    MJAError,
    ensure_permissions,
    request_permissions,
)


@pytest.mark.parametrize(
    ("screen", "accessibility", "code"),
    [
        (False, True, ErrorCode.PERMISSION_SCREEN_CAPTURE),
        (True, False, ErrorCode.PERMISSION_ACCESSIBILITY),
    ],
)
def test_missing_permission_fails_before_window_work(screen, accessibility, code) -> None:
    with pytest.raises(MJAError) as caught:
        ensure_permissions(lambda: screen, lambda: accessibility)
    assert caught.value.code == code


def test_both_permissions_pass() -> None:
    ensure_permissions(lambda: True, lambda: True)


def test_screen_probe_runs_before_accessibility_probe() -> None:
    calls = []

    ensure_permissions(
        lambda: calls.append("screen") or True,
        lambda: calls.append("accessibility") or True,
    )

    assert calls == ["screen", "accessibility"]


def test_probe_exception_maps_to_stable_permission_error() -> None:
    with pytest.raises(MJAError) as caught:
        ensure_permissions(lambda: 1 / 0, lambda: True)

    assert caught.value.code == ErrorCode.PERMISSION_SCREEN_CAPTURE


def test_screen_request_exception_maps_to_stable_permission_error() -> None:
    with pytest.raises(MJAError) as caught:
        request_permissions(
            screen_request=lambda: 1 / 0,
            accessibility_request=lambda: None,
        )

    assert caught.value.code == ErrorCode.PERMISSION_SCREEN_CAPTURE


def test_accessibility_request_exception_maps_to_stable_permission_error() -> None:
    with pytest.raises(MJAError) as caught:
        request_permissions(
            screen_request=lambda: None,
            accessibility_request=lambda: 1 / 0,
        )

    assert caught.value.code == ErrorCode.PERMISSION_ACCESSIBILITY
