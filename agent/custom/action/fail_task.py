"""Stateless custom action for an explicit native MFW task failure."""

from __future__ import annotations

import json
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.crash_evidence import capture_request_error


@AgentServer.custom_action("FailTask")
class FailTask(CustomAction):
    """Return false so MaaFramework emits its native ``Failed`` state."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            params = json.loads(getattr(argv, "custom_action_param", "null") or "null")
        except (TypeError, ValueError):
            params = None
        if isinstance(params, dict) and params.get("capture_request_error") is True:
            capture_request_error(argv)
        return False


__all__ = ["FailTask"]
