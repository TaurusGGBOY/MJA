import threading
from types import SimpleNamespace

import pytest

from agent.workflows.input import AndroidWorkflowDriver, map_box_center
from agent.workflows.models import ActionIntent


class Job:
    succeeded = True

    def __init__(self, calls, name):
        self.calls = calls
        self.name = name

    def wait(self):
        self.calls.append((self.name, "wait"))


def make_controller(calls):
    return SimpleNamespace(
        post_click=lambda x, y: calls.append(("click", x, y)) or Job(calls, "click"),
        post_swipe=lambda *args: calls.append(("swipe", *args)) or Job(calls, "swipe"),
        post_long_press=lambda *args: calls.append(("long_press", *args))
        or Job(calls, "long_press"),
    )


def make_touch_controller(calls):
    return SimpleNamespace(
        post_swipe=lambda *args: calls.append(("swipe", *args))
        or Job(calls, "swipe"),
        post_touch_down=lambda x, y, contact=0, pressure=1: calls.append(
            ("down", x, y, contact, pressure)
        )
        or Job(calls, "down"),
        post_touch_move=lambda x, y, contact=0, pressure=1: calls.append(
            ("move", x, y, contact, pressure)
        )
        or Job(calls, "move"),
        post_touch_up=lambda contact=0: calls.append(("up", contact))
        or Job(calls, "up"),
    )


def test_map_box_center_uses_current_frame_and_calibration_sizes():
    assert map_box_center((100, 100, 20, 20), (2560, 1440), (1280, 720)) == (55, 55)


@pytest.mark.parametrize(
    ("box", "frame_size"),
    [((0, 0, 0, 1), (1280, 720)), ((1270, 0, 20, 20), (1280, 720))],
)
def test_map_box_center_rejects_invalid_or_outside_boxes(box, frame_size):
    with pytest.raises(ValueError):
        map_box_center(box, frame_size)


def test_driver_executes_click_swipe_long_press_and_no_input():
    calls = []
    driver = AndroidWorkflowDriver(make_controller(calls), frame_size=(1280, 720))
    driver.click((100, 100, 20, 20))
    driver.swipe((100, 100, 20, 20), (300, 100, 20, 20), duration_ms=100)
    driver.long_press((100, 100, 20, 20), duration_ms=100)
    driver.execute(ActionIntent("none", "page", "target", input_kind="none"))
    assert calls == [
        ("click", 110, 110),
        ("click", "wait"),
        ("swipe", 110, 110, 310, 110, 100),
        ("swipe", "wait"),
        ("long_press", 110, 110, 100),
        ("long_press", "wait"),
    ]


def test_driver_drag_tap_uses_a_bounded_one_pixel_maa_swipe():
    calls = []
    driver = AndroidWorkflowDriver(make_touch_controller(calls), frame_size=(1280, 720))

    driver.drag_tap((100, 100, 20, 20))

    assert calls == [
        ("down", 110, 110, 0, 1),
        ("down", "wait"),
        ("move", 111, 111, 0, 1),
        ("move", "wait"),
        ("up", 0),
        ("up", "wait"),
    ]


def test_driver_sends_android_key_through_maa_controller():
    calls = []
    controller = SimpleNamespace(
        post_click_key=lambda key: calls.append(("key", key)) or Job(calls, "key")
    )
    driver = AndroidWorkflowDriver(controller)

    driver.click_key(4)

    assert calls == [("key", 4), ("key", "wait")]


def test_driver_requires_fresh_boxes_and_bounded_durations():
    driver = AndroidWorkflowDriver(make_controller([]))
    with pytest.raises(ValueError):
        driver.execute(ActionIntent("click", "page", "target", input_kind="click"))
    with pytest.raises(ValueError):
        driver.swipe((0, 0, 10, 10), (20, 0, 10, 10), duration_ms=5)
    with pytest.raises(ValueError):
        driver.long_press((0, 0, 10, 10), duration_ms=6000)


def test_driver_rejects_controller_without_required_gesture():
    driver = AndroidWorkflowDriver(SimpleNamespace(post_click=lambda *_: Job([], "click")))
    with pytest.raises(ValueError, match="swipe"):
        driver.swipe((0, 0, 10, 10), (20, 0, 10, 10))


def test_driver_times_out_a_stuck_controller_job(monkeypatch):
    release = threading.Event()

    class HangingJob:
        succeeded = True

        def wait(self):
            release.wait()

    monkeypatch.setattr(
        "agent.workflows.input.CONTROLLER_JOB_TIMEOUT_SECONDS",
        0.01,
    )
    driver = AndroidWorkflowDriver(
        SimpleNamespace(post_click=lambda *_: HangingJob())
    )

    with pytest.raises(RuntimeError, match="gesture wait timed out"):
        driver.click((0, 0, 10, 10))
    release.set()
