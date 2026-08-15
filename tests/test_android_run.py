from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.android.config import AndroidConfig
from agent.errors import ErrorCode, MJAError
from tools.android_maa_config import build_android_maa_config
from tools.android_run import AndroidRun


def test_android_maa_config_uses_adb_and_android_resource() -> None:
    config = build_android_maa_config(
        Path("/sdk/platform-tools/adb"),
        "emulator-5556",
        "mail_smoke_test",
    )

    assert config == {
        "controller": {"name": "android"},
        "adb": {
            "name": "emulator-5556",
            "adb_path": "/sdk/platform-tools/adb",
            "address": "emulator-5556",
        },
        "resource": "mja_android",
        "task": [{"name": "mail_smoke_test"}],
    }


def test_android_run_exports_the_resolved_package_to_maa_environment(
    monkeypatch, tmp_path: Path
) -> None:
    import tools.android_run as module

    captured = {}

    def fake_popen(argv, *, cwd, env, start_new_session):
        captured.update(
            argv=list(argv),
            cwd=cwd,
            env=env,
            start_new_session=start_new_session,
        )
        return object()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    run = AndroidRun(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name=None),
        install_root=tmp_path / "install",
    )

    run._spawn(
        ["./MaaPiCli", "-d"],
        adb_path=tmp_path / "sdk/platform-tools/adb",
        serial="emulator-5556",
        package_name="com.actual.game",
    )

    assert captured["env"]["MJA_ANDROID_PACKAGE"] == "com.actual.game"
    assert captured["env"]["MJA_ANDROID_SERIAL"] == "emulator-5556"
    assert captured["start_new_session"] is True


def test_android_run_checks_runtime_health_before_maapi_cli(monkeypatch, tmp_path: Path) -> None:
    import tools.android_run as module

    events: list[str] = []

    class FakeSdk:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ensure(self, install_missing: bool = True):
            events.append("sdk")
            return SimpleNamespace(adb=Path("/sdk/adb"))

    class FakeAvd:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self, *, wipe_data: bool = False):
            events.append("avd")
            return SimpleNamespace(poll=lambda: 0)

        def stop(self) -> None:
            events.append("stop")

    class FakeDevice:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def wait_ready(self) -> None:
            events.append("ready")

        def ensure_phantom_process_monitor_disabled(self) -> None:
            events.append("phantom_monitor")

        def ensure_selinux_mode(self, mode: str) -> None:
            assert mode == "permissive"
            events.append("selinux")

        def start_app(self, _package_name: str) -> None:
            events.append("start_app")

        def dismiss_first_run_overlay(self) -> None:
            events.append("overlay")

        def require_runtime_health(self) -> None:
            events.append("health")

    class FakeInstaller:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ensure_installed(self) -> str:
            events.append("install")
            return "com.example.game"

    class FakeLoginGate:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def wait_until_ready(self, _device, **_kwargs) -> None:
            events.append("login")

    class FakeChild:
        def wait(self) -> int:
            events.append("spawn")
            return 3

    monkeypatch.setattr(module, "AndroidSdk", FakeSdk)
    monkeypatch.setattr(module, "AndroidAvd", FakeAvd)
    monkeypatch.setattr(module, "AdbDevice", FakeDevice)
    monkeypatch.setattr(module, "GameInstaller", FakeInstaller)
    monkeypatch.setattr(module, "LoginGate", FakeLoginGate)

    run = AndroidRun(
        AndroidConfig(sdk_root=tmp_path / "sdk", keep_running=True),
        install_root=tmp_path / "install",
        spawn=lambda _argv: FakeChild(),
    )

    assert run.run(stop=True) == 3
    assert events.index("start_app") < events.index("login")
    assert events.index("phantom_monitor") < events.index("start_app")
    assert events.index("selinux") < events.index("start_app")
    assert events.index("health") < events.index("spawn")
    assert "stop" not in events


def test_prepare_game_session_can_restart_an_existing_process(monkeypatch, tmp_path: Path) -> None:
    import tools.android_run as module

    events: list[str] = []

    class FakeDevice:
        def restart(self, package_name: str) -> None:
            assert package_name == "com.example.game"
            events.append("restart")

        def start_app(self, package_name: str) -> None:
            assert package_name == "com.example.game"
            events.append("start_app")

        def dismiss_first_run_overlay(self) -> None:
            events.append("overlay")

        def require_runtime_health(self) -> None:
            events.append("health")

    class FakeLoginGate:
        def __init__(self, _config) -> None:
            pass

        def wait_until_ready(self, _device, **_kwargs) -> None:
            events.append("login")

    monkeypatch.setattr(module, "LoginGate", FakeLoginGate)

    module.AndroidRun._prepare_game_session(
        FakeDevice(),
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        "com.example.game",
        restart_if_running=True,
    )

    assert events == ["restart", "overlay", "login", "health"]


def test_android_run_recovers_foreground_loss_at_maa_handoff(
    monkeypatch, tmp_path: Path
) -> None:
    import tools.android_run as module

    events: list[str] = []
    health_calls = 0

    class FakeDevice:
        def require_runtime_health(self) -> None:
            nonlocal health_calls
            health_calls += 1
            events.append(f"health:{health_calls}")
            if health_calls == 1:
                raise MJAError(
                    ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                    "game returned to Launcher during Maa handoff",
                )

        def restart(self, package_name: str) -> None:
            assert package_name == "com.example.game"
            events.append("restart")

        def dismiss_first_run_overlay(self) -> None:
            events.append("overlay")

        def require_game_process(self, package_name: str) -> None:
            assert package_name == "com.example.game"
            events.append("process")

    class FakeLoginGate:
        def __init__(self, _config) -> None:
            pass

        def wait_until_ready(self, _device, **kwargs) -> None:
            assert kwargs["require_interactive"] is True
            events.append("login")

    monkeypatch.setattr(module, "LoginGate", FakeLoginGate)

    module.AndroidRun._stabilize_game_handoff(
        FakeDevice(),
        AndroidConfig(
            sdk_root=tmp_path / "sdk",
            package_name="com.example.game",
        ),
        "com.example.game",
    )

    assert events == [
        "health:1",
        "restart",
        "overlay",
        "login",
        "health:2",
        "process",
        "health:3",
        "process",
    ]


def test_android_run_terminates_child_and_records_error_on_child_exception(
    monkeypatch, tmp_path: Path
) -> None:
    import tools.android_run as module

    events: list[str] = []

    class FakeSdk:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ensure(self, install_missing: bool = True):
            return SimpleNamespace(adb=Path("/sdk/adb"))

    class FakeAvd:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self, *, wipe_data: bool = False):
            return SimpleNamespace(poll=lambda: 0)

        def stop(self) -> None:
            events.append("stop")

    class FakeDevice:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def wait_ready(self) -> None:
            pass

        def start_app(self, _package_name: str) -> None:
            pass

        def dismiss_first_run_overlay(self) -> None:
            pass

        def require_runtime_health(self) -> None:
            pass

    class FakeInstaller:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ensure_installed(self) -> str:
            return "com.example.game"

    class FakeLoginGate:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def wait_until_ready(self, _device, **_kwargs) -> None:
            pass

    class FakeChild:
        def poll(self):
            return None

        def wait(self) -> int:
            raise RuntimeError("child failed")

        def terminate(self) -> None:
            events.append("terminate")

    monkeypatch.setattr(module, "AndroidSdk", FakeSdk)
    monkeypatch.setattr(module, "AndroidAvd", FakeAvd)
    monkeypatch.setattr(module, "AdbDevice", FakeDevice)
    monkeypatch.setattr(module, "GameInstaller", FakeInstaller)
    monkeypatch.setattr(module, "LoginGate", FakeLoginGate)

    run = AndroidRun(
        AndroidConfig(sdk_root=tmp_path / "sdk", keep_running=True),
        install_root=tmp_path / "install",
        spawn=lambda _argv: FakeChild(),
    )

    with pytest.raises(RuntimeError, match="child failed"):
        run.run()

    assert events == ["terminate"]
    result_files = list(
        (tmp_path / "install" / "debug" / "runs" / "android").rglob("result.json")
    )
    assert len(result_files) == 1
    assert json.loads(result_files[0].read_text(encoding="utf-8"))["status"] == "error"


def test_android_run_login_timeout_keeps_avd_for_inspection_and_writes_result(
    monkeypatch, tmp_path: Path
) -> None:
    import tools.android_run as module

    events: list[str] = []

    class FakeSdk:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ensure(self, install_missing: bool = True):
            return SimpleNamespace(adb=Path("/sdk/adb"))

    class FakeAvd:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self, *, wipe_data: bool = False):
            return SimpleNamespace(poll=lambda: 0)

        def stop(self) -> None:
            events.append("stop")

    class FakeDevice:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def wait_ready(self) -> None:
            pass

        def start_app(self, _package_name: str) -> None:
            pass

        def dismiss_first_run_overlay(self) -> None:
            pass

        def require_runtime_health(self) -> None:
            pass

    class FakeInstaller:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ensure_installed(self) -> str:
            return "com.example.game"

    class FakeLoginGate:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def wait_until_ready(self, _device, **_kwargs) -> None:
            raise MJAError(ErrorCode.ANDROID_LOGIN_REQUIRED, "login timeout")

    monkeypatch.setattr(module, "AndroidSdk", FakeSdk)
    monkeypatch.setattr(module, "AndroidAvd", FakeAvd)
    monkeypatch.setattr(module, "AdbDevice", FakeDevice)
    monkeypatch.setattr(module, "GameInstaller", FakeInstaller)
    monkeypatch.setattr(module, "LoginGate", FakeLoginGate)

    run = AndroidRun(
        AndroidConfig(sdk_root=tmp_path / "sdk", keep_running=False),
        install_root=tmp_path / "install",
        spawn=lambda _argv: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )

    with pytest.raises(MJAError) as exc_info:
        run.run()

    assert exc_info.value.code is ErrorCode.ANDROID_LOGIN_REQUIRED
    assert events == []
    result_files = list(
        (tmp_path / "install" / "debug" / "runs" / "android").rglob("result.json")
    )
    assert json.loads(result_files[0].read_text(encoding="utf-8"))["status"] == "error"


def test_finalize_task_artifacts_preserves_terminal_native_diagnostic(
    tmp_path: Path,
) -> None:
    task_dir = (
        tmp_path
        / "debug"
        / "runs"
        / "daily"
        / "mail_reward_daily"
        / "2026-08-03T02:00:00+08:00"
    )
    task_dir.mkdir(parents=True)
    original = {
        "schema_version": 1,
        "status": "failed",
        "started_at": "2026-08-03T02:00:00+08:00",
        "finished_at": "2026-08-03T02:00:12+08:00",
        "duration_ms": 12000,
        "error": {
            "code": "WORKFLOW_POSTCONDITION_MISSING",
            "message": "the native task recorded its actual failure",
        },
    }
    (task_dir / "run.json").write_text(
        json.dumps(original),
        encoding="utf-8",
    )

    AndroidRun._finalize_task_artifacts(
        tmp_path / "debug" / "runs",
        "mail_reward_daily",
        started_at="2026-08-03T02:00:00+08:00",
        error_code="MAA_CHILD_EXIT_NONZERO",
    )

    assert json.loads((task_dir / "run.json").read_text(encoding="utf-8")) == original


def test_finalize_task_artifacts_closes_an_open_diagnostic(tmp_path: Path) -> None:
    task_dir = (
        tmp_path
        / "debug"
        / "runs"
        / "daily"
        / "mail_reward_daily"
        / "2026-08-03T02:00:00+08:00"
    )
    task_dir.mkdir(parents=True)
    (task_dir / "run.json").write_text(
        json.dumps({"status": "running", "events": []}),
        encoding="utf-8",
    )

    AndroidRun._finalize_task_artifacts(
        tmp_path / "debug" / "runs",
        "mail_reward_daily",
        started_at="2026-08-03T02:00:00+08:00",
        error_code="WORKFLOW_TIMEOUT",
    )

    payload = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "WORKFLOW_TIMEOUT"


def test_finalize_task_artifacts_fills_blank_failed_result_code(tmp_path: Path) -> None:
    task_dir = (
        tmp_path
        / "debug"
        / "runs"
        / "daily"
        / "weekly_free_gift_monday"
        / "2026-08-03T02:00:00+08:00"
    )
    task_dir.mkdir(parents=True)
    (task_dir / "run.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    (task_dir / "result.json").write_text(
        json.dumps(
            {
                "task_id": "WEEKLY_FREE_GIFT_MONDAY",
                "status": "failed",
                "postcondition": "weekly",
                "action_counts": {},
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )

    AndroidRun._finalize_task_artifacts(
        tmp_path / "debug" / "runs",
        "weekly_free_gift_monday",
        started_at="2026-08-03T02:00:00+08:00",
        error_code="WORKFLOW_POSTCONDITION_MISSING",
    )

    payload = json.loads((task_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["error_code"] == "WORKFLOW_POSTCONDITION_MISSING"


def test_stop_child_hard_kills_after_terminate_timeout() -> None:
    events: list[str] = []

    class FakeChild:
        def poll(self):
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def kill(self) -> None:
            events.append("kill")

        def wait(self, *, timeout: float) -> int:
            if "kill" not in events:
                raise subprocess.TimeoutExpired("fake", timeout)
            return -9

    AndroidRun._stop_child(FakeChild())

    assert events == ["terminate", "kill"]
