"""Deterministic Batch 1 definitions migrated from jianzhichuan_daily."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..models import ActionIntent, Decision, InputKind, StateSnapshot, TaskStatus, Transition

MAX_DAILY_REWARD_SCROLLS = 5


@dataclass(frozen=True, slots=True)
class TableWorkflowDefinition:
    task_id: str
    initial_state: str
    transitions: Mapping[str, Transition]
    complete_markers: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    already_markers: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    text_requirements: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def recognizers(self, state: str) -> tuple[str, ...]:
        transition = self.transitions.get(state)
        values = set((transition.intent.page_marker,) if transition else ())
        if transition:
            values.add(transition.intent.target_marker)
            if transition.intent.approved_resource is not None:
                values.add(transition.intent.approved_resource)
        values.update(self.complete_markers.get(state, ()))
        values.update(self.already_markers.get(state, ()))
        if self.task_id == "BATTLE_PASS_REWARD_DAILY":
            # The battle-pass loop has two safe fallbacks when the current
            # page has no claimable item: switch from tasks to rewards, or
            # close the rewards page.  Include those targets in the same
            # frame so the decision never relies on stale coordinates.
            values.update({"battle_pass.reward_popup", "battle_pass.reward_popup_close"})
            values.add("battle_pass.item_popup")
            if state in {"main", "tasks"}:
                values.add("battle_pass.rewards_tab")
            elif state == "rewards":
                values.update({"battle_pass.close", "battle_pass.basic_all_claimed"})
        if self.task_id == "DAILY_TASK_REWARD_CLAIM_DAILY" and state == "main":
            values.add("daily.unlocked_activity_chest")
        if self.task_id == "DAILY_TASK_REWARD_CLAIM_DAILY" and state == "home":
            values.update(
                {
                    "daily.page",
                    "daily.completed_row_claim",
                    "daily.unlocked_activity_chest",
                    "daily.reward_popup",
                    "daily.reward_popup_close",
                    "no_claimable_row",
                    "no_claimable",
                }
            )
        if self.task_id == "EAT_STAMINA_FOOD_DAILY" and state in {
            "food",
            "food_detail",
        }:
            # The live account keeps 龙井虾仁 at a known card slot in the
            # all-consumables page.  The card template is the non-consumptive
            # candidate marker; the selected item's detail evidence remains
            # required before any consumptive action is authorized.
            values.update(
                {
                    "food_candidate",
                    "food_detail_changed",
                    "food_buff_replace_prompt",
                    "food_buff_replace_confirm",
                    "food_buff_replace_prompt_template",
                    "food_buff_replace_confirm_template",
                    "food_use_result",
                    "food_overfull",
                    "longjing_shrimp_eat_target",
                    "龙井虾仁",
                }
            )
        if self.task_id == "EAT_STAMINA_FOOD_DAILY" and state == "home":
            # A timeout can leave the explicit replacement prompt open. Keep
            # that same-frame evidence available so a resumed run can confirm
            # the already-authorized food action instead of rebuilding the
            # route or clicking an unrelated home control.
            values.update(
                {
                    "food_buff_replace_prompt",
                    "food_buff_replace_confirm",
                    "food_buff_replace_prompt_template",
                    "food_buff_replace_confirm_template",
                    "food_use_result",
                    "food_overfull",
                }
            )
        if self.task_id == "DUNGEON_SWEEP_DAILY":
            # A full-bag toast is a hard stop for the sweep flow. Keep it in
            # every dungeon frame so a toast that appears immediately after
            # opening the sweep panel is still captured as same-frame task
            # evidence instead of becoming an uninformative postcondition
            # failure.
            values.add("dungeon_bag_full")
            # The ticket counter is rendered on the selected dungeon page.
            # With 0/10 tickets the sweep button is inert, so the task is not
            # eligible for a bounded sweep and must not keep clicking it.
            values.add("dungeon_no_sweep_ticket")
            values.update(
                {
                    "sweep_panel_page",
                    "ticket_plus",
                }
            )
            if state == "home":
                # A failed run may intentionally remain on the already
                # selected 燕王秘陵 page. Expose its bounded continuation
                # markers at the initial state so the next attempt can resume
                # at the sweep panel instead of reopening the dungeon list.
                values.update(
                    {
                        "yanwangling_master_selected",
                        "yanwangling_title",
                        "sweep_target",
                        "sweep_panel_page",
                        "ticket_plus",
                    }
                )
        if self.task_id == "TRIAL_SWORD_DAILY":
            # Resume safely from any already-open Trial modal instead of
            # requiring every retry to reconstruct the route from home.
            values.update(
                {
                    "home",
                    "trial.page",
                    "trial.reward_claim",
                    "trial.free_claim",
                    "trial.free_popup",
                    "trial.free_confirm",
                    "trial.reward_popup",
                    "trial.popup_close",
                    "trial.close",
                }
            )
        if self.task_id == "BUY_TEA_DAILY" and state == "quantity_panel_selected":
            # Keep the explicit text fallback alongside the result template
            # in the purchase verification frame. Generic 茶叶/当前拥有 OCR
            # is intentionally not part of this proof.
            values.add("expected_purchase_result")
        if self.task_id == "BUY_TEA_DAILY" and state == "quantity_panel":
            # The translucent panel title is more stable than the small
            # decorative template on the Android renderer.
            values.add("quantity_panel_title")
        if self.task_id == "BUY_TEA_DAILY" and state in {
            "shop",
            "tea_scroll",
            "tea",
            "tea_scrolled",
            "tea_selected",
        }:
            # The product grid can be scrolled so that 茶叶 is outside the
            # viewport. Keep the stable 玉盟商会 title as an independent
            # shop-boundary proof; the page marker itself must not depend on
            # the currently visible product card.
            values.add("universal_shop_boundary")
        if self.task_id == "BUY_TEA_DAILY" and state in {"tea", "tea_scrolled"}:
            # A previous isolated run can leave the shop list one viewport
            # lower while the task boundary still remains valid. Recognize
            # the shifted card at the initial state so a retry selects it
            # directly instead of scrolling it off the top a second time.
            values.add("tea_item_scrolled")
            # The card can be clipped by the list viewport after a prior
            # scroll, leaving its 茶叶 label visible while the 88px icon
            # template has no full match. Keep that label as a same-frame
            # recovery proof for the adapter's bounded card box.
            values.add("tea_card_label")
        if self.task_id == "SHOP_FREE_GIFT_DAILY" and state == "reward":
            # The reward overlay fades back to the daily-benefits page before
            # its ``已领取`` OCR becomes stable. Keep the parent page in the
            # same verification frame so the Android adapter can apply its
            # action-bound, conservative completion fallback.
            values.add("shop.period_benefits.page")
        if self.task_id == "WEEKLY_FREE_GIFT_MONDAY" and state == "home":
            # A prior isolated run may intentionally leave the weekly reward
            # sheet open for diagnosis. Allow a targeted retry to resume at
            # that recognized surface instead of rebuilding the shop route.
            values.update({"shop.weekly.reward", "shop.weekly.reward_close"})
        if self.task_id == "COLLECTION_DEPLOYMENT_DAILY" and state == "collection_reward_popup":
            # The live reward sheet identifies itself with the horizontal
            # 据传太吾旧影 title; the vertical 恭喜获得 label is frequently
            # split into OCR lines. Keep both proofs available for this frame.
            values.update(
                {
                    "collection.reward_title",
                    "collection.reward_popup",
                    "collection.popup_close",
                }
            )
        values.update({"unknown_dialog", "safety.paid", "safety.verification"})
        return tuple(sorted(values))

    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision:
        evidence = snapshot.evidence
        if evidence is None:
            return Decision.finish(TaskStatus.FAILED)
        if (
            self.task_id == "WEEKLY_FREE_GIFT_MONDAY"
            and snapshot.state == "home"
            and evidence.page_hits.get("shop.weekly.reward", 0) == 1
            and evidence.target_hits.get("shop.weekly.reward_close", 0) == 1
        ):
            return Decision.act(self.transitions["weekly_reward"])
        if self.task_id == "TRIAL_SWORD_DAILY":
            if (
                evidence.page_hits.get("trial.free_popup", 0) == 1
                and evidence.target_hits.get("trial.free_confirm", 0) == 1
            ):
                return Decision.act(self.transitions["free_popup"])
            if (
                evidence.page_hits.get("trial.reward_popup", 0) == 1
                and evidence.target_hits.get("trial.popup_close", 0) == 1
            ):
                transition_name = (
                    "free_reward"
                    if counters.get("confirm_free_trial", 0) >= 1
                    else "reward_popup"
                )
                return Decision.act(self.transitions[transition_name])
        if (
            self.task_id == "DUNGEON_SWEEP_DAILY"
            and evidence.target_hits.get("dungeon_no_sweep_ticket", 0) == 1
            and evidence.target_hits.get("yanwangling_title", 0) == 1
            and evidence.target_hits.get("sweep_target", 0) == 1
        ):
            return Decision.finish(TaskStatus.NOT_ELIGIBLE)
        if (
            self.task_id == "DUNGEON_SWEEP_DAILY"
            and snapshot.state == "home"
            and evidence.target_hits.get("yanwangling_title", 0) == 1
            and evidence.target_hits.get("sweep_target", 0) == 1
            and not (
                evidence.page_hits.get("sweep_panel_page", 0) == 1
                and evidence.target_hits.get("ticket_plus", 0) == 1
            )
        ):
            # Resume from the detail page left by a failed selection step.
            # The title and the sweep target are same-frame proof that the
            # selected dungeon is already 燕王秘陵; no second list selection
            # is needed.
            return Decision.act(self.transitions["selected"])
        if (
            self.task_id == "DUNGEON_SWEEP_DAILY"
            and evidence.page_hits.get("sweep_panel_page", 0) == 1
            and evidence.target_hits.get("ticket_plus", 0) == 1
            and counters.get("assign_sweep_ticket", 0) == 0
        ):
            # A failed run is intentionally left on the open sweep panel.
            # Resume there directly instead of rebuilding the route from home.
            return Decision.act(self.transitions["sweep"])
        if (
            self.task_id == "BUY_TEA_DAILY"
            and snapshot.state in {"tea", "tea_scrolled", "tea_selected"}
            and evidence.target_hits.get("tea_sold_out", 0) == 1
        ):
            # The reference workflow treats an explicit no-stock state as the
            # daily terminal boundary.  It is already complete for today even
            # though this invocation does not need to click Buy.
            return Decision.finish(TaskStatus.ALREADY_COMPLETE)
        already = self.already_markers.get(snapshot.state, ())
        if (
            self.task_id == "MAIL_REWARD_DAILY"
            and snapshot.state == "mail"
            and evidence.target_hits.get("mail.claim_all", 0) == 1
        ):
            # A frame may briefly expose the footer and the claim control
            # together during the mail-page transition.  The actionable
            # target is stronger evidence than the already-read footer.
            already = ()
        if (
            self.task_id == "FREE_APPRAISAL_DAILY"
            and snapshot.state == "appraisal"
            and evidence.target_hits.get("appraisal.free_once", 0) == 1
        ):
            # The live Android page always keeps the descriptive text
            # ``每日赠送一次免费鉴宝`` visible.  The old ``appraisal.used``
            # OCR marker matched that same text, so a page with a still
            # claimable free action was classified as already complete and
            # never reached the protected click.  When the action-specific
            # free target is present, it is the stronger same-frame proof;
            # same-day duplicate runs are suppressed by the persisted
            # business-result check in DailyWorkflowAction.
            already = ()
        daily_main = (
            self.task_id == "DAILY_TASK_REWARD_CLAIM_DAILY" and snapshot.state == "main"
        )
        if (
            already
            and all(evidence.target_hits.get(marker, 0) == 1 for marker in already)
            and not daily_main
        ):
            return Decision.finish(TaskStatus.ALREADY_COMPLETE)
        if self.task_id == "BUY_TEA_DAILY" and snapshot.state == "tea":
            if evidence.target_hits.get("tea_item_scrolled", 0) == 1:
                return Decision.act(self.transitions["tea_scrolled"])
            if (
                evidence.page_hits.get("universal_shop_page", 0) == 1
                and evidence.target_hits.get("tea_item", 0) == 0
                and counters.get("scroll_tea_list", 0) == 0
            ):
                # The live shop moved 茶叶 below the initial viewport. A
                # missing card is not a business result: perform exactly one
                # page-bounded downward scroll, then recognize the post-scroll
                # card from its own expanded ROI.
                return Decision.act(self.transitions["tea_scroll"])
        if self.task_id == "BUY_TEA_DAILY" and snapshot.state == "tea_scrolled":
            if (
                evidence.page_hits.get("universal_shop_page", 0) == 1
                and evidence.target_hits.get("tea_item_scrolled", 0) == 0
                and evidence.target_hits.get("tea_sold_out", 0) == 0
            ):
                # One controlled scroll is the complete recovery budget. If
                # the card is still absent, leave the shop visible with a
                # precise failure instead of declaring a purchase complete.
                return Decision.finish(TaskStatus.FAILED)
        if (
            self.task_id == "EAT_STAMINA_FOOD_DAILY"
            and snapshot.state == "home"
            and evidence.target_hits.get("food_buff_replace_prompt", 0) == 1
            and evidence.target_hits.get("food_buff_replace_confirm", 0) == 1
        ):
            # Resume an interrupted food use from the visible replacement
            # prompt. The transition moves into the normal food loop; it does
            # not start a new study or infer a consumptive target.
            return Decision.act(self.transitions["confirm_food_buff_replace"])
        if self.task_id == "EAT_STAMINA_FOOD_DAILY" and snapshot.state == "food":
            # The game refuses further food once the daily stamina-food limit
            # is reached. This terminal signal also handles a run that starts
            # after some successful uses, so the total is not inferred only
            # from this run's local action counter.
            if evidence.target_hits.get("food_overfull", 0) == 1:
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            if evidence.target_hits.get("food_buff_replace_prompt", 0) == 1:
                confirm = self.transitions.get("confirm_food_buff_replace")
                if (
                    confirm is not None
                    and evidence.target_hits.get("food_buff_replace_confirm", 0) == 1
                ):
                    return Decision.act(confirm)
                return Decision.finish(TaskStatus.FAILED)
            eaten = counters.get("eat_longjing_shrimp", 0)
            if eaten >= 5:
                return Decision.finish(TaskStatus.COMPLETED)
            inspect = self.transitions.get(snapshot.state)
            if inspect is not None and evidence.target_hits.get("food_candidate", 0) == 1:
                return Decision.act(inspect)
            if evidence.page_hits.get("consumables_page", 0) == 1:
                # The selected card is fixed by the live template.  If its
                # detail or use evidence is absent, finish as a valid no-op
                # instead of scanning other inventory slots.
                return Decision.finish(TaskStatus.NOT_ELIGIBLE)
        if self.task_id == "DAILY_TASK_REWARD_CLAIM_DAILY" and snapshot.state == "main":
            # Live behavior: one visible claim action auto-claims every
            # completed task row. Activity chests remain independent and are
            # claimed from their blue-glow template until none remains.
            row_target = "daily.completed_row_claim"
            chest_target = "daily.unlocked_activity_chest"
            if (
                counters.get("claim_completed_daily_row", 0) == 0
                and evidence.target_hits.get(row_target, 0) == 1
            ):
                return Decision.act(self.transitions["main"])
            if evidence.target_hits.get(chest_target, 0) == 1:
                return Decision.act(self.transitions["main_chest"])
            if (
                counters.get("claim_completed_daily_row", 0) >= 1
                or counters.get("claim_unlocked_activity_chest", 0) >= 1
            ):
                return Decision.finish(TaskStatus.COMPLETED)
            if any(
                evidence.target_hits.get(marker, 0) == 1
                for marker in self.already_markers.get("main", ())
            ):
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
            if counters.get("scroll_daily_reward_rows", 0) < MAX_DAILY_REWARD_SCROLLS:
                scroll = self.transitions.get("scroll")
                if scroll is not None:
                    return Decision.act(scroll)
            return Decision.finish(TaskStatus.ALREADY_COMPLETE)
        if self.task_id == "DAILY_TASK_REWARD_CLAIM_DAILY" and snapshot.state == "home":
            if (
                evidence.page_hits.get("daily.reward_popup", 0) == 1
                and evidence.target_hits.get("daily.reward_popup_close", 0) == 1
            ):
                return Decision.act(self.transitions["reward_popup"])
            if evidence.page_hits.get("daily.page", 0) == 1:
                if evidence.target_hits.get("daily.completed_row_claim", 0) == 1:
                    return Decision.act(self.transitions["main"])
                if evidence.target_hits.get("daily.unlocked_activity_chest", 0) == 1:
                    return Decision.act(self.transitions["main_chest"])
                if any(
                    evidence.target_hits.get(marker, 0) == 1
                    for marker in self.already_markers.get("main", ())
                ):
                    return Decision.finish(TaskStatus.ALREADY_COMPLETE)
                return Decision.finish(TaskStatus.ALREADY_COMPLETE)
        if (
            self.task_id == "BATTLE_PASS_REWARD_DAILY"
            and snapshot.state in {"home", "battle_pass", "tasks"}
            and evidence.page_hits.get("battle_pass.reward_popup", 0) == 1
            and evidence.target_hits.get("battle_pass.reward_popup", 0) == 1
        ):
            # A previous claim can leave the shared reward sheet over the
            # battle-pass page before the next tab action is authorized. Close
            # that non-destructive overlay first, then resume at the tasks
            # page; this also handles the sheet appearing immediately after
            # the tasks-tab click.
            return Decision.act(self.transitions["tasks_reward_popup"])
        complete = self.complete_markers.get(snapshot.state, ())
        if complete and all(evidence.target_hits.get(marker, 0) == 1 for marker in complete):
            return Decision.finish(TaskStatus.COMPLETED)
        transition = self.transitions.get(snapshot.state)
        if transition is None:
            return Decision.finish(TaskStatus.FAILED)
        target = transition.intent.target_marker
        if self.task_id == "BATTLE_PASS_REWARD_DAILY":
            if snapshot.state in {"main", "tasks"} and evidence.target_hits.get(target, 0) == 0:
                transition = self.transitions.get("open_rewards_tab")
                if transition and evidence.target_hits.get(transition.intent.target_marker, 0) == 1:
                    return Decision.act(transition)
                return Decision.finish(TaskStatus.FAILED)
            if snapshot.state == "rewards" and evidence.target_hits.get(target, 0) == 0:
                if evidence.target_hits.get("battle_pass.basic_all_claimed", 0) == 1:
                    close = self.transitions.get("close")
                    if close is not None and evidence.target_hits.get("battle_pass.close", 0) == 1:
                        return Decision.act(close)
                    return Decision.finish(TaskStatus.ALREADY_COMPLETE)
                # A rewards page with neither a claimable basic-track reward
                # nor an explicit all-claimed marker is inconclusive.  Keep
                # the page for diagnosis instead of publishing a false
                # success after navigation only.
                return Decision.finish(TaskStatus.FAILED)
        if evidence.target_hits.get(target, 0) != 1:
            return Decision.finish(TaskStatus.FAILED)
        required = self.text_requirements.get(target, ())
        normalized_text = "".join(evidence.texts)
        if required and not all(text in normalized_text for text in required):
            return Decision.finish(TaskStatus.FAILED)
        return Decision.act(transition)


def _t(
    action: str,
    page: str,
    target: str,
    next_state: str,
    postcondition: str,
    *,
    postcondition_alternatives: tuple[str, ...] = (),
) -> Transition:
    return Transition(
        ActionIntent(action, page, target, input_kind=InputKind.CLICK),
        postcondition,
        next_state,
        postcondition_alternatives,
    )


def _definition(
    task_id: str,
    transitions: Mapping[str, Transition],
    *,
    initial_state: str = "home",
    complete_markers: Mapping[str, tuple[str, ...]] | None = None,
    already_markers: Mapping[str, tuple[str, ...]] | None = None,
    text_requirements: Mapping[str, tuple[str, ...]] | None = None,
) -> TableWorkflowDefinition:
    return TableWorkflowDefinition(
        task_id,
        initial_state,
        transitions,
        complete_markers or {},
        already_markers or {},
        text_requirements or {},
    )


MAIL_REWARD_DAILY_DEFINITION = _definition(
    "MAIL_REWARD_DAILY",
    {
        "home": _t(
            "open_function_panel",
            "home",
            "function_panel.open",
            "function_panel",
            "function_panel.page",
        ),
        "function_panel": _t("open_mail", "function_panel.page", "mail.entry", "mail", "mail.page"),
        "mail": _t(
            "claim_all_mail",
            "mail.page",
            "mail.claim_all",
            "mail_reward_popup",
            "mail.reward_popup",
        ),
        "mail_reward_popup": _t(
            "close_reward_popup",
            "mail.reward_popup",
            "mail.reward_popup_close",
            "mail_after_claim",
            "mail.page",
        ),
        "mail_after_claim": _t(
            "close_mail",
            "mail.page",
            "mail.close",
            "function_panel_after_mail",
            "function_panel.page",
        ),
        "function_panel_after_mail": _t(
            "close_function_panel",
            "function_panel.page",
            "reset.panel_close",
            "home_done",
            "home",
        ),
    },
    complete_markers={"home_done": ("home",)},
    already_markers={"mail": ("mail.empty",)},
)

SHOP_FREE_GIFT_DAILY_DEFINITION = _definition(
    "SHOP_FREE_GIFT_DAILY",
    {
        "home": _t(
            "open_function_panel",
            "home",
            "function_panel.open",
            "function_panel",
            "function_panel.page",
        ),
        "function_panel": _t("open_shop", "function_panel.page", "shop.entry", "shop", "shop.page"),
        "shop": _t(
            "open_period_benefits",
            "shop.page",
            "shop.period_benefits",
            "benefits",
            "shop.period_benefits.page",
        ),
        "benefits": _t(
            "claim_free_gift",
            "shop.period_benefits.page",
            "shop.daily_free_gift",
            "reward",
            "shop.free_gift.reward",
        ),
        "reward": _t(
            "dismiss_free_gift_reward",
            "shop.free_gift.reward",
            "shop.free_gift.dismiss",
            "claimed",
            "shop.daily_free_gift_claimed",
        ),
        "claimed": _t("close_shop", "shop.page", "shop.close", "home_done", "home"),
    },
    complete_markers={"home_done": ("home",)},
    already_markers={"benefits": ("shop.daily_free_gift_claimed",)},
    text_requirements={"shop.daily_free_gift": ("免费",)},
)

WEEKLY_FREE_GIFT_MONDAY_DEFINITION = _definition(
    "WEEKLY_FREE_GIFT_MONDAY",
    {
        "home": _t(
            "open_function_panel",
            "home",
            "function_panel.open",
            "function_panel",
            "function_panel.page",
        ),
        "function_panel": _t("open_shop", "function_panel.page", "shop.entry", "shop", "shop.page"),
        "shop": _t("open_gift_tab", "shop.page", "shop.gift_tab", "gift_tab", "shop.gift_tab.page"),
        "gift_tab": _t(
            "open_weekly_must_buy",
            "shop.gift_tab.page",
            "shop.weekly_must_buy",
            "weekly",
            "shop.weekly.page",
        ),
        "weekly": _t(
            "claim_weekly_lucky_bag",
            "shop.weekly.page",
            "shop.weekly_lucky_bag_free",
            "weekly_reward",
            "shop.weekly.reward",
        ),
        "weekly_reward": _t(
            "dismiss_weekly_reward",
            "shop.weekly.reward",
            "shop.weekly.reward_close",
            "claimed",
            "weekly_gift.reward_popup_seen",
        ),
        "claimed": _t("close_shop", "shop.page", "shop.close", "home_done", "home"),
    },
    complete_markers={"home_done": ("home",)},
    already_markers={},
    text_requirements={"shop.weekly_lucky_bag_free": ("免费",)},
)

TRIAL_SWORD_DAILY_DEFINITION = _definition(
    "TRIAL_SWORD_DAILY",
    {
        "home": _t("open_trial_sword", "home", "trial.open", "trial", "trial.page"),
        "trial": _t(
            "claim_trial_sword_reward",
            "trial.page",
            "trial.reward_claim",
            "reward_popup",
            "trial.reward_popup",
            postcondition_alternatives=("home",),
        ),
        "reward_popup": _t(
            "close_reward_popup",
            "trial.reward_popup",
            "trial.popup_close",
            "free_trial",
            "trial.page",
        ),
        "free_trial": _t(
            "claim_free_trial", "trial.page", "trial.free_claim", "free_popup", "trial.free_popup"
        ),
        "free_popup": _t(
            "confirm_free_trial",
            "trial.free_popup",
            "trial.free_confirm",
            "free_reward",
            "trial.reward_popup",
        ),
        "free_reward": _t(
            "close_reward_popup",
            "trial.reward_popup",
            "trial.popup_close",
            "trial_done",
            "trial.reward_popup_seen",
        ),
        "trial_done": _t(
            "close_trial",
            "trial.page",
            "trial.close",
            "home_done",
            "home",
        ),
    },
    complete_markers={"home_done": ("home",)},
    already_markers={},
    text_requirements={"trial.free_claim": ("免费",)},
)

FREE_APPRAISAL_DAILY_DEFINITION = _definition(
    "FREE_APPRAISAL_DAILY",
    {
        "home": _t("open_appraisal", "home", "appraisal.open", "appraisal", "appraisal.page"),
        "appraisal": _t(
            "claim_free_appraisal_once",
            "appraisal.page",
            "appraisal.free_once",
            "result_popup",
            "appraisal.popup_close",
        ),
        "result_popup": _t(
            "close_appraisal_popup",
            "appraisal.result_popup",
            "appraisal.popup_close",
            "appraisal_done",
            "appraisal.page",
        ),
    },
    complete_markers={
        "home_done": ("home",),
        # Closing the result sheet leaves the appraisal page open on Android;
        # the shared successful-task boundary then closes that recognized
        # page and verifies the real home screen.
        "appraisal_done": ("appraisal.page",),
    },
    already_markers={},
    text_requirements={"appraisal.free_once": ("免费鉴宝",)},
)

COLLECTION_DEPLOYMENT_DAILY_DEFINITION = _definition(
    "COLLECTION_DEPLOYMENT_DAILY",
    {
        "home": _t(
            "open_painting_scroll",
            "home",
            "painting_scroll.open",
            "painting_scroll",
            "painting_scroll.page",
        ),
        "painting_scroll": _t(
            "select_yanwu_world",
            "painting_scroll.page",
            "collection.yanwu_world",
            "yanwu",
            "yanwu.page",
        ),
        "yanwu": _t(
            "open_collection_deployment",
            "yanwu.page",
            "collection.open",
            "collection",
            "collection.page",
        ),
        "collection": _t(
            "claim_all_collection",
            "collection.page",
            "collection.harvest_all",
            "collection_reward_popup",
            "collection.reward_popup",
        ),
        "collection_reward_popup": _t(
            "close_reward_popup",
            "collection.reward_popup",
            "collection.popup_close",
            "painting_scroll_done",
            "painting_scroll.page",
        ),
    },
    complete_markers={
        "home_done": ("home",),
        # Dismissing the collection reward returns to the 画卷 map. The
        # shared successful-task boundary closes that page and verifies home.
        "painting_scroll_done": ("painting_scroll.page",),
    },
    already_markers={},
)


def _loop_definition(
    task_id: str,
    open_action: str,
    open_target: str,
    page: str,
    row_action: str,
    row_target: str,
    chest_action: str | None,
    chest_target: str | None,
    close_action: str,
    close_target: str,
    *,
    open_from_home: bool = False,
) -> TableWorkflowDefinition:
    transitions: dict[str, Transition] = {
        "home": (
            _t(open_action, "home", open_target, "main", page)
            if open_from_home
            else _t(
                "open_function_panel",
                "home",
                "function_panel.open",
                "function_panel",
                "function_panel.page",
            )
        ),
        "function_panel": _t(open_action, "function_panel.page", open_target, "main", page),
        "main": _t(
            row_action,
            page,
            row_target,
            "reward_popup" if task_id == "DAILY_TASK_REWARD_CLAIM_DAILY" else "main",
            (
                "daily.reward_popup"
                if task_id == "DAILY_TASK_REWARD_CLAIM_DAILY"
                else f"{row_target}.claimed"
            ),
        ),
        "close": _t(close_action, page, close_target, "home_done", "home"),
    }
    if task_id == "DAILY_TASK_REWARD_CLAIM_DAILY":
        transitions["reward_popup"] = _t(
            "close_reward_popup",
            "daily.reward_popup",
            "daily.reward_popup_close",
            "main",
            page,
        )
        transitions["main_chest"] = _t(
            chest_action,
            page,
            chest_target,
            "reward_popup",
            "daily.reward_popup",
        )
        transitions["scroll"] = Transition(
            ActionIntent(
                "scroll_daily_reward_rows",
                page,
                page,
                input_kind=InputKind.SWIPE,
            ),
            page,
            "main",
        )
    if chest_action and chest_target:
        transitions.setdefault(
            "main_chest",
            _t(chest_action, page, chest_target, "main", f"{chest_target}.claimed"),
        )
    return _definition(
        task_id,
        transitions,
        complete_markers={"home_done": ("home",)},
        already_markers={"main": ("no_claimable_row", "no_claimable")},
    )


DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION = _loop_definition(
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "open_daily_tasks",
    "daily.entry",
    "daily.page",
    "claim_completed_daily_row",
    "daily.completed_row_claim",
    "claim_unlocked_activity_chest",
    "daily.unlocked_activity_chest",
    "close_daily_tasks",
    "daily.close",
)

BATTLE_PASS_REWARD_DAILY_DEFINITION = _definition(
    "BATTLE_PASS_REWARD_DAILY",
    {
        "home": _t(
            "open_battle_pass",
            "home",
            "battle_pass.open",
            "battle_pass",
            "battle_pass.page",
            postcondition_alternatives=("battle_pass.reward_popup",),
        ),
        "battle_pass": _t(
            "open_battle_pass_tasks",
            "battle_pass.page",
            "battle_pass.tasks_tab",
            "tasks",
            "battle_pass.tasks",
            postcondition_alternatives=("battle_pass.reward_popup",),
        ),
        "tasks": _t(
            "claim_task_reward",
            "battle_pass.tasks",
            "battle_pass.task_reward_claim",
            "tasks_reward_popup",
            "battle_pass.reward_popup",
        ),
        # Compatibility alias retained for fixture consumers written against
        # the earlier loop definition; live execution enters ``tasks``.
        "main": _t(
            "claim_task_reward",
            "battle_pass.tasks",
            "battle_pass.task_reward_claim",
            "tasks_reward_popup",
            "battle_pass.reward_popup",
        ),
        "tasks_reward_popup": _t(
            "close_reward_popup",
            "battle_pass.reward_popup",
            "battle_pass.reward_popup",
            "tasks",
            "battle_pass.tasks",
        ),
        "open_rewards_tab": _t(
            "open_battle_pass_rewards",
            "battle_pass.tasks",
            "battle_pass.rewards_tab",
            "rewards",
            "battle_pass.rewards",
        ),
        "rewards": _t(
            "claim_basic_red_dot_reward",
            "battle_pass.rewards",
            "battle_pass.basic_red_dot_reward",
            "rewards_reward_popup",
            "battle_pass.reward_popup",
        ),
        "rewards_reward_popup": _t(
            "close_reward_popup",
            "battle_pass.reward_popup",
            "battle_pass.reward_popup",
            "rewards",
            "battle_pass.rewards",
        ),
        "close": _t(
            "close_battle_pass",
            "battle_pass.rewards",
            "battle_pass.close",
            "home_done",
            "home",
        ),
    },
    complete_markers={"home_done": ("home",)},
)


__all__ = [name for name in globals() if name.endswith("_DEFINITION")]
