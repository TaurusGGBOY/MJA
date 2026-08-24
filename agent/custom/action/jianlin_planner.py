"""Pure Jianlin challenge planning exposed as one narrow MFW action."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.controller_input import click_box


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
    *,
    max_total_cost: int | None = None,
) -> ChallengePlan:
    """Calculate the largest declared safe challenge for the current stamina."""

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
    if max_total_cost is not None and (
        isinstance(max_total_cost, bool)
        or not isinstance(max_total_cost, int)
        or max_total_cost <= 0
    ):
        raise ValueError("unsafe maximum challenge cost")
    for multiplier in sorted(multipliers, reverse=True):
        count = min(stamina // (cost * multiplier), visible_max)
        if max_total_cost is not None:
            count = min(count, max_total_cost // (cost * multiplier))
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


def _ocr_nonnegative_amount(detail: Any) -> int:
    match = _INTEGER.search(_ocr_text(detail))
    if match is None:
        raise ValueError("planner OCR result has no integer")
    return int(match.group(1))


def _at(results: Sequence[Any], index: int) -> Any:
    if index >= len(results):
        raise ValueError("planner OCR index is out of range")
    return results[index]


@AgentServer.custom_action("PlanJianlinChallenge")
class PlanJianlinChallenge(CustomAction):
    """Choose and apply only the settlement multiplier from current stamina."""

    _SLIDER_LEFT = 930
    _SLIDER_RIGHT = 1206
    _MULTIPLIER_Y = 427

    @classmethod
    def _slider_box(cls, value: int, maximum: int, y: int) -> tuple[int, int, int, int]:
        if not 1 <= value <= maximum or maximum <= 1 or maximum > 12:
            raise ValueError("unsafe Jianlin slider value")
        position = cls._SLIDER_LEFT + round(
            (value - 1) * (cls._SLIDER_RIGHT - cls._SLIDER_LEFT) / (maximum - 1)
        )
        return position - 8, y - 14, 16, 28

    @classmethod
    def _apply_multiplier(
        cls,
        context: Any,
        multiplier: int,
        multiplier_max: int,
    ) -> None:
        controller = context.tasker.controller
        resolution = getattr(controller, "resolution", None)
        click_box(
            controller,
            cls._slider_box(multiplier, multiplier_max, cls._MULTIPLIER_Y),
            resolution=resolution,
        )

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        try:
            payload = _payload(argv)
            dispatch_node = payload.get("dispatch_node")
            if not isinstance(dispatch_node, str) or not dispatch_node.strip():
                raise ValueError("dispatch_node must be a non-empty string")
            stamina_index = _index(payload, "stamina_index")
            results = _and_results(getattr(argv, "reco_detail", None))
            stamina_per_multiplier = _positive_int(
                payload.get("stamina_per_multiplier"),
                "stamina_per_multiplier",
            )
            max_multiplier = _positive_int(
                payload.get("max_multiplier"),
                "max_multiplier",
            )
            if max_multiplier != 6:
                raise ValueError("Jianlin multiplier slider maximum must be 6")
            stop_stamina_at_or_below = payload.get("stop_stamina_at_or_below", 0)
            if (
                isinstance(stop_stamina_at_or_below, bool)
                or not isinstance(stop_stamina_at_or_below, int)
                or stop_stamina_at_or_below < 0
            ):
                raise ValueError("stop_stamina_at_or_below is unsafe")

            branch = "0934-剑林凝结体体力-挑战-凝结体"
            get_node_data = getattr(context, "get_node_data")
            if get_node_data(dispatch_node) is None or get_node_data(branch) is None:
                return False

            stamina = _ocr_nonnegative_amount(_at(results, stamina_index))
            multiplier = min(stamina // stamina_per_multiplier, max_multiplier)
            if stamina <= stop_stamina_at_or_below or multiplier < 1:
                insufficient_node = payload.get("insufficient_node")
                if (
                    not isinstance(insufficient_node, str)
                    or get_node_data(insufficient_node) is None
                ):
                    return False
                override_next = getattr(context, "override_next")
                return bool(override_next(dispatch_node, [insufficient_node]))

            type(self)._apply_multiplier(context, multiplier, max_multiplier)
            return True
        except (AttributeError, TypeError, ValueError, KeyError):
            return False


__all__ = ["ChallengePlan", "PlanJianlinChallenge", "plan_safe_challenge"]
