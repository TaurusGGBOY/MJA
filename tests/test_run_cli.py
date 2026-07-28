from __future__ import annotations

import json
import signal

import pytest

from tools.run_cli import run_cli


class FakeChild:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.signals: list[signal.Signals] = []

    def wait(self) -> int:
        return self.returncode

    def send_signal(self, value: signal.Signals) -> None:
        self.signals.append(value)


class FakeLifecycle:
    def __init__(self, prepared=41) -> None:
        self.prepared = prepared
        self.calls: list[object] = []

    def prepare(self, timeout_seconds: int):
        self.calls.append(("prepare", timeout_seconds))
        return self.prepared

    def restore(self) -> None:
        self.calls.append("restore")


def test_cli_restores_after_child_failure(tmp_path) -> None:
    lifecycle = FakeLifecycle()
    with pytest.raises(RuntimeError, match="child failed"):
        run_cli(
            lifecycle,
            install_root=tmp_path / "install",
            launch=lambda: None,
            spawn=lambda argv: (_ for _ in ()).throw(RuntimeError("child failed")),
        )
    assert lifecycle.calls == [("prepare", 60), "restore"]


def test_cli_writes_exact_configuration_and_passes_environment(tmp_path, monkeypatch) -> None:
    lifecycle = FakeLifecycle(prepared=type("Window", (), {"window_id": 41})())
    child = FakeChild(returncode=7)
    observed: dict[str, object] = {}

    def spawn(argv):
        observed["argv"] = argv
        return child

    monkeypatch.setenv("MJA_DEBUG_DIR", "original")
    result = run_cli(
        lifecycle,
        install_root=tmp_path / "install",
        launch=lambda: observed.setdefault("launched", True),
        spawn=spawn,
    )

    assert result == 7
    assert observed["launched"] is True
    assert observed["argv"] == ["./MaaPiCli", "-d"]
    assert lifecycle.calls == [("prepare", 60), "restore"]
    assert (tmp_path / "install" / "config" / "maa_pi_config.json").exists()
    payload = json.loads(
        (tmp_path / "install" / "config" / "maa_pi_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload == {
        "controller": {"name": "macos"},
        "macos": {
            "window_id": 41,
            "title": "对决！剑之川",
            "screencap": "ScreenCaptureKit",
            "input": "GlobalEvent",
        },
        "resource": "mja",
        "task": [{"name": "mail_smoke_test"}],
    }


def test_sigint_is_forwarded_and_restore_still_runs(tmp_path) -> None:
    lifecycle = FakeLifecycle()
    child = FakeChild()
    captured: dict[str, object] = {}

    def spawn(argv):
        captured["handler"] = signal.getsignal(signal.SIGINT)
        return child

    run_cli(
        lifecycle,
        install_root=tmp_path / "install",
        launch=lambda: None,
        spawn=spawn,
    )

    handler = captured["handler"]
    assert callable(handler)
    handler(signal.SIGINT, None)
    assert child.signals == [signal.SIGINT]
    assert lifecycle.calls[-1] == "restore"


def test_cli_reports_task_failure_when_maapi_cli_returns_zero(tmp_path) -> None:
    lifecycle = FakeLifecycle()
    child = FakeChild(returncode=0)
    debug_dir = tmp_path / "install" / "debug" / "runs"
    debug_dir.mkdir(parents=True)
    (debug_dir / "maafw.log").write_text("Tasker.Task.Failed\n", encoding="utf-8")

    result = run_cli(
        lifecycle,
        install_root=tmp_path / "install",
        launch=lambda: None,
        spawn=lambda argv: child,
    )

    assert result == 3
    assert lifecycle.calls[-1] == "restore"
