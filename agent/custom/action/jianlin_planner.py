"""Pure Jianlin challenge planning exposed as one narrow MFW action."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction


@dataclass(frozen=True, slots=True)
class ChallengePlan:
    """One safe count and multiplier for a Jianlin challenge."""

    count: int
    multiplier: int


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def plan_safe_challenge(
    stamina: int,
    cost: int,
    visible_max: int,
    safe_multipliers: tuple[int, ...],
) -> ChallengePlan:
    """Calculate a bounded challenge without falling back to an unsafe value."""

    if (
        isinstance(stamina, bool)
        or not isinstance(stamina, int)
        or stamina < 0
        or isinstance(cost, bool)
        or not isinstance(cost, int)
        or cost <= 0
        or isinstance(visible_max, bool)
        or not isinstance(visible_max, int)
        or visible_max <= 0
        or not isinstance(safe_multipliers, Sequence)
        or isinstance(safe_multipliers, (str, bytes, bytearray))
        or not safe_multipliers
    ):
        raise ValueError("unsafe challenge inputs")
    multipliers = tuple(
        value
        for value in safe_multipliers
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    )
    if not multipliers:
        raise ValueError("unsafe multipliers")
    for multiplier in sorted(multipliers, reverse=True):
        count = min(stamina // (cost * multiplier), visible_max)
        if count >= 1:
            return ChallengePlan(count=count, multiplier=multiplier)
    raise ValueError("insufficient stamina")


_INTEGER = re.compile(r"(?<!\d)(\d{1,6})(?!\d)")


def _payload(argv: Any) -> Mapping[str, Any]:
    raw = getattr(argv, "custom_action_param", argv)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("planner parameters must be UTF-8 JSON") from exc
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("planner parameters must be valid JSON") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("planner parameters must be an object")
    return raw


def _index(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _indices(payload: Mapping[str, Any]) -> tuple[int, ...]:
    values = payload.get("multiplier_indices")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ValueError("multiplier_indices must be an array")
    result = tuple(
        _index({"value": value}, "value")
        for value in values
    )
    if not result or len(set(result)) != len(result):
        raise ValueError("multiplier_indices must contain unique values")
    return result


def _and_results(reco_detail: Any) -> list[Any]:
    if not getattr(reco_detail, "hit", False):
        raise ValueError("planner recognition missed")
    algorithm = getattr(reco_detail, "algorithm", "")
    algorithm = getattr(algorithm, "value", algorithm)
    if str(algorithm).casefold() != "and":
        raise ValueError("planner requires an And recognition")
    best_result = getattr(reco_detail, "best_result", None)
    results = getattr(best_result, "sub_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes, bytearray)):
        raise ValueError("planner recognition has no indexed results")
    return list(results)


def _ocr_text(detail: Any) -> str:
    if not getattr(detail, "hit", False):
        raise ValueError("planner OCR result missed")
    best_result = getattr(detail, "best_result", None)
    text = getattr(best_result, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    for result in getattr(detail, "filtered_results", ()) or ():
        text = getattr(result, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise ValueError("planner OCR result has no text")


def _ocr_amount(detail: Any) -> int:
    match = _INTEGER.search(_ocr_text(detail))
    if match is None:
        raise ValueError("planner OCR result has no integer")
    return _positive_int(int(match.group(1)), "OCR amount")


def _at(results: Sequence[Any], index: int) -> Any:
    if index >= len(results):
        raise ValueError("planner OCR index is out of range")
    return results[index]


def _selected_plan(
    results: Sequence[Any],
    *,
    stamina_index: int,
    total_cost_index: int,
    visible_max_index: int,
    count_index: int,
    multiplier_index: int,
    max_total_cost: int,
) -> ChallengePlan:
    """Use the already-selected controls when the live page exposes totals.

    Jianlin's live page shows the aggregate ``消耗体力`` for the current
    slider positions, not a per-run base cost.  The old planner treated that
    aggregate as a base cost and then multiplied it again, which rejected a
    valid page such as ``400/310`` with ``消耗体力 360``.  Keeping the current
    selection is safe when the page itself proves that its aggregate cost is
    affordable and within this task's budget.
    """

    stamina = _ocr_amount(_at(results, stamina_index))
    total_cost = _ocr_amount(_at(results, total_cost_index))
    visible_max = _ocr_amount(_at(results, visible_max_index))
    count = _ocr_amount(_at(results, count_index))
    multiplier = _ocr_amount(_at(results, multiplier_index))
    if count > visible_max or multiplier not in (1, 2, 3):
        raise ValueError("current challenge selection is unsafe")
    if total_cost <= max_total_cost and total_cost <= stamina:
        return ChallengePlan(count=count, multiplier=multiplier)

    # The page's total is aggregate cost for the selected count and
    # multiplier.  When the default selection is too expensive, derive the
    # per-attempt base cost and choose the largest safe declared plan instead
    # of abandoning an otherwise eligible Jianlin challenge.
    divisor = count * multiplier
    if divisor <= 0 or total_cost % divisor:
        raise ValueError("cannot derive challenge base cost")
    base_cost = total_cost // divisor
    return plan_safe_challenge(
        stamina,
        base_cost,
        visible_max,
        (3, 2, 1),
    )


@AgentServer.custom_action("PlanJianlinChallenge")
class PlanJianlinChallenge(CustomAction):
    """Select one already-declared count/multiplier branch from one frame."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _payload(argv)
            dispatch_node = payload.get("dispatch_node")
            if not isinstance(dispatch_node, str) or not dispatch_node.strip():
                raise ValueError("dispatch_node must be a non-empty string")
            stamina_index = _index(payload, "stamina_index")
            cost_index = _index(payload, "cost_index")
            visible_max_index = _index(payload, "visible_max_index")
            results = _and_results(getattr(argv, "reco_detail", None))
            if any(
                field in payload
                for field in (
                    "selected_count_index",
                    "selected_multiplier_index",
                    "max_total_cost",
                )
            ):
                selected_count_index = _index(payload, "selected_count_index")
                selected_multiplier_index = _index(payload, "selected_multiplier_index")
                max_total_cost = payload.get("max_total_cost")
                if (
                    isinstance(max_total_cost, bool)
                    or not isinstance(max_total_cost, int)
                    or max_total_cost <= 0
                ):
                    raise ValueError("max_total_cost must be a positive integer")
                plan = _selected_plan(
                    results,
                    stamina_index=stamina_index,
                    total_cost_index=cost_index,
                    visible_max_index=visible_max_index,
                    count_index=selected_count_index,
                    multiplier_index=selected_multiplier_index,
                    max_total_cost=max_total_cost,
                )
            else:
                multiplier_indices = _indices(payload)
                stamina = _ocr_amount(_at(results, stamina_index))
                cost = _ocr_amount(_at(results, cost_index))
                visible_max = _ocr_amount(_at(results, visible_max_index))
                safe_multipliers = tuple(
                    _ocr_amount(_at(results, index)) for index in multiplier_indices
                )
                plan = plan_safe_challenge(
                    stamina,
                    cost,
                    visible_max,
                    safe_multipliers,
                )
            branch = (
                "剑林凝结体体力-设置-倍率-次数-"
                f"{plan.count}-倍率-{plan.multiplier}"
            )
            get_node_data = getattr(context, "get_node_data")
            if get_node_data(dispatch_node) is None or get_node_data(branch) is None:
                return False
            override_next = getattr(context, "override_next")
            return bool(override_next(dispatch_node, [branch]))
        except (AttributeError, TypeError, ValueError, KeyError):
            return False


__all__ = ["ChallengePlan", "PlanJianlinChallenge", "plan_safe_challenge"]
