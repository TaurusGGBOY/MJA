from __future__ import annotations

import inspect

import pytest

from agent import pretask
from agent.errors import ErrorCode, MJAError
from tools import request_permissions as command


def test_request_native_permissions_requests_before_nonprompting_verify() -> None:
    calls: list[str] = []

    command.request_native_permissions(
        request=lambda: calls.append("request"),
        verify=lambda: calls.append("verify"),
    )

    assert calls == ["request", "verify"]


def test_request_exception_returns_stable_nonzero_exit(monkeypatch, capsys) -> None:
    def fail() -> None:
        raise RuntimeError("native API unavailable")

    monkeypatch.setattr(command, "request_native_permissions", fail)

    assert command.main([]) == command.PERMISSION_FAILURE_EXIT
    output = capsys.readouterr().err
    assert "native permission request failed: native API unavailable" in output
    assert "System Settings > Privacy & Security" in output


def test_verification_failure_reports_the_permission_and_system_settings(
    monkeypatch, capsys
) -> None:
    failure = MJAError(
        ErrorCode.PERMISSION_ACCESSIBILITY,
        "accessibility permission is not granted",
    )

    def fail() -> None:
        raise failure

    monkeypatch.setattr(command, "request_native_permissions", fail)

    assert command.main([]) == command.PERMISSION_FAILURE_EXIT
    output = capsys.readouterr().err
    assert "PERMISSION_ACCESSIBILITY" in output
    assert "System Settings > Privacy & Security > Accessibility" in output


def test_ordinary_pretask_does_not_import_or_call_explicit_request_command() -> None:
    source = inspect.getsource(pretask)

    assert "tools.request_permissions" not in source
    assert "request_native_permissions" not in source
    assert "ensure_permissions" in source


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("request failed"),
        MJAError(ErrorCode.PERMISSION_SCREEN_CAPTURE, "denied"),
    ],
)
def test_request_native_permissions_does_not_verify_after_request_failure(error) -> None:
    calls: list[str] = []

    def request() -> None:
        calls.append("request")
        raise error

    with pytest.raises(type(error)):
        command.request_native_permissions(
            request=request,
            verify=lambda: calls.append("verify"),
        )

    assert calls == ["request"]
