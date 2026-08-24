"""Compatibility registration for the retired break-array custom action.

``BREAK_ARRAY_MARTIAL_DAILY`` is now implemented entirely by its native MFW
pipeline.  The registration remains because the agent bootstrap imports this
module, but it deliberately fails closed if an obsolete resource still tries
to invoke it.  Business terminals are owned by the native task pipeline.
"""

from __future__ import annotations

from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

TASK_LOCAL_CLEANUP_RECOGNIZERS = (
    "break_array.home",
    "break_array.page",
    "break_array.close",
    "activity.page",
    "activity.close",
    "break_array.result",
    "break_array.result_close",
    "break_array.unknown_dialog",
    "safety.paid",
    "safety.verification",
)


@AgentServer.custom_action("BreakArrayMartialDailyAction")
class BreakArrayMartialDailyAction(CustomAction):
    """Reject stale custom-action invocations without performing input."""

    def run(self, _context: Any, _argv: Any) -> Any:
        return CustomAction.RunResult(success=False)


__all__ = ["BreakArrayMartialDailyAction", "TASK_LOCAL_CLEANUP_RECOGNIZERS"]
