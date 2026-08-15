from __future__ import annotations

from typing import Any

from agent.workflows.input import AndroidWorkflowDriver, map_box_center

try:
    from maa.context import Context
    from maa.custom_action import CustomAction
except ImportError:  # pragma: no cover
    Context = Any  # type: ignore[misc,assignment]

    class CustomAction:
        class RunResult:
            def __init__(self, success: bool) -> None:
                self.success = success


class AndroidForegroundClick(CustomAction):
    def run(self, context: Context, argv: Any) -> Any:
        controller = context.tasker.controller
        try:
            AndroidWorkflowDriver(controller, frame_size=controller.resolution).click(
                argv.box,
                frame_size=controller.resolution,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return CustomAction.RunResult(success=False)
        return CustomAction.RunResult(success=True)


try:  # Register only inside a real Maa agent process.
    from maa.agent.agent_server import AgentServer
except ImportError:  # pragma: no cover
    AgentServer = None  # type: ignore[assignment]

if AgentServer is not None:
    AndroidForegroundClick = AgentServer.custom_action("AndroidForegroundClick")(
        AndroidForegroundClick
    )


__all__ = ["AndroidForegroundClick", "map_box_center"]
