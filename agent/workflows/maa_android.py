"""Maa Android controller adapter for the bounded workflow engine."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from functools import wraps
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from agent.android.login import LoginGate
from agent.android.runtime_gate import AndroidRuntimeGate
from agent.errors import ErrorCode, MJAError

from .input import AndroidWorkflowDriver
from .models import CapturedFrame, VisualEvidence


def _image_size(image: Any) -> tuple[int, int]:
    shape = getattr(image, "shape", None)
    if not isinstance(shape, Sequence) or len(shape) < 2:
        raise RuntimeError("Maa screencap did not return an image array")
    height, width = int(shape[0]), int(shape[1])
    if (width, height) != (1280, 720):
        raise RuntimeError(f"Maa Android frame must be 1280x720, got {width}x{height}")
    return width, height


_SHADOW_FOREGROUND_MARKERS = (
    "shadow_foreground_left",
    "shadow_foreground_center",
    "shadow_foreground_right",
)

_RING_PAGE_PROOF_MARKERS = (
    "ring_entry",
    "ring_start",
    "ring_master_mode",
    "ring_master_rank",
    "ring_score_label",
    "ring_score_value",
    "ring_challenge_target.done",
)

# A client hot-update can be several gigabytes.  Keep the Maa controller
# polling the update surface for up to ten minutes; this remains bounded and
# is long enough for a normal local-network download without treating the game
# as an unknown page.  The game can show the mobile-network confirmation again
# after a partial download, so each same-frame prompt/allow pair is handled.
_RESOURCE_UPDATE_MAX_STEPS = 120
_RESOURCE_UPDATE_POLL_SECONDS = 5.0

# A title click can leave Unity on an unlabelled transition frame while the
# first home HUD is being constructed.  Keep that hand-off inside the Maa
# boundary loop instead of falling through to lifecycle recovery, whose
# Android login gate can wait for several minutes on the same title surface.
_TITLE_START_WAIT_SECONDS = 90.0
_TITLE_START_POLL_SECONDS = 3.0

_SHADOW_BATTLE_MODE_RECOGNIZERS = (
    "shadow_stage_page",
    "shadow_speed_enabled",
    "shadow_speed_toggle",
    "shadow_auto_enabled",
    "shadow_auto_toggle",
    "shadow_battle_result",
    "shadow_battle_failure",
    "shadow_formation_page",
    "shadow_battle_target",
)

_SHADOW_SPEED_TOGGLE_BOX = (1035, 20, 110, 70)
_SHADOW_AUTO_TOGGLE_BOX = (1110, 20, 80, 70)

# A successful one-row scroll on the Android renderer can move only the
# upper card stack while leaving the foreground row almost unchanged.  The
# live 1280x720 trace is just below the old 2%/0.8 thresholds after the
# detector's 8x downsampling, so keep the thresholds explicit and calibrated
# to that renderer instead of accepting any page-level animation noise.
_SHADOW_GRID_MIN_CHANGED_RATIO = 0.015
_SHADOW_GRID_MIN_MEAN_DELTA = 0.5
_SHADOW_GRID_MIN_LOCAL_DENSITY = 0.08
_SHADOW_GRID_MAX_ACTIVE_BLOCK_RATIO = 0.55

# The blue 研习/突破 button is a large Unity hit area. Maa OCR commonly
# returns only the decorative right-hand glyph, but that glyph rectangle is
# not the button's reliable pointer target. Keep OCR as authorization and use
# this same-renderer full button rectangle for the actual bounded gesture.
_MARTIAL_ACTION_BUTTON_BOX = (880, 535, 320, 70)

# The live painting map renders 侠客派遣 as the left control in the lower
# right corner, immediately beside 蜃影武墟.  OCR returns the label baseline
# near the bottom of the control; tapping that text box can miss the Unity
# hitbox.  Keep the current-frame OCR hit as authorization, but send the tap
# through this calibrated interior box instead of the text rectangle.
_HERO_DISPATCH_ENTRY_BOX = (990, 590, 120, 70)

# The Android study detail uses a stable 3x3 candidate grid and three skill
# tabs.  These boxes are deliberately broad enough to hit the card/tab body,
# but remain inside the respective control so an OCR miss cannot redirect a
# selection to an adjacent control.  They are calibrated against the same
# 1280x720 Maa frame as the live pipeline.
_MARTIAL_CANDIDATE_BOXES = (
    (125, 130, 100, 130),
    (243, 130, 100, 130),
    (364, 130, 100, 130),
    (125, 280, 100, 130),
    (243, 280, 100, 130),
    (364, 280, 100, 130),
    (125, 430, 100, 130),
    (243, 430, 100, 130),
    (364, 430, 100, 130),
)
_MARTIAL_SKILL_BOXES = (
    (525, 190, 210, 90),
    (745, 190, 210, 90),
    (965, 190, 210, 90),
)
_MARTIAL_CONFIGURATION_RECOGNIZERS = (
    "martial_study_detail",
    "martial_study_action",
    "martial_breakthrough_action",
    "martial_material_ratio_1",
    "martial_material_ratio_2",
    "martial_material_ratio_3",
    "martial_material_ratio_4",
    "martial_materials_sufficient",
    "martial_materials_insufficient",
    "martial_candidate_in_progress",
)

# A terminal shop result can be ``already_complete`` before the workflow has
# emitted a close action.  Keep the hand-off probe cheap in that case: the
# full boundary catalog is deliberately expensive on the Android renderer.
_SHOP_BOUNDARY_ACTIONS = frozenset(
    {
        "open_shop",
        "open_period_benefits",
        "open_gift_tab",
        "open_weekly_must_buy",
        "open_universal_shop",
        "boundary_shop_close",
    }
)


def _boundary_cleanup_method(method):
    """Mark recognitions performed by task-boundary cleanup.

    Boundary cleanup is allowed to dismiss a verified non-purchase reward or
    promotional sheet left by the previous task.  Keeping this as a scoped
    method flag avoids weakening action-bound recognition during normal task
    execution.
    """

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        previous = self._boundary_cleanup_active
        self._boundary_cleanup_active = True
        try:
            return method(self, *args, **kwargs)
        finally:
            self._boundary_cleanup_active = previous

    return wrapped


def _boundary_probe_names(action_id: str | None) -> tuple[str, ...]:
    """Return a small surface-specific probe for a known last action."""

    if not action_id:
        return ()
    if action_id == "boundary_shop_close":
        return ("reset.function_panel", "reset.panel_close")
    if action_id == "boundary_collection_close":
        return (
            "painting_page",
            "reset.function_panel",
            "reset.panel_close",
        )
    if action_id in {
        "boundary_collection_reward_close",
        "boundary_painting_close",
        "boundary_food_close",
    }:
        return ("reset.function_panel", "reset.panel_close")
    action = action_id.casefold()
    names: list[str] = ["reset.function_panel", "reset.panel_close"]
    if action_id in _SHOP_BOUNDARY_ACTIONS or "shop" in action or "tea" in action:
        names.extend(
            (
                "shop.page",
                "shop.period_benefits.page",
                "shop.gift_tab.page",
                "shop.weekly.page",
                "universal_shop_boundary",
                "tea_purchase_result",
                "reset.modal_close",
                "reset.daily_close",
                "reset.trial_close",
            )
        )
    if "appraisal" in action:
        names.extend(
            (
                "appraisal.page",
                "reset.modal_close",
                "reset.daily_close",
                "reset.trial_close",
            )
        )
    if "collection" in action or "painting" in action or action in {
        "select_yanwu_world",
        "select_yunzhou",
    }:
        names.extend(
            (
                "collection.page",
                "collection.reward_popup",
                "collection.popup_close",
                "painting_page",
                "reset.modal_close",
                "reset.daily_close",
                "reset.trial_close",
            )
        )
    if "shadow" in action or action in {"battle", "battle_result"}:
        names.extend(
            (
                "shadow_exploration_page",
                "shadow_page",
                "shadow_card_list",
                "shadow_active_card",
                "shadow_no_active_card",
                "shadow_popup",
                "shadow_go",
                "reset.shadow_leave",
                "reset.world_return",
                "reset.modal_close",
            )
        )
    if "martial" in action or "study" in action or "breakthrough" in action:
        names.extend(
            (
                "martial_success_result",
                "martial_result_close",
                "martial_claim_progress",
                "martial_study_detail",
                "martial_page",
                "martial_close",
                "reset.modal_close",
            )
        )
    if "food" in action or "bag" in action or "eat" in action:
        names.extend(
            (
                "bag_page",
                "consumables_page",
                "food_category",
                "food_tab_page",
                "reset.modal_close",
            )
        )
    if "dungeon" in action or "sweep" in action:
        names.extend(("dungeon_page", "dungeon_close", "reset.modal_close"))
    if "jianlin" in action or "condensate" in action or "stamina" in action:
        names.extend(("jianlin_page", "jianlin_page_close", "reset.modal_close"))
    if "dispatch" in action or "hero" in action:
        names.extend(
            (
                "hero.dispatch.page",
                "hero.all_completed",
                "hero.first_task_claimable",
                "hero.first_task_dispatchable",
                "hero.first_task_in_progress",
                "hero.claim_button",
                "hero.smart_configure",
                "hero.dispatch_button",
                "hero.reward_popup",
                "hero.reward_popup_close",
                "hero.dispatch.close",
            )
        )
    if "daily" in action or "task" in action:
        names.extend(("daily.page", "reset.daily_close"))
    if "battle_pass" in action or "rewards" in action:
        names.extend(
            (
                "battle_pass.page",
                "battle_pass.tasks",
                "battle_pass.rewards",
                "battle_pass.close",
                "battle_pass.reward_popup",
                "battle_pass.reward_popup_close",
            )
        )
    if "ring" in action:
        names.extend(
            (
                "ring_page",
                "ring_page_close",
                "ring_sweep_result",
                "ring_battle_result",
                "ring_result_close",
                "ring_match_setup_page",
                "ring_match_start",
                "ring_reward_popup",
            )
        )
    if "trial" in action:
        names.extend(("trial.page", "trial.reward_popup", "reset.trial_close"))
    return tuple(dict.fromkeys(names))


def _parse_martial_ratios(values: Sequence[str]) -> tuple[tuple[int, int], ...]:
    """Extract material counters recognized from the detail-page material ROIs."""

    ratios: list[tuple[int, int]] = []
    for value in values:
        for match in re.finditer(r"(?<!\d)(\d{1,6})\s*/\s*(\d{1,6})(?!\d)", value):
            owned, required = (int(match.group(1)), int(match.group(2)))
            if required > 0:
                ratios.append((owned, required))
    return tuple(ratios)


def _shadow_grid_changed(previous: Any, current: Any) -> bool:
    """Detect a real shadow-grid transition without treating page OCR as progress.

    The exploration page keeps the same ``传送/离开`` labels while a click is
    ignored. Compare the stable grid ROI after the ordered anchor sweep; the
    upper edge is included because a successful move can remove the nearest
    card above the foreground row while leaving the lower cards almost
    unchanged.

    A full-frame pixel ratio is not enough here: the Unity scene continuously
    animates stars, fog, and lighting. Require the change to be concentrated
    in a small number of local blocks, while rejecting a broad low-amplitude
    scene animation. The caller additionally confirms this result on a second
    settled frame before exposing ``shadow_grid_advanced``.
    """

    if previous is None or current is None:
        return False
    try:
        # The live 1280x720 renderer lays out the visible card stack from
        # roughly y=180 through y=600.  Starting at y=300 misses the upper
        # part of a real one-row scroll and turns a successful move into a
        # false postcondition failure.
        before = previous[180:600, 320:960][::8, ::8]
        after = current[180:600, 320:960][::8, ::8]
        if getattr(before, "shape", None) != getattr(after, "shape", None):
            return False
        delta = after.astype("int16") - before.astype("int16")
        absolute = abs(delta)
        if getattr(absolute, "ndim", 0) >= 3:
            changed = (absolute > 18).any(axis=-1)
        else:
            changed = absolute > 18
        ratio = float(changed.mean())
        mean_delta = float(absolute.mean())

        # A genuine card/row transition occupies contiguous local structure.
        # Count occupancy in small blocks instead of relying on a connected
        # component implementation that would add a computer-vision runtime
        # dependency to the Maa agent.
        height, width = changed.shape[:2]
        block_height = 8
        block_width = 8
        active_blocks = 0
        total_blocks = 0
        max_density = 0.0
        for row in range(0, height, block_height):
            for column in range(0, width, block_width):
                block = changed[
                    row : min(height, row + block_height),
                    column : min(width, column + block_width),
                ]
                density = float(block.mean())
                total_blocks += 1
                max_density = max(max_density, density)
                if density >= _SHADOW_GRID_MIN_LOCAL_DENSITY:
                    active_blocks += 1
        if total_blocks == 0:
            return False
        return (
            ratio >= _SHADOW_GRID_MIN_CHANGED_RATIO
            and mean_delta >= _SHADOW_GRID_MIN_MEAN_DELTA
            and max_density >= _SHADOW_GRID_MIN_LOCAL_DENSITY
            and active_blocks / total_blocks <= _SHADOW_GRID_MAX_ACTIVE_BLOCK_RATIO
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _shadow_reward_popup_visible(image: Any) -> bool:
    """Detect the bright reward sheet when transition-frame OCR misses it.

    The final Shadow reward sheet has a stable visual layout on the Android
    renderer: a broad pale-blue horizontal banner occupies the middle of the
    frame while the dimmed game scene remains visible above and below it.
    This is intentionally a conservative visual fallback and is only used
    after the workflow has just executed its bounded exploration move. It
    authorizes the non-destructive blank-area dismissal, never a reward or
    purchase control.
    """

    if image is None:
        return False
    try:
        panel = image[240:470, :]
        upper = image[:220, :]
        lower = image[600:, :]
        if (
            getattr(panel, "ndim", 0) < 3
            or getattr(upper, "ndim", 0) < 3
            or getattr(lower, "ndim", 0) < 3
        ):
            return False
        brightness = panel.astype("float32").mean(axis=-1)
        bright_ratio = float((brightness > 180).mean())
        return (
            bright_ratio >= 0.40
            and float(upper.astype("float32").mean()) <= 45.0
            and float(lower.astype("float32").mean()) <= 30.0
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _dungeon_bag_full_visible(image: Any) -> bool:
    """Detect the full-inventory sweep toast when Android OCR drops its text.

    The current dungeon renderer shows this toast as a centered, high-contrast
    line in the top strip. Keep the visual fallback deliberately narrow and
    conservative: the caller additionally requires the just-authorized
    ``open_sweep_panel`` action and the ``燕王秘陵`` page marker. This helper
    only turns a visible refusal into evidence; it never authorizes an input.
    """

    if image is None:
        return False
    try:
        strip = image[12:68, 380:900]
        if getattr(strip, "ndim", 0) < 3:
            return False
        rgb = strip.astype("int16")
        spread = rgb.max(axis=-1) - rgb.min(axis=-1)
        light_text = (
            (rgb[:, :, 0] >= 170)
            & (rgb[:, :, 1] >= 165)
            & (rgb[:, :, 2] >= 155)
            & (spread <= 80)
        )
        # The toast contains a full sentence, not just a single decorative
        # glyph. A ratio of 2% is well above the clean detail page's roughly
        # 0.7% background highlight ratio on the calibrated 1280x720 frame.
        return float(light_text.mean()) >= 0.02
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _dungeon_sweep_panel_visible(image: Any) -> bool:
    """Recognize the open sweep panel when its page OCR is transiently absent.

    The Android dungeon panel has a large saturated-blue ``开始扫荡`` button
    in the lower-right and a dark three-card body above it.  This fallback is
    consumed only after the task has just authorized ``open_sweep_panel``;
    the visual test therefore exposes a page boundary, never a standalone
    sweep input.
    """

    if image is None:
        return False
    try:
        control = image[515:590, 930:1270]
        cards = image[150:510, 120:1260]
        if (
            getattr(control, "ndim", 0) < 3
            or getattr(cards, "ndim", 0) < 3
            or control.shape[-1] < 3
        ):
            return False
        red = control[..., 0].astype("int16")
        green = control[..., 1].astype("int16")
        blue = control[..., 2].astype("int16")
        blue_button = (blue >= 90) & (blue >= red + 25) & (blue >= green + 10)
        return (
            float(blue_button.mean()) >= 0.35
            and int(blue_button.sum()) >= 5_000
            and float(cards.astype("float32").mean()) <= 105.0
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _shadow_formation_page_visible(image: Any) -> bool:
    """Recognize the Shadow formation page when its OCR title is missed.

    The Android renderer uses a large saturated-blue ``开战`` control in the
    lower-right corner.  The title OCR can disappear during the transition
    from exploration, while the button remains fully rendered.  The
    surrounding page is dark enough that a conservative blue-area check is a
    useful same-frame boundary; callers still gate this fallback to the
    Shadow transition actions and never use it as a standalone input path.
    """

    if image is None:
        return False
    try:
        control = image[545:710, 1060:1280]
        backdrop = image[50:500, 450:830]
        if (
            getattr(control, "ndim", 0) < 3
            or getattr(backdrop, "ndim", 0) < 3
            or control.shape[-1] < 3
        ):
            return False
        red = control[..., 0].astype("int16")
        green = control[..., 1].astype("int16")
        blue = control[..., 2].astype("int16")
        blue_button = (blue >= 90) & (blue >= red + 25) & (blue >= green + 10)
        return (
            float(blue_button.mean()) >= 0.20
            and int(blue_button.sum()) >= 3_000
            and float(backdrop.astype("float32").mean()) <= 95.0
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _reward_popup_visible(image: Any) -> bool:
    """Detect the shared pale-blue reward sheet when OCR misses it.

    Daily and battle-pass claims use the same animated reward overlay.  On
    the live Android renderer the overlay can be fully visible while its OCR
    layer returns no result at all, so a postcondition based only on
    ``恭喜获得`` leaves a successfully claimed task marked as failed.  The
    fallback is deliberately structural: it requires a broad pale-blue
    center banner and a substantially dimmer scene above and below it.  It
    can therefore authorize only the blank-area dismissal of a known reward
    sheet; it never authorizes a claim or purchase.
    """

    if image is None:
        return False
    try:
        # The live battle-pass result is a centered modal. The old detector
        # averaged the entire 1280px-wide strip, so the dimmed game scene
        # overwhelmed the bright modal and made a real claim look missing.
        panel = image[180:540, 400:880]
        body = image[350:530, 420:860]
        upper = image[:180, :]
        lower = image[560:, :]
        # Keep the broad-sheet variant used by older Unity reward layouts.
        # It is deliberately an alternative, not a weaker threshold for the
        # centered battle-pass modal.
        legacy_panel = image[240:470, :]
        legacy_upper = image[:220, :]
        legacy_lower = image[600:, :]
        if (
            getattr(panel, "ndim", 0) < 3
            or getattr(body, "ndim", 0) < 3
            or getattr(upper, "ndim", 0) < 3
            or getattr(lower, "ndim", 0) < 3
            or getattr(legacy_panel, "ndim", 0) < 3
            or getattr(legacy_upper, "ndim", 0) < 3
            or getattr(legacy_lower, "ndim", 0) < 3
            or panel.shape[-1] < 3
        ):
            return False
        panel_rgb = panel.astype("float32")
        body_rgb = body.astype("float32")
        body_brightness = body_rgb.mean(axis=-1)
        pale_body = (
            (body_rgb[:, :, 0] >= 100)
            & (body_rgb[:, :, 1] >= 115)
            & (body_rgb[:, :, 2] >= 120)
        )
        panel_mean = float(panel_rgb.mean())
        body_mean = float(body_rgb.mean())
        upper_mean = float(upper.astype("float32").mean())
        lower_mean = float(lower.astype("float32").mean())
        centered_modal = (
            panel_mean >= 125.0
            and body_mean >= 180.0
            and float((body_brightness >= 170.0).mean()) >= 0.80
            and float(pale_body.mean()) >= 0.80
            and panel_mean - upper_mean >= 55.0
            and panel_mean - lower_mean >= 55.0
        )
        legacy_mean = legacy_panel.astype("float32").mean(axis=-1)
        legacy_sheet = (
            float((legacy_mean > 180.0).mean()) >= 0.40
            and float(legacy_upper.astype("float32").mean()) <= 45.0
            and float(legacy_lower.astype("float32").mean()) <= 30.0
        )
        return centered_modal or legacy_sheet
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _ring_sweep_reward_popup_visible(image: Any) -> bool:
    """Recognize the ring sweep reward sheet when OCR misses its title.

    The ring sweep uses the wide, pale-blue ``恭喜获得`` sheet.  On the live
    Android renderer the sheet can be fully visible while the OCR result is
    still the previous confirmation dialog (or the opponent page), so the
    text-only ``ring_sweep_result`` recognizer is not sufficient.  This
    detector is intentionally more structural than the centered shared
    reward detector because the ring sheet spans almost the full width.

    It is only consumed after the authorized ``confirm_ring_sweep`` action,
    and only authorizes result recognition/blank-area cleanup; it never
    authorizes the sweep or the confirmation click.
    """

    if image is None:
        return False
    try:
        panel = image[240:470, :]
        center = image[270:445, 300:1050]
        upper = image[:220, :]
        lower = image[600:, :]
        if (
            getattr(panel, "ndim", 0) < 3
            or getattr(center, "ndim", 0) < 3
            or getattr(upper, "ndim", 0) < 3
            or getattr(lower, "ndim", 0) < 3
            or panel.shape[-1] < 3
        ):
            return False
        panel_rgb = panel.astype("float32")
        center_rgb = center.astype("float32")
        red = panel_rgb[..., 0]
        green = panel_rgb[..., 1]
        blue = panel_rgb[..., 2]
        pale_blue = (
            (red >= 120)
            & (green >= 155)
            & (blue >= 185)
            & (green >= red + 10)
            & (blue >= green - 5)
        )
        center_red = center_rgb[..., 0]
        center_green = center_rgb[..., 1]
        center_blue = center_rgb[..., 2]
        center_pale_blue = (
            (center_red >= 120)
            & (center_green >= 155)
            & (center_blue >= 185)
            & (center_green >= center_red + 10)
            & (center_blue >= center_green - 5)
        )
        return (
            float(pale_blue.mean()) >= 0.72
            and float(center_pale_blue.mean()) >= 0.80
            and float(panel_rgb.mean()) >= 175.0
            and float(upper.astype("float32").mean()) <= 115.0
            and float(lower.astype("float32").mean()) <= 115.0
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _ring_battle_result_visible(image: Any) -> bool:
    """Recognize the arena battle-result title when Android OCR drops it.

    The current renderer shows a large blue/red result title in the dark
    upper-right band.  It can omit the ``战斗胜利``/``战斗失败`` OCR while the
    result sheet is already settled, which otherwise makes the no-input
    ``wait_ring_battle`` transition poll the same frame forever.  This is
    deliberately a result-only visual proof: it never authorizes matching,
    fighting, or any other consumptive action.
    """

    if image is None:
        return False
    try:
        title = image[80:300, 650:1260]
        if getattr(title, "ndim", 0) < 3 or title.shape[-1] < 3:
            return False
        rgb = title.astype("int16")
        red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        blue_title = (
            (blue >= 80)
            & (blue >= red + 20)
            & (blue >= green + 10)
            & (red <= 150)
        )
        warm_title = (
            (red >= 100)
            & (red >= blue + 20)
            & (red >= green + 5)
            & (blue <= 150)
        )
        title_ink = blue_title | warm_title
        occupied_rows = (title_ink.mean(axis=1) >= 0.08).sum()
        return (
            float(title_ink.mean()) >= 0.08
            and int(occupied_rows) >= 45
            and float(rgb.mean()) <= 115.0
            and float((rgb.mean(axis=-1) < 100).mean()) >= 0.60
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _daily_page_visible(image: Any) -> bool:
    """Recognize the daily list when a transition frame loses OCR.

    The Android renderer can briefly return an empty OCR result one frame
    after the daily page is visibly settled.  The list has several broad
    pale-blue row panels, unlike Launcher or the function panel.  Keep this
    visual fallback structural and only use it for the already-authorized
    ``open_daily_tasks`` navigation postcondition.
    """

    if image is None:
        return False
    try:
        body = image[180:710, 180:1180]
        if getattr(body, "ndim", 0) < 3 or body.shape[-1] < 3:
            return False
        red = body[..., 0].astype("int16")
        green = body[..., 1].astype("int16")
        blue = body[..., 2].astype("int16")
        pale_blue = (
            (red >= 145)
            & (green >= 175)
            & (blue >= 195)
            & (blue >= green)
            & (green >= red + 10)
        )
        if float(pale_blue.mean()) < 0.22:
            return False
        covered_bands = 0
        for row in range(0, pale_blue.shape[0], 20):
            if float(pale_blue[row : row + 20].mean()) >= 0.35:
                covered_bands += 1
        return covered_bands >= 5 and not _reward_popup_visible(image)
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _mail_page_visible(image: Any) -> bool:
    """Recognize the mail sheet when the small title OCR is dropped.

    The current Android renderer keeps the mail body as a large pale-blue
    detail panel beside a stack of pale-blue message rows.  This is a
    page-boundary fallback only; callers gate it to the already-authorized
    ``open_mail`` transition, so it cannot authorize opening or claiming a
    message.
    """

    if image is None:
        return False
    try:
        detail = image[120:600, 520:1100]
        message_list = image[160:525, 200:515]
        if (
            getattr(detail, "ndim", 0) < 3
            or getattr(message_list, "ndim", 0) < 3
            or detail.shape[-1] < 3
            or message_list.shape[-1] < 3
        ):
            return False
        detail_rgb = detail.astype("int16")
        list_rgb = message_list.astype("int16")
        detail_pale = (
            (detail_rgb[..., 0] >= 120)
            & (detail_rgb[..., 1] >= 150)
            & (detail_rgb[..., 2] >= 170)
            & (detail_rgb[..., 1] >= detail_rgb[..., 0] + 10)
            & (detail_rgb[..., 2] >= detail_rgb[..., 1] - 5)
        )
        list_pale = (
            (list_rgb[..., 0] >= 120)
            & (list_rgb[..., 1] >= 150)
            & (list_rgb[..., 2] >= 170)
            & (list_rgb[..., 1] >= list_rgb[..., 0] + 10)
            & (list_rgb[..., 2] >= list_rgb[..., 1] - 5)
        )
        return (
            float(detail_pale.mean()) >= 0.80
            and float(list_pale.mean()) >= 0.45
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _shop_page_visible(image: Any) -> bool:
    """Recognize the shop page when its title/tab OCR is dropped.

    The shop surface has a saturated-blue product grid occupying the center
    and a substantially darker navigation rail on the left.  As with the
    mail fallback, this is only a post-navigation page proof and is never
    used as a business-action target.
    """

    if image is None:
        return False
    try:
        product_grid = image[130:600, 300:1240]
        navigation_rail = image[65:520, 30:265]
        if (
            getattr(product_grid, "ndim", 0) < 3
            or getattr(navigation_rail, "ndim", 0) < 3
            or product_grid.shape[-1] < 3
            or navigation_rail.shape[-1] < 3
        ):
            return False
        grid_rgb = product_grid.astype("int16")
        rail_rgb = navigation_rail.astype("int16")
        blue_grid = (
            (grid_rgb[..., 2] >= 90)
            & (grid_rgb[..., 2] >= grid_rgb[..., 0] + 20)
            & (grid_rgb[..., 2] >= grid_rgb[..., 1] - 5)
        )
        return (
            float(blue_grid.mean()) >= 0.65
            and float(rail_rgb.astype("float32").mean()) <= 80.0
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _welcome_title_visible(image: Any) -> bool:
    """Recognize the game's welcome title when its button OCR is absent.

    The Android client can settle on a nearly solid magenta welcome surface
    with the ``进入游戏`` glyph rendered too small/low-contrast for Maa OCR.
    The broad background is distinctive enough to be a conservative title
    boundary.  Callers use this only to authorize the fixed, non-business
    start-game region; it never authorizes a task action or a purchase.
    """

    if image is None:
        return False
    try:
        interior = image[35:685, 80:1200]
        center = image[100:620, 180:1080]
        if (
            getattr(interior, "ndim", 0) < 3
            or getattr(center, "ndim", 0) < 3
            or interior.shape[-1] < 3
            or center.shape[-1] < 3
        ):
            return False
        interior_rgb = interior.astype("int16")
        center_rgb = center.astype("int16")
        def magenta_ratio(rgb: Any) -> float:
            red = rgb[..., 0]
            green = rgb[..., 1]
            blue = rgb[..., 2]
            return float(
                (
                    (red >= 180)
                    & (blue >= 180)
                    & (green <= 55)
                    & (abs(red - blue) <= 45)
                ).mean()
            )

        return magenta_ratio(interior_rgb) >= 0.78 and magenta_ratio(center_rgb) >= 0.82
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _shadow_left_transfer_layout_visible(image: Any) -> bool:
    """Recognize the Android left-circular transfer sheet conservatively.

    OCR can miss the lower-left ``传送`` label during the sheet's glow/fade,
    while the right-layout OCR ROI can report a false hit from the dimmed map.
    The left layout has a distinctive saturated-blue control occupying the
    lower-left panel and a dark translucent sheet behind it.  This visual
    fallback only authorizes the already-known non-destructive transfer
    control; it is never used on its own for a business-page transition.
    """

    if image is None:
        return False
    try:
        control = image[545:710, 320:500]
        panel = image[50:540, 450:830]
        if (
            getattr(control, "ndim", 0) < 3
            or getattr(panel, "ndim", 0) < 3
            or control.shape[-1] < 3
            or panel.shape[-1] < 3
        ):
            return False
        red = control[..., 0].astype("int16")
        green = control[..., 1].astype("int16")
        blue = control[..., 2].astype("int16")
        blue_control = (blue >= 90) & (blue >= red + 25) & (blue >= green + 10)
        blue_ratio = float(blue_control.mean())
        panel_mean = float(panel.astype("float32").mean())
        return blue_ratio >= 0.20 and int(blue_control.sum()) >= 3_000 and panel_mean <= 95.0
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _same_daily_row(
    row_box: tuple[int, int, int, int] | None,
    status_box: tuple[int, int, int, int] | None,
) -> bool:
    """Keep a daily-row status tied to the row that produced its text."""

    if row_box is None or status_box is None:
        return False
    row_center = row_box[1] + row_box[3] / 2
    status_center = status_box[1] + status_box[3] / 2
    return abs(row_center - status_center) <= 90


def _green_daily_completion(
    image: Any,
    row_box: tuple[int, int, int, int] | None,
) -> bool:
    """Recognize the live green completion tick beside one daily row.

    Some Android frames render the completed state as a green tick without
    the ``已完成`` OCR text.  The row text is still OCR'd reliably, so inspect
    only the bounded status column around that row.  This is deliberately
    conservative and is never used as a purchase or resource authorization.
    """

    if row_box is None or image is None:
        return False
    try:
        _, row_y, _, row_height = row_box
        y0 = max(0, row_y - 50)
        y1 = min(720, row_y + row_height + 50)
        # The right-side completion control is fixed to this column while the
        # daily list scrolls vertically.
        crop = image[y0:y1, 1000:1170]
        if getattr(crop, "ndim", 0) < 3 or crop.shape[-1] < 3:
            return False
        red = crop[..., 0].astype("int16")
        green = crop[..., 1].astype("int16")
        blue = crop[..., 2].astype("int16")
        green_pixels = (green >= 100) & (green >= red + 20) & (green >= blue + 10)
        return int(green_pixels.sum()) >= 80
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _has_ring_page_proof(page_hits: dict[str, int]) -> bool:
    """Require a marker that belongs to the arena surface itself."""

    return any(page_hits.get(marker, 0) == 1 for marker in _RING_PAGE_PROOF_MARKERS)


class MaaAndroidWorkflowDriver:
    """Bridge a Maa custom action to the capture/recognize/authorize engine.

    Recognition is delegated to named TemplateMatch nodes already loaded by
    the selected Android resource. No coordinate is accepted from a pipeline;
    execution uses the box returned by recognition for the same frame.
    """

    def __init__(
        self,
        context: Any,
        runtime_gate: AndroidRuntimeGate | None = None,
    ) -> None:
        try:
            controller = context.tasker.controller
        except AttributeError as exc:
            raise RuntimeError("Maa context has no Android tasker controller") from exc
        self.context = context
        self.controller = controller
        self.runtime_gate = runtime_gate or getattr(context, "android_runtime_gate", None)
        self.gestures = AndroidWorkflowDriver(controller, frame_size=(1280, 720))
        self._sequence = 0
        self._last_frame_id: str | None = None
        self._last_frame_payload: Any = None
        self._shadow_move_baseline: Any = None
        self._shadow_grid_observations = 0
        self._shadow_grid_changed_observations = 0
        self._boxes: dict[str, tuple[str, tuple[int, int, int, int]]] = {}
        self._settle_until = 0.0
        self._last_action_id: str | None = None
        self._boundary_cleanup_active = False
        self._yanwu_selection_confirmed = False
        self._trial_reward_claimed = False
        self._trial_free_confirmed = False
        self._food_overfull_seen = False
        self._martial_configuration_unavailable = False
        self._jianlin_count_value = 1
        self._jianlin_multiplier_value = 1

    def _effective_last_action_id(self) -> str | None:
        return self._last_action_id or getattr(self.context, "_mja_last_action_id", None)

    def _retry_network_timeout(self, *, attempts: int = 3) -> bool:
        """Retry the game's bounded network-timeout dialog through Maa.

        Unity can leave the game surface visible behind this modal.  The
        normal task postcondition therefore cannot distinguish it from a
        stalled page unless the modal is handled explicitly.  Only the
        dialog OCR and its same-frame retry target authorize this input; the
        fixed rectangle is a narrow fallback inside that recognized button
        ROI for the renderer's occasional missing OCR box.
        """

        previous_action_id = self._last_action_id
        try:
            for attempt in range(max(1, attempts)):
                sleep(0.8 if attempt == 0 else 1.2)
                frame = self.capture()
                evidence = self.recognize(
                    frame,
                    ("reset.network_timeout", "reset.network_retry"),
                )
                if evidence.target_hits.get("reset.network_timeout", 0) != 1:
                    return False
                retry = self._boxes.get("reset.network_retry")
                box = retry[1] if retry is not None and retry[0] == frame.frame_id else (
                    830,
                    300,
                    110,
                    220,
                )
                self._last_action_id = "retry_network_timeout"
                self._controller_tap(box)
                self._settle_until = monotonic() + 1.2
            return True
        finally:
            # The next workflow recognition still belongs to the original
            # action and must retain its action-bound fallbacks/postconditions.
            self._last_action_id = previous_action_id

    def _requires_android_home_hud(self) -> bool:
        """Return whether this driver is running against the real Android path.

        Unit-test contexts intentionally construct the adapter without an
        Android runtime gate.  Real Maa Android runs carry either the gate or
        the runner's environment marker; both paths must reject Launcher
        artwork even when the package/activity probe is stale.
        """

        gate = self.runtime_gate
        return bool(
            (
                gate is not None
                and getattr(gate, "device", None) is not None
            )
            or os.environ.get("MJA_CONTROLLER") == "android"
            or os.environ.get("MJA_ANDROID_ADB")
        )

    def _home_boundary_hit(self, evidence: VisualEvidence) -> bool:
        """Accept only a game HUD boundary on the real Android runner."""

        target_hits = evidence.target_hits
        reset_home = target_hits.get("reset.home", 0) == 1
        hud_hit = any(
            target_hits.get(marker, 0) == 1
            for marker in ("home.power_text", "home.quest_text")
        )
        if self._requires_android_home_hud():
            # The decorative home template can drift with map lighting and
            # renderer output.  Keep its stronger fast path, but accept the
            # two fixed-region HUD OCR markers when the template and the
            # top-row 画卷 label are visually similar but below threshold.
            # The live client may render the latter as only ``画`` after an
            # update, while ``武力值`` and the task-panel marker remain
            # stable.  Both are game-HUD regions, so this does not accept a
            # Launcher frame as the task boundary.
            return reset_home and hud_hit or (
                target_hits.get("home.power_text", 0) == 1
                and target_hits.get("home.quest_text", 0) == 1
            ) or (
                target_hits.get("home.painting_scroll_text", 0) == 1
                and target_hits.get("home.power_text", 0) == 1
                and target_hits.get("home.quest_text", 0) == 1
            )
        return reset_home or (
            target_hits.get("home.painting_scroll_text", 0) == 1
            and target_hits.get("home.power_text", 0) == 1
            and target_hits.get("home.quest_text", 0) == 1
        )

    def require_task_boundary(self, task_id: str | None = None) -> None:
        """Require a known game boundary before starting a daily task.

        A Launcher is not a game boundary, but it is a recoverable session
        state when the Unity process has been killed between two independent
        daily jobs.  Restart the app through the Android lifecycle API and
        then let the Maa controller recognize the title/home boundary.  No
        game input is sent through ADB shell commands.
        """

        if self.runtime_gate is not None:
            recoverable = {
                ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                ErrorCode.ANDROID_GAME_PROCESS_DIED,
            }
            # The live emulator can briefly return to Launcher while the Maa
            # controller is attaching.  Recovery itself includes a bounded
            # login/interactive-home gate, but its first visual probe may also
            # race that transition.  Permit two lifecycle recoveries and
            # always re-run the authoritative foreground/process checks before
            # any business action is admitted.
            for attempt in range(3):
                try:
                    self.runtime_gate.require_foreground()
                    device = getattr(self.runtime_gate, "device", None)
                    require_process = getattr(device, "require_game_process", None)
                    if callable(require_process):
                        require_process(self.runtime_gate.package_name)
                    break
                except MJAError as exc:
                    if exc.code not in recoverable or attempt >= 2:
                        raise
                    self.recover_game_ready(restart_if_needed=True)
        # A failed task is intentionally left on its live surface for
        # diagnosis. When the same task is invoked again, preserve that
        # surface and resume from it instead of closing it back to home first.
        # A different task must never inherit that resume point in a shared
        # AggregateDailyWorkflowAction session.
        if task_id is not None:
            try:
                failed_task_id = getattr(self.context, "_mja_failed_task_id", None)
                if failed_task_id in (None, task_id) and self.can_resume_task(task_id):
                    return
            except Exception:
                # A task surface can disappear while the game process is
                # being reclaimed.  Treat that as a boundary miss and let
                # the lifecycle recovery below establish a fresh session.
                pass
        try:
            if self.return_to_home(max_steps=30, check_foreground=False) and (
                self._verify_android_home_boundary()
            ):
                return
        except Exception:
            # ``return_to_home`` is visual best-effort cleanup.  It must not
            # prevent the independent next task from trying a clean app
            # restart when the previous process/surface is wedged.
            pass
        if self.runtime_gate is not None and self.recover_game_ready(restart_if_needed=True):
            return
        suffix = f" for {task_id}" if task_id else ""
        raise MJAError(
            ErrorCode.WORKFLOW_POSTCONDITION_MISSING,
            f"no recognized game task boundary{suffix}",
        )

    def _verify_android_home_boundary(self) -> bool:
        """Require a fresh game HUD frame after Android lifecycle recovery.

        Package/activity checks can briefly report the Unity process as
        foreground while the emulator is still showing Launcher artwork. A
        task must not consume that frame as ``home``: the next workflow would
        otherwise fail before its first action. Keep the extra visual check
        Android-only so lightweight unit-test drivers and the macOS path keep
        their existing boundary contract.
        """

        gate = self.runtime_gate
        if gate is None or getattr(gate, "device", None) is None:
            return True
        # Android may report the Unity package/activity as foreground several
        # seconds before its HUD replaces Launcher artwork.  A single capture
        # here made the first independent task fail nondeterministically at
        # the boundary.  Wait only on visual evidence, never sending input,
        # and keep the retry window finite.
        for attempt in range(8):
            try:
                evidence = self.recognize(
                    self.capture(),
                    (
                        "reset.home",
                        "home.painting_scroll_text",
                        "home.power_text",
                        "home.quest_text",
                    ),
                )
            except Exception:
                evidence = None
            if evidence is not None:
                if self._home_boundary_hit(evidence):
                    return True
            if attempt < 7:
                sleep(1.5)
        return False

    def recover_game_ready(self, *, restart_if_needed: bool = True) -> bool:
        """Restore a live game process and verify a Maa-recognized home state.

        This is the hand-off between independent daily jobs.  It may start or
        restart the Android application, but all visual input after launch is
        still emitted by the Maa ADB controller through ``return_to_home``.
        """

        gate = self.runtime_gate
        if gate is None:
            return False
        device = gate.device
        package_name = gate.package_name
        needs_start = False
        try:
            if device.foreground_package() != package_name:
                needs_start = True
            process_id = getattr(device, "game_process_id", None)
            if callable(process_id) and process_id(package_name) is None:
                needs_start = True
        except MJAError:
            needs_start = True

        def wait_for_game() -> None:
            # The login gate only observes UI/package state. It never clicks
            # an account or verification surface, so it is safe to reuse for
            # a process restart between jobs.
            LoginGate(device.config).wait_until_ready(
                device,
                # Boundary recovery may be entered while Android still
                # reports the Unity package as foreground.  Renderer-only
                # readiness accepts colorful HSF/loading frames and sends
                # the expensive boundary scanner into a dead-end.  Wait for
                # a title/home template before handing the surface to Maa.
                require_interactive=True,
            )
            require_memory = getattr(device, "require_memory_health", None)
            if callable(require_memory):
                require_memory()
            require_process = getattr(device, "require_game_process", None)
            if callable(require_process):
                require_process(package_name)

        def dismiss_stale_daily_reward_popup() -> None:
            """Clear a known daily reward overlay before the login gate.

            A failed daily task deliberately leaves its live surface for
            diagnosis.  If that surface is the shared daily reward sheet,
            the next independent run cannot pass the interactive-home gate
            until the sheet is dismissed.  Require both popup OCR markers and
            use only the existing blank-area Maa tap; never dismiss an
            unrecognized modal during lifecycle recovery.
            """

            try:
                evidence = self.recognize(
                    self.capture(),
                    ("daily.reward_popup", "daily.reward_popup_close"),
                )
            except Exception:
                return
            if evidence.target_hits.get("daily.reward_popup_close", 0) == 1:
                self._controller_tap((1150, 620, 100, 100))
                sleep(1.0)

        def attempt(starter: Any | None) -> bool:
            """Run one lifecycle attempt, including process and visual checks.

            A game can disappear between Android's foreground/package check
            and the process check.  Keep each attempt isolated so a failed
            launch still falls through to the force-stop restart below.
            """

            try:
                if starter is not None:
                    starter(package_name)
                dismiss_stale_daily_reward_popup()
                wait_for_game()
                dismiss_stale_daily_reward_popup()
                return bool(
                    self.return_to_home(
                        max_steps=30,
                        check_foreground=False,
                    )
                    and self._verify_android_home_boundary()
                )
            except Exception:
                return False

        # First preserve the existing fast path: only start the app when the
        # package/process is absent.  Crucially, a failure here must not abort
        # recovery before the restart fallback gets a chance.
        initial_starter = getattr(device, "start_app", None) if needs_start else None
        if attempt(initial_starter):
            return True
        if not restart_if_needed:
            return False

        # An unknown or stale game surface can be safely reloaded at a task
        # boundary; no business action is repeated here. Prefer a clean
        # force-stop restart, then fall back to Maa's normal foreground launch
        # if Android reports the package ready before its Unity surface is
        # actually visible.
        for starter in (
            getattr(device, "restart", None),
            getattr(device, "start_app", None),
        ):
            if callable(starter) and attempt(starter):
                return True
        return False

    def capture(self) -> CapturedFrame:
        remaining = self._settle_until - monotonic()
        if remaining > 0:
            sleep(remaining)
        job = self.controller.post_screencap()
        job.wait()
        if hasattr(job, "succeeded") and not job.succeeded:
            raise RuntimeError("Maa Android screencap failed")
        image = job.get()
        size = _image_size(image)
        self._sequence += 1
        frame_id = f"maa-android:{self._sequence}"
        self._last_frame_id = frame_id
        copy = getattr(image, "copy", None)
        self._last_frame_payload = copy() if callable(copy) else image
        self._boxes.clear()
        return CapturedFrame(frame_id, size, image)

    def recognize(
        self,
        frame: CapturedFrame,
        recognizer_names: Sequence[str],
    ) -> VisualEvidence:
        if frame.frame_id != self._last_frame_id:
            raise RuntimeError("recognition frame is stale")
        image = frame.payload
        if image is None:
            raise RuntimeError("captured frame has no image payload")

        page_hits: dict[str, int] = {}
        target_hits: dict[str, int] = {}
        danger_hits: dict[str, int] = {}
        frame_ids: dict[str, str] = {}
        resources: list[str] = []
        texts: list[str] = []
        martial_ratio_texts: list[str] = []
        last_action_id = self._effective_last_action_id()
        # Resource OCR is intentionally demand-driven by the workflow
        # definition.  Running every inventory recognizer on every frame adds
        # several seconds per step and can make a free task hit the timeout.
        names = tuple(dict.fromkeys(recognizer_names))
        if "home" in names and "home.painting_scroll_text" not in names:
            # The decorative home template changes with world lighting. The
            # top-row 画卷 text is stable on the same main UI and is already
            # the proven home marker used by the painting workflows.
            names = (*names, "home.painting_scroll_text")
        resource_names = {
            "凝晶", "文", "龙井虾仁", "紫色魂玉", "体力", "擂台券", "副本票", "研习材料"
        }
        # Some workflow markers are derived from several same-frame hits and
        # deliberately have no Maa pipeline entry.  Keep them in ``names``
        # for the post-recognition synthesis below, but never ask Maa to run
        # them as native recognizers (which would report
        # ``get_pipeline_data failed`` and leave the task spinning).
        derived_names = frozenset(
            {
                "martial_full_slots",
                "martial_study_button",
                "martial_materials_sufficient",
                "martial_materials_insufficient",
                "shadow_grid_advanced",
                "shadow_grid_stalled",
                "shadow_transfer",
                "shadow_recommended_team",
                "collection_reward_popup",
                "jianlin_postpurchase_surface",
                "resource_entry",
                "break_array.prepare_page",
            }
        )
        for name in names:
            if name in derived_names:
                continue
            detail = self.context.run_recognition(name, image)
            if detail is None:
                continue
            frame_ids[name] = frame.frame_id
            hit = bool(getattr(detail, "hit", False))
            count = 1 if hit else 0
            page_hits[name] = count
            target_hits[name] = count
            if name in resource_names and hit:
                resources.append(name)
            if (
                name == "unknown_dialog"
                or name.startswith("safety.")
                or name
                in {
                    "jianlin_refill_prompt",
                    "jianlin_unknown_currency",
                    "ring_unknown_currency",
                }
            ):
                danger_hits[name] = count
            if name == "food_overfull" and hit:
                # The toast is short-lived. Retain this same-task terminal
                # signal so the next food-page frame can finish successfully
                # even if OCR misses the toast after the transition settles.
                self._food_overfull_seen = True
            # Maa OCR exposes every detected string in ``all_results``.  Those
            # results include unrelated paid prices on a shop page, so they
            # must not become workflow evidence.  Only OCR results that match
            # the recognizer's expected text are actionable evidence.  For a
            # successful recognizer without a filtered list, the best result is
            # the safe fallback.
            results = getattr(detail, "filtered_results", None)
            if results is None:
                results = ()
            if name == "jianlin_stamina_cost_value" and hit:
                # This small numeric ROI can produce a low-confidence glyph
                # fragment alongside the real total. Maa already exposes the
                # highest-confidence OCR candidate as ``best_result``; do not
                # leak the weaker alternatives into workflow evidence.
                best_result = getattr(detail, "best_result", None)
                if best_result is not None:
                    results = (best_result,)
            if not results and hit:
                best_result = getattr(detail, "best_result", None)
                results = (best_result,) if best_result is not None else ()
            for result in results:
                text = getattr(result, "text", None)
                if isinstance(text, str) and text.strip():
                    texts.append(text)
                    if name in {
                        "martial_material_ratio_1",
                        "martial_material_ratio_2",
                        "martial_material_ratio_3",
                        "martial_material_ratio_4",
                    }:
                        martial_ratio_texts.append(text)
                    compact = re.sub(r"\s+", "", text)
                    if name in {"jianlin_count_selected", "jianlin_count_changed"}:
                        match = re.search(r"挑战次数[x×]?(\d{1,2})", compact, re.IGNORECASE)
                        if match:
                            self._jianlin_count_value = int(match.group(1))
                    if name in {
                        "jianlin_multiplier_selected",
                        "jianlin_multiplier_changed",
                    }:
                        match = re.search(r"结算倍率[x×]?([1-3l])", compact, re.IGNORECASE)
                        if match:
                            value = match.group(1).lower()
                            self._jianlin_multiplier_value = 1 if value == "l" else int(value)
            box = getattr(detail, "box", None)
            if hit and box is not None:
                self._boxes[name] = (frame.frame_id, tuple(int(value) for value in box))

        if (
            page_hits.get("trial.page", 0) == 1
            and target_hits.get("trial.free_used", 0) == 1
        ):
            # r22 keeps the ordinary orange 领取 control visible after both
            # Trial actions are complete. ``trial.free_used`` is now the
            # strict same-frame combination of the Trial page, 敬请期待, and
            # the first current-reward quantity being exactly 0. Make that
            # terminal proof authoritative over stale claim-shaped controls.
            for marker in (
                "trial.reward_claim",
                "trial.current_reward_claim",
                "trial.free_claim",
            ):
                page_hits[marker] = 0
                target_hits[marker] = 0
                frame_ids.pop(marker, None)
                self._boxes.pop(marker, None)

        if (
            "break_array.result_close" in names
            and page_hits.get("break_array.result", 0) == 1
            and page_hits.get("break_array.success", 0) == 1
            and page_hits.get("break_array.failure", 0) != 1
            and target_hits.get("break_array.result_close", 0) != 1
        ):
            # r22's full-screen victory card has no 确认/继续 footer.  Its
            # tight same-frame title and game-brand anchors are authoritative,
            # and the lower-right decorative field is the bounded blank-area
            # dismissal used by this result surface.
            target_hits["break_array.result_close"] = 1
            frame_ids["break_array.result_close"] = frame.frame_id
            self._boxes["break_array.result_close"] = (
                frame.frame_id,
                (1040, 600, 160, 70),
            )

        # The r20 formation screen exposed a native ``And`` short-circuit:
        # its first two OCR children and the orange 开战 target matched, but
        # the aggregate page marker disappeared as soon as the duration OCR
        # used the renderer's full ``战斗时长`` wording.  Build the runtime
        # snapshot from the four independently requested, same-frame page
        # anchors instead of trusting the opaque aggregate result.  The
        # strict combat markers remain separate and are never inferred from
        # ``首领战斗`` or other formation text.
        prepare_components = (
            "break_array.prepare_formation",
            "break_array.prepare_boss",
            "break_array.prepare_duration",
            "break_array.prepare_tactics",
        )
        if "break_array.prepare_page" in names:
            prepare_visible = all(
                page_hits.get(marker, 0) == 1 for marker in prepare_components
            )
            if prepare_visible:
                page_hits["break_array.prepare_page"] = 1
                target_hits["break_array.prepare_page"] = 1
                frame_ids["break_array.prepare_page"] = frame.frame_id
                for marker in (
                    "break_array.confirm_transition",
                    "break_array.battle_loading",
                    "break_array.battle",
                ):
                    page_hits[marker] = 0
                    target_hits[marker] = 0
                    frame_ids.pop(marker, None)
                    self._boxes.pop(marker, None)
            elif any(
                page_hits.get(marker, 0) == 1
                for marker in ("break_array.battle_loading", "break_array.battle")
            ):
                # A real combat frame is authoritative in the opposite
                # direction.  Do not retain a decorative orange color hit as
                # a formation-page start target once combat is established.
                page_hits["break_array.prepare_page"] = 0
                target_hits["break_array.prepare_page"] = 0
                frame_ids.pop("break_array.prepare_page", None)
                page_hits["break_array.prepare_start"] = 0
                target_hits["break_array.prepare_start"] = 0
                frame_ids.pop("break_array.prepare_start", None)
                self._boxes.pop("break_array.prepare_start", None)

        if (
            (
                last_action_id == "close_reward_popup"
                or self._trial_reward_claimed
            )
            and not self._trial_free_confirmed
            and "trial.free_claim" in names
            and page_hits.get("trial.page", 0) == 1
            and target_hits.get("trial.free_used", 0) != 1
            and target_hits.get("trial.free_claim", 0) != 1
        ):
            # The free control is rendered as the blue 领取 button on this
            # skin; the adjacent 免费 glyph and the small 0 counter are often
            # absent from OCR. It is safe to synthesize only immediately after
            # the authorized ordinary reward popup was dismissed while the
            # trial page is still visible. Once confirmation is sent, this
            # fallback is disabled.
            page_hits["trial.free_claim"] = 1
            target_hits["trial.free_claim"] = 1
            frame_ids["trial.free_claim"] = frame.frame_id
            self._boxes["trial.free_claim"] = (frame.frame_id, (270, 600, 100, 100))
            # The text requirement belongs to the same action-bound fallback:
            # the live glyph is visibly absent from OCR, but the authorized
            # page-bound control is the 免费领取 control on this skin.
            texts.append("免费")

        # The 传送 selection sheet keeps the exploration scene visible behind
        # it. Its OCR therefore often satisfies the broad exploration and
        # stage markers as well. Treat the narrow, lower-center transfer-sheet
        # recognizer as the authoritative page boundary and suppress those
        # ambiguous markers on this same frame; otherwise opening the sheet
        # can be mistaken for having completed the transfer.
        #
        # The lower-right ``shadow_transfer_right_page`` ROI is different: on
        # the live Android renderer it covers the normal exploration-page
        # 传送 button, not a second transfer sheet. It may not authorize a
        # confirmation merely because the task has just entered exploration.
        # Keep a narrowly gated compatibility path for a renderer that really
        # exposes that layout, but require a transfer action context and the
        # absence of the exploration-page marker.
        transfer_sheet_context = last_action_id in {
            "transfer_shadow_stage",
            "confirm_shadow_transfer",
        }
        right_transfer_sheet_visible = (
            page_hits.get("shadow_transfer_right_page", 0) == 1
            and transfer_sheet_context
            and page_hits.get("shadow_exploration_page", 0) != 1
        )
        if page_hits.get("shadow_transfer_page", 0) == 1 and not transfer_sheet_context:
            page_hits["shadow_transfer_page"] = 0
            target_hits["shadow_transfer_page"] = 0
            frame_ids.pop("shadow_transfer_page", None)
            self._boxes.pop("shadow_transfer_page", None)
            page_hits["shadow_confirm_transfer"] = 0
            target_hits["shadow_confirm_transfer"] = 0
            frame_ids.pop("shadow_confirm_transfer", None)
            self._boxes.pop("shadow_confirm_transfer", None)
        if page_hits.get("shadow_transfer_right_page", 0) == 1 and not right_transfer_sheet_visible:
            page_hits["shadow_transfer_right_page"] = 0
            target_hits["shadow_transfer_right_page"] = 0
            frame_ids.pop("shadow_transfer_right_page", None)
            self._boxes.pop("shadow_transfer_right_page", None)
            page_hits["shadow_confirm_transfer_right"] = 0
            target_hits["shadow_confirm_transfer_right"] = 0
            frame_ids.pop("shadow_confirm_transfer_right", None)
            self._boxes.pop("shadow_confirm_transfer_right", None)

        transfer_sheet_visible = (
            page_hits.get("shadow_transfer_page", 0) == 1
            and transfer_sheet_context
        ) or right_transfer_sheet_visible
        if transfer_sheet_visible:
            for marker in (
                "shadow_exploration_page",
                "shadow_stage_any",
                "shadow_progress_any",
            ):
                page_hits[marker] = 0
                target_hits[marker] = 0
                frame_ids.pop(marker, None)
                self._boxes.pop(marker, None)

        # Selecting an empty slot does not guarantee that the default
        # character/skill is usable. The live detail sheet exposes four
        # material counters; promote all independently OCR'd ratios that are
        # visible on this skill to same-frame evidence. Skills can require two,
        # three, or four counters, so the first two are the minimum contract
        # while every additional recognized counter also participates in the
        # sufficiency decision.
        if (
            "martial_materials_sufficient" in names
            or "martial_materials_insufficient" in names
        ):
            ratios = _parse_martial_ratios(martial_ratio_texts)
            if len(ratios) >= 2:
                sufficient = all(owned >= required for owned, required in ratios)
                marker = (
                    "martial_materials_sufficient"
                    if sufficient
                    else "martial_materials_insufficient"
                )
                page_hits[marker] = 1
                target_hits[marker] = 1
                frame_ids[marker] = frame.frame_id

        # The right-side 领取/已完成 OCR target is shared by every daily row.
        # Keep it only when its recognized box belongs to the exact Jianlin
        # row; otherwise a nearby completed row must not fake Jianlin status.
        if (
            target_hits.get("jianlin_daily_done", 0) == 1
            and target_hits.get("jianlin_daily_row", 0) == 1
            and not _same_daily_row(
                self._boxes.get("jianlin_daily_row", (None, None))[1]
                if self._boxes.get("jianlin_daily_row") is not None
                else None,
                self._boxes.get("jianlin_daily_done", (None, None))[1]
                if self._boxes.get("jianlin_daily_done") is not None
                else None,
            )
        ):
            page_hits["jianlin_daily_done"] = 0
            target_hits["jianlin_daily_done"] = 0
            self._boxes.pop("jianlin_daily_done", None)
        if (
            target_hits.get("jianlin_daily_done", 0) == 1
            and target_hits.get("jianlin_daily_row", 0) != 1
        ):
            page_hits["jianlin_daily_done"] = 0
            target_hits["jianlin_daily_done"] = 0
            self._boxes.pop("jianlin_daily_done", None)

        if (
            "jianlin_daily_done" in names
            and target_hits.get("jianlin_daily_done", 0) != 1
            and target_hits.get("jianlin_daily_row", 0) == 1
        ):
            row_record = self._boxes.get("jianlin_daily_row")
            row_box = row_record[1] if row_record is not None else None
            if _green_daily_completion(image, row_box):
                page_hits["jianlin_daily_done"] = 1
                target_hits["jianlin_daily_done"] = 1
                frame_ids["jianlin_daily_done"] = frame.frame_id
                if row_box is not None:
                    _, row_y, _, row_height = row_box
                    self._boxes["jianlin_daily_done"] = (
                        frame.frame_id,
                        (1000, max(0, row_y - 45), 170, row_height + 90),
                    )

        if (
            "home" in names
            and page_hits.get("home", 0) != 1
            and page_hits.get("home.painting_scroll_text", 0) == 1
        ):
            page_hits["home"] = 1
            target_hits["home"] = 1
            frame_ids["home"] = frame.frame_id
            if "home.painting_scroll_text" in self._boxes:
                self._boxes["home"] = self._boxes["home.painting_scroll_text"]

        # The updated client removed 背包 from the function-panel grid.  The
        # live resource page is opened from the left-side 资源 shortcut on
        # the main HUD.  This is a derived target, not an unconditional click:
        # the current-frame home proof is the authorization boundary and the
        # next frame must still prove the 资源 page before food input.
        if (
            "resource_entry" in names
            and page_hits.get("home", 0) == 1
            and target_hits.get("resource_entry", 0) != 1
        ):
            page_hits["resource_entry"] = 1
            target_hits["resource_entry"] = 1
            frame_ids["resource_entry"] = frame.frame_id
            self._boxes["resource_entry"] = (frame.frame_id, (0, 90, 70, 100))

        # The world HUD and the painting page both contain the word ``画卷``.
        # On the home/world-map surface the restricted home shortcut can
        # therefore make the full-screen painting-page OCR hit as well. Keep
        # the shortcut as the home proof and suppress that ambiguous page hit
        # until the recognized open-painting action has actually occurred.
        if (
            "painting_page" in names
            and page_hits.get("painting_page", 0) == 1
            and page_hits.get("home.painting_scroll_text", 0) == 1
            and self._last_action_id
            not in {"open_painting_scroll", "boundary_collection_close"}
        ):
            page_hits["painting_page"] = 0
            target_hits["painting_page"] = 0
            self._boxes.pop("painting_page", None)

        # The Shadow formation page can render its large blue 开战 button
        # before the title OCR becomes available.  A broad exploration OCR hit
        # is also possible on that transition frame, so establish the more
        # specific formation boundary first and make it authoritative.  This
        # keeps the ordered foreground sweep from clicking formation artwork
        # while the engine is still waiting for its movement postcondition.
        shadow_formation_transition = self._last_action_id in {
            "enter_shadow_stage",
            "advance_shadow_foreground_triplet",
            "battle",
        }
        if (
            shadow_formation_transition
            and "shadow_formation_page" in names
            and page_hits.get("shadow_formation_page", 0) != 1
            and _shadow_formation_page_visible(image)
        ):
            page_hits["shadow_formation_page"] = 1
            target_hits["shadow_formation_page"] = 1
            frame_ids["shadow_formation_page"] = frame.frame_id
            self._boxes["shadow_formation_page"] = (
                frame.frame_id,
                (450, 0, 420, 100),
            )
        if page_hits.get("shadow_formation_page", 0) == 1:
            for marker in (
                "shadow_exploration_page",
                "shadow_transfer_page",
                "shadow_confirm_transfer",
                "shadow_transfer_right_page",
                "shadow_confirm_transfer_right",
                "shadow_foreground_left",
                "shadow_foreground_center",
                "shadow_foreground_right",
                "shadow_transfer",
                "shadow_grid_stalled",
            ):
                page_hits[marker] = 0
                target_hits[marker] = 0
                frame_ids.pop(marker, None)
                self._boxes.pop(marker, None)

        # Some Maa OCR results expose a hit and text but omit the filtered
        # result rectangle on this renderer.  Keep the click bounded to the
        # recognizer's already restricted ROI instead of losing an otherwise
        # valid target box.
        if (
            "shadow_stage_entry" in names
            and target_hits.get("shadow_stage_entry", 0) == 1
            and "shadow_stage_entry" not in self._boxes
        ):
            self._boxes["shadow_stage_entry"] = (
                frame.frame_id,
                (0, 500, 360, 220),
            )
        if page_hits.get("shadow_exploration_page", 0) == 1:
            foreground_boxes = {
                # The reference anchors are (350,532), (493,532), and
                # (636,532) on a 984x768 Computer Use frame.  The Android
                # renderer uses a different game viewport: on the live
                # 1280x720 frame the foreground row is bounded by the two
                # guide lines at roughly x=360 and x=944, so its three lower
                # hit anchors are (448,548), (641,548), and (834,548).
                # Keep the recognition boxes on those same lower hit areas;
                # the old aspect-ratio projection landed on card centers and
                # the 前往 control instead of the foreground ground.
                "shadow_foreground_left": (436, 536, 24, 24),
                "shadow_foreground_center": (629, 536, 24, 24),
                "shadow_foreground_right": (822, 536, 24, 24),
            }
            for marker, box in foreground_boxes.items():
                if marker in names and target_hits.get(marker, 0) == 0:
                    target_hits[marker] = 1
                    page_hits[marker] = 1
                    frame_ids[marker] = frame.frame_id
                    self._boxes[marker] = (frame.frame_id, box)
            if "shadow_transfer" in names and target_hits.get("shadow_transfer", 0) == 0:
                # ``传送`` is a stable, explicit control on the exploration
                # surface. It is not used for normal movement; the workflow
                # only authorizes it after a complete foreground sweep has
                # been proven stalled on a fresh frame.
                target_hits["shadow_transfer"] = 1
                page_hits["shadow_transfer"] = 1
                frame_ids["shadow_transfer"] = frame.frame_id
                self._boxes["shadow_transfer"] = (
                    frame.frame_id,
                    (920, 600, 180, 100),
                )
        if page_hits.get("shadow_transfer_page", 0) == 1 and transfer_sheet_context:
            # The Android renderer has a second transfer-sheet layout in
            # which the actionable 传送 control is a blue circle on the left
            # of the lower panel.  The native OCR box can cover the whole ROI
            # or disappear during the glow animation; keep the click inside
            # that same-frame, page-bounded control instead of reusing the
            # exploration page's lower-right button.
            #
            # The right-layout OCR ROI overlaps dark scene/background pixels
            # on this renderer and can intermittently report a false 传送
            # hit while the left circular layout is actually visible.  The
            # left page has the narrower, more specific evidence, so make it
            # authoritative for this frame.  Otherwise the state machine
            # alternates between the real circle and the empty lower-right
            # area, producing a successful Maa input with no UI transition.
            if page_hits.get("shadow_transfer_right_page", 0) == 1:
                page_hits["shadow_transfer_right_page"] = 0
                target_hits["shadow_transfer_right_page"] = 0
                frame_ids.pop("shadow_transfer_right_page", None)
                self._boxes.pop("shadow_transfer_right_page", None)
                page_hits["shadow_confirm_transfer_right"] = 0
                target_hits["shadow_confirm_transfer_right"] = 0
                frame_ids.pop("shadow_confirm_transfer_right", None)
                self._boxes.pop("shadow_confirm_transfer_right", None)
            if (
                "shadow_confirm_transfer" in names
                and target_hits.get("shadow_confirm_transfer", 0) != 1
            ):
                target_hits["shadow_confirm_transfer"] = 1
                page_hits["shadow_confirm_transfer"] = 1
                frame_ids["shadow_confirm_transfer"] = frame.frame_id
                self._boxes["shadow_confirm_transfer"] = (
                    frame.frame_id,
                    (330, 560, 170, 140),
                )
        elif (
            "shadow_transfer_page" in names
            and "shadow_confirm_transfer" in names
            and transfer_sheet_context
            and _shadow_left_transfer_layout_visible(image)
        ):
            # The visual fallback is intentionally placed before the
            # right-layout branch below. It repairs an OCR miss on the
            # left-circle page and makes the more specific layout evidence
            # authoritative for this frame.
            page_hits["shadow_transfer_page"] = 1
            target_hits["shadow_transfer_page"] = 1
            frame_ids["shadow_transfer_page"] = frame.frame_id
            page_hits["shadow_confirm_transfer"] = 1
            target_hits["shadow_confirm_transfer"] = 1
            frame_ids["shadow_confirm_transfer"] = frame.frame_id
            self._boxes["shadow_transfer_page"] = (
                frame.frame_id,
                (300, 540, 320, 180),
            )
            self._boxes["shadow_confirm_transfer"] = (
                frame.frame_id,
                (330, 560, 170, 140),
            )
            page_hits["shadow_transfer_right_page"] = 0
            target_hits["shadow_transfer_right_page"] = 0
            frame_ids.pop("shadow_transfer_right_page", None)
            self._boxes.pop("shadow_transfer_right_page", None)
            page_hits["shadow_confirm_transfer_right"] = 0
            target_hits["shadow_confirm_transfer_right"] = 0
            frame_ids.pop("shadow_confirm_transfer_right", None)
            self._boxes.pop("shadow_confirm_transfer_right", None)
        if (
            right_transfer_sheet_visible
            and page_hits.get("shadow_transfer_page", 0) != 1
        ):
            # The other layout exposes a rectangular blue 传送 button at the
            # lower right. It is intentionally separate from the exploration
            # marker so the two layouts cannot authorize one another.
            if (
                "shadow_confirm_transfer_right" in names
                and target_hits.get("shadow_confirm_transfer_right", 0) != 1
            ):
                target_hits["shadow_confirm_transfer_right"] = 1
                page_hits["shadow_confirm_transfer_right"] = 1
                frame_ids["shadow_confirm_transfer_right"] = frame.frame_id
                self._boxes["shadow_confirm_transfer_right"] = (
                    frame.frame_id,
                    (900, 560, 360, 160),
                )
        if (
            page_hits.get("shadow_formation_page", 0) == 1
            and "shadow_battle_target" in names
            and target_hits.get("shadow_battle_target", 0) == 0
        ):
            # The large orange button uses a decorative vertical font that
            # Maa OCR can miss.  The independently recognized formation title
            # proves the page, so use its stable lower-right button rectangle.
            target_hits["shadow_battle_target"] = 1
            page_hits["shadow_battle_target"] = 1
            frame_ids["shadow_battle_target"] = frame.frame_id
            self._boxes["shadow_battle_target"] = (
                frame.frame_id,
                (1090, 545, 175, 175),
            )
        if (
            page_hits.get("shadow_formation_page", 0) == 1
            and "shadow_recommended_team" in names
            and target_hits.get("shadow_recommended_team", 0) == 0
        ):
            # The formation page's 推荐阵容 control is a non-consumptive
            # setup action. Keep it page-gated and bounded to the live
            # Android button before starting a difficult floor.
            target_hits["shadow_recommended_team"] = 1
            page_hits["shadow_recommended_team"] = 1
            frame_ids["shadow_recommended_team"] = frame.frame_id
            self._boxes["shadow_recommended_team"] = (
                frame.frame_id,
                (190, 0, 150, 80),
            )

        if (
            page_hits.get("shadow_recommended_team_page", 0) == 1
            and "shadow_use_recommended_team" in names
            and page_hits.get("shadow_formation_page", 0) != 1
            and target_hits.get("shadow_use_recommended_team", 0) == 0
        ):
            # The recommendation surface's blue 使用阵容 button is stable,
            # but its decorative OCR can disappear during the page fade. The
            # dedicated title marker proves that this is the recommendation
            # surface, so keep the fallback bounded to the lower-right button.
            target_hits["shadow_use_recommended_team"] = 1
            page_hits["shadow_use_recommended_team"] = 1
            frame_ids["shadow_use_recommended_team"] = frame.frame_id
            self._boxes["shadow_use_recommended_team"] = (
                frame.frame_id,
                (1020, 550, 240, 150),
            )

        # The food category tab is rendered as an icon-only tab on some
        # Android builds, so OCR can miss its label.  The bag page itself is
        # independently recognized from the visible ``资源`` heading; keep
        # this fallback inside the left tab strip and require that page marker
        # in the same frame.  The narrow box is the second category icon, not
        # the wider top-tab area.
        if (
            page_hits.get("bag_page", 0) == 1
            and "food_category" in names
            and target_hits.get("food_category", 0) == 0
        ):
            page_hits["food_category"] = 1
            target_hits["food_category"] = 1
            frame_ids["food_category"] = frame.frame_id
            self._boxes["food_category"] = (frame.frame_id, (25, 150, 95, 104))

        # The game's top-right function-panel glyph changes with the world
        # lighting filter.  On the world-map variant the normal home marker is
        # not present, so when no other page has evidence this bounded entry
        # remains actionable even if the decorative glyph template misses.
        if (
            "function_panel.open" in names
            and page_hits.get("function_panel.open", 0) != 1
            and (
                page_hits.get("home", 0) == 1
                or not any(
                    page_hits.get(name, 0) == 1
                    for name in names
                    if name not in {"function_panel.open", "home"}
                )
            )
        ):
            page_hits["function_panel.open"] = 1
            target_hits["function_panel.open"] = 1
            frame_ids["function_panel.open"] = frame.frame_id
            self._boxes["function_panel.open"] = (frame.frame_id, (1160, 0, 80, 90))

        # Opening the function panel is a task-owned navigation result.  Its
        # translucent right-side chrome can be missed by TemplateMatch on the
        # first settled frame, even though the panel is visibly present.  Keep
        # this fallback tied to the immediately preceding authorized action;
        # it must never turn an arbitrary screen into a panel.
        if (
            last_action_id == "open_function_panel"
            and "function_panel.page" in names
            and page_hits.get("function_panel.page", 0) != 1
            and page_hits.get("home", 0) != 1
            and not any(danger_hits.values())
        ):
            page_hits["function_panel.page"] = 1
            target_hits["function_panel.page"] = 1
            frame_ids["function_panel.page"] = frame.frame_id
        if (
            "battle_pass.open" in names
            and page_hits.get("battle_pass.open", 0) != 1
            and page_hits.get("home", 0) == 1
        ):
            # The first top-right home shortcut is stable in position while
            # its decorative glyph/OCR varies with the game's lighting.
            page_hits["battle_pass.open"] = 1
            target_hits["battle_pass.open"] = 1
            frame_ids["battle_pass.open"] = frame.frame_id
            self._boxes["battle_pass.open"] = (frame.frame_id, (780, 0, 120, 130))

        if (
            {"painting_scroll_entry", "painting_scroll.open"}.intersection(names)
            and self._last_action_id != "open_painting_scroll"
            and not any(
                page_hits.get(name, 0) == 1
                for name in names
                if name not in {"painting_scroll_entry", "painting_scroll.open", "home"}
            )
        ):
            # The world-map variant has no stable home marker, but the 画卷
            # shortcut remains fixed in the upper-right strip.
            marker = (
                "painting_scroll_entry"
                if "painting_scroll_entry" in names
                else "painting_scroll.open"
            )
            if page_hits.get(marker, 0) != 1:
                page_hits[marker] = 1
                target_hits[marker] = 1
                frame_ids[marker] = frame.frame_id
                self._boxes[marker] = (frame.frame_id, (1080, 0, 120, 130))

        if (
            "painting_scroll_entry" in names
            and self._last_action_id != "open_painting_scroll"
        ):
            # On the home/world-map renderer this shortcut can produce an
            # ambiguous OCR box.  The task requested this known navigation
            # marker and no safety signal is active, so use its bounded
            # shortcut region and verify the resulting page afterward.
            page_hits["painting_scroll_entry"] = 1
            target_hits["painting_scroll_entry"] = 1
            frame_ids["painting_scroll_entry"] = frame.frame_id
            self._boxes["painting_scroll_entry"] = (frame.frame_id, (1080, 0, 120, 130))

        # The painting screen's large map title is rendered during the route
        # transition and its full-screen OCR can miss for one frame.  These
        # fallbacks are only enabled immediately after the corresponding
        # recognized navigation action, and never override a detected home or
        # safety marker.
        if (
            self._last_action_id == "open_painting_scroll"
            and "painting_page" in names
            and page_hits.get("home", 0) != 1
            and not any(
                page_hits.get(name, 0) == 1
                for name in names
                if name not in {"painting_page", "yanwu_world_tab", "yanwu_world_page"}
            )
        ):
            page_hits["painting_page"] = 1
            target_hits["painting_page"] = 1
            frame_ids["painting_page"] = frame.frame_id
        if (
            self._last_action_id == "open_painting_scroll"
            and "yanwu_world_tab" in names
            and page_hits.get("home", 0) != 1
            and page_hits.get("yanwu_world_tab", 0) != 1
        ):
            page_hits["yanwu_world_tab"] = 1
            target_hits["yanwu_world_tab"] = 1
            frame_ids["yanwu_world_tab"] = frame.frame_id
            self._boxes["yanwu_world_tab"] = (frame.frame_id, (0, 100, 350, 120))
        if (
            self._last_action_id == "open_tea_purchase"
            and "quantity_panel" in names
            and page_hits.get("home", 0) != 1
            and page_hits.get("quantity_panel", 0) != 1
        ):
            # The modal title is stable, while OCR/template recognition of
            # this translucent overlay can miss during its fade-in.
            page_hits["quantity_panel"] = 1
            target_hits["quantity_panel"] = 1
            frame_ids["quantity_panel"] = frame.frame_id
            self._boxes["quantity_panel"] = (frame.frame_id, (200, 70, 520, 180))
        if (
            "quantity_panel_title" in names
            and target_hits.get("quantity_panel_title", 0) == 1
            and "quantity_panel" in names
        ):
            # On the live shop the title ``购买物品`` remains visible even
            # when TemplateMatch misses the small cropped title asset. It is
            # the panel's own page boundary, so promote it to the canonical
            # quantity-panel marker in this same frame. If the action-bound
            # template fallback already synthesized the narrow ROI, the
            # stronger title evidence must replace that narrow box with the
            # full modal boundary.
            page_hits["quantity_panel"] = 1
            target_hits["quantity_panel"] = 1
            frame_ids["quantity_panel"] = frame.frame_id
            self._boxes["quantity_panel"] = (frame.frame_id, (200, 70, 850, 560))
        # The current battle-pass renderer presents a claimed item as a
        # centered detail sheet (物品 / 当前拥有) instead of the older
        # ``恭喜获得`` reward banner. Treat that exact item sheet as the
        # battle-pass reward popup and retain the non-destructive blank-area
        # dismissal path.
        if (
            "battle_pass.item_popup" in names
            and target_hits.get("battle_pass.item_popup", 0) == 1
            and "battle_pass.reward_popup" in names
            and page_hits.get("battle_pass.reward_popup", 0) != 1
        ):
            page_hits["battle_pass.reward_popup"] = 1
            target_hits["battle_pass.reward_popup"] = 1
            frame_ids["battle_pass.reward_popup"] = frame.frame_id
            self._boxes["battle_pass.reward_popup"] = (
                frame.frame_id,
                (400, 170, 520, 380),
            )
            if (
                "battle_pass.reward_popup_close" in names
                and target_hits.get("battle_pass.reward_popup_close", 0) != 1
            ):
                page_hits["battle_pass.reward_popup_close"] = 1
                target_hits["battle_pass.reward_popup_close"] = 1
                frame_ids["battle_pass.reward_popup_close"] = frame.frame_id
                self._boxes["battle_pass.reward_popup_close"] = (
                    frame.frame_id,
                    (300, 560, 700, 160),
                )
        if (
            "battle_pass.rewards" in names
            and page_hits.get("battle_pass.rewards", 0) == 1
            and "battle_pass.basic_red_dot_reward" in names
            and target_hits.get("battle_pass.basic_red_dot_reward", 0) != 1
            and "battle_pass.basic_all_claimed" in names
            and target_hits.get("battle_pass.basic_all_claimed", 0) != 1
        ):
            # The live basic track renders claimed cards with checkmarks and
            # omits the literal 已领取 text. Once the basic-row red-dot
            # recognizer has no same-frame hit, the rewards page itself is
            # sufficient proof that there is no remaining basic claim. This
            # fallback is deliberately scoped to the basic-track marker and
            # never treats premium/典藏版 cards as claim targets.
            page_hits["battle_pass.basic_all_claimed"] = 1
            target_hits["battle_pass.basic_all_claimed"] = 1
            frame_ids["battle_pass.basic_all_claimed"] = frame.frame_id
            self._boxes["battle_pass.basic_all_claimed"] = (
                frame.frame_id,
                (150, 320, 700, 150),
            )
        if (
            self._last_action_id == "open_tea_tab"
            and "tea_selected" in names
            and page_hits.get("universal_shop_page", 0) == 1
            and page_hits.get("home", 0) != 1
            and target_hits.get("tea_selected", 0) != 1
        ):
            # The detail title/current-owned text is intermittently missed
            # after the card click, but the action was authorized by the
            # current-frame tea card and the shop page remains visible. Keep
            # the fallback strictly bound to the right-side detail panel.
            page_hits["tea_selected"] = 1
            target_hits["tea_selected"] = 1
            frame_ids["tea_selected"] = frame.frame_id
            self._boxes["tea_selected"] = (frame.frame_id, (820, 100, 430, 230))
        if (
            self._last_action_id == "open_universal_shop"
            and "universal_shop_page" in names
            and page_hits.get("home", 0) != 1
            and page_hits.get("universal_shop_page", 0) != 1
        ):
            page_hits["universal_shop_page"] = 1
            target_hits["universal_shop_page"] = 1
            frame_ids["universal_shop_page"] = frame.frame_id

        if (
            "universal_shop_boundary" in names
            and target_hits.get("universal_shop_boundary", 0) == 1
            and "universal_shop_page" in names
            and page_hits.get("universal_shop_page", 0) != 1
            and page_hits.get("home", 0) != 1
        ):
            # The shop title remains visible after the product list scrolls,
            # while the old universal_shop_page OCR also required 茶叶 to be
            # in the same viewport. Promote the independent title boundary
            # to the canonical page marker so scrolling a product off-screen
            # cannot make the already-open shop disappear.
            page_hits["universal_shop_page"] = 1
            target_hits["universal_shop_page"] = 1
            frame_ids["universal_shop_page"] = frame.frame_id
            boundary_record = self._boxes.get("universal_shop_boundary")
            if boundary_record is not None and boundary_record[0] == frame.frame_id:
                self._boxes["universal_shop_page"] = boundary_record

        # OCR is intentionally the primary recognizer.  The Android renderer
        # still drops small glyphs during transitions, and several old
        # resources contain transparent/empty 80x80 templates.  The bounded
        # fallbacks below only fill a requested marker when its parent page is
        # already visible in this same frame; they never create a page or a
        # danger signal out of thin air.
        def fallback(marker: str, box: tuple[int, int, int, int], *pages: str) -> None:
            if marker not in names:
                return
            if pages and not any(page_hits.get(page, 0) == 1 for page in pages):
                return
            current_box = self._boxes.get(marker)
            if (
                target_hits.get(marker, 0) == 1
                and current_box is not None
                and current_box[0] == frame.frame_id
            ):
                return
            # A native recognizer may report a hit without returning a
            # filtered result rectangle.  In that case the hit is valid
            # evidence, but it is not executable until this same-frame
            # bounded fallback supplies a box.  Also replace stale boxes from
            # an earlier frame instead of allowing a click to use old input
            # coordinates.
            target_hits[marker] = 1
            page_hits[marker] = 1
            frame_ids[marker] = frame.frame_id
            self._boxes[marker] = (frame.frame_id, box)
            if marker == "trial.free_claim":
                # Keep the action-bound fallback consistent with the
                # definition's same-frame 免费 text requirement.
                texts.append("免费")

        if (
            last_action_id == "open_mail"
            and "mail.page" in names
            and page_hits.get("mail.page", 0) != 1
            and page_hits.get("home", 0) != 1
            and _mail_page_visible(image)
        ):
            # The live Android skin can drop the small 邮件数量 OCR while
            # leaving the complete sheet visible.  Promote only this
            # action-bound structural page proof; the existing mail.empty /
            # mail.claim_all recognizers still decide whether any claim is
            # authorized.
            page_hits["mail.page"] = 1
            target_hits["mail.page"] = 1
            frame_ids["mail.page"] = frame.frame_id

        if (
            last_action_id == "open_shop"
            and "shop.page" in names
            and page_hits.get("shop.page", 0) != 1
            and page_hits.get("home", 0) != 1
            and _shop_page_visible(image)
        ):
            # The shop title OCR is similarly intermittent during the
            # transition from the function panel.  This only proves the
            # already-requested shop surface and does not create a purchase
            # target.
            page_hits["shop.page"] = 1
            target_hits["shop.page"] = 1
            frame_ids["shop.page"] = frame.frame_id

        if (
            last_action_id == "open_period_benefits"
            and "shop.period_benefits.page" in names
            and page_hits.get("shop.period_benefits.page", 0) != 1
            and page_hits.get("home", 0) != 1
            and _shop_page_visible(image)
        ):
            # The selected 周期福利 tab can be visually settled while its
            # OCR is absent.  The action is already authorized from shop.page;
            # this fallback only exposes the destination page marker so the
            # free-gift recognizer can make the business decision.
            page_hits["shop.period_benefits.page"] = 1
            target_hits["shop.period_benefits.page"] = 1
            frame_ids["shop.period_benefits.page"] = frame.frame_id

        if (
            last_action_id == "open_sweep_panel"
            and "dungeon_bag_full" in names
            and target_hits.get("dungeon_bag_full", 0) != 1
            and page_hits.get("sweep_panel_page", 0) != 1
            and page_hits.get("yanwangling_title", 0) == 1
            and (
                _dungeon_bag_full_visible(image)
                or target_hits.get("sweep_target", 0) == 1
            )
        ):
            # The live client refuses the sweep on the detail page when the
            # inventory is full. Maa OCR can reduce the centered sentence to
            # one unrelated glyph, and the toast can fade before the first
            # settled post-action frame. In that renderer the stable refusal
            # state is the unchanged detail page with the same sweep target;
            # it is safe to classify only this exact action-bound state as the
            # known full-bag business precondition. The workflow engine maps
            # it to NOT_ELIGIBLE and performs no decomposition or other
            # destructive cleanup.
            page_hits["dungeon_bag_full"] = 1
            target_hits["dungeon_bag_full"] = 1
            frame_ids["dungeon_bag_full"] = frame.frame_id
            self._boxes["dungeon_bag_full"] = (
                frame.frame_id,
                (380, 12, 520, 56),
            )
            texts.append("背包已满，请先进行装备分解后再进行扫荡")

        # The panel close glyph is visually stable but its transparent
        # template can miss on the current Android skin. Once the panel
        # marker itself is recognized, the fixed top-right control is a
        # bounded, non-business boundary action and may be supplied here.
        fallback("reset.panel_close", (1170, 0, 110, 110), "reset.function_panel")

        # A clipped product card may expose its label while hiding enough of
        # the icon for TemplateMatch to fail. The label recognizer is limited
        # to the product grid, and its same-frame box is converted into a
        # compact card-body target. This is only considered for the tea
        # workflow's explicitly requested tea markers, never for detail-panel
        # OCR or a generic shop-page hit.
        if (
            "tea_card_label" in names
            and target_hits.get("tea_card_label", 0) == 1
            and page_hits.get("universal_shop_page", 0) == 1
        ):
            label_record = self._boxes.get("tea_card_label")
            if label_record is not None and label_record[0] == frame.frame_id:
                label_x, label_y, _, _ = label_record[1]
                if label_x < 800:
                    card_box = (
                        max(180, label_x - 20),
                        max(120, label_y - 100),
                        140,
                        150,
                    )
                    marker = (
                        "tea_item_scrolled"
                        if "tea_item_scrolled" in names
                        else "tea_item"
                    )
                    if target_hits.get(marker, 0) != 1:
                        page_hits[marker] = 1
                        target_hits[marker] = 1
                        frame_ids[marker] = frame.frame_id
                        self._boxes[marker] = (frame.frame_id, card_box)

        def visual_reward_popup(
            page_marker: str,
            close_marker: str,
            allowed_actions: frozenset[str],
        ) -> None:
            """Promote a known reward overlay without inventing its source."""

            if page_marker not in names:
                return
            boundary_battle_pass = (
                self._boundary_cleanup_active
                and page_marker == "battle_pass.reward_popup"
                and close_marker == "battle_pass.reward_popup_close"
            )
            if (
                last_action_id is not None
                and last_action_id not in allowed_actions
                and not boundary_battle_pass
            ):
                return
            if page_hits.get("home", 0) == 1 or not _reward_popup_visible(image):
                return
            if target_hits.get(page_marker, 0) != 1:
                page_hits[page_marker] = 1
                target_hits[page_marker] = 1
                frame_ids[page_marker] = frame.frame_id
                self._boxes[page_marker] = (
                    frame.frame_id,
                    (0, 100, 1280, 620),
                )
            if close_marker in names and target_hits.get(close_marker, 0) != 1:
                page_hits[close_marker] = 1
                target_hits[close_marker] = 1
                frame_ids[close_marker] = frame.frame_id
                self._boxes[close_marker] = (
                    frame.frame_id,
                    (300, 560, 700, 160),
                )

        visual_reward_popup(
            "daily.reward_popup",
            "daily.reward_popup_close",
            frozenset(
                {
                    "claim_completed_daily_row",
                    "claim_unlocked_activity_chest",
                    "close_reward_popup",
                }
            ),
        )
        visual_reward_popup(
            "hero.reward_popup",
            "hero.reward_popup_close",
            frozenset({"claim_first_dispatch", "close_reward_popup"}),
        )
        if (
            last_action_id == "claim_all_mail"
            and "mail.reward_popup" in names
            and target_hits.get("mail.reward_popup", 0) != 1
            and target_hits.get("mail.reward_popup_close", 0) == 1
        ):
            # Mail's reward sheet fades in from the same animation as the
            # daily reward sheet. The stable footer ``点击空白处关闭`` can be
            # visible one frame before the ``恭喜获得`` heading, so keep the
            # postcondition truthful only after the authorized mail claim and
            # the same-frame safe close marker are both present.
            page_hits["mail.reward_popup"] = 1
            target_hits["mail.reward_popup"] = 1
            frame_ids["mail.reward_popup"] = frame.frame_id
            self._boxes["mail.reward_popup"] = (
                frame.frame_id,
                (0, 100, 1280, 620),
            )
        if (
            last_action_id == "open_mail"
            and "mail.empty" in names
            and page_hits.get("mail.page", 0) == 1
            and target_hits.get("mail.claim_all", 0) != 1
            and target_hits.get("mail.empty", 0) != 1
        ):
            # On the post-update Android skin the stable "删除已读" footer can
            # be missed by OCR even though the mail page is fully rendered.
            # The claim-all control is an exact, bounded template in the same
            # frame; when that template is absent after the authorized
            # open-mail transition, there is no free mail action to perform.
            # Promote the existing terminal marker only in this action-bound
            # state. No input is sent by the already-complete branch.
            page_hits["mail.empty"] = 1
            target_hits["mail.empty"] = 1
            frame_ids["mail.empty"] = frame.frame_id
            self._boxes["mail.empty"] = (
                frame.frame_id,
                (300, 520, 900, 180),
            )
        # The battle-pass task page itself is a large pale-blue panel and can
        # satisfy the shared reward-sheet pixel heuristic. Prefer its
        # explicit page OCR whenever it is present; only use the visual
        # reward fallback while neither battle-pass content page is visible.
        if not any(
            page_hits.get(marker, 0) == 1
            for marker in ("battle_pass.tasks", "battle_pass.rewards")
        ):
            visual_reward_popup(
                "battle_pass.reward_popup",
                "battle_pass.reward_popup_close",
                frozenset(
                    {
                        "open_battle_pass_tasks",
                        "claim_task_reward",
                        "claim_basic_red_dot_reward",
                        "close_reward_popup",
                    }
                ),
            )

        # The dungeon header is a stable page hand-off, but OCR can miss the
        # two-character ``副本`` label immediately after the top-row entry or a
        # list scroll. The action was already authorized from the home/dungeon
        # surface, so this fallback only covers that exact navigation result;
        # it does not invent a target dungeon or a sweep control.
        if (
            last_action_id in {"open_dungeon", "scroll_dungeon_list"}
            and "dungeon_page" in names
            and page_hits.get("dungeon_page", 0) != 1
            and page_hits.get("home", 0) != 1
        ):
            page_hits["dungeon_page"] = 1
            target_hits["dungeon_page"] = 1
            frame_ids["dungeon_page"] = frame.frame_id
        if page_hits.get("dungeon_page", 0) == 1:
            fallback("dungeon_close", (1160, 0, 100, 90), "dungeon_page")

        # The updated dispatch screen can OCR its large title as ``画卷``
        # even after the authorized 侠客派遣 tap. Its page-specific close
        # template remains reliable, so promote that same-frame evidence to
        # the canonical page marker. The action-bound gate prevents a
        # generic close glyph on the painting map from authorizing a page.
        if (
            last_action_id == "open_hero_dispatch"
            and "hero.dispatch.page" in names
            and page_hits.get("hero.dispatch.page", 0) != 1
            and target_hits.get("hero.dispatch.close", 0) == 1
            and page_hits.get("home", 0) != 1
        ):
            page_hits["hero.dispatch.page"] = 1
            target_hits["hero.dispatch.page"] = 1
            frame_ids["hero.dispatch.page"] = frame.frame_id
            close_record = self._boxes.get("hero.dispatch.close")
            if close_record is not None and close_record[0] == frame.frame_id:
                self._boxes["hero.dispatch.page"] = close_record

        # Opening the battle-pass shortcut can first show the current
        # season's non-purchasing-safe promotional sheet. It is still a
        # verified battle-pass surface: the task may dismiss the sheet and
        # continue to the task/reward tabs. The native popup OCR and its
        # same-frame close marker are required; no generic modal is promoted.
        if (
            last_action_id == "open_battle_pass"
            and "battle_pass.reward_popup" in names
            and target_hits.get("battle_pass.reward_popup", 0) == 1
            and target_hits.get("battle_pass.reward_popup_close", 0) == 1
            and page_hits.get("home", 0) != 1
        ):
            page_hits["battle_pass.page"] = 1
            target_hits["battle_pass.page"] = 1
            frame_ids["battle_pass.page"] = frame.frame_id
            popup_record = self._boxes.get("battle_pass.reward_popup")
            if popup_record is not None and popup_record[0] == frame.frame_id:
                self._boxes["battle_pass.page"] = popup_record

        if last_action_id == "boundary_collection_close":
            fallback("painting_page", (0, 0, 1280, 720))
        if last_action_id == "boundary_food_close":
            fallback("reset.function_panel", (840, 0, 280, 160))
            fallback("reset.panel_close", (1170, 0, 110, 110), "reset.function_panel")

        # Collection and food pages have stable task-owned navigation actions,
        # while their decorative headers are OCR-sensitive. Keep the fallback
        # tied to the immediately preceding task surface and still require the
        # page's own close control before sending boundary input.
        if last_action_id in {
            "open_collection_deployment",
            "claim_all_collection",
        }:
            fallback("collection.page", (0, 0, 420, 110))
        if target_hits.get("food_tab_page", 0) == 1:
            if "consumables_page" in names and target_hits.get("consumables_page", 0) != 1:
                page_hits["consumables_page"] = 1
                target_hits["consumables_page"] = 1
                frame_ids["consumables_page"] = frame.frame_id
            fallback("reset.modal_close", (1160, 0, 100, 100), "food_tab_page")

        # The battle-pass reward surface is a known navigation result. Its
        # large changing artwork can make the title OCR intermittent, but the
        # only producer of this fallback is the task-owned reward-tab action.
        if (
            last_action_id == "open_battle_pass_rewards"
            and "battle_pass.rewards" in names
            and page_hits.get("battle_pass.rewards", 0) != 1
            and page_hits.get("home", 0) != 1
        ):
            page_hits["battle_pass.rewards"] = 1
            target_hits["battle_pass.rewards"] = 1
            frame_ids["battle_pass.rewards"] = frame.frame_id
        if page_hits.get("battle_pass.rewards", 0) == 1:
            fallback("battle_pass.close", (1180, 10, 70, 70), "battle_pass.rewards")

        if (
            last_action_id
            in {
                "open_bag",
                "open_food_category",
                "inspect_food_candidate",
                "eat_longjing_shrimp",
                "confirm_food_buff_replace",
            }
            and any(
                page_hits.get(page, 0) == 1
                for page in ("bag_page", "consumables_page", "food_category", "food_tab_page")
            )
        ):
            fallback(
                "reset.modal_close",
                (1160, 0, 100, 90),
                "bag_page",
                "consumables_page",
                "food_category",
                "food_tab_page",
            )

        # Collection rewards use a stable horizontal 据传太吾旧影 title while
        # the vertical 恭喜获得 heading is frequently split by Android OCR.
        # Either same-frame proof identifies the sheet; closing remains a safe
        # blank-area tap and never targets a reward card.
        if (
            "collection.reward_title" in names
            and target_hits.get("collection.reward_title", 0) == 1
            and "collection.reward_popup" in names
        ):
            page_hits["collection.reward_popup"] = 1
            target_hits["collection.reward_popup"] = 1
            frame_ids["collection.reward_popup"] = frame.frame_id
        if page_hits.get("collection.reward_popup", 0) == 1:
            fallback("collection.popup_close", (350, 580, 600, 140), "collection.reward_popup")
            if "collection_reward_popup" in names:
                page_hits["collection_reward_popup"] = 1
                target_hits["collection_reward_popup"] = 1
                frame_ids["collection_reward_popup"] = frame.frame_id

        if "jianlin_postpurchase_surface" in names and any(
            target_hits.get(marker, 0) == 1
            for marker in (
                "jianlin_stamina_purchase_prompt",
                "jianlin_stamina_purchase_result",
                "jianlin_condensate_selected",
                "jianlin_page",
            )
        ):
            page_hits["jianlin_postpurchase_surface"] = 1
            target_hits["jianlin_postpurchase_surface"] = 1
            frame_ids["jianlin_postpurchase_surface"] = frame.frame_id

        # The arena header is rendered as 擂台 on some Android builds and as
        # 论剑 on others.  The title-only ring_entry recognizer is still
        # page-bounded by the next-state recognizer set; promote it to the
        # canonical page marker so the pure definition does not depend on one
        # localization/skin spelling.
        if (
            "ring_page" in names
            and target_hits.get("ring_entry", 0) == 1
        ):
            page_hits["ring_page"] = 1
            target_hits["ring_page"] = 1
            frame_ids["ring_page"] = frame.frame_id

        # The daily list contains the announcement ``论剑玩法已开启``.  A
        # broad title OCR for the arena therefore fires on the daily page as
        # well, and its generic ``返回/关闭`` OCR can then make boundary
        # cleanup close the wrong surface.  A real arena page must carry at
        # least one arena-only marker; the authorized post-click fallback
        # below handles the short title-missed transition frame.
        if (
            page_hits.get("daily.page", 0) == 1
            and page_hits.get("ring_page", 0) == 1
            and not _has_ring_page_proof(page_hits)
        ):
            page_hits["ring_page"] = 0
            target_hits["ring_page"] = 0
            frame_ids.pop("ring_page", None)
            self._boxes.pop("ring_page", None)

        if (
            last_action_id == "confirm_ring_sweep"
            and "ring_sweep_result" in names
            and target_hits.get("ring_sweep_result", 0) != 1
            and _ring_sweep_reward_popup_visible(image)
        ):
            # The live ring reward sheet is visually unambiguous even when
            # OCR retains the old confirmation text.  Confirmation has
            # already consumed the ticket, so promote only the result and
            # its safe blank-area close target on this same frame.
            page_hits["ring_sweep_result"] = 1
            target_hits["ring_sweep_result"] = 1
            frame_ids["ring_sweep_result"] = frame.frame_id
            self._boxes["ring_sweep_result"] = (
                frame.frame_id,
                (150, 100, 980, 520),
            )

        # The daily-row click is already authorized on the current frame.
        # When the arena title is in its transition animation, both title
        # recognizers can miss for one settled frame.  Derive only the
        # post-navigation page marker, and only when the old daily page is no
        # longer visible; this keeps an ignored click from masquerading as a
        # successful navigation.
        if (
            last_action_id == "open_ring_challenge"
            and "ring_page" in names
            and page_hits.get("ring_page", 0) != 1
            and page_hits.get("daily.page", 0) != 1
        ):
            page_hits["ring_page"] = 1
            target_hits["ring_page"] = 1
            frame_ids["ring_page"] = frame.frame_id
            self._boxes["ring_page"] = (
                frame.frame_id,
                (0, 0, 1280, 180),
            )

        if (
            last_action_id == "buy_tea"
            and "tea_purchase_result" in names
            and target_hits.get("expected_purchase_result", 0) == 1
        ):
            # OCR is an explicit text fallback for the result template. It is
            # only promoted immediately after the authorized purchase action;
            # no generic 当前拥有/茶叶 text can satisfy this proof.
            page_hits["tea_purchase_result"] = 1
            target_hits["tea_purchase_result"] = 1
            frame_ids["tea_purchase_result"] = frame.frame_id
            self._boxes["tea_purchase_result"] = (
                frame.frame_id,
                (560, 260, 260, 200),
            )

        # The replacement dialog is a known same-category food modal.  Its
        # OCR can drop the short 确认 glyph while the dialog and blue button
        # remain visually stable, especially after the fourth use.  Keep OCR
        # as the primary evidence, but promote the two independent templates
        # to the canonical prompt/confirm markers only when both recognizers
        # refer to this exact modal.  This preserves the safety boundary: a
        # lone generic confirmation button never authorizes a food action.
        prompt_template_hit = (
            target_hits.get("food_buff_replace_prompt_template", 0) == 1
        )
        confirm_template_hit = (
            target_hits.get("food_buff_replace_confirm_template", 0) == 1
        )
        if prompt_template_hit and "food_buff_replace_prompt" in names:
            target_hits["food_buff_replace_prompt"] = 1
            page_hits["food_buff_replace_prompt"] = 1
            frame_ids["food_buff_replace_prompt"] = frame.frame_id
            self._boxes["food_buff_replace_prompt"] = self._boxes.get(
                "food_buff_replace_prompt_template",
                (frame.frame_id, (300, 180, 680, 370)),
            )
        if confirm_template_hit and "food_buff_replace_confirm" in names:
            target_hits["food_buff_replace_confirm"] = 1
            page_hits["food_buff_replace_confirm"] = 1
            frame_ids["food_buff_replace_confirm"] = frame.frame_id
            self._boxes["food_buff_replace_confirm"] = self._boxes.get(
                "food_buff_replace_confirm_template",
                (frame.frame_id, (813, 482, 130, 42)),
            )

        # The food workflow uses a live TemplateMatch for the verified
        # third-row/fourth-column 龙井虾仁 card.  Do not synthesize a target
        # box or scan other inventory slots here; execution must use the
        # recognizer box returned for this frame.
        # After a second and later use, the game shows an explicit same-food
        # buff-replacement prompt instead of the consumables page.  Treat that
        # recognized prompt as the eat action's result so the workflow can
        # authorize its separate 确认 action on the next frame.
        if (
            self._last_action_id == "eat_longjing_shrimp"
            and "consumables_page" in names
            and target_hits.get("consumables_page", 0) != 1
            and target_hits.get("food_buff_replace_prompt", 0) == 1
        ):
            page_hits["consumables_page"] = 1
            target_hits["consumables_page"] = 1
            frame_ids["consumables_page"] = frame.frame_id

        # Maa_bbb models a modal confirmation button as an independent node
        # in the same ``next`` branch as the action result.  On this renderer
        # the full prompt OCR can miss a line or its right edge even though
        # the blue 确认 button and the full-screen result OCR are both clear.
        # Promote that same-frame combination to the prompt page marker so the
        # workflow can authorize the bounded confirm click without inventing
        # a modal from a button seen on an unrelated page.
        if (
            self._last_action_id == "eat_longjing_shrimp"
            and "food_buff_replace_prompt" in names
            and "food_buff_replace_confirm" in names
            and target_hits.get("food_buff_replace_prompt", 0) != 1
            and target_hits.get("food_buff_replace_confirm", 0) == 1
            and target_hits.get("food_use_result", 0) == 1
        ):
            page_hits["food_buff_replace_prompt"] = 1
            target_hits["food_buff_replace_prompt"] = 1
            frame_ids["food_buff_replace_prompt"] = frame.frame_id
            self._boxes["food_buff_replace_prompt"] = (
                frame.frame_id,
                (380, 270, 520, 150),
            )

        # Food use returns to the consumables page. The same postcondition is
        # also accepted for the replacement prompt and the short-lived
        # "吃得太撑" terminal toast.
        if (
            self._last_action_id in {"eat_longjing_shrimp", "confirm_food_buff_replace"}
            and "food_use_result" in names
            and target_hits.get("food_use_result", 0) != 1
            and (
                target_hits.get("food_buff_replace_prompt", 0) == 1
                or prompt_template_hit
                or page_hits.get("consumables_page", 0) == 1
                or target_hits.get("food_overfull", 0) == 1
            )
        ):
            page_hits["food_use_result"] = 1
            target_hits["food_use_result"] = 1
            frame_ids["food_use_result"] = frame.frame_id

        if (
            "food_overfull" in names
            and self._food_overfull_seen
            and target_hits.get("food_overfull", 0) != 1
        ):
            target_hits["food_overfull"] = 1
            page_hits["food_overfull"] = 1
            frame_ids["food_overfull"] = frame.frame_id

        fallback("open_dungeon", (1040, 0, 100, 100), "home")
        fallback("dungeon_entry", (1040, 0, 100, 100), "home")
        fallback("dungeon_close", (1160, 0, 100, 90), "dungeon_page")
        fallback("yanwangling_master_selected", (60, 560, 210, 130), "dungeon_page")
        # The live 1.6 detail page renders 扫荡 as a narrow blue button around
        # (1025, 615). The old 300x160 fallback put its center on the
        # button's top border, which authorized the action but could leave the
        # Unity page unchanged. Keep the fallback bounded to the actual
        # control interior so the Maa tap lands on the clickable surface.
        fallback("sweep_target", (970, 595, 120, 45), "yanwangling_title")
        if (
            last_action_id in {None, "open_sweep_panel", "assign_sweep_ticket"}
            and "sweep_panel_page" in names
            and page_hits.get("sweep_panel_page", 0) != 1
            and page_hits.get("home", 0) != 1
            and _dungeon_sweep_panel_visible(image)
        ):
            page_hits["sweep_panel_page"] = 1
            target_hits["sweep_panel_page"] = 1
            frame_ids["sweep_panel_page"] = frame.frame_id
            self._boxes["sweep_panel_page"] = (
                frame.frame_id,
                (120, 150, 1140, 440),
            )
        fallback("ticket_plus", (1200, 370, 80, 100), "sweep_panel_page")
        fallback("start_sweep", (930, 500, 330, 150), "sweep_panel_page")
        if (
            last_action_id == "assign_sweep_ticket"
            and "assigned_ticket_counter_changed" in names
            and page_hits.get("sweep_panel_page", 0) == 1
            and target_hits.get("assigned_ticket_counter_changed", 0) != 1
            and target_hits.get("start_sweep", 0) == 1
        ):
            # On the current Android build the numeric counter changes to
            # ``6(-6)`` after the bounded plus-tap loop, but Maa's OCR node
            # frequently misses that small animated glyph.  The same-frame
            # blue 开始扫荡 control is an independent proof that the panel
            # accepted the assignment; promote only this post-action marker,
            # never on an untouched panel.
            page_hits["assigned_ticket_counter_changed"] = 1
            target_hits["assigned_ticket_counter_changed"] = 1
            frame_ids["assigned_ticket_counter_changed"] = frame.frame_id
            self._boxes["assigned_ticket_counter_changed"] = (
                frame.frame_id,
                (770, 510, 170, 80),
            )
        fallback("confirm_sweep", (780, 430, 240, 150), "normal_sweep_confirm_page")
        fallback("ring_start", (980, 500, 290, 120), "ring_page")
        # The updated client inserts a 队伍配置 page before matchmaking.
        # Keep this target scoped to that page so it cannot be mistaken for
        # the old opponent-card action.
        fallback("ring_match_start", (1000, 520, 280, 190), "ring_match_setup_page")
        fallback("ring_sweep", (0, 570, 250, 140), "ring_opponent_page")
        # A current client update can open directly on the battle-preparation
        # page. Never manufacture an opponent-card target from the broad
        # opponent-page fallback while any battle surface is visible.
        if not any(
            page_hits.get(marker, 0) == 1
            for marker in (
                "ring_battle_prepare_page",
                "ring_ready",
                "ring_battle_loading",
                "ring_fight_page",
                "ring_match_setup_page",
            )
        ):
            fallback("ring_fight_target", (800, 140, 440, 150), "ring_opponent_page")
        fallback("ring_sweep_confirm", (760, 360, 460, 180), "ring_sweep_prompt")
        if (
            "ring_battle_result" in names
            and page_hits.get("ring_battle_result", 0) != 1
            and _ring_battle_result_visible(image)
        ):
            # The updated result page can be visually settled before its
            # title/footer OCR becomes available. Promote only the result
            # surface and its safe blank-area close target; this branch never
            # creates an opponent or battle-start target.
            page_hits["ring_battle_result"] = 1
            target_hits["ring_battle_result"] = 1
            frame_ids["ring_battle_result"] = frame.frame_id
            self._boxes["ring_battle_result"] = (
                frame.frame_id,
                (150, 100, 980, 520),
            )
            if "ring_result_close" in names and target_hits.get(
                "ring_result_close", 0
            ) != 1:
                target_hits["ring_result_close"] = 1
                frame_ids["ring_result_close"] = frame.frame_id
                self._boxes["ring_result_close"] = (
                    frame.frame_id,
                    (350, 580, 600, 140),
                )
        # The result footer is not a global ring affordance.  It only exists
        # on a recognized result surface; leaving this fallback ungated makes
        # every ordinary opponent list look like a result page during
        # boundary cleanup, which then loops on a harmless blank-area tap.
        fallback("ring_result_close", (350, 580, 600, 140), "ring_battle_result")
        fallback("ring_result_close", (350, 580, 600, 140), "ring_sweep_result")
        if (
            "ring_result_close" in names
            and target_hits.get("ring_result_close", 0) == 1
            and page_hits.get("ring_battle_result", 0) != 1
            and page_hits.get("ring_sweep_result", 0) != 1
        ):
            # The close footer is the stable part of the animated result
            # sheet.  It is OCR-scoped to the result footer ROI, so it is
            # sufficient proof for either ring result page when the changing
            # title/artwork is missed.  Prefer the result surface requested by
            # this frame; boundary cleanup only needs one safe close path.
            result_marker = (
                "ring_battle_result"
                if "ring_battle_result" in names
                else "ring_sweep_result"
            )
            if result_marker in names:
                page_hits[result_marker] = 1
                target_hits[result_marker] = 1
                frame_ids[result_marker] = frame.frame_id
                self._boxes[result_marker] = (
                    frame.frame_id,
                    (150, 100, 980, 520),
                )
        fallback("ring_opponent_close", (1120, 0, 160, 120), "ring_opponent_page")
        fallback("ring_page_close", (1120, 0, 160, 120), "ring_page")
        ring_task_record = self._boxes.get("ring_daily_task_text")
        ring_task_box = ring_task_record[1] if ring_task_record is not None else None
        ring_row_record = self._boxes.get("ring_daily_row")
        ring_done_record = self._boxes.get("ring_daily_done")
        if (
            target_hits.get("ring_daily_done", 0) == 1
            and target_hits.get("ring_daily_task_text", 0) == 1
            and not _same_daily_row(
                ring_task_box,
                ring_done_record[1] if ring_done_record is not None else None,
            )
        ):
            page_hits["ring_daily_done"] = 0
            target_hits["ring_daily_done"] = 0
            self._boxes.pop("ring_daily_done", None)
        if (
            "ring_daily_done" in names
            and target_hits.get("ring_daily_done", 0) != 1
            and target_hits.get("ring_daily_task_text", 0) == 1
            and page_hits.get("daily.page", 0) == 1
            and _green_daily_completion(image, ring_task_box)
        ):
            # The live list renders a completed 擂台 row as a green tick,
            # without the literal 已完成 text. Tie that visual check to the
            # exact row text and its y-position; another completed row cannot
            # prove this task.
            page_hits["ring_daily_done"] = 1
            target_hits["ring_daily_done"] = 1
            frame_ids["ring_daily_done"] = frame.frame_id
            if ring_task_box is not None:
                _, row_y, _, row_height = ring_task_box
                self._boxes["ring_daily_done"] = (
                    frame.frame_id,
                    (950, max(0, row_y - 45), 220, row_height + 90),
                )
        if (
            target_hits.get("ring_daily_done", 0) != 1
            and target_hits.get("ring_daily_row", 0) == 1
            and not _same_daily_row(
                ring_task_box,
                ring_row_record[1] if ring_row_record is not None else None,
            )
        ):
            page_hits["ring_daily_row"] = 0
            target_hits["ring_daily_row"] = 0
            self._boxes.pop("ring_daily_row", None)
        if (
            target_hits.get("ring_daily_row", 0) != 1
            and target_hits.get("ring_daily_task_text", 0) == 1
            and page_hits.get("daily.page", 0) == 1
            and ring_task_box is not None
        ):
            # The list scrolls, so derive the right-side 前往 box from the
            # current frame's exact ring-row OCR y-coordinate. Never use the
            # old fixed first-row y-coordinate as a generic fallback.
            _, row_y, _, row_height = ring_task_box
            row_box = (
                1000,
                max(0, row_y - 45),
                240,
                min(180, max(100, row_height + 90)),
            )
            page_hits["ring_daily_row"] = 1
            target_hits["ring_daily_row"] = 1
            frame_ids["ring_daily_row"] = frame.frame_id
            self._boxes["ring_daily_row"] = (frame.frame_id, row_box)

        fallback("shop.entry", (920, 210, 190, 180), "function_panel.page")
        fallback(
            "daily.reward_popup_close",
            (300, 560, 700, 160),
            "daily.reward_popup",
        )
        if (
            self._last_action_id
            in {"open_daily_tasks", "open_daily_tasks_initial", "open_daily_tasks_verify"}
            and "daily.page" in names
            and page_hits.get("daily.page", 0) != 1
            and page_hits.get("home", 0) != 1
            and page_hits.get("function_panel.page", 0) != 1
            and _daily_page_visible(image)
        ):
            # Preserve the same-frame page boundary after a transient empty
            # OCR result.  This does not run on an arbitrary frame and cannot
            # promote Launcher artwork because it has no daily row panels.
            page_hits["daily.page"] = 1
            target_hits["daily.page"] = 1
            frame_ids["daily.page"] = frame.frame_id
            self._boxes["daily.page"] = (frame.frame_id, (0, 100, 1280, 620))
        if (
            "daily.reward_popup" in names
            and target_hits.get("daily.reward_popup", 0) != 1
            and target_hits.get("daily.reward_popup_close", 0) == 1
        ):
            # The vertical reward banner animates while the bottom
            # "click blank to close" text stays stable. Their same-frame
            # combination is sufficient proof of this non-purchase overlay.
            page_hits["daily.reward_popup"] = 1
            target_hits["daily.reward_popup"] = 1
            frame_ids["daily.reward_popup"] = frame.frame_id
            self._boxes["daily.reward_popup"] = (
                frame.frame_id,
                (130, 180, 130, 350),
            )
        # The updated function panel no longer renders 背包 in the grid. The
        # food definition authorizes the right-toolbar action below and then
        # requires a fresh bag-page recognition. Do not synthesize a grid bag
        # box: the old fallback clicked the 技能 tile.
        # The 日常 shortcut remains in the top row on the updated 1280x720
        # layout; this rectangle covers that tile rather than 武学研习.
        fallback("daily.entry", (1065, 220, 110, 105), "function_panel.page")
        fallback("battle_pass.rewards_tab", (20, 0, 180, 130), "battle_pass.tasks")
        fallback("battle_pass.close", (1180, 10, 70, 70), "battle_pass.rewards")
        fallback("martial_study_entry", (930, 330, 180, 150), "function_panel.page")
        fallback("mail.entry", (1120, 115, 160, 210), "function_panel.page")
        # Keep the fallback on the narrow, live button label. The former
        # broad rectangle centered at (1068, 643) could hit the adjacent
        # system/app surface when OCR missed the shortcut for one frame.
        fallback("trial.open", (986, 640, 50, 28), "home")
        fallback("appraisal.open", (920, 0, 100, 100), "home")
        fallback("shop.period_benefits", (0, 110, 500, 170), "shop.page")
        fallback("shop.gift_tab", (0, 110, 500, 170), "shop.page")
        # The weekly tab is in the horizontal tab strip, not in the gift-card
        # grid below it.  The old fallback clicked the first card on the
        # ``版本限定`` tab, leaving the page unchanged until the workflow
        # timeout.  Keep the fallback inside the live ``每周必买`` tab ROI;
        # native TemplateMatch remains preferred when it returns a box.
        fallback("shop.weekly_must_buy", (500, 70, 160, 80), "shop.gift_tab.page")
        fallback("shop.daily_free_gift", (970, 160, 280, 170), "shop.period_benefits.page")
        fallback("shop.free_gift.dismiss", (400, 580, 500, 140), "shop.free_gift.reward")
        fallback("shop.close", (1160, 0, 100, 100), "shop.page")
        if (
            last_action_id == "dismiss_free_gift_reward"
            and "shop.daily_free_gift_claimed" in names
            and page_hits.get("shop.period_benefits.page", 0) == 1
            and page_hits.get("shop.free_gift.reward", 0) != 1
            and target_hits.get("shop.free_gift.dismiss", 0) != 1
            and target_hits.get("shop.daily_free_gift_claimed", 0) != 1
        ):
            # The Android renderer can show the stable ``已领取`` badge in a
            # low-contrast corner that Maa OCR misses for one or more frames.
            # Promote it only after the authorized reward-dismiss action has
            # removed the reward overlay and the underlying daily-benefits
            # page is recognized in this same fresh frame. This cannot turn a
            # failed click or an arbitrary shop page into a claim.
            page_hits["shop.daily_free_gift_claimed"] = 1
            target_hits["shop.daily_free_gift_claimed"] = 1
            frame_ids["shop.daily_free_gift_claimed"] = frame.frame_id
        # The universal shop is a recognized task surface in the original
        # jianzhichuan workflow (its title is ``玉盟商会``).  It is a common
        # task-boundary page, not a purchase decision: a previous tea task can
        # leave it open before the next task starts.  Maa_bbb closes recognized
        # parent pages at the boundary, so expose the same bounded top-right
        # close target only after this page marker is present.
        fallback(
            "reset.modal_close",
            (1160, 0, 100, 100),
            "universal_shop_boundary",
        )
        fallback(
            "reset.modal_close",
            (1160, 0, 100, 100),
            "bag_page",
            "consumables_page",
            "food_category",
        )
        if (
            last_action_id == "open_trial_sword"
            and "trial.page" in names
            and page_hits.get("trial.page", 0) != 1
            and page_hits.get("home", 0) != 1
        ):
            # The old fallback accepted ``home`` as the parent page, so a
            # missed trial click could manufacture a trial page on the same
            # world-HUD frame.  Only repair the page hand-off after the
            # authorized trial shortcut click and only when home is absent.
            fallback("trial.page", (0, 130, 430, 320))
        if (
            last_action_id == "close_reward_popup"
            and "trial.page" in names
            and page_hits.get("trial.page", 0) != 1
            and page_hits.get("home", 0) != 1
            and not _reward_popup_visible(image)
        ):
            # After either trial reward sheet closes, the game can briefly
            # omit the small 挂机收益/挂机时长 OCR even though the sheet is
            # visibly gone. The close action was already authorized from a
            # trial reward popup; require the overlay to be absent before
            # restoring the trial-page boundary.
            fallback("trial.page", (0, 130, 430, 320))
        if (
            last_action_id == "close_reward_popup"
            and not self._trial_free_confirmed
            and target_hits.get("trial.free_used", 0) != 1
        ):
            # The page-bound fallback above also covers the live frame where
            # both 免费 and the current-reward 0 are missed by OCR.
            # On the live 1280x720 Android page the free control is the
            # separate purple button immediately to the right of the blue
            # ordinary 领取 button (roughly x=280..345).  The previous
            # fallback covered the blue button itself and caused a second
            # ordinary reward popup instead of opening the free prompt.
            fallback("trial.free_claim", (270, 600, 100, 100), "trial.page")
        if target_hits.get("trial.free_used", 0) != 1:
            fallback("trial.reward_claim", (0, 540, 360, 180), "trial.page")
            # Keep the OCR-miss fallback on the same right-hand free control;
            # it must never overlap the ordinary blue 领取 button or revive a
            # control after the strict r22 completion state is visible.
            fallback("trial.free_claim", (270, 600, 100, 100), "trial.page")
        fallback("trial.free_confirm", (700, 350, 500, 250), "trial.free_popup")
        fallback("trial.popup_close", (350, 580, 600, 140), "trial.reward_popup")
        fallback("appraisal.page", (0, 0, 500, 230), "home", "appraisal.open")
        fallback("appraisal.free_once", (300, 520, 680, 180), "appraisal.page")
        if (
            self._last_action_id == "select_yanwu_world"
            and self._yanwu_selection_confirmed
        ):
            # The original workflow continues directly from the selected
            # 偃武世界 map to the lower-left 万用商店 entry. The live map
            # does not always contain the OCR text used by the page marker
            # (冰川森林), so authorize the known map surface after the
            # already-authorized 偃武世界 tab click.
            fallback("yanwu_world_page", (0, 100, 1000, 620))
            fallback(
                "universal_shop_entry",
                (0, 570, 320, 150),
                "yanwu_world_page",
            )
        if (
            self._last_action_id
            in {
                "select_yunzhou",
                "close_yunzhou_currency_purchase",
                "dismiss_yunzhou_reward_popup",
            }
        ):
            # The 云州 map uses the same stable left-side selected-region row
            # as the original workflow. OCR of the small label is intermittent
            # on the Android renderer, so after a known, already-authorized
            # transition use the bounded live page template as the proof of
            # the resulting map surface.
            fallback("yunzhou_world_page", (60, 200, 300, 130))
        if (
            self._last_action_id == "claim_free_appraisal_once"
        ):
            # The appraisal result is a full-screen blurred overlay. Its OCR
            # and close-icon template can both disappear during animation,
            # although the result is visibly present. Enable this fallback
            # only immediately after the protected free appraisal action.
            fallback("appraisal.result_popup", (150, 250, 1000, 430))
            fallback(
                "appraisal.popup_close",
                (1160, 0, 100, 100),
                "appraisal.result_popup",
            )
        fallback("painting_scroll_entry", (1080, 0, 120, 130), "home")
        fallback("painting_scroll.open", (1080, 0, 120, 130), "home")
        fallback("collection.yanwu_world", (0, 100, 350, 140), "painting_scroll.page")
        fallback("collection.open", (0, 520, 320, 160), "yanwu.page")
        fallback("collection.harvest_all", (820, 550, 430, 170), "collection.page")
        fallback("hero.dispatch.close", (1175, 5, 75, 75), "hero.dispatch.page")
        fallback("hero.painting.close", (1175, 5, 75, 75), "painting_page")
        # 侠客派遣 and 蜃影武墟 are adjacent.  Prefer its live OCR box, but
        # keep a narrow painting-page fallback for the renderer that drops the
        # stylized label.  The fallback ends before the neighboring 蜃影武墟
        # icon so it cannot authorize the wrong task.  execute() uses the
        # calibrated interior box below rather than the OCR text baseline.
        fallback("hero_dispatch_entry", _HERO_DISPATCH_ENTRY_BOX, "painting_page")
        if last_action_id == "select_first_visible_dispatch":
            # Selecting a completed row exposes the right-hand 领取 control;
            # the same action is also used for an empty row, whose postcondition
            # is 智能配置.  Keep both fallbacks page-bound and action-bound so
            # a missed OCR label cannot turn a stale control into authorization.
            fallback("hero.claim_button", (950, 520, 300, 100), "hero.dispatch.page")
            fallback("hero.smart_configure", (760, 520, 220, 100), "hero.dispatch.page")
        if last_action_id == "smart_configure_team":
            fallback("hero.dispatch_button", (950, 520, 300, 100), "hero.dispatch.page")
        fallback("shadow_challenge", (1110, 560, 150, 160), "painting_page")
        fallback("shadow_go", (730, 460, 250, 110), "shadow_popup")
        if self._last_action_id == "open_shadow":
            # The verified workflow surface after clicking 蜃影武墟 is the
            # card page titled 蜃影武墟, not the active-card popup. OCR of
            # this large title can miss during the blur transition, so keep a
            # bounded same-action page fallback for the known result surface.
            fallback("shadow_page", (250, 300, 1000, 400))
        fallback("open_yanwu_currency_purchase", (1010, 0, 210, 120), "yanwu_world_page")
        fallback("yanwu_currency_shop", (1010, 0, 210, 120), "yanwu_world_page")
        fallback("yanwu_currency_purchase_target", (300, 120, 900, 500), "yanwu_currency_purchase")
        if (
            "凝晶" in names
            and target_hits.get("凝晶", 0) != 1
            and any(
                page_hits.get(page, 0) == 1
                for page in (
                    "yanwu_currency_purchase",
                    "yunzhou_currency_purchase",
                )
            )
            and any(
                target_hits.get(target, 0) == 1
                for target in (
                    "yanwu_currency_purchase_target",
                    "yunzhou_currency_purchase_target",
                )
            )
        ):
            # Live-account confirmation: the red icon in the bounded 消耗
            # row of both regional purchase panels is 凝晶. Keep this proof
            # page-specific and same-frame; it must never become a generic
            # currency fallback on another shop or purchase dialog.
            page_hits["凝晶"] = 1
            target_hits["凝晶"] = 1
            frame_ids["凝晶"] = frame.frame_id
            resources.append("凝晶")
            self._boxes["凝晶"] = (frame.frame_id, (730, 470, 80, 55))
        if target_hits.get("jianlin_daily_done", 0) != 1:
            fallback("jianlin_entry", (1010, 420, 230, 90), "daily.page")
        if (
            (
                target_hits.get("jianlin_condensate_title", 0) == 1
                or target_hits.get("jianlin_challenge_button", 0) == 1
            )
            and "jianlin_page" in names
            and target_hits.get("jianlin_page", 0) != 1
        ):
            page_hits["jianlin_page"] = 1
            target_hits["jianlin_page"] = 1
            frame_ids["jianlin_page"] = frame.frame_id
        fallback("jianlin_condensate_resource", (0, 210, 280, 150), "jianlin_page")
        if (
            target_hits.get("jianlin_condensate_title", 0) == 1
            and "jianlin_condensate_selected" in names
        ):
            # The selected left card's small subtitle is OCR-sensitive, while
            # the large right-side 铜水将军 title unambiguously identifies the
            # same 凝晶 challenge on this resource page.  Do not use the
            # generic 挑战 button as proof: it is also present when the default
            # 无面剑客/经验 card is selected.
            page_hits["jianlin_condensate_selected"] = 1
            target_hits["jianlin_condensate_selected"] = 1
            frame_ids["jianlin_condensate_selected"] = frame.frame_id
        fallback("jianlin_stamina_plus", (1110, 10, 55, 60), "jianlin_condensate_selected")
        if (
            page_hits.get("jianlin_stamina_purchase_prompt", 0) == 1
            and target_hits.get("jianlin_stamina_amount", 0) == 1
            and target_hits.get("jianlin_stamina_price", 0) == 1
            and "jianlin_stamina_resource" in names
        ):
            # The +80 option renders 紫色魂玉 as its icon, not OCR text.
            # The original workflow authorizes this exact right-hand option
            # only after +80 and price 10 are both present in the same prompt.
            page_hits["jianlin_stamina_resource"] = 1
            target_hits["jianlin_stamina_resource"] = 1
            frame_ids["jianlin_stamina_resource"] = frame.frame_id
            danger_hits["jianlin_refill_prompt"] = 0
            if "紫色魂玉" not in resources:
                resources.append("紫色魂玉")
            if target_hits.get("jianlin_stamina_purchase_confirm", 0) == 1:
                self._boxes["jianlin_stamina_purchase_confirm"] = (
                    frame.frame_id,
                    (680, 385, 135, 55),
                )
        if all(
            target_hits.get(marker, 0) == 1
            for marker in (
                "jianlin_stamina_confirmation_prompt",
                "jianlin_stamina_confirmation_price",
                "jianlin_stamina_confirmation_amount",
                "jianlin_stamina_confirmation_resource",
                "jianlin_stamina_confirmation_confirm",
            )
        ):
            # The original workflow treats this as the second half of the
            # verified +80-for-10 stamina purchase.  Clear only the expected
            # Clear the expected refill-modal marker after the exact
            # confirmation is recognized; danger hits are diagnostic only.
            danger_hits["jianlin_refill_prompt"] = 0
            if "紫色魂玉" not in resources:
                resources.append("紫色魂玉")
        if (
            target_hits.get("jianlin_stamina_purchase_prompt", 0) == 1
            and target_hits.get("jianlin_stamina_amount", 0) == 1
            and target_hits.get("jianlin_stamina_escalated_price", 0) == 1
        ):
            # A 50-cost +80 offer is the game's escalated second purchase.
            # It proves today's 10-cost purchase already happened and only
            # authorizes closing this panel, never another purchase.
            danger_hits["jianlin_refill_prompt"] = 0
        fallback(
            "jianlin_stamina_purchase_confirm",
            (760, 300, 460, 180),
            "jianlin_stamina_purchase_prompt",
        )
        fallback(
            "jianlin_stamina_result_close",
            (1080, 580, 180, 120),
            "jianlin_stamina_purchase_result",
        )
        if (
            last_action_id in {
                "confirm_jianlin_stamina_purchase",
                "dismiss_jianlin_stamina_result",
            }
            and "jianlin_stamina_result_close" in names
            and target_hits.get("jianlin_stamina_result_close", 0) == 1
        ):
            # The live result footer can be OCR-hit without a filtered box
            # while the reward sheet is fading in. The preceding purchase
            # confirmation is the only producer of this result surface, so
            # provide its fixed blank-area close box on that same frame.
            fallback("jianlin_stamina_result_close", (1080, 580, 180, 120))
        if (
            "jianlin_stamina_purchase_result" in names
            and target_hits.get("jianlin_stamina_purchase_result", 0) != 1
            and target_hits.get("jianlin_stamina_result_close", 0) == 1
        ):
            # The reward banner's vertical 恭喜获得 heading can straddle OCR
            # lines.  Its unique 点击空白处关闭 footer is an equivalent marker
            # for this non-purchase result layer.
            page_hits["jianlin_stamina_purchase_result"] = 1
            target_hits["jianlin_stamina_purchase_result"] = 1
            frame_ids["jianlin_stamina_purchase_result"] = frame.frame_id
        fallback("jianlin_count_bar", (500, 390, 520, 80), "jianlin_condensate_selected")
        fallback(
            "jianlin_multiplier_bar",
            (500, 460, 520, 80),
            "jianlin_condensate_selected",
        )
        if page_hits.get("jianlin_condensate_selected", 0) == 1:
            # These are the actual horizontal bars on the 1280x720 Android
            # resource page. OCR identifies their labels, but its text boxes
            # are not the clickable slider tracks.
            if "jianlin_count_bar" in names and target_hits.get("jianlin_count_bar", 0) == 1:
                self._boxes["jianlin_count_bar"] = (
                    frame.frame_id,
                    (925, 485, 285, 42),
                )
            if (
                "jianlin_multiplier_bar" in names
                and target_hits.get("jianlin_multiplier_bar", 0) == 1
            ):
                self._boxes["jianlin_multiplier_bar"] = (
                    frame.frame_id,
                    (925, 405, 285, 42),
                )
        fallback(
            "jianlin_challenge_button",
            (900, 560, 380, 160),
            "jianlin_condensate_selected",
        )
        fallback("jianlin_buy_confirm", (780, 430, 400, 200), "jianlin_page")
        fallback("jianlin_battle_start", (1000, 500, 280, 220), "jianlin_battle_page")
        fallback("jianlin_result_close", (1080, 580, 180, 120), "jianlin_battle_result")
        fallback("jianlin_page_close", (1160, 0, 100, 90), "jianlin_condensate_selected")
        fallback("study_slot_0_action", (750, 240, 220, 220), "martial_page")
        fallback("martial_result_close", (350, 580, 600, 140), "martial_success_result")
        fallback(
            "martial_close",
            (1160, 0, 100, 100),
            "martial_page",
            "martial_claim_progress",
        )
        if (
            last_action_id == "open_martial_study"
            and "martial_page" in names
            and page_hits.get("martial_page", 0) != 1
            and page_hits.get("home", 0) != 1
            and page_hits.get("function_panel.page", 0) != 1
            and any(
                target_hits.get(marker, 0) == 1
                for marker in (
                    "martial_success_card",
                    "martial_candidate_in_progress",
                    "martial_plus_slot_0",
                    "martial_plus_slot_1",
                    "martial_plus_slot_2",
                    "martial_timer_slot_0",
                    "martial_timer_slot_1",
                    "martial_timer_slot_2",
                )
            )
        ):
            # The page title is briefly missed by OCR on the live Android
            # renderer after the function-panel navigation settles.  Do not
            # promote the page from the navigation action alone: require a
            # slot-owned marker that cannot be present on the function panel.
            page_hits["martial_page"] = 1
            target_hits["martial_page"] = 1
            frame_ids["martial_page"] = frame.frame_id
            self._boxes["martial_page"] = (frame.frame_id, (0, 0, 1280, 720))
        if page_hits.get("martial_page", 0) == 1:
            fallback("martial_close", (1160, 0, 100, 100), "martial_page")
        if (
            last_action_id == "study_martial_slot"
            and "martial_study_detail" in names
            and page_hits.get("martial_study_detail", 0) != 1
            and page_hits.get("home", 0) != 1
            and page_hits.get("function_panel.page", 0) != 1
            and (
                target_hits.get("martial_close", 0) == 1
                or target_hits.get("martial_study_action", 0) == 1
                or target_hits.get("martial_breakthrough_action", 0) == 1
                or (
                    target_hits.get("martial_material_ratio_1", 0) == 1
                    and target_hits.get("martial_material_ratio_2", 0) == 1
                )
            )
        ):
            # A study click keeps the same detail sheet open while the
            # selected skill/material values refresh. During that refresh the
            # title and button OCR can both disappear for a frame. The action
            # was already authorized from this sheet, so a same-frame Martial
            # close/control/material marker is sufficient to retain its
            # detail boundary, while home and function-panel evidence still
            # vetoes the fallback.
            page_hits["martial_study_detail"] = 1
            target_hits["martial_study_detail"] = 1
            frame_ids["martial_study_detail"] = frame.frame_id
            self._boxes["martial_study_detail"] = (
                frame.frame_id,
                (500, 100, 730, 540),
            )
        if page_hits.get("martial_study_detail", 0) == 1:
            if "martial_study_button" in names and target_hits.get(
                "martial_study_button", 0
            ) != 1:
                target_hits["martial_study_button"] = 1
                page_hits["martial_study_button"] = 1
                frame_ids["martial_study_button"] = frame.frame_id
                self._boxes["martial_study_button"] = (
                    frame.frame_id,
                    _MARTIAL_ACTION_BUTTON_BOX,
                )

        # A bounded candidate/skill scan can prove that the current account
        # has no safe martial configuration left for this slot. Keep this as
        # explicit same-frame evidence so the definition can report
        # ``not_eligible`` instead of turning a safe refusal into a driver
        # exception (and therefore a false runtime failure).
        if self._martial_configuration_unavailable:
            page_hits["martial_no_sufficient_configuration"] = 1
            target_hits["martial_no_sufficient_configuration"] = 1
            frame_ids["martial_no_sufficient_configuration"] = frame.frame_id
        if (
            last_action_id is not None
            and last_action_id.startswith("open_martial_plus_slot_")
            and "martial_study_detail" in names
            and page_hits.get("martial_study_detail", 0) != 1
            and (
                (
                    page_hits.get("martial_page", 0) == 1
                )
                or any(
                    target_hits.get(marker, 0) == 1
                    for marker in (
                        "martial_study_action",
                        "martial_breakthrough_action",
                    )
                )
            )
        ):
            # The detail title can be absent for one transition frame. The
            # martial page title plus disappearance of the just-opened plus
            # slot, or a button hit in the detail ROI, is a bounded same-frame
            # proof of the detail modal.
            page_hits["martial_study_detail"] = 1
            target_hits["martial_study_detail"] = 1
            frame_ids["martial_study_detail"] = frame.frame_id
        if (
            last_action_id in {None, "study_martial_slot"}
            and "martial_study_detail" in names
            and page_hits.get("martial_study_detail", 0) != 1
            and page_hits.get("martial_page", 0) != 1
            and page_hits.get("martial_claim_progress", 0) == 1
            and page_hits.get("martial_success_result", 0) != 1
            and page_hits.get("home", 0) != 1
            and page_hits.get("function_panel.page", 0) != 1
            and target_hits.get("martial_close", 0) == 1
        ):
            # A retry, or the result of a study click, can remain on the
            # detail modal after its title OCR has dropped. The broad
            # claim-progress OCR plus the martial-only close control
            # identifies that same recoverable surface when no parent page
            # marker is visible.
            page_hits["martial_study_detail"] = 1
            target_hits["martial_study_detail"] = 1
            frame_ids["martial_study_detail"] = frame.frame_id
        if (
            "martial_study_detail" in names
            and page_hits.get("martial_study_detail", 0) == 1
        ):
            if (
                "martial_study_button" in names
                and target_hits.get("martial_study_button", 0) != 1
            ):
                target_hits["martial_study_button"] = 1
                page_hits["martial_study_button"] = 1
                frame_ids["martial_study_button"] = frame.frame_id
                self._boxes["martial_study_button"] = (
                    frame.frame_id,
                    _MARTIAL_ACTION_BUTTON_BOX,
                )
            # Native OCR boxes for the partial 习/破 glyph are similarly too
            # narrow for this Unity control. Preserve the marker hit as
            # authorization, but normalize its current-frame input box to the
            # full button before execute() consumes it.
            for marker in ("martial_study_action", "martial_breakthrough_action"):
                if target_hits.get(marker, 0) == 1:
                    self._boxes[marker] = (frame.frame_id, _MARTIAL_ACTION_BUTTON_BOX)

        # After confirming a breakthrough, the detail sheet can show only the
        # centered in-progress status. Its background still exposes the
        # martial title and plus-slot artwork, which must not authorize the
        # next slot until this sheet is closed. The status recognizer is
        # deliberately located on the lower detail panel; promote the detail
        # boundary and suppress the ambiguous background markers on this frame.
        if (
            "martial_candidate_in_progress" in names
            and target_hits.get("martial_candidate_in_progress", 0) == 1
            and "martial_study_detail" in names
            and (
                last_action_id == "confirm_martial_breakthrough"
                or page_hits.get("martial_study_detail", 0) == 1
                or (
                    page_hits.get("martial_page", 0) != 1
                    and target_hits.get("martial_close", 0) == 1
                )
            )
        ):
            page_hits["martial_study_detail"] = 1
            target_hits["martial_study_detail"] = 1
            frame_ids["martial_study_detail"] = frame.frame_id
            self._boxes["martial_study_detail"] = (
                frame.frame_id,
                (500, 100, 730, 540),
            )
            for marker in (
                "martial_page",
                "martial_claim_progress",
                "martial_study_entry",
                "martial_plus_slot_0",
                "martial_plus_slot_1",
                "martial_plus_slot_2",
            ):
                page_hits[marker] = 0
                target_hits[marker] = 0
                frame_ids.pop(marker, None)
                self._boxes.pop(marker, None)

        # A no-op martial run is complete only when all three visible slots
        # independently show countdowns and no slot still exposes the plus
        # target.  Keep this derived marker same-frame so a single missed OCR
        # glyph cannot turn a partially configured page into success.
        if (
            "martial_full_slots" in names
            and page_hits.get("martial_page", 0) == 1
            and all(
                target_hits.get(marker, 0) == 1
                for marker in (
                    "martial_timer_slot_0",
                    "martial_timer_slot_1",
                    "martial_timer_slot_2",
                )
            )
            and not any(
                target_hits.get(marker, 0) == 1
                for marker in (
                    "martial_plus_slot_0",
                    "martial_plus_slot_1",
                    "martial_plus_slot_2",
                )
            )
        ):
            page_hits["martial_full_slots"] = 1
            target_hits["martial_full_slots"] = 1
            frame_ids["martial_full_slots"] = frame.frame_id

        if self._last_action_id == "open_appraisal":
            fallback("appraisal.page", (0, 0, 500, 230))
        if self._last_action_id == "open_collection_deployment":
            # The live collection header is OCR-unreliable on the Android
            # renderer. The navigation action was already authorized by the
            # current-frame 偃武世界/采集入口 evidence; retain this fallback
            # only for the post-action page marker.
            fallback("collection.page", (0, 0, 420, 110))
        if self._last_action_id == "open_ring_attempt_mode":
            if not any(
                page_hits.get(marker, 0) == 1
                for marker in (
                    "ring_battle_prepare_page",
                    "ring_ready",
                    "ring_battle_loading",
                    "ring_fight_page",
                    "ring_match_setup_page",
                )
            ):
                fallback("ring_opponent_page", (0, 0, 1280, 720))
        if self._last_action_id == "start_ring_matching":
            # A successful tap enters a network-backed matching animation.
            # Use a bounded loading fallback only after the setup page has
            # disappeared; the native OCR remains authoritative whenever it
            # can see the explicit 匹配中 text or a result surface.
            if (
                page_hits.get("ring_match_setup_page", 0) != 1
                and page_hits.get("ring_page", 0) != 1
                and page_hits.get("ring_battle_result", 0) != 1
            ):
                fallback("ring_battle_loading", (0, 0, 1280, 720))

        # The welcome screen's large magenta background is stable, while the
        # small bottom ``进入游戏`` text is intermittently invisible to Maa
        # OCR.  Keep this fallback limited to the three non-business title
        # recognizers and to their fixed start ROI.  The actual input remains
        # the existing Maa drag-tap path in ``return_to_home``/``execute``.
        if _welcome_title_visible(image):
            for marker in (
                "reset.start_game",
                "reset.start_game_welcome",
                "reset.start_game_button",
            ):
                if marker in names and target_hits.get(marker, 0) != 1:
                    page_hits[marker] = 1
                    target_hits[marker] = 1
                    frame_ids[marker] = frame.frame_id
                    self._boxes[marker] = (
                        frame.frame_id,
                        (430, 600, 420, 100),
                    )
            if any(
                target_hits.get(marker, 0) == 1
                for marker in (
                    "reset.start_game",
                    "reset.start_game_welcome",
                    "reset.start_game_button",
                )
            ):
                texts.append("进入游戏")

        if self._last_action_id == "fight_ring_opponent":
            fallback("ring_battle_prepare_page", (0, 150, 1280, 570))
        if self._last_action_id == "start_ring_battle":
            fallback("ring_fight_page", (0, 0, 1280, 720))
            if (
                page_hits.get("ring_skip", 0) != 1
                and page_hits.get("ring_battle_result", 0) != 1
            ):
                fallback("ring_battle_loading", (0, 0, 1280, 720))
        if self._last_action_id == "wait_ring_battle":
            # The loading overlay is a real intermediate state. Keep a
            # bounded synthetic marker only while neither the skip control nor
            # a result overlay is visible; once either appears, the native
            # recognizer remains authoritative.
            if (
                page_hits.get("ring_skip", 0) != 1
                and page_hits.get("ring_battle_result", 0) != 1
            ):
                fallback("ring_battle_loading", (0, 0, 1280, 720))
        if self._last_action_id == "skip_ring_battle":
            fallback("ring_battle_result", (150, 100, 980, 520))
        if self._last_action_id == "dismiss_ring_reward":
            # The current client shows a reward sheet first and the full
            # 战斗胜利 page after the blank-area tap. Preserve the result
            # boundary even when the title OCR is briefly missing.
            if page_hits.get("ring_page", 0) != 1:
                fallback("ring_battle_result", (150, 100, 980, 520))
        if (
            self._last_action_id in {"dismiss_ring_reward", "dismiss_ring_result"}
            and page_hits.get("ring_battle_result", 0) == 1
            and page_hits.get("ring_page", 0) != 1
            and target_hits.get("ring_result_close", 0) != 1
        ):
            # The victory screen in the updated client omits the old footer
            # hint, but still closes with the same bounded blank-area tap.
            fallback("ring_result_close", (350, 580, 600, 140), "ring_battle_result")
        if self._last_action_id == "dismiss_ring_result":
            if (
                page_hits.get("ring_page", 0) != 1
                and page_hits.get("ring_battle_result", 0) != 1
                and page_hits.get("ring_sweep_result", 0) != 1
            ):
                fallback("ring_opponent_page", (0, 0, 1280, 720))
        if self._last_action_id == "close_ring_opponents":
            fallback("ring_page", (0, 0, 1280, 180))
        if self._last_action_id == "close_ring_page":
            fallback("daily.page", (0, 100, 1280, 620))
        if self._last_action_id == "start_yanwangling_master_sweep":
            fallback("normal_sweep_confirm_page", (280, 150, 700, 420))
        if self._last_action_id == "confirm_yanwangling_master_sweep":
            fallback("expected_sweep_result", (200, 100, 1000, 520))
            fallback("sweep_result_close", (350, 580, 600, 140), "expected_sweep_result")
        if self._last_action_id == "dismiss_sweep_result":
            fallback("dungeon_page", (0, 0, 500, 240))
            fallback("dungeon_close", (1160, 0, 100, 90), "dungeon_page")
        if self._last_action_id == "study":
            fallback("study_slot_0_action.done", (300, 150, 900, 520))
        if (
            self._last_action_id
            in {"buy_yanwu_currency_max", "buy_yunzhou_currency_max"}
        ):
            # The item-reward overlay hides both the purchase panel and the
            # map labels while it animates in. A vanished purchase page after
            # this bounded, approved purchase is the stable completion signal
            # when vertical 恭喜获得 text has not been emitted by OCR yet.
            for marker in (
                "yanwu_currency_purchase_target.done",
                "yunzhou_currency_purchase_target.done",
            ):
                if (
                    marker in names
                    and page_hits.get("yanwu_currency_purchase", 0) != 1
                    and page_hits.get("yunzhou_currency_purchase", 0) != 1
                ):
                    fallback(marker, (0, 100, 1280, 520))

        # The ring sweep confirmation uses a different close glyph skin and
        # places it in the modal header instead of the normal top-right chrome.
        # OCR the modal text, then keep the actual input bounded to its header
        # close box; never click the orange confirmation button.
        if (
            "reset.confirm_close" in names
            and target_hits.get("reset.confirm_close", 0) == 1
        ):
            self._boxes["reset.confirm_close"] = (
                frame.frame_id,
                (900, 160, 120, 120),
            )

        if (
            "shadow_reward_popup" in names
            and self._last_action_id == "advance_shadow_foreground_triplet"
            and target_hits.get("shadow_reward_popup", 0) != 1
            and _shadow_reward_popup_visible(image)
        ):
            # The final Shadow reward sheet is often still in its fade-in
            # animation when OCR runs. Its pale-blue banner and dimmed game
            # scene are a stronger same-frame proof than a generic popup
            # marker, and the only action authorized from this fallback is
            # the already-safe blank-area dismissal.
            page_hits["shadow_reward_popup"] = 1
            target_hits["shadow_reward_popup"] = 1
            frame_ids["shadow_reward_popup"] = frame.frame_id
            self._boxes["shadow_reward_popup"] = (
                frame.frame_id,
                (0, 100, 1280, 620),
            )

        if "shadow_grid_advanced" in names and self._last_action_id == (
            "advance_shadow_foreground_triplet"
        ):
            # A transition to formation, combat, reward, completion, or home
            # is unambiguous.  Otherwise require a meaningful change in the
            # stable grid ROI; the unchanged exploration page must not satisfy
            # the movement postcondition merely because it still says 传送.
            terminal_advanced = any(
                page_hits.get(marker, 0) == 1
                for marker in (
                    "shadow_formation_page",
                    "shadow_battle_result",
                    "shadow_reward_popup",
                    "shadow_final_prompt",
                    "shadow_challenge.done",
                    "home",
                )
            )
            grid_changed = _shadow_grid_changed(self._shadow_move_baseline, image)
            self._shadow_grid_observations += 1
            if grid_changed:
                self._shadow_grid_changed_observations += 1
            else:
                self._shadow_grid_changed_observations = 0
            advanced = terminal_advanced or self._shadow_grid_changed_observations >= 2
            if advanced:
                page_hits["shadow_grid_advanced"] = 1
                target_hits["shadow_grid_advanced"] = 1
                frame_ids["shadow_grid_advanced"] = frame.frame_id
            elif (
                "shadow_grid_stalled" in names
                and page_hits.get("shadow_exploration_page", 0) == 1
                and target_hits.get("shadow_transfer", 0) == 1
                and self._shadow_grid_observations >= 2
            ):
                # Preserve the failed sweep as explicit evidence so the
                # definition can take its one bounded dead-end recovery
                # branch instead of raising a generic postcondition error.
                page_hits["shadow_grid_stalled"] = 1
                target_hits["shadow_grid_stalled"] = 1
                frame_ids["shadow_grid_stalled"] = frame.frame_id

        evidence = VisualEvidence(
            frame_id=frame.frame_id,
            page_hits=page_hits,
            target_hits=target_hits,
            danger_hits=danger_hits,
            recognizer_frame_ids=frame_ids,
            texts=tuple(texts),
            resource_hits=tuple(resources),
        )
        trace_root = os.environ.get("MJA_DEBUG_DIR")
        if trace_root:
            try:
                trace_path = Path(trace_root) / "android-recognition.jsonl"
                trace_path.parent.mkdir(parents=True, exist_ok=True)
                with trace_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            {
                                "frame": frame.frame_id,
                                "last_action_id": last_action_id,
                                "names": names,
                                "page_hits": page_hits,
                                "target_hits": target_hits,
                                "danger_hits": danger_hits,
                                "resources": resources,
                                "ocr_texts": texts,
                                "martial_ratio_texts": martial_ratio_texts,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except OSError:
                pass
        return evidence

    def _capture_martial_configuration(self) -> VisualEvidence:
        """Capture the current study detail with configuration-only OCR."""

        frame = self.capture()
        return self.recognize(frame, _MARTIAL_CONFIGURATION_RECOGNIZERS)

    def _prepare_martial_study_configuration(
        self,
        *,
        target_action: str = "martial_study_action",
    ) -> bool:
        """Select the first safe candidate/skill before a martial action.

        An empty martial slot opens with a default selection, but that
        selection can have one or more material counters below their
        requirements.  The
        old workflow handled this by trying the nine visible candidates and
        three skills, skipping candidates already in breakthrough and
        accepting only a configuration with all recognized material ratios
        sufficient.  The same bounded
        search is also required before a breakthrough: a prior rejected
        configuration can leave the detail page on an insufficient 破组合.
        Every candidate/skill input is sent through Maa's Android controller
        and every decision is verified by a fresh Maa frame.
        """

        if target_action not in {
            "martial_study_action",
            "martial_breakthrough_action",
        }:
            raise ValueError(f"unsupported martial action: {target_action}")

        evidence = self._capture_martial_configuration()
        if evidence.target_hits.get("martial_materials_sufficient", 0) == 1:
            if evidence.target_hits.get(target_action, 0) == 1:
                return True
        for candidate_box in _MARTIAL_CANDIDATE_BOXES:
            self._controller_tap(candidate_box)
            sleep(0.35)
            candidate_evidence = self._capture_martial_configuration()
            if candidate_evidence.target_hits.get("martial_candidate_in_progress", 0) == 1:
                continue
            for skill_box in _MARTIAL_SKILL_BOXES:
                self._controller_tap(skill_box)
                sleep(0.35)
                evidence = self._capture_martial_configuration()
                if evidence.target_hits.get("martial_candidate_in_progress", 0) == 1:
                    break
                if (
                    evidence.target_hits.get(target_action, 0) == 1
                    and evidence.target_hits.get("martial_materials_sufficient", 0) == 1
                ):
                    return True
        return False

    def execute(self, intent: Any) -> None:
        marker = intent.target_marker
        self._last_action_id = intent.action_id
        setattr(self.context, "_mja_last_action_id", intent.action_id)
        if intent.action_id in {
            "transfer_shadow_stage",
            "confirm_shadow_transfer",
            "confirm_shadow_auto_route",
            "apply_shadow_recommended_team",
            "use_shadow_recommended_team",
            "close_shadow_recommended_team",
        }:
            raise RuntimeError("Shadow transfer/recommendation actions are disabled")
        record = self._boxes.get(marker)
        if (
            intent.action_id
            not in {
                "close_reward_popup",
                "close_appraisal_popup",
                "wait_ring_battle",
                # This action uses a calibrated bounded row after the
                # same-frame painting page and 偃武世界 OCR evidence. The
                # OCR target occasionally has hit=True but no result box;
                # no target box is consumed by this branch.
                "select_yanwu_world",
                # These bounded list scans use a fixed Maa swipe region. The
                # page marker is their visual authorization; a page OCR hit
                # does not need a pointer box of its own.
                "scroll_daily_jianlin",
                "scroll_daily_reward_rows",
                "scroll_tea_list",
            }
            and (record is None or record[0] != self._last_frame_id)
        ):
            raise RuntimeError(f"no current-frame recognition box for {marker}")
        if intent.action_id == "open_function_panel":
            # Keep native navigation bounded to the recognized top-right
            # region and send it through the tasker's single ADB controller.
            sleep(1.0)
            self._controller_tap((1160, 0, 80, 90))
        elif intent.action_id == "open_battle_pass":
            self._controller_tap((780, 0, 120, 130))
        elif intent.action_id in {"open_dungeon", "open_appraisal", "open_trial_sword"}:
            native_boxes = {
                "open_dungeon": (1040, 0, 100, 100),
                "open_appraisal": (920, 0, 100, 100),
            }
            if intent.action_id == "open_trial_sword":
                # Maa's live OCR box is the authoritative hit area for the
                # shortcut.  The previous fixed box was deliberately broad,
                # but its center landed to the right of the actual 试剑 label
                # on the current renderer and could open Android's system
                # surface instead.  Consume the same-frame box so the tap is
                # centered on the button Maa actually recognized.
                self._controller_tap(record[1])
            else:
                self._controller_tap(native_boxes[intent.action_id])
        elif intent.action_id == "scroll_dungeon_list":
            self._controller_swipe((160, 650), (160, 250), duration_ms=1000)
        elif intent.action_id == "open_resource_page":
            # The 1.6 client moved the resource/inventory page out of the
            # function panel.  Consume the same-frame home-authorized target
            # for the left-side 资源 shortcut; bag_page/资源 must be visible
            # before the food-category action is allowed.
            self._controller_tap(record[1])
        elif intent.action_id == "scroll_tea_list":
            # The shop remembers its product-list offset between openings.
            # Re-select 全部, rewind inside the product grid, then perform the
            # single downward row scroll required by the live layout. The
            # next frame still has to prove the tea card before any detail or
            # purchase action is allowed.
            self._controller_tap((65, 110, 110, 70))
            sleep(1.0)
            for _ in range(3):
                self._controller_swipe((500, 270), (500, 500), duration_ms=600)
                sleep(0.25)
            self._controller_swipe((500, 500), (500, 270), duration_ms=800)
        elif intent.action_id == "select_yanwangling":
            self._controller_tap((60, 560, 210, 130))
        elif intent.action_id == "select_yanwu_world":
            self._yanwu_selection_confirmed = True
            self._controller_tap((100, 130, 200, 75))
        elif intent.action_id == "open_hero_dispatch":
            # The current-frame OCR hit authorizes this navigation, while the
            # calibrated interior box reaches the Unity button reliably.  The
            # next workflow state still has to prove hero.dispatch.page; a
            # successful OCR hit on the painting map alone is not completion.
            self._controller_tap(_HERO_DISPATCH_ENTRY_BOX)
        elif intent.action_id in {
            "close_hero_dispatch",
            "close_hero_dispatch_painting",
        }:
            self._controller_tap((1175, 5, 75, 75))
        elif intent.action_id == "select_yanwangling_in_panel":
            self._controller_tap((1060, 370, 190, 100))
        elif intent.action_id == "open_sweep_panel":
            # The detail-page 扫荡 control is an OCR target.  Use its
            # same-frame box instead of silently falling through to no input;
            # the postcondition must prove that the sweep panel actually
            # opened before any ticket is assigned.
            self._controller_tap(record[1])
        elif intent.action_id == "assign_sweep_ticket":
            # The approved dungeon workflow assigns all currently available
            # tickets to 燕王秘陵(大师).  The UI caps the count itself; the
            # bounded repetition is intentionally finite for empty/changed
            # inventories.
            for _ in range(10):
                self._controller_tap(record[1])
                sleep(0.05)
        elif intent.action_id == "start_yanwangling_master_sweep":
            self._controller_tap((930, 500, 330, 150))
        elif intent.action_id == "confirm_yanwangling_master_sweep":
            self._controller_tap((780, 430, 240, 150))
        elif intent.action_id == "dismiss_sweep_result":
            # The normal sweep reward overlay explicitly asks for a blank
            # area click.  Keep that input away from reward cards and send it
            # through the same ADB controller as every other Android action.
            self._controller_tap((1120, 640, 120, 70))
        elif intent.action_id == "close_dungeon":
            self._controller_tap((1160, 0, 100, 90))
        elif intent.action_id == "open_ring_challenge":
            # ring_daily_row is the current-frame OCR box for the exact
            # 前往 control, so consume that box rather than guessing a row
            # coordinate.  This action used to change only the state machine
            # state and sent no Maa input at all.
            self._controller_tap(record[1])
        elif intent.action_id == "open_ring_attempt_mode":
            self._controller_tap((990, 570, 270, 140))
        elif intent.action_id in {
            "start_ring_matching",
            "fight_ring_opponent",
            "start_ring_battle",
            "skip_ring_battle",
        }:
            self._controller_tap(record[1])
            if intent.action_id == "start_ring_battle":
                # The battle-loading request can show the same transient
                # network modal as Shadow movement. Recover it before the
                # loading postcondition is evaluated, while keeping the
                # battle state/action id intact for the next frame.
                self._retry_network_timeout()
        elif intent.action_id == "wait_ring_battle":
            # Do not touch the game while Unity moves from the battle-loading
            # overlay to the live fight page. The next engine iteration takes
            # a fresh Maa screenshot and re-evaluates the skip/result markers.
            sleep(1.5)
        elif intent.action_id == "sweep_ring":
            # The workflow can reach this branch only after the explicit
            # master-tier/sufficient-score gate has selected the sweep path.
            self._controller_tap((0, 570, 250, 140))
        elif intent.action_id == "confirm_ring_sweep":
            self._controller_tap(record[1])
        elif intent.action_id == "dismiss_ring_reward":
            self._controller_tap(record[1])
        elif intent.action_id == "dismiss_ring_result":
            self._controller_tap((1120, 640, 120, 70))
        elif intent.action_id == "close_ring_opponents":
            self._controller_tap((1160, 0, 100, 90))
        elif intent.action_id == "close_ring_page":
            self._controller_tap((1160, 0, 100, 90))
        elif intent.action_id == "open_jianlin":
            # The current workflow target is the OCR box for the complete
            # ``战胜一次剑林的首领`` row. OCR returns the row text rather
            # than its right-side 前往 button, so preserve that recognized
            # row's vertical center and tap only the matching button column.
            if marker == "jianlin_daily_row":
                _, row_box = record
                row_center_y = row_box[1] + row_box[3] // 2
                button_box = (1010, max(0, row_center_y - 45), 230, 90)
                if button_box[1] + button_box[3] > 720:
                    button_box = (1010, 630, 230, 90)
                self._controller_tap(button_box)
            else:
                # Compatibility for older resources/tests that still target
                # the former fixed-row marker.
                self._controller_tap((1010, 420, 230, 90))
        elif intent.action_id == "scroll_daily_jianlin":
            # The original workflow reaches the Jianlin row by a bounded
            # upward list scroll, through Maa's same ADB controller.
            self._controller_swipe((650, 650), (650, 250), duration_ms=900)
        elif intent.action_id == "scroll_daily_reward_rows":
            # Reward claiming scans the daily list one viewport at a time;
            # the state machine caps this action so a changed list cannot
            # cause an unbounded swipe loop.
            self._controller_swipe((650, 650), (650, 300), duration_ms=800)
        elif intent.action_id == "open_jianlin_stamina_purchase":
            # The stamina capsule sits at the far right of the Jianlin
            # resource header, away from the page close control.
            self._controller_tap((1110, 10, 55, 60))
        elif intent.action_id == "select_jianlin_condensate":
            # The resource page opens with the experience card selected.  The
            # 凝晶 resource is the second visible card on the left; select it
            # before authorizing the stamina-consuming challenge.
            self._controller_tap((0, 210, 280, 150))
        elif intent.action_id == "buy_stamina_once":
            # The prompt target is OCR-authorized in this exact frame.  The
            # definition has already proved +80 for 10 紫色魂玉 before this
            # controller click is allowed.
            self._controller_tap(record[1])
        elif intent.action_id == "confirm_jianlin_stamina_purchase":
            self._controller_tap(record[1])
        elif intent.action_id == "close_postpurchase_stamina_prompt":
            self._controller_tap((620, 70, 40, 40))
        elif intent.action_id == "dismiss_jianlin_stamina_result":
            self._controller_tap((620, 650, 40, 40))
        elif intent.action_id in {"set_safe_count", "set_safe_multiplier"}:
            # The live control ignores clicks on the track. Drag the current
            # knob to the verified target tick through Maa's ADB controller.
            maximum = 6 if intent.action_id == "set_safe_count" else 3
            value = min(maximum, int(intent.parameter or 0))
            if value < 1:
                raise RuntimeError("Jianlin control value is missing")
            current = (
                self._jianlin_count_value
                if intent.action_id == "set_safe_count"
                else self._jianlin_multiplier_value
            )
            current = min(maximum, max(1, current))
            left_x, right_x = 930, 1204
            y = 505 if intent.action_id == "set_safe_count" else 427

            def tick_x(tick: int) -> int:
                return round(left_x + (right_x - left_x) * (tick - 1) / (maximum - 1))

            self._controller_swipe(
                (tick_x(current), y),
                (tick_x(value), y),
                duration_ms=900,
            )
        elif intent.action_id == "challenge_condensate":
            self._controller_tap(record[1])
        elif intent.action_id == "buy_jianlin_resource":
            # ``挑战`` is the orange action on the lower-right of the
            # 剑林/资源 page.  The OCR hit authorizes the action; this bounded
            # rectangle is the stable button hit area on the Android build.
            self._controller_tap((900, 560, 380, 160))
        elif intent.action_id == "start_jianlin_battle":
            # Formation is a separate page after 挑战.  Start the approved
            # resource battle from its large lower-right 开战 button.
            self._controller_tap((1000, 500, 280, 220))
        elif intent.action_id == "close_condensate_result":
            self._controller_tap((1120, 620, 140, 80))
        elif intent.action_id == "close_jianlin_page":
            self._controller_tap((1160, 0, 100, 90))
        elif intent.action_id == "open_tea_purchase":
            # The item detail is recognized first; the actual purchase card
            # opens from its lower price panel, not from the title OCR box.
            self._controller_tap((900, 170, 260, 120))
        elif intent.action_id == "open_tea_tab":
            # The tea card template is the current-frame authorization and
            # its center is the selectable card body. This action used to
            # fall through to the generic path without sending any input,
            # leaving the task on the shop grid after a successful match.
            self._controller_tap(record[1])
        elif intent.action_id == "select_yanwu_world":
            # OCR can match the nearby ``江湖·偃武`` section heading instead
            # of the selectable 偃武世界 row.  Once the painting page and its
            # heading have been recognized in the current frame, click the
            # bounded row itself.  The OCR box remains the authorization
            # marker, not the tap coordinate; this calibrated rectangle
            # covers the full selectable 偃武世界 row on the Android build.
            self._controller_tap((100, 130, 200, 75))
        elif intent.action_id == "inspect_food_candidate":
            self._controller_tap(record[1])
        elif intent.action_id == "select_food_tab":
            self._controller_tap(record[1])
        elif intent.action_id in {
            "open_yanwu_currency_purchase",
            "open_yunzhou_currency_purchase",
        }:
            # The regional-currency entry is the small top-right currency
            # capsule.  Its OCR hit is the map's regional label on the left,
            # so clicking that OCR box only reselects the active region.  The
            # capsule itself is stable on both 偃武世界 and 云州 maps.
            self._controller_tap((990, 15, 210, 55))
        elif intent.action_id in {
            "close_yanwu_currency_purchase",
            "close_yunzhou_currency_purchase",
        }:
            self._controller_tap((1190, 15, 50, 50))
        elif intent.action_id in {
            "buy_yanwu_currency_max",
            "buy_yunzhou_currency_max",
        }:
            # Both regional purchase panels share this bounded layout: the
            # double-chevron selects the page's maximum safe quantity, then
            # the orange 买 button confirms the approved stored 凝晶 spend.
            self._controller_tap((970, 440, 35, 45))
            sleep(0.5)
            self._controller_tap((710, 545, 300, 60))
        elif intent.action_id in {
            "dismiss_yanwu_reward_popup",
            "dismiss_yunzhou_reward_popup",
        }:
            # The normal obtained-item overlay closes from empty lower-right
            # space.  It is reached only after the purchase-result marker has
            # been recognized in the same workflow state.
            self._controller_tap((1120, 620, 140, 80))
        elif intent.action_id == "close_appraisal_popup":
            # The result overlay's X is stable even when its template is not
            # returned by Maa during the blur animation.
            self._controller_tap((1160, 0, 100, 90))
        elif intent.action_id.startswith("open_martial_plus_slot_"):
            # The plus template is restricted to one of the three visible
            # study cards. Use the same-frame template box; never guess a
            # slot from a stale card position.
            self._controller_tap(record[1])
        elif intent.action_id in {
            "study_martial_slot",
        }:
            # Re-select a material-safe configuration before the Unity button
            # gesture. The helper refreshes the current-frame OCR box after
            # each candidate/skill tap, so the final drag remains authorized
            # by the frame immediately preceding the study input.
            prepared = self._prepare_martial_study_configuration(
                target_action="martial_study_action",
            )
            if not prepared:
                # Exhausting the bounded material-safe search is a legitimate
                # eligibility outcome. Leave the detail page untouched and
                # let the next recognition frame classify it as not eligible;
                # never spend on an unverified combination.
                self._martial_configuration_unavailable = True
                return
            current = self._boxes.get("martial_study_action")
            if current is None or current[0] != self._last_frame_id:
                raise RuntimeError("martial study button lost current-frame authorization")
            self.gestures.drag_tap(current[1], frame_size=(1280, 720))
        elif intent.action_id == "breakthrough_martial_slot":
            # Re-select a material-safe breakthrough configuration before the
            # Unity gesture. A previous rejected candidate can leave this
            # detail page on a visible but insufficient 突破 button; clicking
            # it would leave the frame unchanged and lose the confirmation
            # postcondition.
            prepared = self._prepare_martial_study_configuration(
                target_action="martial_breakthrough_action",
            )
            if not prepared:
                self._martial_configuration_unavailable = True
                return
            current = self._boxes.get("martial_breakthrough_action")
            if current is None or current[0] != self._last_frame_id:
                raise RuntimeError(
                    "martial breakthrough button lost current-frame authorization"
                )
            # Unity's blue 突破 button ignores Maa's synthesized click on this
            # Android renderer. Use the current-frame OCR-authorized box and
            # a one-pixel touch move through the same Maa controller.
            self.gestures.drag_tap(current[1], frame_size=(1280, 720))
        elif intent.action_id == "confirm_martial_breakthrough":
            # The confirmation dialog is a normal modal; keep its explicit
            # OCR-authorized button on the ordinary bounded click path.
            self._controller_tap(record[1])
        elif intent.action_id in {"close_martial", "close_martial_page"}:
            # The live Android study sheet has no close glyph. Android Back
            # returns to the function panel; use Maa's key-event API instead
            # of clicking an empty top-right rectangle.
            self._controller_back()
        elif intent.action_id == "claim_trial_sword_reward":
            # Remember the authorized ordinary claim so a live frame that
            # omits both the 免费 glyph and the tiny current-reward counter
            # can still expose the page-bound free control.
            self._trial_reward_claimed = True
            self.gestures.execute(intent, box=record[1], frame_size=(1280, 720))
        elif intent.action_id == "close_reward_popup":
            # Reward overlays expose text but not a stable OCR bounding box
            # on this renderer.  The lower-right blank area dismisses the
            # overlay without selecting a reward or changing game state.
            self.gestures.execute(
                intent,
                box=(1150, 620, 100, 100),
                frame_size=(1280, 720),
            )
        elif intent.action_id == "dismiss_weekly_reward":
            # The weekly lucky-bag result uses the same explicit blank-area
            # dismissal as the other non-purchase reward sheets.
            self._controller_tap((560, 620, 160, 80))
        elif intent.action_id == "confirm_free_trial":
            # The live prompt uses 确认 (older resources used 确定). Keep the
            # tap strictly inside the orange lower-right confirmation button.
            self._trial_free_confirmed = True
            self._controller_tap((800, 460, 160, 80))
        elif intent.action_id in {
            "move_shadow_foreground_left",
            "move_shadow_foreground_center",
            "move_shadow_foreground_right",
        }:
            # The Android build keeps the same three foreground lanes as the
            # reference workflow; use the recognized lane ROI and Android's
            # input bridge for the renderer's card hit area.
            self._controller_tap(record[1])
        elif intent.action_id == "dismiss_shadow_battle_result":
            # Victory waits for a normal blank-screen tap before returning to
            # the grid.  The lower-right corner is *not* blank on the live
            # stage: it contains the gray 离开 control.  Tapping the old
            # rectangle therefore abandoned the stage instead of dismissing
            # the victory layer, leaving the next foreground sweep on a
            # misleading first-layer screen.  Use the same empty lower-center
            # point as the reward-sheet dismissal, which is outside the stage
            # controls and the foreground card anchors.
            self._controller_tap((560, 620, 160, 80))
        elif intent.action_id == "dismiss_shadow_reward_popup":
            # The live reward sheet explicitly says to dismiss it from blank
            # space. The lower-right blue control is actionable, so keep the
            # tap in the empty center below the sheet instead.
            self._controller_tap((560, 620, 160, 80))
        elif intent.action_id == "dismiss_shadow_battle_failure":
            # Defeat uses the same non-actionable full-screen result surface
            # as victory. Dismiss from blank space; the next frame decides
            # whether the stage returned to formation or exploration.
            self._controller_tap((560, 620, 160, 80))
        elif intent.action_id == "confirm_shadow_completion":
            # Final boss completion prompt; the orange 确定 button has a
            # stable bounded position and is independently OCR-authorized.
            self._controller_tap((800, 460, 160, 80))
        elif intent.action_id == "advance_shadow_foreground_triplet":
            # The reference workflow requires one ordered sweep of the three
            # foreground ground anchors. They are recognized and synthesized
            # on this exact frame above; fail closed if any anchor box is
            # missing instead of reusing a stale coordinate.
            anchors: list[tuple[int, int, int, int]] = []
            for anchor_marker in _SHADOW_FOREGROUND_MARKERS:
                anchor = self._boxes.get(anchor_marker)
                if anchor is None or anchor[0] != self._last_frame_id:
                    raise RuntimeError(
                        f"no current-frame recognition box for {anchor_marker}"
                    )
                anchors.append(anchor[1])
            self._shadow_move_baseline = self._last_frame_payload
            self._shadow_grid_observations = 0
            self._shadow_grid_changed_observations = 0
            for index, anchor_box in enumerate(anchors):
                self._controller_tap(anchor_box)
                if index < len(anchors) - 1:
                    # Keep the sequence strictly ordered while allowing the
                    # controller queue to drain between adjacent taps.
                    sleep(0.25)
            # A failed network request can surface immediately after the
            # ordered movement taps, before the normal postcondition frame.
            # Consume only the explicit retry dialog so a transient timeout
            # does not get reported as a false grid-stall failure.
            self._retry_network_timeout()
        elif intent.action_id == "transfer_shadow_stage":
            # This is a dead-end recovery only: the current frame must have
            # recognized the exploration page and its explicit 传送 control.
            self._controller_tap(record[1])
        elif intent.action_id == "confirm_shadow_transfer":
            # The first 传送 click opens a selection sheet. Confirm only from
            # the current frame's OCR box; never reuse the exploration-page
            # button coordinate or click through an inferred page state. The
            # blue Unity transfer control ignores an instantaneous Maa click
            # on one renderer variant, so deliver the same live box as a
            # bounded one-pixel drag tap.
            self.gestures.drag_tap(record[1], frame_size=(1280, 720))
        elif intent.action_id == "enter_shadow_stage":
            # The blue 前往 button is another Unity control that can swallow a
            # synthesized Maa click during its fade-in. Deliver the same
            # current-frame OCR-authorized box as a bounded one-pixel touch
            # move so the stage transition is not left on the card popup.
            self.gestures.drag_tap(record[1], frame_size=(1280, 720))
        elif intent.action_id == "confirm_shadow_auto_route":
            # Entering a stage can show a cross-map auto-route confirmation
            # before the exploration HUD. The prompt and its blue 确认 button
            # are both OCR-authorized on this frame; keep the actual input on
            # that live button box so this navigation branch cannot click a
            # stale transfer or battle control.
            self._controller_tap(record[1])
        elif intent.action_id == "apply_shadow_recommended_team":
            self._controller_tap(record[1])
        elif intent.action_id == "use_shadow_recommended_team":
            # The recommendation surface is a separate page. Only its
            # current-frame 使用阵容 target may authorize this transition
            # back to the formation page. Unity ignores an instantaneous
            # Maa click on this button in the Android build, so preserve the
            # current OCR box but deliver the smallest bounded drag tap.
            self.gestures.drag_tap(record[1], frame_size=(1280, 720))
        elif intent.action_id == "close_shadow_recommended_team":
            # Applying a recommendation updates the formation while the
            # recommendation sheet remains open. Close only that recognized
            # sheet; the next frame must prove the formation page before
            # battle is considered again.
            self._controller_tap((1160, 0, 100, 100))
        elif intent.action_id == "battle":
            # Open the battle from the current-frame formation target, then
            # reproduce the original workflow's explicit auto/speed setup
            # before the engine starts polling for victory or defeat.
            self._controller_tap(record[1])
            self._ensure_shadow_battle_modes()
        elif intent.action_id in {
            "open_trial_sword",
            "open_painting_scroll",
        }:
            box = record[1]
            if intent.action_id == "open_painting_scroll":
                # OCR often returns the glyph's text baseline rather than its
                # full hit area.  The recognized shortcut occupies this
                # stable upper-right region; its center is the actual tap
                # target on the Android renderer.
                box = (1080, 0, 120, 130)
            self._controller_tap(box)
        else:
            self.gestures.execute(intent, box=record[1], frame_size=(1280, 720))
        # Android transitions are asynchronous.  Maa's normal pipeline runner
        # waits for the next recognition timeout; this custom-action bridge
        # must provide an equivalent short settling window before the engine's
        # postcondition capture.
        settle_seconds = 3.0 if intent.action_id in {
            "select_first_visible_dispatch",
            "open_painting_scroll",
            "select_yanwu_world",
            "select_yunzhou",
            "open_dungeon",
            "open_jianlin",
            "open_shop",
            "scroll_daily_jianlin",
                "scroll_tea_list",
            "open_tea_tab",
            "open_jianlin_stamina_purchase",
            "select_jianlin_condensate",
            "buy_jianlin_resource",
            "buy_stamina_once",
            "confirm_jianlin_stamina_purchase",
            "close_postpurchase_stamina_prompt",
            "dismiss_jianlin_stamina_result",
            "set_safe_count",
            "set_safe_multiplier",
            "challenge_condensate",
            "start_jianlin_battle",
            "close_condensate_result",
            "close_jianlin_page",
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
            "open_trial_sword",
            "open_appraisal",
            "open_shadow",
            "select_active_shadow_card",
            "enter_shadow_stage",
            "confirm_shadow_auto_route",
            "open_yanwu_currency_purchase",
            "open_yunzhou_currency_purchase",
            "buy_yanwu_currency_max",
            "buy_yunzhou_currency_max",
            "open_martial_plus_slot_0",
            "open_martial_plus_slot_1",
            "open_martial_plus_slot_2",
            "breakthrough_martial_slot",
            "confirm_martial_breakthrough",
        } else 1.5
        if intent.action_id == "enter_shadow_stage":
            settle_seconds = 8.0
        if intent.action_id == "open_martial_study":
            # The title/close chrome renders before the study cards.  Wait for
            # the final card (and its large 成功 label) before the engine takes
            # the first actionable OCR frame.
            settle_seconds = 8.0
        if intent.action_id in {
            "open_martial_plus_slot_0",
            "open_martial_plus_slot_1",
            "open_martial_plus_slot_2",
            "study_martial_slot",
            "breakthrough_martial_slot",
            "confirm_martial_breakthrough",
        }:
            settle_seconds = 3.0
        if intent.action_id in {
            "dismiss_shadow_battle_result",
            "dismiss_shadow_reward_popup",
            "dismiss_shadow_battle_failure",
            "confirm_shadow_completion",
        }:
            settle_seconds = 8.0
        if intent.action_id in {
            "move_shadow_foreground_left",
            "move_shadow_foreground_center",
            "move_shadow_foreground_right",
            "advance_shadow_foreground_triplet",
            "transfer_shadow_stage",
            "confirm_shadow_transfer",
            "confirm_shadow_auto_route",
            "apply_shadow_recommended_team",
            "use_shadow_recommended_team",
            "close_shadow_recommended_team",
        }:
            # Moving onto a foreground card, including the verified three
            # anchor sweep, can trigger a full black loading transition.  The
            # live Android renderer remains black beyond the generic 1.5s
            # window, so wait for the next stage frame before verification.
            settle_seconds = 8.0
        if intent.action_id == "close_reward_popup":
            # The collection reward overlay fades before the world HUD is
            # fully rendered.  Live Android traces show the home marker can
            # appear roughly nine seconds after the dismiss tap.
            settle_seconds = 10.0
        if intent.action_id == "start_jianlin_battle":
            # The live formation page shows a two-minute combat timer.  Wait
            # for the normal auto-combat result before checking the result
            # postcondition; no polling click or alternate input path is
            # needed.
            settle_seconds = 135.0
        if intent.action_id == "battle":
            # The engine polls OCR for 战斗胜利.  Keep only a short initial
            # settle here so a fast battle is handled immediately instead of
            # being hidden behind a fixed multi-minute sleep.
            settle_seconds = 3.0
        self._settle_until = monotonic() + settle_seconds

    def _controller_tap(self, box: tuple[int, int, int, int]) -> None:
        """Send one bounded tap through the tasker's MAA ADB controller."""

        self.gestures.click(box, frame_size=(1280, 720))

    def _controller_back(self) -> None:
        """Leave a modal/page through Android Back via Maa's controller."""

        # Android KEYCODE_BACK is 4. This remains inside Maa's Android
        # controller and does not invoke a raw adb shell input command.
        self.gestures.click_key(4)

    def _controller_drag_tap(self, box: tuple[int, int, int, int]) -> None:
        """Send a bounded down/move/up tap through Maa's Android controller."""

        self.gestures.drag_tap(box, frame_size=(1280, 720))

    def _ensure_shadow_battle_modes(self) -> None:
        """Enable Shadow auto-combat modes only when the live page proves they are off.

        The reference workflow explicitly enables automatic combat and speed
        after opening a Shadow battle. The Android renderer exposes the
        controls as OCR text, but a generic ``自动`` hit is not sufficient:
        the enabled label is ``自动中``. Capture a fresh battle frame, use the
        enabled marker when present, and otherwise authorize one bounded tap
        from the same control ROI. Re-capture once after any toggle so a
        successful Maa input is not confused with a changed game state.
        """

        battle_page_markers = (
            "shadow_stage_page",
            "shadow_battle_result",
            "shadow_battle_failure",
        )
        retried_formation = False
        evidence: VisualEvidence | None = None
        # Opening a Shadow battle briefly blanks the Unity viewport. Maa's
        # screencap is valid during that transition, but no page OCR can be
        # expected until the loading surface has rendered. Poll a bounded
        # number of settled frames instead of treating the first black frame
        # as a driver failure.
        for attempt in range(5):
            self._settle_until = monotonic() + (1.5 if attempt == 0 else 2.0)
            frame = self.capture()
            evidence = self.recognize(frame, _SHADOW_BATTLE_MODE_RECOGNIZERS)
            if any(evidence.page_hits.get(marker, 0) == 1 for marker in battle_page_markers):
                break

            # Unity occasionally ignores Maa's synthesized click on the blue
            # 开战 button while leaving the formation page fully visible. That
            # is an explicit safe retry surface: use the current-frame target
            # and deliver one bounded touch down/move/up sequence exactly once.
            # Do not retry on an unknown or still-loading screen.
            formation_target = self._boxes.get("shadow_battle_target")
            if (
                not retried_formation
                and evidence.page_hits.get("shadow_formation_page", 0) == 1
                and formation_target is not None
                and formation_target[0] == frame.frame_id
            ):
                self.gestures.drag_tap(
                    formation_target[1],
                    frame_size=(1280, 720),
                )
                retried_formation = True

        if evidence is None or not any(
            evidence.page_hits.get(marker, 0) == 1 for marker in battle_page_markers
        ):
            raise RuntimeError("Shadow battle page was not recognized after opening battle")

        changed = False
        if evidence.target_hits.get("shadow_speed_enabled", 0) != 1:
            if evidence.target_hits.get("shadow_speed_toggle", 0) != 1:
                raise RuntimeError("Shadow speed state is not recognized")
            self._controller_tap(_SHADOW_SPEED_TOGGLE_BOX)
            changed = True
        if evidence.target_hits.get("shadow_auto_enabled", 0) != 1:
            if evidence.target_hits.get("shadow_auto_toggle", 0) != 1:
                raise RuntimeError("Shadow auto-combat state is not recognized")
            self._controller_tap(_SHADOW_AUTO_TOGGLE_BOX)
            changed = True

        if not changed:
            return

        self._settle_until = monotonic() + 1.0
        verified = self.recognize(self.capture(), _SHADOW_BATTLE_MODE_RECOGNIZERS)
        for marker in ("shadow_speed_enabled", "shadow_auto_enabled"):
            if verified.target_hits.get(marker, 0) != 1:
                raise RuntimeError(f"Shadow battle mode did not become enabled: {marker}")

    def _controller_long_press(
        self,
        x: int,
        y: int,
        *,
        duration_seconds: float,
    ) -> None:
        """Hold and release one point through the tasker's MAA ADB controller."""

        down = self.controller.post_touch_down(x, y)
        down.wait()
        if hasattr(down, "succeeded") and not down.succeeded:
            raise RuntimeError(f"MAA touch down failed at {(x, y)}")
        try:
            sleep(duration_seconds)
        finally:
            up = self.controller.post_touch_up()
            up.wait()
            if hasattr(up, "succeeded") and not up.succeeded:
                raise RuntimeError(f"MAA touch up failed at {(x, y)}")

    def _controller_multi_long_press(
        self,
        points: tuple[tuple[int, int], ...],
        *,
        duration_seconds: float,
    ) -> None:
        """Hold several Maa ADB touch contacts during the same time window."""

        active_contacts: list[int] = []
        try:
            for contact, (x, y) in enumerate(points):
                down = self.controller.post_touch_down(
                    x,
                    y,
                    contact=contact,
                    pressure=1,
                )
                down.wait()
                if hasattr(down, "succeeded") and not down.succeeded:
                    raise RuntimeError(f"MAA touch down failed at {(x, y)}")
                active_contacts.append(contact)
            sleep(duration_seconds)
        finally:
            for contact in reversed(active_contacts):
                up = self.controller.post_touch_up(contact=contact)
                up.wait()
                if hasattr(up, "succeeded") and not up.succeeded:
                    raise RuntimeError(f"MAA touch up failed for contact {contact}")

    def _controller_swipe(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        duration_ms: int,
    ) -> None:
        """Send one bounded swipe through the tasker's MAA ADB controller."""

        # Android controllers that expose the touch lifecycle advertise
        # ``MaaControllerFeature_UseMouseDownAndUpInsteadOfClick``. On that
        # path Maa's queued post_swipe is a deprecated compatibility call and
        # may complete without delivering a Unity drag. Use the controller's
        # own touch_down/move/up jobs so the gesture is a real ADB-controller
        # input, not a raw adb fallback.
        post_down = getattr(self.controller, "post_touch_down", None)
        post_move = getattr(self.controller, "post_touch_move", None)
        post_up = getattr(self.controller, "post_touch_up", None)
        if all(callable(method) for method in (post_down, post_move, post_up)):
            def wait_job(job: Any, label: str) -> None:
                job.wait()
                if hasattr(job, "succeeded") and not job.succeeded:
                    raise RuntimeError(f"MAA {label} failed")

            wait_job(post_down(start[0], start[1], contact=0, pressure=1), "touch down")
            try:
                steps = max(2, min(12, round(duration_ms / 80)))
                duration_seconds = duration_ms / 1000
                for step in range(1, steps + 1):
                    sleep(duration_seconds / steps)
                    x = round(start[0] + (end[0] - start[0]) * step / steps)
                    y = round(start[1] + (end[1] - start[1]) * step / steps)
                    wait_job(post_move(x, y, contact=0, pressure=1), "touch move")
            finally:
                wait_job(post_up(contact=0), "touch up")
            return

        # Keep compatibility with older/test controllers that expose only
        # the queued swipe method.
        self.gestures.swipe(
            (start[0] - 1, start[1] - 1, 2, 2),
            (end[0] - 1, end[1] - 1, 2, 2),
            duration_ms=duration_ms,
            frame_size=(1280, 720),
        )

    @_boundary_cleanup_method
    def return_to_home(
        self,
        max_steps: int = 30,
        *,
        check_foreground: bool = True,
    ) -> bool:
        """Close only recognized mail/panel chrome left by a daily task.

        This is task-boundary cleanup, not a business action.  It is deliberately
        limited to two known close controls and stops without input if neither
        close control nor the home marker is recognized.  Android callers keep
        the foreground check enabled so dynamic map backgrounds may rely on
        the game-only OCR marker without accepting Launcher artwork.
        """

        # A full boundary pass invokes the complete page/OCR catalog and is
        # materially more expensive than the small probes above.  Unknown
        # screens must fail fast so an independent daily task still gets its
        # own runtime budget; recognized multi-level surfaces can continue
        # through the cheap probe after each bounded close.
        full_scan_attempts = 0
        full_scan_limit = min(max_steps, 3)
        title_wait_deadline: float | None = None
        martial_detail_boundary_attempts = 0
        martial_page_boundary_attempts = 0
        step = 0
        while step < max_steps:
            step += 1
            if title_wait_deadline is not None and monotonic() >= title_wait_deadline:
                return False
            if check_foreground and self.runtime_gate is not None:
                self.runtime_gate.require_foreground()
            frame = self.capture()
            # Keep the title/known-overlay hand-off cheap.  A full boundary
            # pass contains many OCR nodes and can take tens of seconds on the
            # Android renderer; running it before this probe made an obscured
            # title page spend all eight attempts without ever reaching the
            # stable start action.
            quick_names = [
                "reset.home",
                "home.painting_scroll_text",
                "home.power_text",
                "home.quest_text",
                "reset.announcement_page",
                "reset.version_announcement_page",
                "reset.start_game_welcome",
                "reset.start_game",
                "reset.start_game_button",
                "reset.monthly_signin_page",
                "reset.loading",
                "reset.resource_update_prompt",
                "reset.resource_update_allow",
                "reset.resource_update_progress",
                "reset.network_timeout",
                "reset.network_retry",
                "reset.guild_unlock_dialog",
                "reset.dialog_skip",
                "mail.page",
                "mail.empty",
                "mail.close",
                "reset.mail_close",
                "reset.function_panel",
                "reset.panel_close",
                "ring_page",
                "ring_page_close",
                *_RING_PAGE_PROOF_MARKERS,
                "ring_opponent_page",
                "ring_opponent_close",
                "ring_match_setup_page",
                "ring_match_start",
                "ring_reward_popup",
                "shadow_formation_page",
                "shadow_recommended_team_page",
                "shadow_use_recommended_team",
                "battle_pass.page",
                "battle_pass.tasks",
                "battle_pass.rewards",
                "battle_pass.close",
                "battle_pass.reward_popup",
                "battle_pass.reward_popup_close",
                # A fresh task boundary can inherit the martial detail sheet
                # from a previous task, so probe this exact page even when no
                # last action is available in the new runner process.
                "martial_study_detail",
                "martial_page",
                "martial_close",
            ]
            quick_names.extend(_boundary_probe_names(self._effective_last_action_id()))
            quick = self.recognize(frame, tuple(quick_names))
            if quick.target_hits.get("reset.resource_update_prompt", 0) == 1:
                # The game asks before downloading a mobile-network hot
                # update.  Authorize it only when the prompt and its exact
                # same-frame "允许下载" target are both recognized.  The
                # input still goes through Maa's Android controller; no raw
                # ADB input is used here.
                title_wait_deadline = None
                max_steps = max(max_steps, _RESOURCE_UPDATE_MAX_STEPS)
                allow = self._boxes.get("reset.resource_update_allow")
                if allow is not None:
                    if allow[0] != frame.frame_id:
                        return False
                    self._last_action_id = "allow_resource_update"
                    self._controller_tap(allow[1])
                self._settle_until = monotonic() + _RESOURCE_UPDATE_POLL_SECONDS
                continue
            if quick.target_hits.get("reset.resource_update_progress", 0) == 1:
                # Keep polling while the bounded update progress surface is
                # visible.  Do not send another input during the download.
                title_wait_deadline = None
                max_steps = max(max_steps, _RESOURCE_UPDATE_MAX_STEPS)
                self._settle_until = monotonic() + _RESOURCE_UPDATE_POLL_SECONDS
                continue
            if quick.target_hits.get("reset.network_timeout", 0) == 1:
                retry = self._boxes.get("reset.network_retry")
                if retry is None or retry[0] != frame.frame_id:
                    return False
                self._last_action_id = "retry_network_timeout"
                self._controller_tap(retry[1])
                self._settle_until = monotonic() + 1.2
                continue
            if quick.target_hits.get("reset.dialog_skip", 0) == 1:
                # The updated client can show a one-time guild-unlock/tutorial
                # layer above the live home HUD.  The HUD remains visible, so
                # it must be handled before accepting the home boundary.  OCR
                # authorizes only the current-frame 跳过 control; the input is
                # still delivered through Maa's Android controller.
                skip = self._boxes.get("reset.dialog_skip")
                if skip is None or skip[0] != frame.frame_id:
                    return False
                self._last_action_id = "dismiss_guild_unlock_dialog"
                self._controller_tap(skip[1])
                self._settle_until = monotonic() + 1.5
                continue
            if quick.target_hits.get("reset.guild_unlock_dialog", 0) == 1:
                # Wait for the animated dialog's explicit 跳过 label to render
                # instead of allowing the visible home HUD to bypass it.
                self._settle_until = monotonic() + 0.5
                continue
            if quick.target_hits.get("reset.loading", 0) == 1:
                # Loading is a known, input-free hand-off after the title
                # button.  Do not fall through to the expensive unknown-page
                # recognizer set or send another click while Unity is loading.
                self._settle_until = monotonic() + 3.0
                continue
            if any(
                quick.target_hits.get(marker, 0) == 1
                for marker in (
                    "reset.announcement_page",
                    "reset.version_announcement_page",
                )
            ):
                # The title's announcement sheet covers the start button.
                # Its top-right close region is a fixed, non-purchase control;
                # require an announcement OCR marker before tapping it.  The
                # 1.6 client uses a version-update layout without the old
                # ``万象藏宝阁`` label, so it has its own marker above.
                self._controller_tap((1010, 90, 150, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if self._home_boundary_hit(quick):
                return True
            if quick.page_hits.get("mail.page", 0) == 1:
                # Mail's live close template is affected by the changing
                # panel artwork.  The page OCR is the stronger same-frame
                # marker; once it is recognized, close only the fixed,
                # task-owned mail region.  This is still a Maa-controller
                # input through _controller_tap, never a raw ADB input.
                self._controller_tap((1040, 80, 160, 160))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("ring_page", 0) == 1
                and _has_ring_page_proof(quick.page_hits)
                and quick.target_hits.get("ring_page_close", 0) == 1
            ):
                # A recognized ring close control is a normal cleanup
                # boundary. Do not infer task eligibility from unrelated
                # page text.
                self._last_action_id = "boundary_ring_close"
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("ring_opponent_page", 0) == 1
                and quick.target_hits.get("ring_opponent_close", 0) == 1
            ):
                # A failed/manual arena attempt can leave the opponent list
                # open. It is a recognized task surface, so close only its
                # own top-right control before handing the game to the next
                # independent daily task.
                self._last_action_id = "boundary_ring_opponents_close"
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if any(
                quick.page_hits.get(page, 0) == 1
                for page in (
                    "shadow_formation_page",
                    "shadow_recommended_team_page",
                )
            ):
                # A failed Shadow task can leave either the formation page or
                # its recommendation sheet open. Both expose the same
                # non-business top-right close control. Recognize the page
                # first, then close it through Maa's controller so the next
                # independent task gets a verified home boundary.
                self._last_action_id = "boundary_shadow_close"
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("martial_study_detail", 0) == 1
            ):
                # A fresh runner can inherit this sheet without a last-action
                # marker. The visible circular control is the only reliable
                # exit on this build; use its bounded current-page tap first,
                # then allow one Android Back fallback if the sheet persists.
                martial_detail_boundary_attempts += 1
                if martial_detail_boundary_attempts > 2:
                    return False
                self._last_action_id = "boundary_martial_detail_close"
                if martial_detail_boundary_attempts == 1:
                    # This Unity close glyph ignores a queued click on some
                    # Android frames. Use the normal Maa touch lifecycle
                    # (down/move/up) for the bounded same-page control.
                    self._controller_drag_tap((1160, 0, 100, 100))
                else:
                    self._controller_back()
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("martial_page", 0) == 1
                and quick.page_hits.get("martial_study_detail", 0) != 1
                and quick.page_hits.get("home", 0) != 1
                and quick.page_hits.get("function_panel.page", 0) != 1
            ):
                # The parent 武学研习 page also uses the changing circular
                # top-right return control, so its stale martial_close
                # template is not a safe reason to keep sending Back. Close
                # this recognized page with the same bounded Maa touch path.
                martial_page_boundary_attempts += 1
                if martial_page_boundary_attempts > 2:
                    return False
                self._last_action_id = "boundary_martial_page_close"
                if martial_page_boundary_attempts == 1:
                    self._controller_drag_tap((1160, 0, 100, 100))
                else:
                    self._controller_back()
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    quick.page_hits.get(page, 0) == 1
                    for page in (
                        "shop.page",
                        "shop.period_benefits.page",
                        "shop.gift_tab.page",
                        "shop.weekly.page",
                        "universal_shop_boundary",
                    )
                )
                and any(
                    quick.target_hits.get(marker, 0) == 1
                    for marker in (
                        "reset.modal_close",
                        "reset.daily_close",
                        "reset.trial_close",
                    )
                )
            ):
                self._last_action_id = "boundary_shop_close"
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.target_hits.get("reset.function_panel", 0) == 1
                and quick.target_hits.get("reset.panel_close", 0) == 1
            ):
                self._controller_tap((1180, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("appraisal.page", 0) == 1
                and any(
                    quick.target_hits.get(marker, 0) == 1
                    for marker in (
                        "reset.modal_close",
                        "reset.daily_close",
                        "reset.trial_close",
                    )
                )
            ):
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("collection.reward_popup", 0) == 1
                and quick.target_hits.get("collection.popup_close", 0) == 1
            ):
                self._last_action_id = "boundary_collection_reward_close"
                self._controller_tap((1150, 620, 100, 100))
                self._settle_until = monotonic() + 10.0
                continue
            if quick.page_hits.get("collection.page", 0) == 1:
                self._last_action_id = "boundary_collection_close"
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if quick.page_hits.get("painting_page", 0) == 1:
                self._last_action_id = "boundary_painting_close"
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("shadow_exploration_page", 0) == 1
                and quick.target_hits.get("reset.shadow_leave", 0) == 1
            ):
                self._controller_tap((1050, 580, 180, 100))
                self._settle_until = monotonic() + 2.5
                continue
            if any(
                quick.page_hits.get(page, 0) == 1
                for page in ("shadow_page", "shadow_card_list", "shadow_active_card")
            ):
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    quick.page_hits.get(page, 0) == 1
                    for page in (
                        "martial_success_result",
                        "martial_claim_progress",
                        "martial_study_detail",
                        "martial_page",
                    )
                )
                and quick.target_hits.get("martial_close", 0) == 1
            ):
                # The live study detail has no top-right close glyph. Use the
                # Android Back key to return to the function panel, then let
                # the next boundary iteration close that panel normally.
                self._controller_back()
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    quick.page_hits.get(page, 0) == 1
                    for page in (
                        "bag_page",
                        "consumables_page",
                        "food_category",
                        "food_tab_page",
                    )
                )
                and quick.target_hits.get("reset.modal_close", 0) == 1
            ):
                self._last_action_id = "boundary_food_close"
                self._controller_tap((1160, 0, 100, 90))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("dungeon_page", 0) == 1
                and quick.target_hits.get("dungeon_close", 0) == 1
            ):
                self._controller_tap((1160, 0, 100, 90))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("jianlin_page", 0) == 1
                and quick.target_hits.get("jianlin_page_close", 0) == 1
            ):
                self._controller_tap((1160, 0, 100, 90))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("hero.dispatch.page", 0) == 1
                and (
                    quick.target_hits.get("hero.dispatch.close", 0) == 1
                    or quick.target_hits.get("hero.all_completed", 0) == 1
                )
            ):
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("daily.page", 0) == 1
                and quick.target_hits.get("reset.daily_close", 0) == 1
            ):
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("battle_pass.reward_popup", 0) == 1
                and quick.target_hits.get("battle_pass.reward_popup_close", 0) == 1
            ):
                # A battle-pass season can show a non-purchasing-safe reward
                # catalogue before the actual page. It is still a recognized
                # non-purchase sheet; dismiss it from blank space, then let
                # the next frame prove the underlying page before closing it.
                self._controller_tap((1150, 620, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    quick.page_hits.get(page, 0) == 1
                    for page in (
                        "battle_pass.page",
                        "battle_pass.tasks",
                        "battle_pass.rewards",
                    )
                )
                and quick.target_hits.get("battle_pass.close", 0) == 1
            ):
                # The battle-pass task/reward tabs share the same safe
                # top-right close. Require a battle-pass page marker so this
                # cannot become a generic top-right click on an unknown UI.
                self._controller_tap((1180, 10, 70, 70))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                quick.page_hits.get("trial.page", 0) == 1
                and quick.target_hits.get("reset.trial_close", 0) == 1
            ):
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if quick.page_hits.get("tea_purchase_result", 0) == 1:
                # The tea result overlay has no reliable OCR footer on the
                # Android renderer. Its existing result template is the
                # authorization; dismiss from the known blank lower-center
                # area before closing the shop boundary.
                self._controller_tap((600, 640, 80, 60))
                self._settle_until = monotonic() + 1.5
                continue
            reward_closed = False
            for reward_page, reward_close in (
                ("battle_pass.reward_popup", "battle_pass.reward_popup_close"),
                ("ring_sweep_result", "ring_result_close"),
                ("ring_battle_result", "ring_result_close"),
            ):
                if (
                    quick.page_hits.get(reward_page, 0) == 1
                    and quick.target_hits.get(reward_close, 0) == 1
                ):
                    self._controller_tap((1150, 620, 100, 100))
                    self._settle_until = monotonic() + 1.5
                    reward_closed = True
                    break
            if reward_closed:
                continue
            if (
                quick.target_hits.get("reset.start_game_welcome", 0) == 1
                or quick.target_hits.get("reset.start_game", 0) == 1
                or quick.target_hits.get("reset.start_game_button", 0) == 1
            ):
                # The title OCR may resolve either the stable top label or the
                # low-contrast bottom label.  In both cases the input remains
                # the fixed bottom start region on this same captured frame.
                # Unity's title Button can ignore Maa's synthesized
                # post_click while the splash surface is still transitioning.
                # Use the smallest complete Maa touch lifecycle for this
                # recognized title control; it stays inside the same fixed
                # ROI and never falls back to raw adb input.
                if title_wait_deadline is None:
                    title_wait_deadline = monotonic() + _TITLE_START_WAIT_SECONDS
                self._controller_drag_tap((430, 600, 420, 100))
                self._settle_until = monotonic() + 12.0
                continue
            if title_wait_deadline is not None:
                # The title tap was accepted, but this frame has no stable
                # label yet. Poll the same boundary cheaply; a full catalog
                # scan here only delays the next home frame and can send the
                # task into the long Android lifecycle-recovery wait.
                self._settle_until = monotonic() + _TITLE_START_POLL_SECONDS
                continue
            if full_scan_attempts >= full_scan_limit:
                return False
            full_scan_attempts += 1
            evidence = self.recognize(
                frame,
                (
                    "reset.home",
                    "home.painting_scroll_text",
                    "home.power_text",
                    "home.quest_text",
                    "reset.start_game",
                    "reset.start_game_button",
                    "reset.monthly_signin_page",
                    "reset.announcement_page",
                    "mail.reward_popup",
                    "mail.reward_popup_close",
                    "daily.reward_popup",
                    "daily.reward_popup_close",
                    "mail.page",
                    "mail.close",
                    "shop.page",
                    "shop.period_benefits.page",
                    "shop.gift_tab.page",
                    "shop.weekly.page",
                    "universal_shop_boundary",
                    "reset.function_panel",
                    "reset.mail_close",
                    "reset.panel_close",
                    "reset.daily_close",
                    "reset.trial_close",
                    "daily.page",
                    "battle_pass.page",
                    "battle_pass.tasks",
                    "battle_pass.rewards",
                    "battle_pass.close",
                    "battle_pass.reward_popup",
                    "battle_pass.reward_popup_close",
                    "tea_purchase_result",
                    "shop.free_gift.reward",
                    "shop.free_gift.dismiss",
                    "ring_sweep_result",
                    "ring_battle_result",
                    "ring_result_close",
                    "ring_page",
                    "ring_page_close",
                    *_RING_PAGE_PROOF_MARKERS,
                    "ring_opponent_page",
                    "ring_opponent_close",
                    "appraisal.page",
                    "martial_success_result",
                    "martial_result_close",
                    "martial_claim_progress",
                    "martial_study_detail",
                    "martial_page",
                    "martial_close",
                    "bag_page",
                    "consumables_page",
                    "food_category",
                    "food_tab_page",
                    "dungeon_page",
                    "dungeon_close",
                    "jianlin_page",
                    "jianlin_condensate_title",
                    "jianlin_challenge_button",
                    "jianlin_page_close",
                    "reset.modal_close",
                    "reset.shadow_leave",
                    "reset.world_return",
                    "hero.dispatch.page",
                    "hero.all_completed",
                    "hero.dispatch.close",
                    "collection.page",
                    "collection.harvested",
                    "collection.reward_popup",
                    "collection.reward_title",
                    "collection.popup_close",
                    "painting_page",
                    "shadow_page",
                    "shadow_card_list",
                    "shadow_active_card",
                    "shadow_no_active_card",
                    "shadow_popup",
                    "shadow_go",
                    "shadow_formation_page",
                    "shadow_recommended_team_page",
                    "shadow_use_recommended_team",
                    "reset.start_game_welcome",
                    "reset.start_game_button",
                    "reset.loading",
                    "reset.resource_update_prompt",
                    "reset.resource_update_allow",
                    "reset.resource_update_progress",
                    "reset.network_timeout",
                    "reset.network_retry",
                    "reset.guild_unlock_dialog",
                    "reset.dialog_skip",
                    "reset.version_announcement_page",
                ),
            )
            if any(
                evidence.target_hits.get(marker, 0) == 1
                for marker in (
                    "reset.start_game_welcome",
                    "reset.start_game",
                    "reset.start_game_button",
                )
            ):
                if title_wait_deadline is None:
                    title_wait_deadline = monotonic() + _TITLE_START_WAIT_SECONDS
                self._controller_drag_tap((430, 600, 420, 100))
                self._settle_until = monotonic() + 12.0
                continue
            if evidence.target_hits.get("reset.dialog_skip", 0) == 1:
                skip = self._boxes.get("reset.dialog_skip")
                if skip is None or skip[0] != frame.frame_id:
                    return False
                self._last_action_id = "dismiss_guild_unlock_dialog"
                self._controller_tap(skip[1])
                self._settle_until = monotonic() + 1.5
                continue
            if evidence.target_hits.get("reset.guild_unlock_dialog", 0) == 1:
                self._settle_until = monotonic() + 0.5
                continue
            # ``home.painting_scroll_text`` alone can also appear in launcher
            # artwork.  Pair it with two independent game-HUD OCR markers so
            # animated map scenery can vary without accepting another game
            # page or a launcher frame as the task boundary.
            if self._home_boundary_hit(evidence) and not any(
                evidence.page_hits.get(marker, 0) == 1
                for marker in (
                    "martial_success_result",
                    "martial_claim_progress",
                    "martial_study_detail",
                    "martial_page",
                )
            ):
                return True
            if any(
                evidence.target_hits.get(marker, 0) == 1
                for marker in (
                    "reset.announcement_page",
                    "reset.version_announcement_page",
                )
            ):
                self._controller_tap((1010, 90, 150, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if evidence.target_hits.get("reset.loading", 0) == 1:
                self._settle_until = monotonic() + 3.0
                continue
            if evidence.target_hits.get("reset.resource_update_prompt", 0) == 1:
                max_steps = max(max_steps, _RESOURCE_UPDATE_MAX_STEPS)
                allow = self._boxes.get("reset.resource_update_allow")
                if allow is not None:
                    if allow[0] != frame.frame_id:
                        return False
                    self._last_action_id = "allow_resource_update"
                    self._controller_tap(allow[1])
                self._settle_until = monotonic() + _RESOURCE_UPDATE_POLL_SECONDS
                continue
            if evidence.target_hits.get("reset.resource_update_progress", 0) == 1:
                max_steps = max(max_steps, _RESOURCE_UPDATE_MAX_STEPS)
                self._settle_until = monotonic() + _RESOURCE_UPDATE_POLL_SECONDS
                continue
            if evidence.target_hits.get("reset.monthly_signin_page", 0) == 1:
                # The monthly sign-in sheet is a known, non-purchase modal
                # shown before the first daily task.  Its close mark is inside
                # the sheet rather than at the screen corner, so only tap
                # this bounded region after the page OCR has identified it.
                self._controller_tap((1030, 120, 100, 80))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("mail.reward_popup", 0) == 1
                and evidence.target_hits.get("mail.reward_popup_close", 0) == 1
            ):
                # Mail claim results use the same safe blank-space dismissal
                # as the other non-purchase reward overlays.  Only dismiss it
                # after both the popup and its footer text are recognized.
                self._controller_tap((1150, 620, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("mail.page", 0) == 1
                and evidence.target_hits.get("mail.close", 0) == 1
            ):
                recognized = self._boxes.get("mail.close")
                if recognized is not None and recognized[0] == frame.frame_id:
                    self._controller_tap(recognized[1])
                    self._settle_until = monotonic() + 1.5
                    continue
            if (
                any(
                    evidence.page_hits.get(page, 0) == 1
                    for page in (
                        "shop.page",
                        "shop.period_benefits.page",
                        "shop.gift_tab.page",
                        "shop.weekly.page",
                        "universal_shop_boundary",
                    )
                )
                and (
                    evidence.target_hits.get("reset.modal_close", 0) == 1
                    or evidence.target_hits.get("reset.daily_close", 0) == 1
                )
            ):
                # Shop tabs use the recognized top-right close.  Depending on
                # the tab's chrome, Maa may expose that same X as either the
                # modal-close or daily-close target.  Do not close a generic X
                # without a shop-page marker; this keeps the boundary action
                # scoped to the live screen.
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if evidence.page_hits.get("painting_page", 0) == 1:
                # Original jianzhichuan_daily return_to_main_ui route:
                # close a recognized 画卷 region with its own top-right X,
                # then verify the main UI on a fresh frame.
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("shadow_exploration_page", 0) == 1
                and evidence.target_hits.get("reset.shadow_leave", 0) == 1
            ):
                # Exploration has a dedicated bottom-right 离开 control;
                # its top-right X belongs to the card-list page and is not
                # present here. Require both the exploration page and the
                # bounded leave marker before sending this input.
                self._controller_tap((1050, 580, 180, 100))
                self._settle_until = monotonic() + 2.5
                continue
            if evidence.page_hits.get("shadow_page", 0) == 1:
                # The original workflow closes the standalone 蜃影武墟 card
                # page at the task boundary. Require the page marker before
                # tapping its top-right X.
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("jianlin_page", 0) == 1
                and evidence.target_hits.get("jianlin_page_close", 0) == 1
            ):
                # Jianlin / 养成 is a supported task surface. Close it only
                # after both the page marker and its own top-right close
                # marker are recognized in the same frame, then require a
                # fresh home frame on the next loop.
                self._controller_tap((1160, 0, 100, 90))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.target_hits.get("reset.function_panel", 0) == 1
                and evidence.target_hits.get("reset.panel_close", 0) == 1
            ):
                self._controller_tap((1180, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("daily.page", 0) == 1
                and evidence.target_hits.get("reset.daily_close", 0) == 1
            ):
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("battle_pass.reward_popup", 0) == 1
                and evidence.target_hits.get("battle_pass.reward_popup_close", 0) == 1
            ):
                self._controller_tap((1150, 620, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    evidence.page_hits.get(page, 0) == 1
                    for page in (
                        "battle_pass.page",
                        "battle_pass.tasks",
                        "battle_pass.rewards",
                    )
                )
                and evidence.target_hits.get("battle_pass.close", 0) == 1
            ):
                self._controller_tap((1180, 10, 70, 70))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("appraisal.page", 0) == 1
                and any(
                    evidence.target_hits.get(marker, 0) == 1
                    for marker in (
                        "reset.modal_close",
                        "reset.daily_close",
                        "reset.trial_close",
                    )
                )
            ):
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("martial_success_result", 0) == 1
                and evidence.target_hits.get("martial_result_close", 0) == 1
            ):
                # A claim-only martial-study run can leave its reward overlay
                # open after a failed boundary.  Dismiss it only when both
                # the success page and its bounded close marker are visible.
                self._controller_tap((1150, 620, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if evidence.page_hits.get("tea_purchase_result", 0) == 1:
                self._controller_tap((600, 640, 80, 60))
                self._settle_until = monotonic() + 1.5
                continue
            reward_closed = False
            for reward_page, reward_close in (
                ("daily.reward_popup", "daily.reward_popup_close"),
                ("battle_pass.reward_popup", "battle_pass.reward_popup_close"),
                ("shop.free_gift.reward", "shop.free_gift.dismiss"),
                ("ring_sweep_result", "ring_result_close"),
                ("ring_battle_result", "ring_result_close"),
            ):
                if (
                    evidence.page_hits.get(reward_page, 0) == 1
                    and evidence.target_hits.get(reward_close, 0) == 1
                ):
                    # These reward sheets all expose the same non-purchase
                    # "click blank to close" interaction. Keep the tap in a
                    # shared safe blank region, but require the exact page
                    # and its own close text in this frame first.
                    self._controller_tap((1150, 620, 100, 100))
                    self._settle_until = monotonic() + 1.5
                    reward_closed = True
                    break
            if reward_closed:
                continue
            if (
                evidence.page_hits.get("ring_page", 0) == 1
                and _has_ring_page_proof(evidence.page_hits)
                and evidence.target_hits.get("ring_page_close", 0) == 1
            ):
                # A closed or already-complete ring page is a recognized
                # task surface. Close its top-right X before publishing the
                # shared home boundary; never leave a not-open page for the
                # next independent task.
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("ring_opponent_page", 0) == 1
                and evidence.target_hits.get("ring_opponent_close", 0) == 1
            ):
                self._controller_tap((1160, 0, 100, 100))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    evidence.page_hits.get(page, 0) == 1
                    for page in (
                        "martial_page",
                        "martial_study_detail",
                        "martial_claim_progress",
                    )
                )
                and evidence.target_hits.get("martial_close", 0) == 1
            ):
                # Martial study uses a two-level boundary: Android Back first
                # returns to the function panel, and the existing panel
                # branch then returns to home. The marker is still required
                # as page evidence; it is not treated as a visible X.
                self._controller_back()
                self._settle_until = monotonic() + 1.5
                continue
            if (
                any(
                    evidence.page_hits.get(page, 0) == 1
                    for page in (
                        "bag_page",
                        "consumables_page",
                        "food_category",
                        "food_tab_page",
                    )
                )
                and evidence.target_hits.get("reset.modal_close", 0) == 1
            ):
                # The food workflow can time out after a use while the game
                # remains inside the bag.  Close only the recognized bag
                # chrome; the next loop reuses the existing panel boundary
                # branch to reach home.
                self._last_action_id = "boundary_food_close"
                self._controller_tap((1160, 0, 100, 90))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("dungeon_page", 0) == 1
                and evidence.target_hits.get("dungeon_close", 0) == 1
            ):
                # A dungeon task can leave the game on a normal dungeon list
                # after a failed or interrupted attempt.  Close only after
                # the page and its bounded close marker are both recognized;
                # never guess at a generic top-right control.
                self._controller_tap((1160, 0, 100, 90))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("hero.dispatch.page", 0) == 1
                and (
                    evidence.target_hits.get("hero.dispatch.close", 0) == 1
                    or evidence.target_hits.get("hero.all_completed", 0) == 1
                )
            ):
                # A failed dispatch task can leave the game on the full
                # 侠客派遣 map. Close it only with the page marker plus
                # either its recognized X or the explicit 已完成:9 marker;
                # this keeps boundary cleanup scoped to the live screen.
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            if (
                evidence.page_hits.get("collection.reward_popup", 0) == 1
                and evidence.target_hits.get("collection.popup_close", 0) == 1
            ):
                # Collection rewards use the same safe blank-area dismissal
                # as the workflow's own postcondition. Keep it in the
                # boundary path as well so a terminal/already-complete frame
                # cannot leave the next task behind the reward overlay.
                self._controller_tap((1150, 620, 100, 100))
                self._settle_until = monotonic() + 10.0
                continue
            if evidence.page_hits.get("collection.page", 0) == 1:
                # An already-harvested collection page is a valid terminal
                # task surface. Its top-right X returns to 画卷, which the
                # existing painting boundary branch then closes to home.
                self._last_action_id = "boundary_collection_close"
                # The next loop has a cheap painting/home probe. Do not spend
                # the remaining expensive full-scan budget on the same stale
                # collection frame if the close gesture is ignored.
                full_scan_attempts = full_scan_limit
                self._controller_tap((1175, 5, 75, 75))
                self._settle_until = monotonic() + 1.5
                continue
            for marker in (
                "reset.start_game",
                "reset.start_game_welcome",
                "reset.start_game_button",
                "reset.mail_close",
                "reset.shadow_leave",
                "reset.world_return",
            ):
                if evidence.target_hits.get(marker, 0) == 1:
                    # Keep title and in-game chrome inputs inside recognized
                    # fixed ROIs and route both through the same controller.
                    boxes = {
                        "reset.start_game": (430, 600, 420, 100),
                        # The bottom button has deliberately low contrast on
                        # the live title.  The top ``欢迎进入游戏`` OCR marker
                        # proves the same title frame; the input remains fixed
                        # to the known bottom button ROI instead of clicking
                        # the OCR box returned for the title text.
                        "reset.start_game_welcome": (430, 600, 420, 100),
                        "reset.start_game_button": (430, 600, 420, 100),
                        "reset.mail_close": (1040, 80, 160, 160),
                        "reset.shadow_leave": (1050, 580, 180, 100),
                        "reset.world_return": (1060, 520, 180, 180),
                    }
                    if marker in {
                        "reset.start_game",
                        "reset.start_game_welcome",
                        "reset.start_game_button",
                    }:
                        self._controller_drag_tap(boxes[marker])
                    else:
                        self._controller_tap(boxes[marker])
                    self._settle_until = monotonic() + (
                        12.0
                        if marker in {"reset.start_game", "reset.start_game_button"}
                        else 1.5
                    )
                    break
            else:
                return False
        return False

    def can_resume_task(self, task_id: str) -> bool:
        """Keep a failed task on one of its explicitly recognized surfaces."""

        marker_sets = {
            "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": (
                "jianlin_page",
                "jianlin_condensate_title",
                "jianlin_challenge_button",
                "jianlin_condensate_selected",
                "jianlin_stamina_purchase_prompt",
                "jianlin_stamina_confirmation_prompt",
                "jianlin_stamina_purchase_result",
                "jianlin_stamina_result_close",
                "jianlin_battle_page",
                "jianlin_battle_result",
            ),
            "RING_CHALLENGE_DAILY": (
                "ring_page",
                "ring_opponent_page",
                "ring_match_setup_page",
                "ring_match_start",
                "ring_sweep_prompt",
                "ring_sweep_confirm",
                "ring_sweep_result",
                "ring_sweep",
                "ring_result_close",
                "ring_reward_popup",
                "ring_start",
                "ring_master_mode",
                "ring_master_rank",
                "ring_score_label",
                "ring_score_value",
                "ring_attempts",
                "ring_attempts_exhausted",
                "ring_fight_target",
                "ring_fight_page",
                "ring_battle_loading",
                "ring_battle_prepare_page",
                "ring_ready",
                "ring_skip",
                "ring_battle_result",
                "ring_opponent_close",
                "ring_page_close",
                "ring_challenge_target.done",
            ),
            "DAILY_TASK_REWARD_CLAIM_DAILY": (
                "daily.page",
                "daily.reward_popup",
                "daily.reward_popup_close",
            ),
            "MARTIAL_STUDY_BREAKTHROUGH_DAILY": (
                "martial_page",
                "martial_success_card",
                "martial_success_result",
                "martial_claim_progress",
                "martial_study_detail",
                "martial_candidate_in_progress",
            ),
            "EAT_STAMINA_FOOD_DAILY": (
                "bag_page",
                "consumables_page",
                "food_category",
                "food_buff_replace_prompt",
                "food_buff_replace_confirm",
                "food_buff_replace_prompt_template",
                "food_buff_replace_confirm_template",
                "food_use_result",
                "food_overfull",
            ),
            "BUY_TEA_DAILY": (
                "universal_shop_page",
                "tea_item",
                "tea_item_scrolled",
                "tea_selected",
                "quantity_panel",
                "tea_purchase_result",
                "tea_sold_out",
            ),
            "COLLECTION_DEPLOYMENT_DAILY": (
                "collection.page",
                "collection.reward_popup",
                "collection.reward_title",
                "collection.popup_close",
            ),
            "SHADOW_RUINS_DAILY": (
                "shadow_page",
                "shadow_card_list",
                "shadow_active_card",
                "shadow_no_active_card",
                "shadow_popup",
                "shadow_auto_route_prompt",
                "shadow_auto_route_confirm",
                "shadow_exploration_page",
                "shadow_formation_page",
                "shadow_battle_result",
                "shadow_battle_failure",
                "shadow_reward_popup",
                "shadow_transfer_page",
                "shadow_transfer_right_page",
                "shadow_confirm_transfer",
                "shadow_confirm_transfer_right",
            ),
            "SPEND_CONDENSATE_DAILY": (
                "painting_page",
                "yanwu_world_page",
                "yanwu_currency_purchase",
                "yunzhou_world_page",
                "yunzhou_currency_purchase",
                "yunzhou_currency_sold_out",
            ),
            "DUNGEON_SWEEP_DAILY": (
                "yanwangling_master_selected",
                "yanwangling_title",
                "sweep_target",
                "sweep_panel_page",
                "ticket_plus",
                "normal_sweep_confirm_page",
                "expected_sweep_result",
            ),
        }
        markers = marker_sets.get(task_id)
        if markers is None:
            return False
        evidence = self.recognize(self.capture(), markers)
        if task_id == "RING_CHALLENGE_DAILY":
            # Counters, buttons, and close glyphs are only meaningful after a
            # ring page has been established.  In particular, a generic
            # ``11/12`` OCR hit must not make an unrelated home screen
            # resumable.  Keep the resume boundary anchored to a ring page,
            # opponent list, matching surface, result, or battle surface.
            ring_surfaces = {
                "ring_page",
                "ring_opponent_page",
                "ring_match_setup_page",
                "ring_sweep_prompt",
                "ring_sweep_result",
                "ring_reward_popup",
                "ring_fight_page",
                "ring_battle_loading",
                "ring_battle_prepare_page",
                "ring_battle_result",
            }
            return any(
                evidence.target_hits.get(marker, 0) == 1
                for marker in ring_surfaces
            )
        return any(evidence.target_hits.get(marker, 0) == 1 for marker in markers)


__all__ = ["MaaAndroidWorkflowDriver"]
