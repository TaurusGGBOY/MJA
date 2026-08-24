"""Immutable business-policy models used by the embedded MFW Agent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


def _positive_caps(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for name, limit in values.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{field_name} names must be non-empty strings")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"{field_name}[{name}] must be a positive integer")
        normalized[name.strip()] = limit
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class TaskPolicy:
    """Immutable limits and permissions for one canonical business task.

    The model deliberately contains no entry point, ordering hint, scheduler, or
    navigation field. Those are control-plane concerns and do not belong in an
    individual MFW task's safety contract.
    """

    task_id: str
    label: str
    risk_levels: frozenset[str]
    max_steps: int
    action_caps: Mapping[str, int]
    approved_resources: frozenset[str]
    resource_caps: Mapping[str, int]
    eligible_weekdays: frozenset[int] | None = None
    cleanup_action_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("label must be non-empty")
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int):
            raise ValueError("max_steps must be a positive integer")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")

        risks = frozenset(self.risk_levels)
        if not risks or not all(isinstance(level, str) and level for level in risks):
            raise ValueError("risk_levels must contain non-empty strings")

        action_caps = _positive_caps(self.action_caps, "action_caps")
        resource_caps = _positive_caps(self.resource_caps, "resource_caps")
        resources = frozenset(self.approved_resources)
        if not all(isinstance(resource, str) and resource.strip() for resource in resources):
            raise ValueError("approved_resources must contain non-empty strings")
        if resources != frozenset(resource_caps):
            raise ValueError("approved_resources must match resource_caps")

        cleanup_actions = frozenset(self.cleanup_action_ids)
        if not all(
            isinstance(action, str) and action.strip()
            for action in cleanup_actions
        ):
            raise ValueError("cleanup_action_ids must contain non-empty strings")
        if not cleanup_actions <= frozenset(action_caps):
            raise ValueError("cleanup_action_ids must be a subset of action_caps")

        weekdays = self.eligible_weekdays
        if weekdays is not None:
            weekdays = frozenset(weekdays)
            if any(
                isinstance(day, bool) or not isinstance(day, int) or day not in range(7)
                for day in weekdays
            ):
                raise ValueError("eligible_weekdays must contain integers from 0 to 6")

        object.__setattr__(self, "task_id", self.task_id.strip().upper())
        object.__setattr__(self, "label", self.label.strip())
        object.__setattr__(self, "risk_levels", risks)
        object.__setattr__(self, "action_caps", action_caps)
        object.__setattr__(self, "approved_resources", resources)
        object.__setattr__(self, "resource_caps", resource_caps)
        object.__setattr__(self, "eligible_weekdays", weekdays)
        object.__setattr__(
            self,
            "cleanup_action_ids",
            frozenset(action.strip().lower() for action in cleanup_actions),
        )


__all__ = ["TaskPolicy"]
