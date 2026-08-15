"""Immutable value objects shared by workflow definitions and the runner."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class TaskStatus(StrEnum):
    """The statuses a workflow may return at runtime."""

    COMPLETED = "completed"
    ALREADY_COMPLETE = "already_complete"
    NOT_ELIGIBLE = "not_eligible"
    FAILED = "failed"


class RiskLevel(StrEnum):
    """Policy risk categories used by later safety and scheduling layers."""

    NORMAL = "normal"
    PROTECTED_CLAIM = "protected_claim"
    CONSUMPTIVE = "consumptive"
    STATEFUL = "stateful"
    COMBAT = "combat"


class InputKind(StrEnum):
    """Input primitives a transition may request from the bounded driver."""

    CLICK = "click"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    NONE = "none"


_ACTION_IDS = frozenset(
    {
        "click",
        "swipe",
        "long_press",
        "none",
        "assign_sweep_ticket",
        "buy_tea",
        "buy",
        "buy_yanwu_currency_max",
        "buy_yunzhou_currency_max",
        "claim_all_collection",
        "claim_all_mail",
        "claim",
        "claim_basic_red_dot_reward",
        "claim_completed_daily_row",
        "claim_first_dispatch",
        "claim_free_appraisal_once",
        "claim_free_gift",
        "claim_free_trial",
        "claim_gift_reward",
        "claim_success_card",
        "claim_task_reward",
        "claim_trial_sword_reward",
        "claim_unlocked_activity_chest",
        "claim_weekly_lucky_bag",
        "dismiss_weekly_reward",
        "dismiss_free_gift_reward",
        "open",
        "close_appraisal_page",
        "close_appraisal_popup",
        "close_bag",
        "close_battle_pass",
        "close_collection_deployment",
        "close_collection_painting",
        "close_daily_tasks",
        "close_dungeon",
        "close_free_popup",
        "close_yanwu_currency_purchase",
        "close_yunzhou_currency_purchase",
        "close_trial",
        "close_gift_rewards",
        "close_hero_dispatch",
        "close_hero_dispatch_painting",
        "close_function_panel",
        "close_mail",
        "close_martial",
        "close_martial_page",
        "close_reward_popup",
        "close_shop",
        "confirm_free_trial",
        "confirm_food_buff_replace",
        "confirm_yanwangling_master_sweep",
        "close",
        "dismiss_dispatch_claim_result",
        "dismiss_gift_result",
        "dismiss_success_result",
        "dismiss_sweep_result",
        "dismiss_tea_purchase_result",
        "dismiss_yanwu_reward_popup",
        "dismiss_yunzhou_reward_popup",
        "dispatch",
        "dispatch_team",
        "eat",
        "eat_longjing_shrimp",
        "inspect_food_candidate",
        "study",
        "retry",
        "challenge",
        "sweep",
        "battle",
        "reward",
        "open_appraisal",
        "open_bag",
        "open_battle_pass",
        "open_battle_pass_rewards",
        "open_battle_pass_tasks",
        "open_collection_deployment",
        "open_daily_tasks",
        "open_daily_tasks_initial",
        "open_daily_tasks_verify",
        "open_dungeon",
        "open_food_category",
        "select_food_tab",
        "open_function_panel",
        "open_function_panel_verify",
        "open_gift_rewards",
        "open_gift_tab",
        "open_hero_dispatch",
        "open_mail",
        "open_martial_study",
        "open_martial_plus_slot_0",
        "open_martial_plus_slot_1",
        "open_martial_plus_slot_2",
        "study_martial_slot",
        "breakthrough_martial_slot",
        "confirm_martial_breakthrough",
        "open_jianlin",
        "open_jianlin_stamina_purchase",
        "select_jianlin_condensate",
        "buy_stamina_once",
        "confirm_jianlin_stamina_purchase",
        "close_postpurchase_stamina_prompt",
        "dismiss_jianlin_stamina_result",
        "set_safe_count",
        "set_safe_multiplier",
        "challenge_condensate",
        "close_condensate_result",
        "close_jianlin_page",
        "buy_jianlin_resource",
        "start_jianlin_battle",
        "open_ring_challenge",
        "open_ring_attempt_mode",
        "start_ring_matching",
        "fight_ring_opponent",
        "start_ring_battle",
        "wait_ring_battle",
        "skip_ring_battle",
        "confirm_ring_sweep",
        "dismiss_ring_reward",
        "dismiss_ring_result",
        "close_ring_opponents",
        "close_ring_page",
        "sweep_ring",
        "open_painting_scroll",
        "open_period_benefits",
        "open_shadow",
        "select_active_shadow_card",
        "enter_shadow_stage",
        "confirm_shadow_auto_route",
        "enable_shadow_skip_prepare",
        "challenge_shadow_stage",
        "dismiss_shadow_battle_result",
        "dismiss_shadow_reward_popup",
        "dismiss_shadow_battle_failure",
        "confirm_shadow_completion",
        "advance_shadow_foreground_triplet",
        "transfer_shadow_stage",
        "confirm_shadow_transfer",
        "apply_shadow_recommended_team",
        "use_shadow_recommended_team",
        "close_shadow_recommended_team",
        "close_shadow_page",
        "move_shadow_foreground_left",
        "move_shadow_foreground_center",
        "move_shadow_foreground_right",
        "open_shop",
        "open_sweep_panel",
        "close_dungeon_for_food",
        "close_dungeon_for_jianlin",
        "close_dungeon_for_guild",
        "open_tea_purchase",
        "open_tea_tab",
        "open_trial_sword",
        "open_universal_shop",
        "open_weekly_must_buy",
        "open_yanwu_currency_purchase",
        "open_yunzhou_currency_purchase",
        "scroll_daily_breakthrough_row",
        "scroll_daily_dungeon_row",
        "scroll_daily_jianlin",
        "enable_jianlin_skip_prepare",
        "scroll_guild_affairs",
        "scroll_daily_reward_rows",
        "scroll_dungeon_list",
        "open_resource_page",
        "scroll_tea_list",
        "select_first_visible_dispatch",
        "close_dungeon_reward_preview",
        "select_yanwangling",
        "select_yanwangling_in_panel",
        "select_yanwu_world",
        "select_yunzhou",
        "set_tea_quantity_max",
        "set_yanwu_quantity_max",
        "set_yunzhou_quantity_max",
        "smart_configure_team",
        "start_yanwangling_master_sweep",
        "study_success_detail",
    }
)
_RESOURCE_IDS = frozenset(
    {
        "凝晶",
        "文",
        "龙井虾仁",
        "紫色魂玉",
        "体力",
        "擂台券",
        "副本票",
        "研习材料",
    }
)


def _canonical_task_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("task_id must be non-empty")
    return value.strip().upper()


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value.strip()


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _mapping_proxy(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for key, value in values.items():
        normalized_key = _non_empty(key, f"{field_name} key")
        normalized[normalized_key] = _non_negative_int(value, f"{field_name}[{normalized_key}]")
    return MappingProxyType(normalized)


def _size(value: tuple[int, int] | Iterable[int]) -> tuple[int, int]:
    try:
        width, height = tuple(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("size must contain exactly two integers") from exc
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise ValueError("size must contain two positive integers")
    return width, height


@dataclass(frozen=True, slots=True)
class TaskPolicy:
    """Immutable limits and permissions for one canonical workflow."""

    task_id: str
    label: str
    entry: str
    risk_levels: frozenset[RiskLevel]
    max_steps: int
    action_caps: Mapping[str, int]
    approved_resources: frozenset[str]
    eligible_weekdays: frozenset[int] | None = None
    order_hint: str = ""
    resource_caps: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        task_id = _canonical_task_id(self.task_id)
        label = _non_empty(self.label, "label")
        entry = _non_empty(self.entry, "entry")
        if entry != f"MJA_Daily_{task_id}":
            raise ValueError("entry must match the canonical task ID")
        max_steps = _positive_int(self.max_steps, "max_steps")
        risks = frozenset(self.risk_levels)
        if not risks or not all(isinstance(level, RiskLevel) for level in risks):
            raise ValueError("risk_levels must contain RiskLevel values")
        action_caps = _mapping_proxy(self.action_caps, "action_caps")
        unknown_actions = set(action_caps) - _ACTION_IDS
        if unknown_actions:
            raise ValueError(f"unknown action cap: {sorted(unknown_actions)[0]}")
        resources = frozenset(self.approved_resources)
        unknown_resources = resources - _RESOURCE_IDS
        if unknown_resources:
            raise ValueError(f"unknown approved resource: {sorted(unknown_resources)[0]}")
        resource_caps = _mapping_proxy(self.resource_caps, "resource_caps")
        unknown_resource_caps = set(resource_caps) - _RESOURCE_IDS
        if unknown_resource_caps:
            raise ValueError(f"unknown resource cap: {sorted(unknown_resource_caps)[0]}")
        if not resources <= set(resource_caps):
            raise ValueError("every approved resource must have a finite resource cap")
        weekdays = None
        if self.eligible_weekdays is not None:
            weekdays = frozenset(self.eligible_weekdays)
            if any(
                isinstance(day, bool) or not isinstance(day, int) or day not in range(7)
                for day in weekdays
            ):
                raise ValueError("eligible_weekdays must contain integers from 0 to 6")
        order_hint = self.order_hint.strip() if isinstance(self.order_hint, str) else ""
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "entry", entry)
        object.__setattr__(self, "risk_levels", risks)
        object.__setattr__(self, "max_steps", max_steps)
        object.__setattr__(self, "action_caps", action_caps)
        object.__setattr__(self, "approved_resources", resources)
        object.__setattr__(self, "eligible_weekdays", weekdays)
        object.__setattr__(self, "order_hint", order_hint)
        object.__setattr__(self, "resource_caps", resource_caps)

    @property
    def interface_name(self) -> str:
        return self.task_id.lower()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of this policy."""

        return {
            "task_id": self.task_id,
            "label": self.label,
            "entry": self.entry,
            "risk_levels": sorted(level.value for level in self.risk_levels),
            "max_steps": self.max_steps,
            "action_caps": dict(self.action_caps),
            "approved_resources": sorted(self.approved_resources),
            "eligible_weekdays": (
                None
                if self.eligible_weekdays is None
                else sorted(self.eligible_weekdays)
            ),
            "order_hint": self.order_hint,
            "resource_caps": dict(self.resource_caps),
        }


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """A requested action without permission to execute it."""

    action_id: str
    page_marker: str
    target_marker: str
    approved_resource: str | None = None
    input_kind: InputKind = InputKind.NONE
    frame_id: str | None = None
    parameter: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _non_empty(self.action_id, "action_id"))
        object.__setattr__(self, "page_marker", _non_empty(self.page_marker, "page_marker"))
        object.__setattr__(self, "target_marker", _non_empty(self.target_marker, "target_marker"))
        if isinstance(self.input_kind, str):
            try:
                input_kind = InputKind(self.input_kind)
            except ValueError as exc:
                raise ValueError("input_kind is unsupported") from exc
        elif isinstance(self.input_kind, InputKind):
            input_kind = self.input_kind
        else:
            raise ValueError("input_kind is unsupported")
        if self.approved_resource is not None:
            resource = _non_empty(self.approved_resource, "approved_resource")
            if resource not in _RESOURCE_IDS:
                raise ValueError("approved_resource is unknown")
            object.__setattr__(self, "approved_resource", resource)
        if self.frame_id is not None:
            object.__setattr__(self, "frame_id", _non_empty(self.frame_id, "frame_id"))
        if self.parameter is not None:
            object.__setattr__(
                self,
                "parameter",
                _positive_int(self.parameter, "parameter"),
            )
        object.__setattr__(self, "input_kind", input_kind)


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    frame_id: str
    size: tuple[int, int]
    payload: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _non_empty(self.frame_id, "frame_id"))
        object.__setattr__(self, "size", _size(self.size))


@dataclass(frozen=True, slots=True)
class Recognition:
    marker: str
    frame_id: str
    hits: int
    boxes: tuple[tuple[int, int, int, int], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "marker", _non_empty(self.marker, "marker"))
        object.__setattr__(self, "frame_id", _non_empty(self.frame_id, "frame_id"))
        object.__setattr__(self, "hits", _non_negative_int(self.hits, "hits"))
        normalized_boxes = tuple(tuple(box) for box in self.boxes)
        if any(len(box) != 4 for box in normalized_boxes):
            raise ValueError("boxes must contain four coordinates")
        object.__setattr__(self, "boxes", normalized_boxes)


@dataclass(frozen=True, slots=True)
class VisualEvidence:
    frame_id: str
    page_hits: Mapping[str, int]
    target_hits: Mapping[str, int]
    danger_hits: Mapping[str, int]
    recognizer_frame_ids: Mapping[str, str]
    texts: tuple[str, ...] = ()
    resource_hits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _non_empty(self.frame_id, "frame_id"))
        for field_name in ("page_hits", "target_hits", "danger_hits"):
            object.__setattr__(
                self,
                field_name,
                _mapping_proxy(getattr(self, field_name), field_name),
            )
        recognizer_ids = {
            _non_empty(key, "recognizer key"): _non_empty(value, "recognizer frame_id")
            for key, value in self.recognizer_frame_ids.items()
        }
        object.__setattr__(self, "recognizer_frame_ids", MappingProxyType(recognizer_ids))
        object.__setattr__(self, "texts", tuple(str(text) for text in self.texts))
        object.__setattr__(
            self,
            "resource_hits",
            tuple(str(resource) for resource in self.resource_hits),
        )


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    frame: CapturedFrame
    state: str
    recognitions: tuple[Recognition, ...] = ()
    evidence: VisualEvidence | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", _non_empty(self.state, "state"))
        object.__setattr__(self, "recognitions", tuple(self.recognitions))
        if any(not isinstance(item, Recognition) for item in self.recognitions):
            raise ValueError("recognitions must contain Recognition values")

    @property
    def frame_id(self) -> str:
        return self.frame.frame_id


@dataclass(frozen=True, slots=True)
class Transition:
    intent: ActionIntent
    postcondition: str
    next_state: str | None = None
    postcondition_alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.intent, ActionIntent):
            raise ValueError("transition intent must be an ActionIntent")
        object.__setattr__(self, "postcondition", _non_empty(self.postcondition, "postcondition"))
        if self.next_state is not None:
            object.__setattr__(self, "next_state", _non_empty(self.next_state, "next_state"))
        alternatives = tuple(
            _non_empty(marker, "postcondition alternative")
            for marker in self.postcondition_alternatives
        )
        if self.postcondition in alternatives:
            raise ValueError("postcondition alternatives must differ from postcondition")
        object.__setattr__(self, "postcondition_alternatives", alternatives)


@dataclass(frozen=True, slots=True)
class Decision:
    transition: Transition | None = None
    status: TaskStatus | None = None

    def __post_init__(self) -> None:
        has_transition = self.transition is not None
        has_status = self.status is not None
        if has_transition == has_status:
            raise ValueError("decision must contain exactly one transition or status")
        if has_transition and not isinstance(self.transition, Transition):
            raise ValueError("transition is invalid")
        if has_status and not isinstance(self.status, TaskStatus):
            raise ValueError("status must be a runtime TaskStatus")

    @classmethod
    def act(cls, transition: Transition | None = None) -> Decision:
        if transition is None:
            raise ValueError("transition is required")
        return cls(transition=transition)

    @classmethod
    def finish(cls, status: TaskStatus | None = None) -> Decision:
        if not isinstance(status, TaskStatus):
            raise ValueError("status must be a runtime TaskStatus")
        return cls(status=status)


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    postcondition: str
    action_counts: Mapping[str, int]
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _canonical_task_id(self.task_id))
        if not isinstance(self.status, TaskStatus):
            raise ValueError("status must be a runtime TaskStatus")
        object.__setattr__(self, "postcondition", _non_empty(self.postcondition, "postcondition"))
        object.__setattr__(
            self,
            "action_counts",
            _mapping_proxy(self.action_counts, "action_counts"),
        )
        if self.error_code is not None:
            object.__setattr__(self, "error_code", _non_empty(self.error_code, "error_code"))

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of this result."""

        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "postcondition": self.postcondition,
            "action_counts": dict(self.action_counts),
            "error_code": self.error_code,
        }


@runtime_checkable
class WorkflowDefinition(Protocol):
    """Contract implemented by later task definitions, without task logic here."""

    task_id: str
    initial_state: str

    def recognizers(self, state: str) -> tuple[str, ...]: ...

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision: ...
