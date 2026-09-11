from types import SimpleNamespace as NS

import pytest

from agent.custom.action.task_lifecycle import ReturnToHome, ReturnToWorldHome


@pytest.mark.parametrize("action", [ReturnToHome, ReturnToWorldHome])
@pytest.mark.parametrize("home_after,expected", [(0, True), (2, True), (99, False)])
def test_cleanup_stops_at_home_and_never_calls_exhaustion_success(
    monkeypatch, action, home_after, expected,
):
    monkeypatch.setattr("agent.custom.action.task_lifecycle.sleep", lambda _: None)
    keys = []
    captures = []
    ok = NS(wait=lambda: NS(status=NS(succeeded=True)))
    controller = NS(
        cached_image="fresh", post_screencap=lambda: captures.append(1) or ok,
        post_click_key=lambda key: keys.append(key) or ok,
    )
    context = NS(
        tasker=NS(controller=controller),
        run_recognition=lambda name, frame: NS(
            hit=name == "0026-公共-游戏主页-页面" and len(keys) >= home_after
        ),
    )
    assert action().run(context, NS()) is expected
    assert keys == [4] * min(home_after, 8)
    assert len(captures) == len(keys) + 1


def test_capture_failure_cannot_be_reported_as_home(monkeypatch):
    controller = NS(post_screencap=lambda: NS(wait=lambda: NS(status=NS(succeeded=False))))
    assert not ReturnToWorldHome().run(NS(tasker=NS(controller=controller)), NS())
