"""Exercise real native task states without connecting to a game or emulator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_native_startup_failure_cannot_turn_later_tasks_into_empty_success(tmp_path):
    maa = pytest.importorskip("maa")
    import numpy as np
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit

    from agent.custom.action.fail_task import FailTask
    from agent.custom.sink.task_flow import GlobalPrerequisiteStopSink

    runtime = Path(maa.__file__).parent / "bin"
    if not runtime.is_dir():
        pytest.skip("Maa native runtime is not installed")
    Library.open(runtime)
    Toolkit.init_option(tmp_path / "native-log")
    bundle = tmp_path / "bundle"
    (bundle / "pipeline").mkdir(parents=True)
    start, entry = "0023-启动-游戏入口", "BusinessSentinel"
    (bundle / "pipeline/test.json").write_text(
        json.dumps(
            {
                start: {
                    "recognition": "DirectHit",
                    "action": "Custom",
                    "custom_action": "FailTask",
                },
                entry: {"recognition": "DirectHit", "action": "Custom", "custom_action": "Count"},
            }
        )
    )
    resource = Resource()
    assert resource.post_bundle(bundle).wait().status.succeeded

    def no_input(self, *args):
        raise AssertionError("The native queue regression must never issue device input")

    methods = {
        name: no_input
        for name, method in CustomController.__dict__.items()
        if getattr(method, "__isabstractmethod__", False)
    }
    methods.update(
        connect=lambda self: True,
        request_uuid=lambda self: "native-queue-test",
        screencap=lambda self: np.zeros((720, 1280, 3), dtype=np.uint8),
    )
    controller = type("NoInputController", (CustomController,), methods)()
    assert controller.post_connection().wait().status.succeeded
    calls = []

    class Count(CustomAction):
        def run(self, context, argv):
            calls.append(1)
            return True

    resource.register_custom_action("FailTask", FailTask())
    resource.register_custom_action("Count", Count())
    tasker = Tasker()
    tasker.bind(resource, controller)
    sink = GlobalPrerequisiteStopSink()
    tasker.add_sink(sink)
    assert tasker.post_task(start).wait().status.failed
    # These are separate GUI-style submissions after startup has terminated.
    assert tasker.post_task(entry).wait().status.failed
    assert tasker.post_task(entry).wait().status.failed
    assert not calls
    resource.override_pipeline({start: {"recognition": "DirectHit", "action": "DoNothing"}})
    assert tasker.post_task(start).wait().status.succeeded
    assert tasker.post_task(entry).wait().status.succeeded
    assert calls == [1]
