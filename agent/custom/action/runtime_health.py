"""MFW health action that reads only the live Maa controller properties."""

from __future__ import annotations

from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.controller_input import resolution_values


def _has_property(instance: Any, name: str) -> bool:
    """Check optional test-double compatibility without hiding property errors."""

    return hasattr(instance, name)


@AgentServer.custom_action("RuntimeHealth")
class RuntimeHealth(CustomAction):
    """Return live controller health without device discovery or subprocesses."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        controller = context.tasker.controller
        if not controller.connected:
            return False

        if _has_property(controller, "resolution"):
            resolution = controller.resolution
            if resolution_values(resolution) is None:
                return False
        if _has_property(controller, "cached_image"):
            if controller.cached_image is None:
                return False
        return True


__all__ = ["RuntimeHealth"]
