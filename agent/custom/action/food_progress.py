"""Verify that one visual Longjing shrimp use changed the item quantity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.state import RUN_STORE

from .guarded_input import _ocr_amount, _ocr_text, _sub_results
from .task_lifecycle import diagnostics_for


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


def _record(context: Any, task_id: str, details: Mapping[str, Any]) -> None:
    diagnostics = diagnostics_for(context, task_id)
    if diagnostics is None:
        return
    try:
        diagnostics.record_action("verify_food_quantity_decrease", dict(details))
    except (OSError, RuntimeError, TypeError, ValueError):
        return


@AgentServer.custom_action("VerifyFoodQuantityDecrease")
class VerifyFoodQuantityDecrease(CustomAction):
    """Fail closed unless the post-click OCR amount is lower than before."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        task_id = ""
        try:
            params = _payload(argv)
            raw_task_id = params.get("task_id")
            resource_id = params.get("resource_id")
            amount_index = params.get("amount_index")
            amount_result_name = params.get("amount_result_name")
            task_id = raw_task_id.strip().upper() if isinstance(raw_task_id, str) else ""
            if (
                task_id != "EAT_STAMINA_FOOD_DAILY"
                or resource_id != "龙井虾仁"
                or isinstance(amount_index, bool)
                or not isinstance(amount_index, int)
                or amount_index < 0
                or amount_result_name != "food.available_positive"
            ):
                raise ValueError("unexpected food progress parameters")

            results = _sub_results(argv.reco_detail)
            if (
                results is None
                or amount_index >= len(results)
                or getattr(results[amount_index], "name", None) != amount_result_name
            ):
                raise ValueError("post-use amount observation is missing")
            current_amount = _ocr_amount(_ocr_text(results[amount_index]) or "")
            before_amount = RUN_STORE.get_marker(
                task_id, "food.longjing_shrimp.before_amount"
            )
            verified_uses = RUN_STORE.get_marker(
                task_id, "food.longjing_shrimp.verified_uses", 0
            )
            if (
                not isinstance(before_amount, int)
                or isinstance(before_amount, bool)
                or before_amount <= 0
                or current_amount is None
                or current_amount < 0
                or not isinstance(verified_uses, int)
                or isinstance(verified_uses, bool)
                or verified_uses >= 6
                or current_amount >= before_amount
            ):
                _record(
                    context,
                    task_id,
                    {
                        "task_id": task_id,
                        "allowed": False,
                        "before_amount": before_amount,
                        "after_amount": current_amount,
                        "verified_uses": verified_uses,
                    },
                )
                return False

            verified_uses = RUN_STORE.increment_marker(
                task_id, "food.longjing_shrimp.verified_uses"
            )
            RUN_STORE.set_marker(
                task_id, "food.longjing_shrimp.after_amount", current_amount
            )
            _record(
                context,
                task_id,
                {
                    "task_id": task_id,
                    "allowed": True,
                    "before_amount": before_amount,
                    "after_amount": current_amount,
                    "verified_uses": verified_uses,
                },
            )
            return True
        except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            if task_id:
                _record(context, task_id, {"task_id": task_id, "allowed": False})
            return False


__all__ = ["VerifyFoodQuantityDecrease"]
