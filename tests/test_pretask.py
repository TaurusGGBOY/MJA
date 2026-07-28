from __future__ import annotations

from agent import pretask
from agent.errors import ErrorCode, MJAError


class FakeLifecycle:
    def __init__(self, *, pending: bool = False, prepare_error: Exception | None = None) -> None:
        self.pending = pending
        self.prepare_error = prepare_error
        self.calls: list[object] = []

    def has_pending_restore(self) -> bool:
        return self.pending

    def restore(self) -> None:
        self.calls.append("restore")
        self.pending = False

    def prepare(self, timeout_seconds: float) -> None:
        self.calls.append(("prepare", timeout_seconds))
        if self.prepare_error is not None:
            raise self.prepare_error


def test_pretask_restores_stale_state_before_new_prepare(monkeypatch) -> None:
    lifecycle = FakeLifecycle(pending=True)
    monkeypatch.setattr(pretask, "build_lifecycle", lambda: lifecycle)
    monkeypatch.setattr(pretask, "ensure_permissions", lambda: None)

    assert pretask.main([]) == 0
    assert lifecycle.calls == ["restore", ("prepare", 60)]


def test_pretask_reports_domain_failure_and_returns_two(monkeypatch, capsys) -> None:
    lifecycle = FakeLifecycle(
        prepare_error=MJAError(ErrorCode.WINDOW_NOT_FOUND, "exact game window not found")
    )
    monkeypatch.setattr(pretask, "build_lifecycle", lambda: lifecycle)
    monkeypatch.setattr(pretask, "ensure_permissions", lambda: None)

    assert pretask.main([]) == 2
    assert "WINDOW_NOT_FOUND: exact game window not found" in capsys.readouterr().err


def test_pretask_reports_unexpected_failure_and_returns_three(monkeypatch, capsys) -> None:
    lifecycle = FakeLifecycle(prepare_error=RuntimeError("unexpected"))
    monkeypatch.setattr(pretask, "build_lifecycle", lambda: lifecycle)
    monkeypatch.setattr(pretask, "ensure_permissions", lambda: None)

    assert pretask.main([]) == 3
    assert "unexpected pretask failure" in capsys.readouterr().err
