"""Advance food consumption only after a same-item quantity decrement."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.action.guarded_input import _ocr_amount, _ocr_text, _sub_results
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


@AgentServer.custom_action("FoodConsumptionConfirmed")
class FoodConsumptionConfirmed(CustomAction):
    """Route the native pipeline after an observed, single-item consumption."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            params = _payload(argv)
            if (
                params.get("task_id") != "EAT_STAMINA_FOOD_DAILY"
                or params.get("action_id") != "eat_longjing_shrimp"
                or params.get("limit") != 6
            ):
                return False
            task_id = "EAT_STAMINA_FOOD_DAILY"
            results = _sub_results(argv.reco_detail)
            before = RUN_STORE.get_marker(task_id, "food.longjing_shrimp.before_amount")
            if results is None or len(results) != 3 or not all(r.hit for r in results):
                return False
            if _ocr_text(results[1]) != "龙井虾仁":
                return False
            after = _ocr_amount(_ocr_text(results[2]) or "")
            if not isinstance(before, int) or isinstance(before, bool) or before <= 0:
                return False
            if after != before - 1:
                return False
            count = _food_run_count(task_id, "eat_longjing_shrimp")
            confirmed = RUN_STORE.get_marker(task_id, "food.confirmed_uses", 0)
            if count != confirmed + 1 or not 1 <= count <= 6:
                return False
            next_node = (
                "0401-吃体力食物-六次消耗-关闭背包" if count == 6 else "0385-吃体力食物-候选-循环"
            )
            if not context.override_next(argv.node_name, [next_node]):
                return False
            RUN_STORE.set_marker(task_id, "food.confirmed_uses", count)
            RUN_STORE.set_marker(task_id, "food.longjing_shrimp.before_amount", None)
            return True
        except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            return False


__all__ = ["FoodConsumptionConfirmed"]
