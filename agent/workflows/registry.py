"""Explicit registry for canonical workflow definition slots.

Task implementations are intentionally not part of Task 1. The registry
contains metadata-only references so later tasks can replace them with real
definitions without changing the public catalog contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .catalog import TASK_POLICIES, WORKFLOW_DEFINITION_ORDER
from .definitions import (
    BATTLE_PASS_REWARD_DAILY_DEFINITION,
    BUY_TEA_DAILY_DEFINITION,
    COLLECTION_DEPLOYMENT_DAILY_DEFINITION,
    DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
    DUNGEON_SWEEP_DAILY_DEFINITION,
    EAT_STAMINA_FOOD_DAILY_DEFINITION,
    FREE_APPRAISAL_DAILY_DEFINITION,
    HERO_DISPATCH_DAILY_DEFINITION,
    JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION,
    MAIL_REWARD_DAILY_DEFINITION,
    MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
    RING_CHALLENGE_DAILY_DEFINITION,
    SHADOW_RUINS_DAILY_DEFINITION,
    SHOP_FREE_GIFT_DAILY_DEFINITION,
    SPEND_CONDENSATE_DAILY_DEFINITION,
    TRIAL_SWORD_DAILY_DEFINITION,
    WEEKLY_FREE_GIFT_MONDAY_DEFINITION,
)
from .models import Decision, StateSnapshot, WorkflowDefinition


@dataclass(frozen=True, slots=True)
class CatalogWorkflowDefinition:
    """A definition slot that deliberately contains no game workflow logic."""

    task_id: str
    initial_state: str = "entry"

    def recognizers(self, state: str) -> tuple[str, ...]:
        if not isinstance(state, str) or not state.strip():
            raise ValueError("state must be non-empty")
        return ()

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        raise NotImplementedError(
            f"workflow definition {self.task_id} is registered but not implemented in Task 1"
        )


def _build_registry() -> Mapping[str, WorkflowDefinition]:
    implemented: dict[str, WorkflowDefinition] = {
        definition.task_id: definition
        for definition in (
            MAIL_REWARD_DAILY_DEFINITION,
            BUY_TEA_DAILY_DEFINITION,
            SHOP_FREE_GIFT_DAILY_DEFINITION,
            WEEKLY_FREE_GIFT_MONDAY_DEFINITION,
            TRIAL_SWORD_DAILY_DEFINITION,
            FREE_APPRAISAL_DAILY_DEFINITION,
            COLLECTION_DEPLOYMENT_DAILY_DEFINITION,
            HERO_DISPATCH_DAILY_DEFINITION,
            SHADOW_RUINS_DAILY_DEFINITION,
            SPEND_CONDENSATE_DAILY_DEFINITION,
            MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION,
            EAT_STAMINA_FOOD_DAILY_DEFINITION,
            DUNGEON_SWEEP_DAILY_DEFINITION,
            JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION,
            RING_CHALLENGE_DAILY_DEFINITION,
            DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION,
            BATTLE_PASS_REWARD_DAILY_DEFINITION,
        )
    }
    definitions = {
        task_id: implemented.get(task_id, CatalogWorkflowDefinition(task_id=task_id))
        for task_id in WORKFLOW_DEFINITION_ORDER
    }
    if tuple(definitions) != tuple(TASK_POLICIES):
        raise ValueError("workflow registry and policy catalog are out of sync")
    return MappingProxyType(definitions)


WORKFLOW_DEFINITIONS = _build_registry()
