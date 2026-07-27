from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.actions import macos_foreground_click as click_module
from agent.actions.macos_foreground_click import ClickExecutor, MacOSForegroundClick, map_box_center
from agent.macos.window_lifecycle import GameWindow
from agent.macos.window_state import Bounds


def test_box_center_maps_from_capture_to_window() -> None:
    assert map_box_center((1200, 60, 40, 20), (1280, 720), (10, 20, 1280, 720)) == (
        1230,
        90,
    )


def test_box_center_uses_capture_to_window_ratio() -> None:
    assert map_box_center((100, 100, 20, 20), (2560, 1440), (10, 20, 1280, 720)) == (
        65,
        75,
    )


@pytest.mark.parametrize(
    "box",
    [None, (0, 0, 0, 20), (-1, 0, 20, 20), (0, 0, 20, 20, 1), "1,2,3,4"],
)
def test_missing_or_invalid_recognition_box_never_invokes_process(box) -> None:
    calls: list[object] = []
    executor = ClickExecutor(
        run=lambda *args, **kwargs: calls.append(args),
        sleep=lambda _: None,
        pointer_position=lambda: (7, 8),
        activate=lambda pid: calls.append(["activate", pid]),
    )

    with pytest.raises(ValueError, match="recognition box"):
        executor.click(box, (1280, 720), (10, 20, 1280, 720), pid=902)

    assert calls == []


def test_click_activates_then_restores_pointer() -> None:
    calls: list[object] = []
    executor = ClickExecutor(
        run=lambda argv, **kwargs: calls.append(argv)
        or SimpleNamespace(returncode=0, stderr=""),
        sleep=lambda seconds: calls.append(["sleep", seconds]),
        pointer_position=lambda: (7, 8),
        activate=lambda pid: calls.append(["activate", pid]),
    )

    executor.click((100, 200, 20, 40), (1280, 720), (10, 20, 1280, 720), pid=902)

    assert calls == [
        ["activate", 902],
        ["sleep", 0.15],
        ["/opt/homebrew/bin/cliclick", "c:120,240"],
        ["/opt/homebrew/bin/cliclick", "m:7,8"],
    ]


def test_nonzero_cliclick_still_restores_pointer() -> None:
    calls: list[object] = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=17, stderr="permission denied")

    executor = ClickExecutor(
        run=run,
        sleep=lambda _: None,
        pointer_position=lambda: (7, 8),
        activate=lambda pid: None,
    )

    with pytest.raises(RuntimeError, match="17"):
        executor.click((100, 200, 20, 40), (1280, 720), (10, 20, 1280, 720), pid=902)

    assert calls == [
        ["/opt/homebrew/bin/cliclick", "c:120,240"],
        ["/opt/homebrew/bin/cliclick", "m:7,8"],
    ]


def test_custom_action_uses_prepared_window_and_controller_resolution(monkeypatch) -> None:
    window = GameWindow(41, 902, "对决！剑之川", Bounds(10, 20, 1280, 720))
    lifecycle = SimpleNamespace(current_prepared_window=lambda: window)
    click_calls: list[object] = []
    executor = SimpleNamespace(
        click=lambda *args, **kwargs: click_calls.append(args + (kwargs,))
    )
    controller = SimpleNamespace(resolution=(2560, 1440))
    context = SimpleNamespace(tasker=SimpleNamespace(controller=controller))
    argv = SimpleNamespace(box=(100, 100, 20, 20))

    monkeypatch.setattr(click_module, "build_lifecycle", lambda: lifecycle)
    monkeypatch.setattr(click_module, "build_executor", lambda lifecycle=None: executor)

    result = MacOSForegroundClick().run(context, argv)

    assert result.success is True
    assert click_calls == [
        ((100, 100, 20, 20), (2560, 1440), (10, 20, 1280, 720), 902, {})
    ]
