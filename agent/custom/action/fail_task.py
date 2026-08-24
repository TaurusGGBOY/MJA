"""Stateless custom action for an explicit native MFW task failure."""

from __future__ import annotations

from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction


@AgentServer.custom_action("FailTask")
class FailTask(CustomAction):
    """Return false so MaaFramework emits its native ``Failed`` state."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        del context, argv
        return False


__all__ = ["FailTask"]
