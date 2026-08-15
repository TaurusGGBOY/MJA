"""Bounded resource/combat definitions for Batch 2 and Batch 3."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from ..models import ActionIntent, Decision, InputKind, StateSnapshot, TaskStatus, Transition
from .batch1 import TableWorkflowDefinition, _definition
from .jianlin_resource_condensate_stamina_daily import (
    JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_DEFINITION,  # noqa: F401
)


def _resource_transition(
    action: str,
    page: str,
    target: str,
    resource: str,
    next_state: str,
    post: str,
):
    return Transition(
        ActionIntent(action, page, target, approved_resource=resource, input_kind=InputKind.CLICK),
        post,
        next_state,
    )


def _tr(
    action: str,
    page: str,
    target: str,
    post: str,
    next_state: str,
    *,
    input_kind: InputKind = InputKind.CLICK,
    postcondition_alternatives: tuple[str, ...] = (),
):
    return Transition(
        ActionIntent(action, page, target, input_kind=input_kind),
        post,
        next_state,
        postcondition_alternatives,
    )


def _simple(
    task_id: str,
    action: str,
    page: str,
    target: str,
    *,
    resource: str | None = None,
) -> TableWorkflowDefinition:
    intent = (
        ActionIntent(action, page, target, approved_resource=resource, input_kind=InputKind.CLICK)
        if resource
        else ActionIntent(action, page, target, input_kind=InputKind.CLICK)
    )
    return _definition(
        task_id,
        {"home": Transition(intent, f"{target}.done", "done")},
        complete_markers={"done": (f"{target}.done",)},
        already_markers={"home": (f"{target}.done",)},
    )


class HeroDispatchDailyDefinition(TableWorkflowDefinition):
    """Claim and refill the top visible dispatch slot, matching the original task."""

    def recognizers(self, state: str) -> tuple[str, ...]:
        values = set(super().recognizers(state))
        if state == "inspect":
            values.update(
                {
                    "hero.first_task_claimable",
                    "hero.first_task_dispatchable",
                    "hero.first_task_in_progress",
                    "hero.all_dispatched_waiting",
                    "hero.all_completed",
                    "hero.no_dispatch_tasks",
                    "hero.dispatch.close",
                }
            )
        return tuple(sorted(values))

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        if snapshot.state != "inspect":
            return super().decide(snapshot, counters)
        evidence = snapshot.evidence
        if evidence is None or evidence.page_hits.get("hero.dispatch.page", 0) != 1:
            return Decision.finish(TaskStatus.FAILED)
        # A row marked ``完成派遣`` is still actionable even when the header
        # counter is stale or already renders ``已完成:9``.  Inspect the
        # visible row first; only an explicit no-claimable all-complete
        # marker is a terminal boundary.
        if evidence.target_hits.get("hero.first_task_claimable", 0) == 1:
            return Decision.act(self.transitions["inspect_claimable"])
        if evidence.target_hits.get("hero.all_dispatched_waiting", 0) == 1:
            # A fresh same-frame 9/9 + completed:0 marker proves all slots are
            # occupied and none can be claimed.  Keep this after claimable so
            # a real reward always wins, and finish without dispatch input.
            return Decision.finish(TaskStatus.ALREADY_COMPLETE)
        if evidence.target_hits.get("hero.all_completed", 0) == 1:
            if counters.get("dispatch_team", 0) == 0:
                # The explicit all-completed marker is the daily terminal
                # boundary.  No dispatch click is needed in this run.
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            # A live account can have no claimable/dispatchable row while all
            # nine daily dispatches are already complete.  Treat that as a
            # successful no-op and use the same bounded close action as the
            # normal in-progress path.
            return Decision.act(self.transitions["close_completed_dispatch"])
        if evidence.target_hits.get("hero.no_dispatch_tasks", 0) == 1:
            # The page explicitly reports no assigned or completed row. This
            # is a bounded no-op state, not permission to click the empty map
            # or to spin until the parent timeout.
            return Decision.finish(TaskStatus.ALREADY_COMPLETE)
        # OCR for ``派遣`` can be a substring of the live ``派遣中`` label on
        # some Android frames.  Prefer the explicit countdown/in-progress
        # proof so a running team is never mistaken for an empty slot.
        if evidence.target_hits.get("hero.first_task_in_progress", 0) == 1:
            if counters.get("dispatch_team", 0) == 0:
                # An explicit in-progress/countdown row proves the daily
                # dispatch state is already satisfied; do not dispatch a
                # second team concurrently.
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            return Decision.act(self.transitions["close_dispatch"])
        if evidence.target_hits.get("hero.first_task_dispatchable", 0) == 1:
            if counters.get("dispatch_team", 0) >= 6:
                return Decision.act(self.transitions["close_dispatch"])
            return Decision.act(self.transitions["inspect"])
        return Decision.finish(TaskStatus.FAILED)


HERO_DISPATCH_DAILY_DEFINITION = HeroDispatchDailyDefinition(
    task_id="HERO_DISPATCH_DAILY",
    initial_state="home",
    transitions={
        "home": _tr(
            "open_painting_scroll",
            "home.painting_scroll_text",
            "painting_scroll_entry",
            "painting_page",
            "painting",
        ),
        "painting": _tr(
            "open_hero_dispatch",
            "painting_page",
            "hero_dispatch_entry",
            "hero.dispatch.page",
            "inspect",
        ),
        "inspect": _tr(
            "select_first_visible_dispatch",
            "hero.dispatch.page",
            "hero.first_task_dispatchable",
            "hero.smart_configure",
            "configure",
        ),
        "inspect_claimable": _tr(
            "select_first_visible_dispatch",
            "hero.dispatch.page",
            "hero.first_task_claimable",
            "hero.claim_button",
            "claim",
        ),
        "claim": _tr(
            "claim_first_dispatch",
            "hero.dispatch.page",
            "hero.claim_button",
            "hero.reward_popup",
            "reward_popup",
        ),
        "reward_popup": _tr(
            "close_reward_popup",
            "hero.reward_popup",
            "hero.reward_popup",
            "hero.dispatch.page",
            "inspect",
        ),
        "configure": _tr(
            "smart_configure_team",
            "hero.dispatch.page",
            "hero.smart_configure",
            "hero.dispatch_button",
            "send",
        ),
        "send": _tr(
            "dispatch_team",
            "hero.dispatch.page",
            "hero.dispatch_button",
            "hero.first_task_in_progress",
            "inspect",
        ),
        "close_dispatch": _tr(
            "close_hero_dispatch",
            "hero.dispatch.page",
            "hero.dispatch.close",
            "painting_page",
            "close_painting",
        ),
        "close_completed_dispatch": _tr(
            "close_hero_dispatch",
            "hero.dispatch.page",
            "hero.all_completed",
            "painting_page",
            "close_painting",
        ),
        "close_painting": _tr(
            "close_hero_dispatch_painting",
            "painting_page",
            "hero.painting.close",
            "home.painting_scroll_text",
            "home_done",
        ),
    },
    complete_markers={"home_done": ("home.painting_scroll_text",)},
)

BUY_TEA_DAILY_DEFINITION = _definition(
    "BUY_TEA_DAILY",
    {
        "home": _tr(
            "open_painting_scroll", "home", "painting_scroll_entry", "painting_page", "painting"
        ),
        "painting": _tr(
            "select_yanwu_world", "painting_page", "yanwu_world_tab", "yanwu_world_page", "shop"
        ),
        "shop": _tr(
            "open_universal_shop",
            "yanwu_world_page",
            "universal_shop_entry",
            "universal_shop_page",
            "tea",
        ),
        "tea_scroll": _tr(
            "scroll_tea_list",
            "universal_shop_page",
            "universal_shop_page",
            "universal_shop_page",
            "tea_scrolled",
            input_kind=InputKind.SWIPE,
        ),
        "tea": _tr(
            "open_tea_tab",
            "universal_shop_page",
            "tea_item",
            "tea_selected",
            "tea_selected",
        ),
        "tea_scrolled": _tr(
            "open_tea_tab",
            "universal_shop_page",
            "tea_item_scrolled",
            "tea_selected",
            "tea_selected",
        ),
        "tea_selected": _tr(
            "open_tea_purchase",
            "universal_shop_page",
            "tea_selected",
            "quantity_panel",
            "quantity_panel",
        ),
        "quantity_panel": _tr(
            "set_tea_quantity_max",
            "quantity_panel",
            "tea.max_quantity",
            "quantity_panel",
            "quantity_panel_selected",
        ),
        "quantity_panel_selected": _resource_transition(
            "buy_tea",
            "quantity_panel",
            "buy_confirm",
            "文",
            "done",
            "tea_purchase_result",
        ),
    },
    complete_markers={"done": ("tea_purchase_result",)},
    text_requirements={"buy_confirm": ("500文",)},
    already_markers={
        "tea": ("tea_sold_out",),
        "tea_scrolled": ("tea_sold_out",),
        # The game keeps the detail view open after selecting a tea card even
        # when its daily quota is already exhausted.  Treat that same
        # sold-out/quota evidence as a terminal no-op before opening the
        # purchase controls.
        "tea_selected": ("tea_sold_out",),
    },
)

def _click(
    action: str,
    page: str,
    target: str,
    post: str,
    next_state: str,
    *,
    resource: str | None = None,
) -> Transition:
    return Transition(
        ActionIntent(
            action,
            page,
            target,
            approved_resource=resource,
            input_kind=InputKind.CLICK,
        ),
        post,
        next_state,
    )


class SpendCondensateDailyDefinition(TableWorkflowDefinition):
    """Buy both regional currencies, recovering cleanly after a partial run."""

    def recognizers(self, state: str) -> tuple[str, ...]:
        values = set(super().recognizers(state))
        if state == "home":
            # A failed/paused run can leave either regional purchase panel or
            # map open. Recognize those stable pages from the fresh first
            # frame so retry resumes in place instead of requiring manual X
            # clicks back to the home screen.
            values.update(
                {
                    "painting_page",
                    "yanwu_world_page",
                    "yanwu_currency_shop",
                    "yanwu_currency_purchase",
                    "yanwu_currency_purchase_target",
                    "yanwu_currency_sold_out",
                    "yunzhou_world_page",
                    "yunzhou_currency_shop",
                    "yunzhou_currency_purchase",
                    "yunzhou_currency_purchase_target",
                    "yunzhou_currency_sold_out",
                    "凝晶",
                }
            )
        elif state == "purchase":
            values.add("yanwu_currency_sold_out")
        elif state == "yunzhou_purchase":
            values.add("yunzhou_currency_sold_out")
        return tuple(sorted(values))

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        evidence = snapshot.evidence
        if evidence is not None:
            if snapshot.state == "home":
                if evidence.page_hits.get("yanwu_currency_purchase", 0) == 1:
                    if evidence.target_hits.get("yanwu_currency_sold_out", 0) == 1:
                        return Decision.act(self.transitions["yanwu_sold_out"])
                    return Decision.act(self.transitions["purchase"])
                if evidence.page_hits.get("yunzhou_currency_purchase", 0) == 1:
                    if evidence.target_hits.get("yunzhou_currency_sold_out", 0) == 1:
                        return Decision.act(self.transitions["yunzhou_sold_out"])
                    return Decision.act(self.transitions["yunzhou_purchase"])
                if evidence.page_hits.get("yunzhou_world_page", 0) == 1:
                    return Decision.act(self.transitions["yunzhou"])
                if evidence.page_hits.get("yanwu_world_page", 0) == 1:
                    return Decision.act(self.transitions["yanwu"])
                if evidence.page_hits.get("painting_page", 0) == 1:
                    return Decision.act(self.transitions["painting"])
            if (
                snapshot.state == "purchase"
                and evidence.target_hits.get("yanwu_currency_sold_out", 0) == 1
            ):
                return Decision.act(self.transitions["yanwu_sold_out"])
            if (
                snapshot.state == "yunzhou_purchase"
                and evidence.target_hits.get("yunzhou_currency_sold_out", 0) == 1
            ):
                return Decision.act(self.transitions["yunzhou_sold_out"])
        return super().decide(snapshot, counters)


SPEND_CONDENSATE_DAILY_DEFINITION = SpendCondensateDailyDefinition(
    task_id="SPEND_CONDENSATE_DAILY",
    initial_state="home",
    transitions={
        "home": _click(
            "open_painting_scroll",
            "home.painting_scroll_text",
            "painting_scroll_entry",
            "painting_page",
            "painting",
        ),
        "painting": _click(
            "select_yanwu_world", "painting_page", "yanwu_world_tab", "yanwu_world_page", "yanwu"
        ),
        "yanwu": _click(
            "open_yanwu_currency_purchase",
            "yanwu_world_page",
            "yanwu_currency_shop",
            "yanwu_currency_purchase",
            "purchase",
        ),
        "purchase": _click(
            "buy_yanwu_currency_max",
            "yanwu_currency_purchase",
            "yanwu_currency_purchase_target",
            "yanwu_currency_purchase_target.done",
            "yanwu_reward",
            resource="凝晶",
        ),
        "yanwu_sold_out": _click(
            "close_yanwu_currency_purchase",
            "yanwu_currency_purchase",
            "yanwu_currency_sold_out",
            "yanwu_world_page",
            "yanwu_bought",
        ),
        "yanwu_reward": _click(
            "dismiss_yanwu_reward_popup",
            "yanwu_currency_purchase_target.done",
            "yanwu_currency_purchase_target.done",
            "yanwu_world_page",
            "yanwu_bought",
        ),
        "yanwu_bought": _click(
            "select_yunzhou",
            "yanwu_world_page",
            "yunzhou_world_tab",
            "yunzhou_world_page",
            "yunzhou",
        ),
        "yunzhou": _click(
            "open_yunzhou_currency_purchase",
            "yunzhou_world_page",
            "yunzhou_currency_shop",
            "yunzhou_currency_purchase",
            "yunzhou_purchase",
        ),
        "yunzhou_purchase": _click(
            "buy_yunzhou_currency_max",
            "yunzhou_currency_purchase",
            "yunzhou_currency_purchase_target",
            "yunzhou_currency_purchase_target.done",
            "yunzhou_reward",
            resource="凝晶",
        ),
        "yunzhou_sold_out": _click(
            "close_yunzhou_currency_purchase",
            "yunzhou_currency_purchase",
            "yunzhou_currency_sold_out",
            "yunzhou_world_page",
            "done",
        ),
        "yunzhou_reward": _click(
            "dismiss_yunzhou_reward_popup",
            "yunzhou_currency_purchase_target.done",
            "yunzhou_currency_purchase_target.done",
            "yunzhou_world_page",
            "done",
        ),
    },
    complete_markers={"done": ("yunzhou_world_page",)},
    already_markers={},
)


MARTIAL_STUDY_BREAKTHROUGH_DAILY_DEFINITION = _definition(
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    {
        "home": _tr(
            "open_function_panel",
            "home",
            "function_panel.open",
            "function_panel.page",
            "function_panel",
        ),
        "function_panel": _tr(
            "open_martial_study",
            "function_panel.page",
            "martial_study_entry",
            "martial.page",
            "martial",
        ),
        "martial": _tr(
            "claim_success_card",
            "martial.page",
            "martial_success_card",
            "martial.success_result",
            "reward_popup",
        ),
        "reward_popup": _tr(
            "close_reward_popup",
            "martial.success_result",
            "martial_result_close",
            "martial.page",
            "martial_after_reward",
        ),
        "martial_after_reward": _tr(
            "close_martial_page",
            "martial.page",
            "martial_close",
            "martial.page.closed",
            "done",
        ),
    },
    complete_markers={"done": ("martial.page.closed",)},
)


EAT_STAMINA_FOOD_DAILY_DEFINITION = _definition(
    "EAT_STAMINA_FOOD_DAILY",
    {
        # The 1.6 client removed 背包 from the 功能面板 grid.  The live
        # resource/inventory page is now opened by the left-side 资源 shortcut
        # on the main HUD; the adapter authorizes that calibrated shortcut
        # only after the same-frame home HUD has been recognized.
        "home": _click(
            "open_resource_page", "home", "resource_entry", "bag_page", "bag"
        ),
        "bag": _click(
            "open_food_category", "bag_page", "food_category", "consumables_page", "food"
        ),
        "food": _click(
            "inspect_food_candidate",
            "consumables_page",
            "food_candidate",
            "food_detail_changed",
            "food_detail",
        ),
        "food_detail": _click(
            "eat_longjing_shrimp",
            "food_detail_changed",
            "longjing_shrimp_eat_target",
            "food_use_result",
            "food",
            resource="龙井虾仁",
        ),
        "confirm_food_buff_replace": _click(
            "confirm_food_buff_replace",
            "food_buff_replace_prompt",
            "food_buff_replace_confirm",
            "food_use_result",
            "food",
        ),
    },
    text_requirements={"longjing_shrimp_eat_target": ("使用",)},
)


DUNGEON_SWEEP_DAILY_DEFINITION = _definition(
    "DUNGEON_SWEEP_DAILY",
    {
        # 副本 is a direct top-row home entry, not a function-panel item.
        "home": _click(
            "open_dungeon", "home", "dungeon_entry", "dungeon_page", "dungeon"
        ),
        # 风雪神道 is visible on the initial副本 page; select it directly.
        "dungeon": _click(
            "select_yanwangling",
            "dungeon_page",
            "yanwangling_master_selected",
            "yanwangling_title",
            "selected",
        ),
        "selected": _click(
            "open_sweep_panel", "yanwangling_title", "sweep_target", "sweep_panel_page", "sweep"
        ),
        "sweep": _click(
            "assign_sweep_ticket",
            "sweep_panel_page",
            "ticket_plus",
            "assigned_ticket_counter_changed",
            "sweep_ready",
        ),
        "sweep_ready": _click(
            "start_yanwangling_master_sweep",
            "sweep_panel_page",
            "start_sweep",
            "normal_sweep_confirm_page",
            "confirm",
        ),
        "confirm": _click(
            "confirm_yanwangling_master_sweep",
            "normal_sweep_confirm_page",
            "confirm_sweep",
            "expected_sweep_result",
            "result",
        ),
        # The sweep is complete as soon as the normal reward overlay closes.
        # Task-boundary cleanup can leave the dungeon later; it must not turn
        # a consumed, successful sweep into a failed business result.
        "result": _click(
            "dismiss_sweep_result",
            "expected_sweep_result",
            "sweep_result_close",
            "dungeon_page",
            "done",
        ),
    },
    complete_markers={"done": ("dungeon_page",)},
    # ``ticket_plus`` is an actionable control on the sweep panel.  Its
    # presence means tickets are available, never that the daily objective is
    # complete.  In particular, the normal dungeon page also exposes the
    # ticket counter, so using ``ticket_plus.done`` here caused the workflow to
    # stop immediately after opening the page.  Completion is established only
    # by the post-confirmation sweep result below.
)


class ShadowRuinsDailyDefinition:
    """Bounded Shadow flow with card, checkbox, result, and home evidence."""

    task_id = "SHADOW_RUINS_DAILY"
    initial_state = "home"

    def recognizers(self, state: str) -> tuple[str, ...]:
        values = {
            "home",
            "painting_page",
            "painting_scroll_entry",
            "shadow_page",
            "shadow_card_list",
            "shadow_active_card",
            "shadow_popup",
            "shadow_go",
            "shadow_stage_page",
            "shadow_formation_page",
            "shadow_battle_target",
            "shadow_skip_prepare",
            "shadow_skip_prepare_checked",
            "shadow_exploration_page",
            "shadow_foreground_left",
            "shadow_battle_result",
            "shadow_battle_failure",
            "shadow_reward_popup",
            "shadow_final_prompt",
            "shadow_final_confirm",
            "shadow_close",
            "shadow_challenge.done",
            "unknown_dialog",
            "safety.paid",
            "safety.verification",
        }
        return tuple(sorted(values))

    @staticmethod
    def _action(
        action: str,
        page: str,
        target: str,
        postcondition: str,
        next_state: str,
        *,
        alternatives: tuple[str, ...] = (),
    ) -> Decision:
        return Decision.act(
            _tr(
                action,
                page,
                target,
                postcondition,
                next_state,
                postcondition_alternatives=alternatives,
            )
        )

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        evidence = snapshot.evidence
        if evidence is None:
            return Decision.finish(TaskStatus.FAILED)

        if any(
            evidence.danger_hits.get(marker, 0) == 1
            or evidence.target_hits.get(marker, 0) == 1
            for marker in ("unknown_dialog", "safety.paid", "safety.verification")
        ):
            return Decision.finish(TaskStatus.FAILED)

        if snapshot.state == "completed":
            return Decision.finish(TaskStatus.COMPLETED)
        if snapshot.state == "failed":
            return Decision.finish(TaskStatus.FAILED)

        if evidence.target_hits.get("shadow_challenge.done", 0) == 1:
            return Decision.finish(TaskStatus.ALREADY_COMPLETE)

        if evidence.page_hits.get("shadow_final_prompt", 0) == 1 and evidence.target_hits.get(
            "shadow_final_confirm", 0
        ) == 1:
            return self._action(
                "confirm_shadow_completion",
                "shadow_final_prompt",
                "shadow_final_confirm",
                "shadow_reward_popup",
                "reward",
                alternatives=("shadow_exploration_page", "home"),
            )

        if evidence.page_hits.get("shadow_battle_failure", 0) == 1:
            return self._action(
                "dismiss_shadow_battle_failure",
                "shadow_battle_failure",
                "shadow_battle_failure",
                "shadow_exploration_page",
                "failed",
            )

        if evidence.page_hits.get("shadow_battle_result", 0) == 1:
            return self._action(
                "dismiss_shadow_battle_result",
                "shadow_battle_result",
                "shadow_battle_result",
                "shadow_reward_popup",
                "reward",
                alternatives=("shadow_stage_page",),
            )

        if evidence.page_hits.get("shadow_reward_popup", 0) == 1:
            final_reward = counters.get("confirm_shadow_completion", 0) >= 1
            return self._action(
                "dismiss_shadow_reward_popup",
                "shadow_reward_popup",
                "shadow_reward_popup",
                "home" if final_reward else "shadow_exploration_page",
                "home" if final_reward else "exploration",
            )

        if evidence.page_hits.get("shadow_stage_page", 0) == 1 or evidence.page_hits.get(
            "shadow_formation_page", 0
        ) == 1:
            if evidence.target_hits.get("shadow_skip_prepare", 0) == 1 and evidence.target_hits.get(
                "shadow_skip_prepare_checked", 0
            ) != 1:
                return self._action(
                    "enable_shadow_skip_prepare",
                    "shadow_stage_page",
                    "shadow_skip_prepare",
                    "shadow_skip_prepare_checked",
                    "stage",
                )
            if evidence.target_hits.get("shadow_battle_target", 0) == 1:
                return self._action(
                    "challenge_shadow_stage",
                    "shadow_formation_page",
                    "shadow_battle_target",
                    "shadow_battle_result",
                    "battle_result",
                    alternatives=("shadow_battle_failure",),
                )

        if evidence.page_hits.get("shadow_page", 0) == 1:
            if evidence.target_hits.get("shadow_active_card", 0) == 1:
                if counters.get("select_active_shadow_card", 0) >= 3:
                    if evidence.target_hits.get("shadow_close", 0) == 1:
                        return self._action(
                            "close_shadow_page",
                            "shadow_page",
                            "shadow_close",
                            "home",
                            "completed",
                        )
                    return Decision.finish(TaskStatus.COMPLETED)
                return self._action(
                    "select_active_shadow_card",
                    "shadow_card_list",
                    "shadow_active_card",
                    "shadow_popup",
                    "popup",
                )
            if evidence.target_hits.get("shadow_close", 0) == 1:
                return self._action(
                    "close_shadow_page",
                    "shadow_page",
                    "shadow_close",
                    "home",
                    "completed",
                )
            return Decision.finish(TaskStatus.COMPLETED)

        if evidence.page_hits.get("shadow_popup", 0) == 1 and evidence.target_hits.get(
            "shadow_go", 0
        ) == 1:
            return self._action(
                "enter_shadow_stage",
                "shadow_popup",
                "shadow_go",
                "shadow_stage_page",
                "stage",
            )

        if evidence.page_hits.get("shadow_exploration_page", 0) == 1:
            if evidence.target_hits.get("shadow_final_prompt", 0) == 1 and evidence.target_hits.get(
                "shadow_final_confirm", 0
            ) == 1:
                return self._action(
                    "confirm_shadow_completion",
                    "shadow_final_prompt",
                    "shadow_final_confirm",
                    "shadow_reward_popup",
                    "reward",
                )
            if evidence.target_hits.get("shadow_foreground_left", 0) == 1:
                if counters.get("advance_shadow_foreground_triplet", 0) >= 3:
                    if evidence.target_hits.get("shadow_close", 0) == 1:
                        return self._action(
                            "close_shadow_page",
                            "shadow_exploration_page",
                            "shadow_close",
                            "home",
                            "completed",
                        )
                    return Decision.finish(TaskStatus.COMPLETED)
                return self._action(
                    "advance_shadow_foreground_triplet",
                    "shadow_exploration_page",
                    "shadow_foreground_left",
                    "shadow_exploration_page",
                    "exploration",
                )
            if evidence.target_hits.get("shadow_close", 0) == 1:
                return self._action(
                    "close_shadow_page",
                    "shadow_exploration_page",
                    "shadow_close",
                    "home",
                    "completed",
                )
            return Decision.finish(TaskStatus.COMPLETED)

        if evidence.page_hits.get("home", 0) == 1 and evidence.target_hits.get(
            "painting_scroll_entry", 0
        ) == 1:
            return self._action(
                "open_painting_scroll",
                "home",
                "painting_scroll_entry",
                "painting_page",
                "painting",
            )
        if evidence.page_hits.get("painting_page", 0) == 1 and evidence.target_hits.get(
            "shadow_challenge", 0
        ) == 1:
            return self._action(
                "open_shadow",
                "painting_page",
                "shadow_challenge",
                "shadow_page",
                "shadow_page",
            )
        return Decision.finish(TaskStatus.FAILED)


SHADOW_RUINS_DAILY_DEFINITION = ShadowRuinsDailyDefinition()


RING_MAX_ATTEMPTS = 12
RING_SCORE_THRESHOLD = 5000
_RING_SCORE = re.compile(
    r"(?:擂台积分|当前积分|积分)\s*[:：]?\s*(\d{1,5})|(?<!\d)(\d{1,5})\s*分"
)
_RING_LABELED_ATTEMPTS = re.compile(
    r"(?:剩余(?:挑战)?次数|挑战次数|次数)\s*[:：]?\s*(\d{1,2})\s*/\s*12"
)
_RING_GENERIC_ATTEMPTS = re.compile(r"(?<![\d/])(\d{1,2})\s*/\s*12(?!\d)")


def _ring_hit(snapshot: StateSnapshot, marker: str) -> bool:
    evidence = snapshot.evidence
    return evidence is not None and evidence.target_hits.get(marker, 0) == 1


def _ring_text(snapshot: StateSnapshot) -> str:
    evidence = snapshot.evidence
    return "" if evidence is None else "".join(evidence.texts)


def _ring_score(snapshot: StateSnapshot) -> int | None:
    if not (_ring_hit(snapshot, "ring_score_label") and _ring_hit(snapshot, "ring_score_value")):
        return None
    match = _RING_SCORE.search(_ring_text(snapshot))
    if match is not None:
        value = match.group(1) or match.group(2)
        if value is not None:
            return int(value)
    return None


def _ring_remaining_attempts(snapshot: StateSnapshot) -> int | None:
    """Return the visible *remaining* daily attempts, never an action count.

    The updated client can render a labelled counter (``剩余次数 11/12``)
    or only the compact ``11/12`` capsule.  Prefer the labelled form so a
    separate ticket counter cannot be mistaken for arena attempts.  A
    dedicated exhausted marker is an equally strong proof of ``0``.
    """

    if _ring_hit(snapshot, "ring_attempts_exhausted"):
        return 0
    text = _ring_text(snapshot)
    for pattern in (_RING_LABELED_ATTEMPTS, _RING_GENERIC_ATTEMPTS):
        match = pattern.search(text)
        if match is None:
            continue
        value = int(match.group(1))
        if 0 <= value <= RING_MAX_ATTEMPTS:
            return value
    return None


def _ring_master_mode(snapshot: StateSnapshot) -> bool:
    # After the current client update the numeric arena score disappears once
    # the account enters the master tier.  The explicit 大师赛 marker is the
    # authoritative >=5000 proof; rank text is optional decoration.
    return _ring_hit(snapshot, "ring_master_mode")


def _ring_sweep_eligible(snapshot: StateSnapshot) -> bool:
    master = _ring_master_mode(snapshot)
    score = _ring_score(snapshot)
    return master or (score is not None and score >= RING_SCORE_THRESHOLD)


def _ring_attempts_exhausted(snapshot: StateSnapshot) -> bool:
    return _ring_remaining_attempts(snapshot) == 0


def _ring_transition(
    action: str,
    page: str,
    target: str,
    postcondition: str,
    next_state: str,
    *,
    resource: str | None = None,
    postcondition_alternatives: tuple[str, ...] = (),
) -> Transition:
    return Transition(
        ActionIntent(
            action,
            page,
            target,
            approved_resource=resource,
            input_kind=InputKind.CLICK,
        ),
        postcondition,
        next_state,
        postcondition_alternatives=postcondition_alternatives,
    )


def _ring_wait_for_battle_transition(
    page_marker: str = "ring_fight_page",
) -> Transition:
    """Poll an arena matching/battle surface without sending another input."""

    return Transition(
        ActionIntent(
            "wait_ring_battle",
            page_marker,
            "ring_battle_loading",
            input_kind=InputKind.NONE,
        ),
        "ring_battle_loading",
        "fight",
        postcondition_alternatives=("ring_fight_page",),
    )


class RingChallengeDailyDefinition:
    """Evidence-gated arena flow with a threshold-aware manual/sweep split.

    Below 5000 points the task manually challenges opponents.  Once the
    client exposes the explicit 大师赛 marker (or a visible score >=5000), the
    legacy sweep branch becomes eligible.  Missing score text is never treated
    as a threshold proof.
    """

    task_id = "RING_CHALLENGE_DAILY"
    initial_state = "home"

    _danger_markers = (
        "unknown_dialog",
        "safety.paid",
        "safety.verification",
        "ring_unknown_currency",
    )

    def recognizers(self, state: str) -> tuple[str, ...]:
        common = (*self._danger_markers,)
        values: dict[str, tuple[str, ...]] = {
            "home": (
                "home",
                "function_panel.open",
                "daily.page",
                "daily.reward_popup",
                "daily.reward_popup_close",
                "ring_daily_task_text",
                "ring_daily_row",
                "ring_daily_done",
                "ring_page",
                "ring_start",
                "ring_master_mode",
                "ring_master_rank",
                "ring_score_label",
                "ring_score_value",
                "ring_attempts",
                "ring_challenge_target.done",
                "ring_fight_target",
                "ring_sweep",
                "ring_sweep_prompt",
                "ring_sweep_confirm",
                "ring_sweep_result",
                "ring_fight_page",
                "ring_battle_loading",
                "ring_battle_prepare_page",
                "ring_ready",
                "ring_skip",
                "ring_battle_result",
                "ring_result_close",
                "ring_opponent_page",
                "ring_opponent_close",
                "ring_match_setup_page",
                "ring_match_start",
                "ring_attempts_exhausted",
                "ring_reward_popup",
                "擂台券",
                *common,
            ),
            "panel": ("function_panel.page", "daily.entry", *common),
            "daily": (
                "daily.page",
                "daily.reward_popup",
                "daily.reward_popup_close",
                "ring_daily_task_text",
                "ring_daily_row",
                "ring_daily_done",
                *common,
            ),
            "ring": (
                "ring_page",
                "daily.reward_popup",
                "daily.reward_popup_close",
                "ring_entry",
                "ring_start",
                "ring_master_mode",
                "ring_master_rank",
                "ring_score_label",
                "ring_score_value",
                "ring_attempts",
                "ring_attempts_exhausted",
                "ring_challenge_target.done",
                "ring_sweep_prompt",
                "ring_sweep_confirm",
                "ring_sweep_result",
                "ring_fight_page",
                "ring_battle_loading",
                "ring_battle_prepare_page",
                "ring_ready",
                "ring_skip",
                "ring_battle_result",
                "ring_result_close",
                "ring_match_setup_page",
                "ring_match_start",
                *common,
            ),
            "opponents_sweep": (
                "ring_opponent_page",
                "ring_sweep",
                "ring_challenge_target.done",
                "ring_attempts_exhausted",
                "ring_opponent_close",
                "ring_sweep_prompt",
                "ring_sweep_confirm",
                "ring_sweep_result",
                "ring_result_close",
                "擂台券",
                *common,
            ),
            "opponents_fight": (
                "ring_opponent_page",
                "ring_fight_target",
                "ring_match_setup_page",
                "ring_match_start",
                "ring_attempts",
                "ring_attempts_exhausted",
                "ring_opponent_close",
                "ring_challenge_target.done",
                "ring_fight_page",
                "ring_battle_loading",
                "ring_battle_prepare_page",
                "ring_ready",
                "ring_skip",
                "ring_battle_result",
                "ring_result_close",
                "ring_reward_popup",
                *common,
            ),
            "fight": (
                "ring_fight_page",
                "ring_battle_loading",
                "ring_battle_prepare_page",
                "ring_ready",
                "ring_skip",
                "ring_battle_result",
                "ring_result_close",
                "ring_reward_popup",
                *common,
            ),
            "fight_result": (
                "ring_battle_result",
                "ring_result_close",
                *common,
            ),
            "sweep_interstitial": (
                "ring_sweep_prompt",
                "ring_sweep_confirm",
                "ring_sweep_result",
                "ring_result_close",
                "擂台券",
                *common,
            ),
            "sweep_result": (
                "ring_sweep_result",
                "ring_challenge_target.done",
                "ring_result_close",
                *common,
            ),
            "ring_after": ("ring_page", "ring_page_close", *common),
            # Closing the ring page already proves the task boundary. Keep a
            # distinct terminal state so a dynamic world-map frame cannot be
            # mistaken for the initial daily-list state on the next loop.
            "done": ("home", *common),
            "daily_verify": ("daily.page", "ring_daily_done", *common),
        }
        try:
            return values[state]
        except KeyError as exc:
            raise ValueError(f"unknown ring workflow state: {state}") from exc

    def _danger_transition(
        self,
        state: str,
        counters: Mapping[str, int],
        snapshot: StateSnapshot | None = None,
    ) -> Transition | None:
        if state == "home":
            return _ring_transition(
                "open_function_panel", "home", "function_panel.open", "function_panel.page", "panel"
            )
        if state == "panel":
            return _ring_transition(
                "open_daily_tasks", "function_panel.page", "daily.entry", "daily.page", "daily"
            )
        if state == "daily":
            return _ring_transition(
                "open_ring_challenge",
                "daily.page",
                "ring_daily_row",
                "ring_page",
                "ring",
                postcondition_alternatives=("daily.reward_popup",),
            )
        if state == "ring":
            return _ring_transition(
                "open_ring_attempt_mode",
                "ring_page",
                "ring_start",
                "ring_opponent_page",
                "opponents_fight",
                postcondition_alternatives=(
                    "ring_match_setup_page",
                    "ring_battle_prepare_page",
                    "ring_fight_page",
                    "ring_battle_loading",
                ),
            )
        if (
            state == "opponents_fight"
            and snapshot is not None
            and _ring_hit(snapshot, "ring_match_setup_page")
        ):
            if _ring_hit(snapshot, "ring_match_start"):
                return _ring_transition(
                    "start_ring_matching",
                    "ring_match_setup_page",
                    "ring_match_start",
                    "ring_battle_loading",
                    "fight",
                    resource="擂台券",
                    postcondition_alternatives=(
                        "ring_battle_prepare_page",
                        "ring_fight_page",
                        "ring_battle_result",
                        "ring_reward_popup",
                    ),
                )
            return None
        if state in {"opponents_sweep", "sweep_interstitial", "sweep_result"}:
            # Never guess a consumptive sweep transition while recovering
            # from a danger marker; the normal state decision must prove the
            # explicit master-tier surface first.
            return None
        if state == "opponents_fight":
            return _ring_transition(
                "fight_ring_opponent",
                "ring_opponent_page",
                "ring_fight_target",
                "ring_battle_prepare_page",
                "fight",
                resource="擂台券",
                postcondition_alternatives=("ring_fight_page",),
            )
        if state == "fight":
            return _ring_transition(
                "skip_ring_battle",
                "ring_fight_page",
                "ring_skip",
                "ring_battle_result",
                "fight_result",
            )
        if state == "fight_result":
            return _ring_transition(
                "dismiss_ring_result",
                "ring_battle_result",
                "ring_result_close",
                "ring_opponent_page",
                "opponents_fight",
            )
        if state == "ring_after":
            return _ring_transition(
                "close_ring_page", "ring_page", "ring_page_close", "home", "home"
            )
        return None

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        evidence = snapshot.evidence
        if evidence is None:
            return Decision.finish(TaskStatus.FAILED)
        state = snapshot.state
        if state == "done":
            return Decision.finish(
                TaskStatus.COMPLETED
                if _ring_hit(snapshot, "home")
                else TaskStatus.FAILED
            )
        if state == "home":
            if _ring_hit(snapshot, "daily.reward_popup"):
                if _ring_hit(snapshot, "daily.reward_popup_close"):
                    return Decision.act(
                        _ring_transition(
                            "close_reward_popup",
                            "daily.reward_popup",
                            "daily.reward_popup_close",
                            "daily.page",
                            "daily",
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            # A failed run may be resumed while a result sheet is still
            # visible.  Treat a confirmed sweep result as the terminal
            # business proof; never navigate back into the daily row and
            # accidentally re-run it.
            if _ring_hit(snapshot, "ring_sweep_result"):
                return Decision.finish(
                    TaskStatus.COMPLETED
                    if counters.get("confirm_ring_sweep", 0) > 0
                    else TaskStatus.ALREADY_COMPLETE
                )
            if any(
                _ring_hit(snapshot, marker)
                for marker in (
                    "ring_reward_popup",
                    "ring_battle_result",
                    "ring_battle_loading",
                    "ring_battle_prepare_page",
                    "ring_fight_page",
                    "ring_skip",
                )
            ):
                return self.decide(replace(snapshot, state="fight"), counters)
            if _ring_hit(snapshot, "ring_match_setup_page"):
                return self.decide(replace(snapshot, state="opponents_fight"), counters)
            if _ring_hit(snapshot, "ring_sweep_prompt"):
                if _ring_hit(snapshot, "ring_sweep_confirm"):
                    return Decision.act(
                        _ring_transition(
                            "confirm_ring_sweep",
                            "ring_sweep_prompt",
                            "ring_sweep_confirm",
                            "ring_sweep_result",
                            "sweep_result",
                            resource="擂台券",
                        )
                    )
                if _ring_hit(snapshot, "ring_sweep_result") and _ring_hit(
                    snapshot, "ring_result_close"
                ):
                    return Decision.act(
                        _ring_transition(
                            "dismiss_ring_result",
                            "ring_sweep_result",
                            "ring_result_close",
                            "ring_opponent_page",
                            "opponents_sweep",
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            if _ring_hit(snapshot, "ring_opponent_page"):
                if _ring_hit(snapshot, "ring_sweep") and _ring_hit(
                    snapshot, "ring_fight_target"
                ):
                    # Conflicting continuation affordances are not enough
                    # to choose a consumptive path during recovery.
                    return Decision.finish(TaskStatus.FAILED)
                if _ring_hit(snapshot, "ring_sweep") and not _ring_hit(
                    snapshot, "ring_fight_target"
                ):
                    # A resumed opponent surface can outlive the state that
                    # led to it.  A visible sweep control with no fight-card
                    # target is the continuation proof for the already-gated
                    # master branch; it is not inferred from a missing score.
                    return self.decide(replace(snapshot, state="opponents_sweep"), counters)
                if _ring_attempts_exhausted(snapshot) and _ring_hit(
                    snapshot, "ring_opponent_close"
                ):
                    return Decision.act(
                        _ring_transition(
                            "close_ring_opponents",
                            "ring_opponent_page",
                            "ring_opponent_close",
                            "ring_page",
                            "ring_after",
                        )
                    )
                # Recovery starts with the canonical home state even when
                # the UI is already on the opponent list.  Re-enter the
                # normal fight decision so a visible 11/12 counter causes
                # the remaining eleven attempts to be performed.
                return self.decide(replace(snapshot, state="opponents_fight"), counters)
            if _ring_hit(snapshot, "daily.page"):
                if (
                    _ring_hit(snapshot, "ring_daily_done")
                    or (
                        _ring_hit(snapshot, "ring_daily_task_text")
                        and _ring_hit(snapshot, "ring_daily_row")
                    )
                ):
                    return Decision.act(
                        _ring_transition(
                            "open_ring_challenge",
                            "daily.page",
                            "ring_daily_row",
                            "ring_page",
                            "ring",
                            postcondition_alternatives=("daily.reward_popup",),
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            if _ring_hit(snapshot, "ring_page"):
                sweep_eligible = _ring_sweep_eligible(snapshot)
                if _ring_hit(snapshot, "ring_challenge_target.done") and (
                    sweep_eligible
                ):
                    return Decision.finish(TaskStatus.ALREADY_COMPLETE)
                if not sweep_eligible and _ring_remaining_attempts(snapshot) == 0:
                    return Decision.finish(TaskStatus.ALREADY_COMPLETE)
                if (
                    not sweep_eligible
                    and counters.get("fight_ring_opponent", 0) >= RING_MAX_ATTEMPTS
                ):
                    # The action cap is only a safety fuse.  It is never
                    # evidence that the account consumed all attempts.
                    return Decision.finish(TaskStatus.FAILED)
                if not sweep_eligible and not _ring_hit(snapshot, "ring_start"):
                    return Decision.finish(TaskStatus.FAILED)
                next_state = (
                    "opponents_sweep"
                    if sweep_eligible
                    else "opponents_fight"
                )
                return Decision.act(
                    _ring_transition(
                        "open_ring_attempt_mode",
                        "ring_page",
                        "ring_start",
                        "ring_opponent_page",
                        next_state,
                        postcondition_alternatives=(
                            "ring_match_setup_page",
                            "ring_battle_prepare_page",
                            "ring_fight_page",
                            "ring_battle_loading",
                        ),
                    )
                )
            return Decision.act(
                _ring_transition(
                    "open_function_panel",
                    "home",
                    "function_panel.open",
                    "function_panel.page",
                    "panel",
                )
            )
        if state == "panel":
            return Decision.act(
                _ring_transition(
                    "open_daily_tasks", "function_panel.page", "daily.entry", "daily.page", "daily"
                )
            )
        if state == "daily":
            if _ring_hit(snapshot, "daily.reward_popup"):
                if _ring_hit(snapshot, "daily.reward_popup_close"):
                    return Decision.act(
                        _ring_transition(
                            "close_reward_popup",
                            "daily.reward_popup",
                            "daily.reward_popup_close",
                            "daily.page",
                            "daily",
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            if (
                _ring_hit(snapshot, "ring_daily_done")
                or (
                    _ring_hit(snapshot, "ring_daily_task_text")
                    and _ring_hit(snapshot, "ring_daily_row")
                )
            ):
                return Decision.act(
                    _ring_transition(
                        "open_ring_challenge",
                        "daily.page",
                        "ring_daily_row",
                        "ring_page",
                        "ring",
                        postcondition_alternatives=("daily.reward_popup",),
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "ring":
            if _ring_hit(snapshot, "daily.reward_popup"):
                if _ring_hit(snapshot, "daily.reward_popup_close"):
                    return Decision.act(
                        _ring_transition(
                            "close_reward_popup",
                            "daily.reward_popup",
                            "daily.reward_popup_close",
                            "daily.page",
                            "daily",
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            if counters.get("start_ring_matching", 0) >= RING_MAX_ATTEMPTS:
                # Matching count is not the game's remaining-attempts proof.
                # Do not convert a capped loop into a false success.
                if _ring_remaining_attempts(snapshot) != 0:
                    return Decision.finish(TaskStatus.FAILED)
            sweep_eligible = _ring_sweep_eligible(snapshot)
            if _ring_hit(snapshot, "ring_challenge_target.done") and (
                sweep_eligible
            ):
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            if not sweep_eligible and _ring_remaining_attempts(snapshot) == 0:
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            if (
                not sweep_eligible
                and counters.get("fight_ring_opponent", 0) >= RING_MAX_ATTEMPTS
            ):
                return Decision.finish(TaskStatus.FAILED)
            if not sweep_eligible and not _ring_hit(snapshot, "ring_start"):
                return Decision.finish(TaskStatus.FAILED)
            next_state = (
                "opponents_sweep"
                if sweep_eligible
                else "opponents_fight"
            )
            return Decision.act(
                _ring_transition(
                    "open_ring_attempt_mode",
                    "ring_page",
                    "ring_start",
                    "ring_opponent_page",
                    next_state,
                    postcondition_alternatives=(
                        "ring_match_setup_page",
                        "ring_battle_prepare_page",
                        "ring_fight_page",
                        "ring_battle_loading",
                    ),
                )
            )
        if state == "opponents_sweep":
            if counters.get("dismiss_ring_result", 0) > 0 or _ring_hit(
                snapshot, "ring_challenge_target.done"
            ):
                return Decision.act(
                    _ring_transition(
                        "close_ring_opponents",
                        "ring_opponent_page",
                        "ring_opponent_close",
                        "ring_page",
                        "ring_after",
                    )
                )
            if _ring_hit(snapshot, "ring_sweep"):
                return Decision.act(
                    _ring_transition(
                        "sweep_ring",
                        "ring_opponent_page",
                        "ring_sweep",
                        "ring_sweep_prompt",
                        "sweep_interstitial",
                        resource="擂台券",
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "opponents_fight":
            if _ring_hit(snapshot, "ring_match_setup_page"):
                remaining = _ring_remaining_attempts(snapshot)
                if remaining is None:
                    return Decision.finish(TaskStatus.FAILED)
                if remaining == 0:
                    return Decision.finish(TaskStatus.ALREADY_COMPLETE)
                if _ring_hit(snapshot, "ring_match_start"):
                    return Decision.act(
                        _ring_transition(
                            "start_ring_matching",
                            "ring_match_setup_page",
                            "ring_match_start",
                            "ring_battle_loading",
                            "fight",
                            resource="擂台券",
                            postcondition_alternatives=(
                                "ring_battle_prepare_page",
                                "ring_fight_page",
                                "ring_battle_result",
                                "ring_reward_popup",
                            ),
                        )
                    )
                return Decision.finish(TaskStatus.FAILED)
            if _ring_hit(snapshot, "ring_battle_loading"):
                return Decision.act(
                    _ring_wait_for_battle_transition("ring_battle_loading")
                )
            # If the client opens directly into the live fight page after
            # matching, skip the animation without requiring a phantom
            # opponent-card click.
            if _ring_hit(snapshot, "ring_battle_prepare_page") and _ring_hit(
                snapshot, "ring_ready"
            ):
                return Decision.act(
                    _ring_transition(
                        "start_ring_battle",
                        "ring_battle_prepare_page",
                        "ring_ready",
                        "ring_fight_page",
                        "fight",
                        postcondition_alternatives=("ring_battle_loading",),
                    )
                )
            if _ring_hit(snapshot, "ring_fight_page") and _ring_hit(snapshot, "ring_skip"):
                return Decision.act(
                    _ring_transition(
                        "skip_ring_battle",
                        "ring_fight_page",
                        "ring_skip",
                        "ring_battle_result",
                        "fight_result",
                    )
                )
            if _ring_hit(snapshot, "ring_battle_loading"):
                return Decision.act(_ring_wait_for_battle_transition())
            if _ring_hit(snapshot, "ring_battle_result") and _ring_hit(
                snapshot, "ring_result_close"
            ):
                return Decision.act(
                    _ring_transition(
                        "dismiss_ring_result",
                        "ring_battle_result",
                        "ring_result_close",
                        "ring_opponent_page",
                        "opponents_fight",
                    )
                )
            # Today's objective requires all twelve manual attempts while the
            # account is below the master threshold.  The daily-row green
            # tick after the first fight is not a reason to stop early.
            remaining = _ring_remaining_attempts(snapshot)
            if remaining == 0:
                if not _ring_hit(snapshot, "ring_opponent_close"):
                    return Decision.finish(TaskStatus.ALREADY_COMPLETE)
                return Decision.act(
                    _ring_transition(
                        "close_ring_opponents",
                        "ring_opponent_page",
                        "ring_opponent_close",
                        "ring_page",
                        "ring_after",
                    )
                )
            if remaining is None:
                # A consumptive opponent click without an observed remaining
                # counter cannot prove whether this is the first attempt or
                # the eleventh recovery click.  Fail closed instead of
                # risking an overrun.
                return Decision.finish(TaskStatus.FAILED)
            if counters.get("fight_ring_opponent", 0) >= RING_MAX_ATTEMPTS:
                # The local cap is a guardrail, not a completion condition.
                return Decision.finish(TaskStatus.FAILED)
            if _ring_hit(snapshot, "ring_fight_target"):
                return Decision.act(
                    _ring_transition(
                        "fight_ring_opponent",
                        "ring_opponent_page",
                        "ring_fight_target",
                        "ring_battle_prepare_page",
                        "fight",
                        resource="擂台券",
                        postcondition_alternatives=("ring_fight_page",),
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "fight":
            if _ring_hit(snapshot, "ring_reward_popup") and _ring_hit(
                snapshot, "ring_result_close"
            ):
                return Decision.act(
                    _ring_transition(
                        "dismiss_ring_reward",
                        "ring_battle_result",
                        "ring_result_close",
                        "ring_battle_result",
                        "fight",
                    )
                )
            if _ring_hit(snapshot, "ring_battle_prepare_page") and _ring_hit(
                snapshot, "ring_ready"
            ):
                return Decision.act(
                    _ring_transition(
                        "start_ring_battle",
                        "ring_battle_prepare_page",
                        "ring_ready",
                        "ring_fight_page",
                        "fight",
                        postcondition_alternatives=("ring_battle_loading",),
                    )
                )
            if _ring_hit(snapshot, "ring_skip"):
                return Decision.act(
                    _ring_transition(
                        "skip_ring_battle",
                        "ring_fight_page",
                        "ring_skip",
                        "ring_battle_result",
                        "fight_result",
                    )
                )
            if _ring_hit(snapshot, "ring_battle_loading"):
                return Decision.act(_ring_wait_for_battle_transition())
            if _ring_hit(snapshot, "ring_result_close") and _ring_hit(
                snapshot, "ring_battle_result"
            ):
                new_client_match = counters.get("start_ring_matching", 0) > 0
                return Decision.act(
                    _ring_transition(
                        "dismiss_ring_result",
                        "ring_battle_result",
                        "ring_result_close",
                        "ring_page" if new_client_match else "ring_opponent_page",
                        "ring" if new_client_match else "opponents_fight",
                        postcondition_alternatives=(
                            ("ring_opponent_page",)
                            if new_client_match
                            else ("ring_page",)
                        ),
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "fight_result":
            if _ring_hit(snapshot, "ring_result_close") and _ring_hit(
                snapshot, "ring_battle_result"
            ):
                return Decision.act(
                    _ring_transition(
                        "dismiss_ring_result",
                        "ring_battle_result",
                        "ring_result_close",
                        "ring_opponent_page",
                        "opponents_fight",
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "sweep_interstitial":
            # The sweep result is the business boundary.  Once the explicit
            # master-tier branch has consumed the ticket, the result overlay
            # itself is sufficient evidence; cleanup remains optional.
            if _ring_hit(snapshot, "ring_sweep_result") or _ring_hit(
                snapshot, "ring_challenge_target.done"
            ):
                return Decision.finish(
                    TaskStatus.COMPLETED
                    if counters.get("confirm_ring_sweep", 0) > 0
                    else TaskStatus.ALREADY_COMPLETE
                )
            if _ring_hit(snapshot, "ring_sweep_confirm"):
                return Decision.act(
                    _ring_transition(
                        "confirm_ring_sweep",
                        "ring_sweep_prompt",
                        "ring_sweep_confirm",
                        "ring_sweep_result",
                        "sweep_result",
                        resource="擂台券",
                    )
                )
            if _ring_hit(snapshot, "ring_sweep_result") and _ring_hit(
                snapshot, "ring_result_close"
            ):
                return Decision.act(
                    _ring_transition(
                        "dismiss_ring_result",
                        "ring_sweep_result",
                        "ring_result_close",
                        "ring_opponent_page",
                        "opponents_sweep",
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "sweep_result":
            if _ring_hit(snapshot, "ring_sweep_result") or _ring_hit(
                snapshot, "ring_challenge_target.done"
            ):
                return Decision.finish(
                    TaskStatus.COMPLETED
                    if counters.get("confirm_ring_sweep", 0) > 0
                    else TaskStatus.ALREADY_COMPLETE
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "ring_after":
            if _ring_hit(snapshot, "ring_page_close"):
                return Decision.act(
                    _ring_transition(
                        "close_ring_page",
                        "ring_page",
                        "ring_page_close",
                        "home",
                        "done",
                    )
                )
            return Decision.finish(TaskStatus.FAILED)
        if state == "daily_verify":
            if _ring_hit(snapshot, "ring_daily_done"):
                return Decision.finish(TaskStatus.COMPLETED)
            return Decision.finish(TaskStatus.FAILED)
        return Decision.finish(TaskStatus.FAILED)
RING_CHALLENGE_DAILY_DEFINITION = RingChallengeDailyDefinition()


__all__ = [name for name in globals() if name.endswith("_DEFINITION")]
