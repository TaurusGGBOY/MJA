from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.actions.android_foreground_click import AndroidForegroundClick, map_box_center


def test_map_box_center_maps_controller_resolution_to_1280x720() -> None:
    assert map_box_center((100, 100, 20, 20), (2560, 1440)) == (55, 55)


def test_map_box_center_rejects_outside_box() -> None:
    with pytest.raises(ValueError, match="inside the capture"):
        map_box_center((1270, 0, 20, 20), (1280, 720))


def test_android_action_posts_only_recognized_click() -> None:
    calls: list[tuple[int, int]] = []

    class Job:
        succeeded = True

        def wait(self) -> None:
            calls.append((-1, -1))

    controller = SimpleNamespace(
        resolution=(1280, 720),
        post_click=lambda x, y: calls.append((x, y)) or Job(),
    )
    context = SimpleNamespace(tasker=SimpleNamespace(controller=controller))

    result = AndroidForegroundClick().run(context, SimpleNamespace(box=(100, 200, 20, 40)))

    assert result.success is True
    assert calls == [(110, 220), (-1, -1)]
