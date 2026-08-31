"""Track the fixed six-click Longjing shrimp completion rule."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.state import RUN_STORE


def _payload(argv: Any) -> Mapping[str, Any]:
    raw = getattr(argv, "custom_action_param", argv)
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        decoded = raw.decode("utf-8") if not isinstance(raw, str) else raw
        value = json.loads(decoded)
        if isinstance(value, Mapping):
            return value
    raise ValueError("food progress parameters must be an object")


def _food_run_count(task_id: str, action_id: str) -> int:
    snapshot = RUN_STORE.snapshot(task_id)
    actions = snapshot.get("actions")
    if not isinstance(actions, Mapping):
        return 0
    count = actions.get(action_id, 0)
    return count if isinstance(count, int) and not isinstance(count, bool) else 0


@AgentServer.custom_action("FoodBudgetReached")
class FoodBudgetReached(CustomAction):
    """Allow the six-use food cap to finish through MFW's native success leaf."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        del context
        try:
            params = _payload(argv)
            if (
                params.get("task_id") != "EAT_STAMINA_FOOD_DAILY"
                or params.get("action_id") != "eat_longjing_shrimp"
                or params.get("limit") != 6
            ):
                return False
            return _food_run_count(
                "EAT_STAMINA_FOOD_DAILY", "eat_longjing_shrimp"
            ) >= 6
        except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            return False


__all__ = ["FoodBudgetReached"]
