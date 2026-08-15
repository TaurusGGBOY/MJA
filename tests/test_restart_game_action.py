from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "agent/custom/action/restart_game.py"
)
SPEC = importlib.util.spec_from_file_location("restart_game_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
restart_game = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restart_game)


GAME_PACKAGE = "com.hanjiasongshu.dr22"
GAME_ACTIVITY = "com.hanjiasongshu.dr22/.MainActivity"


class FakeArgv:
    def __init__(self, custom_action_param: str) -> None:
        self.custom_action_param = custom_action_param


class Job:
    def __init__(self, events: list[tuple[object, ...]], name: str) -> None:
        self._events = events
        self._name = name

    def wait(self) -> bool:
        self._events.append((f"{self._name}_wait",))
        return True


def _context(events: list[tuple[object, ...]]) -> SimpleNamespace:
    def stop_app(package: str) -> Job:
        events.append(("stop", package))
        return Job(events, "stop")

    def start_app(activity: str) -> Job:
        events.append(("start", activity))
        return Job(events, "start")

    controller = SimpleNamespace(
        post_stop_app=stop_app,
        post_start_app=start_app,
    )
    return SimpleNamespace(tasker=SimpleNamespace(controller=controller))


@pytest.mark.parametrize(
    ("extra_params", "expected_seconds"),
    [
        ({}, 2.0),
        ({"cooldown_ms": 1_000}, 1.0),
        ({"cooldown_ms": 5_000}, 5.0),
    ],
)
def test_restart_orders_stop_wait_bounded_cooldown_then_start(
    monkeypatch: pytest.MonkeyPatch,
    extra_params: dict[str, object],
    expected_seconds: float,
) -> None:
    events: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        restart_game,
        "sleep",
        lambda seconds: events.append(("cooldown", seconds)),
        raising=False,
    )
    params = {
        "package": GAME_PACKAGE,
        "activity": GAME_ACTIVITY,
        **extra_params,
    }

    assert restart_game.RestartGameSurface().run(
        _context(events), FakeArgv(json.dumps(params))
    )
    assert events == [
        ("stop", GAME_PACKAGE),
        ("stop_wait",),
        ("cooldown", expected_seconds),
        ("start", GAME_ACTIVITY),
        ("start_wait",),
    ]


def test_restart_can_start_the_game_package_five_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        restart_game,
        "sleep",
        lambda seconds: events.append(("cooldown", seconds)),
        raising=False,
    )
    params = {
        "package": GAME_PACKAGE,
        "activity": GAME_ACTIVITY,
        "cooldown_ms": 1_000,
        "start_repeat": 5,
        "start_repeat_delay_ms": 1_000,
    }

    assert restart_game.RestartGameSurface().run(
        _context(events), FakeArgv(json.dumps(params))
    )
    assert events == [
        ("stop", GAME_PACKAGE),
        ("stop_wait",),
        ("cooldown", 1.0),
        ("start", GAME_ACTIVITY),
        ("start_wait",),
        ("cooldown", 1.0),
        ("start", GAME_ACTIVITY),
        ("start_wait",),
        ("cooldown", 1.0),
        ("start", GAME_ACTIVITY),
        ("start_wait",),
        ("cooldown", 1.0),
        ("start", GAME_ACTIVITY),
        ("start_wait",),
        ("cooldown", 1.0),
        ("start", GAME_ACTIVITY),
        ("start_wait",),
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"package": "other.package", "activity": GAME_ACTIVITY},
        {"package": GAME_PACKAGE, "activity": "other.package/.MainActivity"},
        {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY, "cooldown_ms": True},
        {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY, "cooldown_ms": None},
        {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY, "cooldown_ms": 999},
        {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY, "cooldown_ms": 5_001},
        {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY, "cooldown_ms": 2.0},
        {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY, "cooldown_ms": "2000"},
    ],
)
def test_restart_rejects_invalid_parameters_before_controller_calls(
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, object],
) -> None:
    events: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        restart_game,
        "sleep",
        lambda seconds: events.append(("cooldown", seconds)),
        raising=False,
    )

    assert restart_game.RestartGameSurface().run(
        _context(events), FakeArgv(json.dumps(params))
    ) is False
    assert events == []


def test_restart_does_not_cool_down_or_start_when_stop_job_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        restart_game,
        "sleep",
        lambda seconds: events.append(("cooldown", seconds)),
    )

    class FailedJob(Job):
        succeeded = False

    def stop_app(package: str) -> FailedJob:
        events.append(("stop", package))
        return FailedJob(events, "stop")

    def start_app(activity: str) -> Job:
        events.append(("start", activity))
        return Job(events, "start")

    context = SimpleNamespace(
        tasker=SimpleNamespace(
            controller=SimpleNamespace(
                post_stop_app=stop_app,
                post_start_app=start_app,
            )
        )
    )
    params = {"package": GAME_PACKAGE, "activity": GAME_ACTIVITY}

    assert restart_game.RestartGameSurface().run(
        context, FakeArgv(json.dumps(params))
    ) is False
    assert events == [("stop", GAME_PACKAGE), ("stop_wait",)]
