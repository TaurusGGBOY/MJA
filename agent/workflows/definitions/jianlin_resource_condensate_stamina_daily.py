"""Evidence-gated Jianlin condensate resource workflow.

The live game exposes this task as a small stateful loop rather than a single
button: select the 凝晶 resource, buy exactly one verified stamina refill,
configure the largest safe run and multiplier, then repeat until the next run
would exceed the remaining stamina.  All decisions here are pure; the Android
adapter owns the bounded ADB gestures.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..models import ActionIntent, Decision, InputKind, StateSnapshot, TaskStatus, Transition

TASK_ID = "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"
MAX_CHALLENGE_CYCLES = 12
MAX_DAILY_SCROLLS = 3

_INTEGER = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")
_X_VALUE = re.compile(r"[x×]\s*(\d{1,2})", re.IGNORECASE)
_MULTIPLIER_VALUE = re.compile(r"(?:倍率|倍)\s*[:：]?\s*[x×]?\s*(\d{1,2})")

_DANGER_MARKERS = (
    "unknown_dialog",
    "safety.paid",
    "safety.verification",
    "jianlin_refill_prompt",
    "jianlin_unknown_currency",
)
_COMMON = _DANGER_MARKERS + ("紫色魂玉", "体力")
_RESOURCE = (
    "jianlin_page",
    "jianlin_condensate_resource",
    "jianlin_condensate_selected",
    "jianlin_condensate_title",
    "jianlin_stamina_plus",
    "jianlin_stamina_current",
    "jianlin_stamina_cost",
    "jianlin_stamina_cost_value",
    "jianlin_count_bar",
    "jianlin_count_selected",
    "jianlin_count_changed",
    "jianlin_count_max",
    "jianlin_multiplier_bar",
    "jianlin_multiplier_selected",
    "jianlin_multiplier_changed",
    "jianlin_multiplier_1",
    "jianlin_multiplier_2",
    "jianlin_multiplier_3",
    "jianlin_challenge_button",
    "jianlin_page_close",
) + _COMMON

JIANLIN_RECOGNIZERS = MappingProxyType(
    {
        "home": (
            "home",
            "function_panel.open",
            "daily.page",
            "jianlin_daily_row",
            "jianlin_entry",
            "jianlin_page",
            "jianlin_condensate_resource",
            "jianlin_condensate_selected",
            "jianlin_condensate_title",
            "jianlin_challenge_button",
            "jianlin_stamina_plus",
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_amount",
            "jianlin_stamina_price",
            "jianlin_stamina_escalated_price",
            "jianlin_stamina_resource",
            "jianlin_stamina_confirmation_prompt",
            "jianlin_stamina_confirmation_price",
            "jianlin_stamina_confirmation_amount",
            "jianlin_stamina_confirmation_resource",
            "jianlin_stamina_confirmation_confirm",
            "jianlin_stamina_purchase_result",
            "jianlin_stamina_result_close",
            "jianlin_battle_page",
            "jianlin_battle_start",
            *_COMMON,
        ),
        "panel": ("function_panel.page", "daily.entry", *_COMMON),
        "daily": (
            "daily.page",
            "jianlin_daily_row",
            "jianlin_entry",
            *_COMMON,
        ),
        "resource": _RESOURCE,
        "stamina_prompt": (
            "jianlin_page",
            "jianlin_condensate_resource",
            "jianlin_condensate_title",
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_amount",
            "jianlin_stamina_price",
            "jianlin_stamina_escalated_price",
            "jianlin_stamina_resource",
            "jianlin_postpurchase_surface",
            *_COMMON,
        ),
        "stamina_result": (
            "jianlin_stamina_purchase_result",
            "jianlin_stamina_result_close",
            # Dismissing the +80 reward can immediately reveal the second,
            # non-authorized refill offer.  Keep its bounded evidence in the
            # same post-action frame so the derived post-purchase surface can
            # be proven before the state machine closes it without buying.
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_amount",
            "jianlin_stamina_escalated_price",
            *_RESOURCE,
        ),
        "stamina_confirmation": (
            "jianlin_stamina_confirmation_prompt",
            "jianlin_stamina_confirmation_price",
            "jianlin_stamina_confirmation_amount",
            "jianlin_stamina_confirmation_resource",
            "jianlin_stamina_confirmation_confirm",
            # The purchase confirmation can transition directly into the
            # reward overlay. Keep its bounded close marker in the same
            # post-action recognition set so the adapter can synthesize the
            # result page from the stable "click blank to close" footer.
            "jianlin_stamina_result_close",
            *_COMMON,
        ),
        "battle": (
            "jianlin_battle_page",
            "jianlin_battle_start",
            "jianlin_battle_skip_prepare",
            "jianlin_battle_skip_prepare_checked",
            "jianlin_battle_result",
            *_COMMON,
        ),
        "battle_result": (
            "jianlin_battle_result",
            "jianlin_result_close",
            *_RESOURCE,
        ),
        "daily_verify": (
            "daily.page",
            "jianlin_daily_row",
            *_COMMON,
        ),
        "done": ("home", *_COMMON),
    }
)


@dataclass(frozen=True, slots=True)
class ChallengePlan:
    """One safe configuration for a resource challenge."""

    count: int
    multiplier: int


def plan_safe_challenge(
    stamina: int,
    cost: int,
    visible_max: int,
    safe_multipliers: tuple[int, ...],
) -> ChallengePlan:
    """Calculate a bounded challenge without ever falling back to x1."""

    if stamina < 0 or cost <= 0 or visible_max <= 0 or not safe_multipliers:
        raise ValueError("unsafe challenge inputs")
    multipliers = tuple(value for value in safe_multipliers if value > 0)
    if not multipliers:
        raise ValueError("unsafe multipliers")
    for multiplier in sorted(multipliers, reverse=True):
        count = min(stamina // (cost * multiplier), visible_max)
        if count >= 1:
            return ChallengePlan(count=count, multiplier=multiplier)
    raise ValueError("insufficient stamina")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _numbers_after_label(texts: tuple[str, ...], labels: tuple[str, ...]) -> tuple[int, ...]:
    for text in texts:
        compact = _compact(text)
        for label in labels:
            index = compact.find(label)
            if index < 0:
                continue
            values = tuple(
                int(match.group(1))
                for match in _INTEGER.finditer(compact[index + len(label) :])
            )
            if values:
                return values
    return ()


def _current_stamina(texts: tuple[str, ...]) -> int | None:
    values = _numbers_after_label(texts, ("当前体力", "剩余体力"))
    if values:
        return values[0]
    for text in texts:
        compact = _compact(text)
        match = re.search(r"体力[:：]?(\d{1,4})\s*/", compact)
        if match:
            return int(match.group(1))
        match = re.fullmatch(r"(\d{1,4})/(\d{1,4})", compact)
        if match:
            return int(match.group(1))
    return None


def _stamina_below_20(texts: tuple[str, ...]) -> bool:
    current = _current_stamina(texts)
    return current is not None and current < 20


def _stamina_cost(texts: tuple[str, ...]) -> int | None:
    values = _numbers_after_label(texts, ("消耗体力", "单次体力"))
    return values[0] if values else None


def _standalone_stamina_cost(snapshot: StateSnapshot) -> int | None:
    if not _hit(snapshot, "jianlin_stamina_cost_value") or snapshot.evidence is None:
        return None
    values: list[int] = []
    for text in snapshot.evidence.texts:
        compact = _compact(text)
        if re.fullmatch(r"\d{1,3}", compact):
            value = int(compact)
            if value > 0:
                values.append(value)
    # Maa OCR may retain a low-confidence fragment before the actual total
    # (for example ``2`` before ``120``).  The displayed total is the largest
    # positive standalone value in this tightly bounded cost region.
    return max(values, default=None)


def _base_stamina_cost(snapshot: StateSnapshot) -> int | None:
    """Convert the displayed total cost back to one x1 resource run."""

    if snapshot.evidence is None:
        return None
    displayed = _stamina_cost(snapshot.evidence.texts)
    if displayed is None:
        displayed = _standalone_stamina_cost(snapshot)
    if displayed is None:
        return None
    count = _selected_count(snapshot.evidence.texts) or 1
    multiplier = _selected_multiplier(snapshot.evidence.texts) or 1
    divisor = count * multiplier
    if divisor <= 0 or displayed % divisor != 0:
        return None
    base = displayed // divisor
    return base if base > 0 else None


def _visible_count_max(texts: tuple[str, ...]) -> int | None:
    upper_limits = _numbers_after_label(texts, ("上限", "最多"))
    if upper_limits:
        return upper_limits[-1]
    values = _numbers_after_label(texts, ("挑战次数", "挑战数量"))
    if len(values) >= 2:
        return values[-1]
    if values:
        return values[0]
    return None


def _selected_count(texts: tuple[str, ...]) -> int | None:
    values = _numbers_after_label(texts, ("挑战次数", "挑战数量"))
    if values:
        return values[0]
    for text in texts:
        match = _X_VALUE.search(_compact(text))
        if match:
            return int(match.group(1))
    return None


def _selected_multiplier(texts: tuple[str, ...]) -> int | None:
    for text in texts:
        compact = _compact(text)
        match = _MULTIPLIER_VALUE.search(compact)
        if match:
            return int(match.group(1))
        if "倍率" in compact or "倍" in compact:
            match = re.search(r"[x×](\d{1,2})", compact, re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None


def _safe_multipliers(snapshot: StateSnapshot) -> tuple[int, ...]:
    evidence = snapshot.evidence
    assert evidence is not None
    values = tuple(
        value
        for value in (1, 2, 3)
        if evidence.target_hits.get(f"jianlin_multiplier_{value}", 0) == 1
    )
    if values:
        return values
    parsed = _numbers_after_label(evidence.texts, ("结算倍率", "倍率"))
    return tuple(dict.fromkeys(value for value in parsed if 0 < value <= 3))


def _plan(snapshot: StateSnapshot) -> ChallengePlan | None:
    evidence = snapshot.evidence
    if evidence is None:
        return None
    stamina = _current_stamina(evidence.texts)
    cost = _base_stamina_cost(snapshot)
    visible_max = _visible_count_max(evidence.texts)
    multipliers = _safe_multipliers(snapshot)
    if stamina is None or cost is None or visible_max is None or not multipliers:
        return None
    try:
        return plan_safe_challenge(stamina, cost, visible_max, multipliers)
    except ValueError:
        return None


def _hit(snapshot: StateSnapshot, marker: str) -> bool:
    evidence = snapshot.evidence
    return evidence is not None and evidence.target_hits.get(marker, 0) == 1


def _any_hit(snapshot: StateSnapshot, *markers: str) -> bool:
    evidence = snapshot.evidence
    return evidence is not None and any(
        evidence.target_hits.get(marker, 0) != 0 for marker in markers
    )


def _danger(snapshot: StateSnapshot) -> bool:
    evidence = snapshot.evidence
    return evidence is not None and any(
        evidence.danger_hits.get(marker, 0) != 0 for marker in _DANGER_MARKERS
    )


def _transition(
    action: str,
    page: str,
    target: str,
    postcondition: str,
    next_state: str,
    *,
    resource: str | None = None,
    parameter: int | None = None,
    input_kind: InputKind = InputKind.CLICK,
) -> Transition:
    return Transition(
        ActionIntent(
            action,
            page,
            target,
            approved_resource=resource,
            input_kind=input_kind,
            parameter=parameter,
        ),
        postcondition,
        next_state,
    )


def _danger_transition(state: str, counters: Mapping[str, int]) -> Transition | None:
    """Legacy transition helper retained for old fixtures and diagnostics."""

    if state == "home":
        return _transition(
            "open_function_panel",
            "home",
            "function_panel.open",
            "function_panel.page",
            "panel",
        )
    if state == "panel":
        return _transition(
            "open_daily_tasks",
            "function_panel.page",
            "daily.entry",
            "daily.page",
            "daily",
        )
    if state == "daily":
        return _transition(
            "open_jianlin",
            "daily.page",
            "jianlin_daily_row",
            "jianlin_page",
            "resource",
        )
    if state == "resource":
        if not counters.get("select_jianlin_condensate", 0):
            return _transition(
                "select_jianlin_condensate",
                "jianlin_page",
                "jianlin_condensate_resource",
                "jianlin_condensate_selected",
                "resource",
            )
        if counters.get("buy_stamina_once", 0) == 0:
            return _transition(
                "open_jianlin_stamina_purchase",
                "jianlin_condensate_selected",
                "jianlin_stamina_plus",
                "jianlin_stamina_purchase_prompt",
                "stamina_prompt",
            )
        return _transition(
            "challenge_condensate",
            "jianlin_condensate_selected",
            "jianlin_challenge_button",
            "jianlin_battle_page",
            "battle",
            resource="体力",
        )
    if state == "stamina_prompt":
        return _transition(
            "buy_stamina_once",
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_purchase_result",
            "stamina_result",
            resource="紫色魂玉",
        )
    if state == "stamina_result":
        return _transition(
            "dismiss_jianlin_stamina_result",
            "jianlin_stamina_purchase_result",
            "jianlin_stamina_result_close",
            "jianlin_condensate_selected",
            "resource",
        )
    if state == "battle":
        return _transition(
            "start_jianlin_battle",
            "jianlin_battle_page",
            "jianlin_battle_start",
            "jianlin_battle_result",
            "battle_result",
        )
    if state == "battle_result":
        return _transition(
            "close_condensate_result",
            "jianlin_battle_result",
            "jianlin_result_close",
            "jianlin_condensate_selected",
            "resource",
        )
    if state == "daily_verify":
        return _transition(
            "close_jianlin_page",
            "daily.page",
            "jianlin_daily_done",
            "daily.page",
            "daily_verify",
        )
    return None


def _resource_decision(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
    if not _hit(snapshot, "jianlin_condensate_selected"):
        if _hit(snapshot, "jianlin_condensate_resource"):
            return Decision.act(
                _transition(
                    "select_jianlin_condensate",
                    "jianlin_page",
                    "jianlin_condensate_resource",
                    "jianlin_condensate_selected",
                    "resource",
                )
            )
        return Decision.finish(TaskStatus.FAILED)

    purchase_completed = (
        counters.get("confirm_jianlin_stamina_purchase", 0) >= 1
        or counters.get("dismiss_jianlin_stamina_result", 0) >= 1
        or counters.get("close_postpurchase_stamina_prompt", 0) >= 1
    )
    evidence = snapshot.evidence
    assert evidence is not None
    stamina = _current_stamina(evidence.texts)
    if _stamina_below_20(evidence.texts):
        return Decision.act(
            _transition(
                "close_jianlin_page",
                "jianlin_condensate_selected",
                "jianlin_page_close",
                "home",
                "done",
            )
        )
    if counters.get("buy_stamina_once", 0) == 0 and not purchase_completed:
        return Decision.act(
            _transition(
                "open_jianlin_stamina_purchase",
                "jianlin_condensate_selected",
                "jianlin_stamina_plus",
                "jianlin_stamina_purchase_prompt",
                "stamina_prompt",
            )
        )

    cost = _base_stamina_cost(snapshot)
    if stamina is None or cost is None:
        return Decision.finish(TaskStatus.FAILED)
    if stamina is not None and cost is not None and stamina < cost:
        return Decision.act(
            _transition(
                "close_jianlin_page",
                "jianlin_condensate_selected",
                "jianlin_page_close",
                "home",
                "done",
            )
        )
    plan = _plan(snapshot)
    if plan is None:
        safe_multipliers = _safe_multipliers(snapshot)
        if safe_multipliers and stamina < cost * min(safe_multipliers):
            return Decision.act(
                _transition(
                    "close_jianlin_page",
                    "jianlin_condensate_selected",
                    "jianlin_page_close",
                    "home",
                    "done",
                )
            )
        return Decision.finish(TaskStatus.FAILED)
    if counters.get("challenge_condensate", 0) >= MAX_CHALLENGE_CYCLES:
        return Decision.act(
            _transition(
                "close_jianlin_page",
                "jianlin_condensate_selected",
                "jianlin_page_close",
                "home",
                "done",
            )
        )

    selected_count = _selected_count(evidence.texts)
    if selected_count != plan.count:
        return Decision.act(
            _transition(
                "set_safe_count",
                "jianlin_condensate_selected",
                "jianlin_count_bar",
                "jianlin_count_changed",
                "resource",
                parameter=plan.count,
            )
        )
    selected_multiplier = _selected_multiplier(evidence.texts)
    if selected_multiplier != plan.multiplier:
        return Decision.act(
            _transition(
                "set_safe_multiplier",
                "jianlin_condensate_selected",
                "jianlin_multiplier_bar",
                "jianlin_multiplier_changed",
                "resource",
                parameter=plan.multiplier,
            )
        )
    return Decision.act(
        _transition(
            "challenge_condensate",
            "jianlin_condensate_selected",
            "jianlin_challenge_button",
            "jianlin_battle_page",
            "battle",
            resource="体力",
            parameter=plan.count,
        )
    )


def _stamina_purchase_proven(snapshot: StateSnapshot) -> bool:
    evidence = snapshot.evidence
    if evidence is None:
        return False
    text = "|".join(_compact(value) for value in evidence.texts)
    has_amount = bool(re.search(r"\+80", text))
    has_price = bool(re.search(r"(?<!\d)10(?!\d)", text))
    return (
        has_amount
        and has_price
        and _hit(snapshot, "jianlin_stamina_amount")
        and _hit(snapshot, "jianlin_stamina_price")
        and _hit(snapshot, "jianlin_stamina_resource")
        and _hit(snapshot, "jianlin_stamina_purchase_confirm")
    )


def _stamina_confirmation_proven(snapshot: StateSnapshot) -> bool:
    """Prove the second, consumptive confirmation from one captured frame."""

    return all(
        _hit(snapshot, marker)
        for marker in (
            "jianlin_stamina_confirmation_prompt",
            "jianlin_stamina_confirmation_price",
            "jianlin_stamina_confirmation_amount",
            "jianlin_stamina_confirmation_resource",
            "jianlin_stamina_confirmation_confirm",
        )
    )


def _postpurchase_stamina_prompt_proven(snapshot: StateSnapshot) -> bool:
    """Recognize the escalated second-purchase offer without authorizing it."""

    return (
        _hit(snapshot, "jianlin_stamina_purchase_prompt")
        and _hit(snapshot, "jianlin_stamina_amount")
        and _hit(snapshot, "jianlin_stamina_escalated_price")
    )


class JianlinResourceCondensateStaminaDailyDefinition:
    """Pure state machine for the one-purchase, bounded Jianlin loop."""

    task_id = TASK_ID
    initial_state = "home"

    def recognizers(self, state: str) -> tuple[str, ...]:
        try:
            return JIANLIN_RECOGNIZERS[state]
        except KeyError as exc:
            raise ValueError(f"unknown Jianlin workflow state: {state}") from exc

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        evidence = snapshot.evidence
        if evidence is None:
            return Decision.finish(TaskStatus.FAILED)

        if snapshot.state == "done":
            return Decision.finish(
                TaskStatus.COMPLETED
                if (
                    counters.get("challenge_condensate", 0) >= 1
                    or counters.get("close_postpurchase_stamina_prompt", 0) >= 1
                    or counters.get("close_jianlin_page", 0) >= 1
                )
                else TaskStatus.FAILED
            )

        if snapshot.state == "home":
            # Cleanup may intentionally leave the already-open daily list in
            # place. Treat it as a resumable surface before requiring a home
            # marker, so rerunning an already-completed task is a safe no-op.
            if _hit(snapshot, "daily.page"):
                if _hit(snapshot, "jianlin_daily_row"):
                    return Decision.act(
                        _transition(
                            "open_jianlin",
                            "daily.page",
                            "jianlin_daily_row",
                            "jianlin_page",
                            "resource",
                        )
                    )
                if counters.get("scroll_daily_jianlin", 0) < MAX_DAILY_SCROLLS:
                    return Decision.act(
                        _transition(
                            "scroll_daily_jianlin",
                            "daily.page",
                            "daily.page",
                            "daily.page",
                            "daily",
                            input_kind=InputKind.SWIPE,
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            if _hit(snapshot, "jianlin_battle_page"):
                return Decision.act(
                    _transition(
                        "start_jianlin_battle",
                        "jianlin_battle_page",
                        "jianlin_battle_start",
                        "jianlin_battle_result",
                        "battle_result",
                    )
                )
            if _postpurchase_stamina_prompt_proven(snapshot):
                return Decision.act(
                    _transition(
                        "close_postpurchase_stamina_prompt",
                        "jianlin_stamina_purchase_prompt",
                        "jianlin_stamina_escalated_price",
                        "jianlin_condensate_selected",
                        "done",
                    )
                )
            if (
                _hit(snapshot, "jianlin_stamina_purchase_result")
                and _hit(snapshot, "jianlin_stamina_result_close")
            ):
                return Decision.act(
                    _transition(
                        "dismiss_jianlin_stamina_result",
                        "jianlin_stamina_purchase_result",
                        "jianlin_stamina_result_close",
                        "jianlin_stamina_purchase_prompt",
                        "home",
                    )
                )
            if _stamina_confirmation_proven(snapshot):
                return Decision.act(
                    _transition(
                        "confirm_jianlin_stamina_purchase",
                        "jianlin_stamina_confirmation_prompt",
                        "jianlin_stamina_confirmation_confirm",
                        "jianlin_stamina_purchase_result",
                        "stamina_result",
                        resource="紫色魂玉",
                    )
                )
            if _hit(snapshot, "jianlin_stamina_purchase_prompt"):
                if not _stamina_purchase_proven(snapshot):
                    return Decision.finish(TaskStatus.FAILED)
                return Decision.act(
                    _transition(
                        "buy_stamina_once",
                        "jianlin_stamina_purchase_prompt",
                        "jianlin_stamina_purchase_confirm",
                        "jianlin_stamina_confirmation_prompt",
                        "stamina_confirmation",
                        resource="紫色魂玉",
                    )
                )
            if _hit(snapshot, "jianlin_page"):
                return _resource_decision(snapshot, counters)
            return Decision.act(
                _transition(
                    "open_function_panel",
                    "home",
                    "function_panel.open",
                    "function_panel.page",
                    "panel",
                )
            )
        if snapshot.state == "panel":
            return Decision.act(
                _transition(
                    "open_daily_tasks",
                    "function_panel.page",
                    "daily.entry",
                    "daily.page",
                    "daily",
                )
            )
        if snapshot.state == "daily":
            if _hit(snapshot, "jianlin_daily_row"):
                return Decision.act(
                    _transition(
                        "open_jianlin",
                        "daily.page",
                        "jianlin_daily_row",
                        "jianlin_page",
                        "resource",
                    )
                )
            if counters.get("scroll_daily_jianlin", 0) < MAX_DAILY_SCROLLS:
                return Decision.act(
                    _transition(
                        "scroll_daily_jianlin",
                        "daily.page",
                        "daily.page",
                        "daily.page",
                        "daily",
                        input_kind=InputKind.SWIPE,
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if snapshot.state == "resource":
            return _resource_decision(snapshot, counters)
        if snapshot.state == "stamina_prompt":
            if _postpurchase_stamina_prompt_proven(snapshot):
                return Decision.act(
                    _transition(
                        "close_postpurchase_stamina_prompt",
                        "jianlin_stamina_purchase_prompt",
                        "jianlin_stamina_escalated_price",
                        "jianlin_condensate_selected",
                        "done",
                    )
                )
            if counters.get("buy_stamina_once", 0) >= 1:
                return Decision.finish(TaskStatus.FAILED)
            if not _stamina_purchase_proven(snapshot):
                return Decision.finish(TaskStatus.FAILED)
            return Decision.act(
                _transition(
                    "buy_stamina_once",
                    "jianlin_stamina_purchase_prompt",
                    "jianlin_stamina_purchase_confirm",
                    "jianlin_stamina_confirmation_prompt",
                    "stamina_confirmation",
                    resource="紫色魂玉",
                )
            )
        if snapshot.state == "stamina_confirmation":
            if not _stamina_confirmation_proven(snapshot):
                return Decision.finish(TaskStatus.FAILED)
            return Decision.act(
                _transition(
                    "confirm_jianlin_stamina_purchase",
                    "jianlin_stamina_confirmation_prompt",
                    "jianlin_stamina_confirmation_confirm",
                    "jianlin_stamina_purchase_result",
                    "stamina_result",
                    resource="紫色魂玉",
                )
            )
        if snapshot.state == "stamina_result":
            return Decision.act(
                _transition(
                    "dismiss_jianlin_stamina_result",
                    "jianlin_stamina_purchase_result",
                    "jianlin_stamina_result_close",
                    # The game may immediately open the escalated second
                    # +80 refill offer after the reward sheet is dismissed,
                    # or return directly to the selected resource page. Both
                    # are valid post-purchase surfaces; the home branch then
                    # closes the offer without authorizing another purchase.
                    "jianlin_postpurchase_surface",
                    "home",
                )
            )
        if snapshot.state == "battle":
            if _hit(snapshot, "jianlin_battle_skip_prepare") and not _hit(
                snapshot, "jianlin_battle_skip_prepare_checked"
            ):
                return Decision.act(
                    _transition(
                        "enable_jianlin_skip_prepare",
                        "jianlin_battle_page",
                        "jianlin_battle_skip_prepare",
                        "jianlin_battle_skip_prepare_checked",
                        "battle",
                    )
                )
            return Decision.act(
                _transition(
                    "start_jianlin_battle",
                    "jianlin_battle_page",
                    "jianlin_battle_start",
                    "jianlin_battle_result",
                    "battle_result",
                )
            )
        if snapshot.state == "battle_result":
            return Decision.act(
                _transition(
                    "close_condensate_result",
                    "jianlin_battle_result",
                    "jianlin_result_close",
                    "jianlin_condensate_selected",
                    "resource",
                )
            )
        if snapshot.state == "daily_verify":
            return Decision.finish(TaskStatus.COMPLETED)
        return Decision.finish(TaskStatus.FAILED)


JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION = (
    JianlinResourceCondensateStaminaDailyDefinition()
)


__all__ = [
    "ChallengePlan",
    "JIANLIN_RECOGNIZERS",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION",
    "JianlinResourceCondensateStaminaDailyDefinition",
    "MAX_CHALLENGE_CYCLES",
    "MAX_DAILY_SCROLLS",
    "plan_safe_challenge",
]
