"""MFW custom action that authorizes one same-frame controller input."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from agent.custom.support.controller_input import (
    box_values,
    click_box,
    resolution_values,
    swipe_box,
)
from agent.custom.support.params import parse_action_params
from agent.custom.support.policy import TASK_POLICIES
from agent.custom.support.state import RUN_STORE

from .task_lifecycle import diagnostics_for


def _record_denial(context: Any, params: Mapping[str, Any], reason: str) -> None:
    diagnostics = diagnostics_for(context, params.get("task_id", ""))
    if diagnostics is None:
        return
    try:
        diagnostics.record_action(
            params.get("action_id", "guarded_input"),
            {
                "task_id": params.get("task_id", ""),
                "allowed": False,
                "reason": reason,
            },
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return


def _value_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).casefold()


def _strict_index(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _sub_results(reco_detail: Any) -> list[Any] | None:
    if not getattr(reco_detail, "hit", False):
        return None
    if _value_name(getattr(reco_detail, "algorithm", "")) != "and":
        return None
    best_result = getattr(reco_detail, "best_result", None)
    results = getattr(best_result, "sub_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes, bytearray)):
        return None
    return list(results)


def _ocr_text(detail: Any) -> str | None:
    if not getattr(detail, "hit", False):
        return None
    result = getattr(detail, "best_result", None)
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text.strip()
    for result in getattr(detail, "filtered_results", ()) or ():
        text = getattr(result, "text", None)
        if isinstance(text, str):
            return text.strip()
    return None


def _ocr_amount(text: str) -> int | None:
    match = re.search(r"-?\d[\d,]*", text)
    if not match:
        return None
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _ocr_resource_matches(text: str | None, resource_id: str) -> bool:
    """Accept an OCR line containing the expected resource token.

    Maa OCR commonly returns the whole label line (for example ``消耗：500文``)
    even when the node's expected text is only ``文``.  The token must still be
    present in the same-frame result; the independent amount check below keeps
    the monetary guard exact.
    """

    if not isinstance(text, str):
        return False
    observed = text.strip()
    expected = resource_id.strip()
    return bool(expected) and expected in observed


def _material_is_sufficient(results: Sequence[Any], params: Mapping[str, Any]) -> bool:
    relation_index = _strict_index(params.get("material_relation_index"))
    relation_name = params.get("material_relation_name")
    relation = params.get("material_relation")
    if relation_index is not None or relation_name is not None:
        material_id = params.get("material_id")
        expected_relation_name = {
            "owned>=required": "martial.material.sufficient",
            "owned<required": "martial.material.insufficient",
        }.get(relation)
        if (
            not isinstance(material_id, str)
            or not material_id.strip()
            or expected_relation_name is None
            or relation_index is None
            or relation_index >= len(results)
            or not isinstance(relation_name, str)
            or relation_name != expected_relation_name
        ):
            return False
        marker = results[relation_index]
        return bool(
            getattr(marker, "hit", False)
            and getattr(marker, "name", None) == relation_name
        )

    material_id = params.get("material_id")
    material_index = _strict_index(params.get("material_index"))
    owned_index = _strict_index(params.get("owned_index"))
    required_index = _strict_index(params.get("required_index"))
    if (
        not isinstance(material_id, str)
        or not material_id.strip()
        or relation not in {None, "owned>=required"}
        or material_index is None
        or owned_index is None
        or required_index is None
        or material_index >= len(results)
        or owned_index >= len(results)
        or required_index >= len(results)
    ):
        return False
    observed_material = _ocr_text(results[material_index])
    owned_text = _ocr_text(results[owned_index])
    required_text = _ocr_text(results[required_index])
    if (
        not _ocr_resource_matches(observed_material, material_id)
        or owned_text is None
        or required_text is None
    ):
        return False
    owned_amount = _ocr_amount(owned_text)
    required_amount = _ocr_amount(required_text)
    return (
        owned_amount is not None
        and required_amount is not None
        and owned_amount >= required_amount
    )


def validate_and_evidence(
    reco_detail: Any,
    evidence: Mapping[str, Any],
    params: Mapping[str, Any] | None = None,
) -> bool:
    """Require the page and target hits to come from one Maa ``And`` result."""

    if not isinstance(evidence, Mapping):
        return False
    results = _sub_results(reco_detail)
    if results is None:
        return False
    page_index = _strict_index(evidence.get("page_index"))
    target_index = _strict_index(evidence.get("target_index"))
    if page_index is None or target_index is None:
        return False
    if page_index >= len(results) or target_index >= len(results):
        return False
    page = results[page_index]
    target = results[target_index]
    if not getattr(page, "hit", False) or not getattr(target, "hit", False):
        return False

    page_name = evidence.get("page_name")
    target_name = evidence.get("target_name")
    if page_name is not None and getattr(page, "name", None) != page_name:
        return False
    if target_name is not None and getattr(target, "name", None) != target_name:
        return False

    if params is not None and "material_id" in params:
        if not _material_is_sufficient(results, params):
            return False

    if params is None or "resource_id" not in params:
        return True

    resource_id = params["resource_id"]
    resource_index = _strict_index(params.get("resource_index"))
    amount_index = _strict_index(params.get("amount_index"))
    observed_amount = params.get("observed_amount")
    if (
        not isinstance(resource_id, str)
        or not resource_id.strip()
        or resource_index is None
        or amount_index is None
        or resource_index >= len(results)
        or amount_index >= len(results)
    ):
        return False
    if (
        observed_amount is not None
        and (
            isinstance(observed_amount, bool)
            or not isinstance(observed_amount, int)
            or observed_amount <= 0
        )
    ):
        return False
    resource_result = results[resource_index]
    observed_resource = _ocr_text(resource_result)
    observed_text = _ocr_text(results[amount_index])
    resource_evidence_name = params.get("resource_evidence_name")
    if resource_evidence_name is None:
        resource_matches = _ocr_resource_matches(observed_resource, resource_id)
    else:
        resource_matches = (
            isinstance(resource_evidence_name, str)
            and bool(resource_evidence_name.strip())
            and getattr(resource_result, "hit", False)
            and getattr(resource_result, "name", None) == resource_evidence_name
        )
    if not resource_matches or observed_text is None:
        return False
    amount = _ocr_amount(observed_text)
    if amount is None or amount <= 0:
        return False
    if observed_amount is None:
        # Resource amounts may vary between runs. The run-local policy still
        # enforces the aggregate resource budget before the click is sent.
        return True
    if params.get("observed_amount_mode") == "minimum":
        return amount >= observed_amount
    return amount == observed_amount


def _validate_input_shape(
    kind: str, box: Any, evidence: Mapping[str, Any], resolution: Any
) -> bool:
    try:
        if kind == "none":
            return True
        normalized = box_values(box)
        size = resolution_values(resolution)
        if size is not None and (
            normalized[0] + normalized[2] > size[0]
            or normalized[1] + normalized[3] > size[1]
        ):
            return False
        if kind == "click":
            return True
        values = (evidence.get("dx"), evidence.get("dy"), evidence.get("duration_ms"))
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            return False
        dx, dy, duration_ms = values
        if abs(dx) > 1000 or abs(dy) > 1000 or not 50 <= duration_ms <= 5000:
            return False
        start_x = normalized[0] + normalized[2] // 2
        start_y = normalized[1] + normalized[3] // 2
        if size is not None and not (
            0 <= start_x + dx < size[0] and 0 <= start_y + dy < size[1]
        ):
            return False
        return True
    except (TypeError, ValueError):
        return False


def _target_box(reco_detail: Any, evidence: Mapping[str, Any], fallback: Any) -> Any:
    """Use the verified target sub-result box when Maa supplied one.

    An ``And`` recognition's outer box is commonly the page/template box. The
    target OCR/template is the only safe point to click, and it must come from
    the same recognition frame that satisfied the evidence contract.
    """

    results = _sub_results(reco_detail)
    target_index = _strict_index(evidence.get("target_index"))
    if results is None or target_index is None or target_index >= len(results):
        return fallback
    target = results[target_index]
    if not getattr(target, "hit", False):
        return fallback
    target_box = getattr(target, "box", None)
    return target_box if target_box is not None else fallback


def _fixed_click_boxes(params: Mapping[str, Any]) -> tuple[tuple[int, int, int, int], ...] | None:
    """Validate the one action that intentionally clicks static game anchors.

    The Shadow foreground row has no reliable OCR target.  Its page marker is
    still required as same-frame evidence, while this action uses three
    calibrated, bounded Android hit boxes in a fixed left-to-right order.
    Keeping this exception action-specific prevents arbitrary custom payloads
    from turning GuardedInput into an unrestricted coordinate clicker.
    """

    if "fixed_click_boxes" not in params:
        return None
    if params.get("action_id") != "advance_shadow_foreground_triplet":
        raise ValueError("fixed_click_boxes is not allowed for this action")
    if params.get("kind") != "click":
        raise ValueError("fixed_click_boxes requires click kind")
    raw_boxes = params["fixed_click_boxes"]
    if not isinstance(raw_boxes, Sequence) or isinstance(
        raw_boxes, (str, bytes, bytearray)
    ) or len(raw_boxes) != 3:
        raise ValueError("fixed_click_boxes must contain exactly three boxes")
    try:
        return tuple(box_values(box) for box in raw_boxes)
    except (TypeError, ValueError) as exc:
        raise ValueError("fixed_click_boxes must contain valid rectangles") from exc


_FIXED_CLICK_MODES: Mapping[tuple[str, str], tuple[int, int, int, int]] = {
    # The trial shortcut is a stable home-only anchor, but its decorative
    # glyph is not a reliable OCR/ColorMatch target.  The named mode keeps
    # the fixed box action-specific; the home page still has to be present in
    # the same-frame GuardedInput evidence before this click is allowed.
    (
        "open_trial_sword",
        "trial_entry_button",
    ): (987, 530, 52, 60),
    # The home-page dueling icon sits above the 310/310 counter.  It is a
    # stable decorative icon, so use a bounded fixed box instead of guessing
    # among the nearby OCR labels.
    (
        "open_dueling_menu",
        "dueling_menu_button",
    ): (1090, 585, 85, 80),
    # The world-page function row is a decorative image strip.  OCR can
    # merge 副本/画卷/祈福 into one box and clicking that merged box opens the
    # wrong neighbouring icon.  This named mode is the only coordinate path
    # for opening the painting scroll: the pipeline must first prove the
    # world-page image marker in the same frame.
    (
        "open_painting_scroll",
        "painting_scroll_button",
    ): (1105, 35, 50, 55),
    # The arena sweep control is a stable lower-left button.  Its label can
    # be greyed out at 0/12 and then disappear from OCR, so the opponent-page
    # evidence gates this fixed click instead of the label OCR.
    (
        "sweep_ring",
        "ring_sweep_button",
    ): (0, 570, 250, 140),
    # The opponent and arena pages both close through the stable upper-right
    # X.  Keep these taps action-specific and require page evidence in the
    # pipeline before allowing them.
    (
        "close_ring_opponents",
        "ring_opponents_close",
    ): (1160, 0, 100, 90),
    (
        "close_ring_page",
        "ring_page_close",
    ): (1160, 0, 100, 90),
    (
        "close_dueling_menu",
        "dueling_menu_close",
    ): (1205, 33, 18, 18),
    (
        "enter_shadow_stage",
        "shadow_stage_entry_button",
    ): (740, 490, 210, 50),
    (
        "dismiss_shadow_battle_result",
        "shadow_result_blank",
    ): (560, 620, 160, 80),
    (
        "dismiss_shadow_battle_failure",
        "shadow_result_blank",
    ): (560, 620, 160, 80),
    (
        "dismiss_ring_result",
        "ring_result_blank",
    ): (560, 620, 160, 80),
    (
        "close_condensate_result",
        "jianlin_result_blank",
    ): (560, 620, 160, 80),
    (
        "dismiss_guild_result",
        "guild_result_blank",
    ): (560, 620, 160, 80),
    (
        "dismiss_guild_defeat_result",
        "guild_result_defeat_blank",
    ): (560, 620, 160, 80),
    (
        "dismiss_shadow_reward_popup",
        "shadow_reward_blank",
    ): (250, 560, 160, 120),
    (
        "close_jianlin_for_food",
        "jianlin_page_close",
    ): (1180, 15, 95, 95),
    # Jianlin's resource/battle page uses the same stable upper-right X. The
    # cleanup path deliberately gates this fixed tap with the Jianlin page
    # marker because the icon is not reliably read as the word “关闭”.
    (
        "close_jianlin_page",
        "jianlin_page_close",
    ): (1205, 33, 18, 18),
    # The equipment page's template covers a larger area than the actual X;
    # click the center of the visible upper-right close icon instead of the
    # template-box center, which is above the hit target.
    (
        "close_equipment_page",
        "equipment_page_close",
    ): (1198, 35, 40, 42),
    # Cross-map teleport confirm for shadow ruins: the dialog's 确认 button is
    # OCR-unstable, so pin the click to the confirmed button area.
    (
        "confirm_shadow_teleport",
        "shadow_teleport_confirm",
    ): (875, 500, 60, 40),
    # Leave the shadow stage from the stage screen; Android BACK does not
    # close this screen reliably.
    (
        "leave_shadow_stage",
        "shadow_stage_leave",
    ): (1080, 625, 150, 55),
    # Guild activity defeat reward popup dismisses by tapping blank area.
    (
        "dismiss_guild_activity_reward_popup",
        "guild_activity_reward_blank",
    ): (560, 620, 160, 80),
    # Daily-task reward overlays have no dependable close label. The reward
    # popup itself is still required as same-frame evidence; this named blank
    # area only supplies the stable dismissal point.
    (
        "close_reward_popup",
        "daily_reward_popup_blank",
    ): (550, 665, 180, 45),
    # Donation reward sheets use the same blank-tap dismissal as the other
    # reward overlays. The popup and its close-text evidence are still
    # required in the same frame before this fixed tap is permitted.
    (
        "close_android_donation_reward",
        "guild_donation_reward_blank",
    ): (550, 665, 180, 45),
    # Appraisal reward overlay is a borderless dim-layer graphic with no close
    # button; it dismisses on a blank tap.  Keep the tap below the paid
    # 鉴宝 buttons (which end at y=643) so it cannot hit page controls.
    (
        "close_appraisal_popup",
        "appraisal_reward_blank",
    ): (550, 665, 180, 45),
    (
        "close_extra_reward_popup",
        "appraisal_reward_blank",
    ): (550, 665, 180, 45),
    **{
        (action_id, "function_panel_close"): (1195, 10, 70, 70)
        for action_id in (
            "close_function_panel",
            "close_shop",
        )
    },
}


def _fixed_click_mode_box(params: Mapping[str, Any]) -> tuple[int, int, int, int] | None:
    """Resolve a named, action-specific blank-area dismissal target."""

    if "fixed_click_mode" not in params:
        return None
    if "fixed_click_boxes" in params:
        raise ValueError("fixed_click_mode cannot be combined with fixed_click_boxes")
    mode = params["fixed_click_mode"]
    if not isinstance(mode, str) or (params.get("action_id"), mode) not in _FIXED_CLICK_MODES:
        raise ValueError("fixed_click_mode is not allowed for this action")
    if params.get("kind") != "click":
        raise ValueError("fixed_click_mode requires click kind")
    return _FIXED_CLICK_MODES[(params["action_id"], mode)]


@AgentServer.custom_action("GuardedInput")
class GuardedInput(CustomAction):
    """Perform click/swipe only after same-frame evidence and budget checks."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        params: Mapping[str, Any] | None = None
        try:
            params = parse_action_params(argv)
            if not validate_and_evidence(argv.reco_detail, params["evidence"], params):
                _record_denial(context, params, "same_frame_evidence")
                return False
            policy = TASK_POLICIES[params["task_id"]]
            resource_id = params.get("resource_id")
            budget_amount = params.get("budget_amount")
            if resource_id is not None:
                if resource_id not in policy.resource_caps:
                    _record_denial(context, params, "resource_policy")
                    return False
                if (
                    isinstance(budget_amount, bool)
                    or not isinstance(budget_amount, int)
                    or budget_amount <= 0
                ):
                    _record_denial(context, params, "resource_budget")
                    return False
            controller = context.tasker.controller
            resolution = getattr(controller, "resolution", None)
            input_box = _target_box(argv.reco_detail, params["evidence"], argv.box)
            if not _validate_input_shape(
                params["kind"], input_box, params["evidence"], resolution
            ):
                _record_denial(context, params, "input_shape")
                return False
            fixed_boxes = _fixed_click_boxes(params)
            fixed_mode_box = _fixed_click_mode_box(params)
            if fixed_boxes is not None and any(
                not _validate_input_shape("click", box, params["evidence"], resolution)
                for box in fixed_boxes
            ):
                _record_denial(context, params, "fixed_input_shape")
                return False
            if fixed_mode_box is not None and not _validate_input_shape(
                "click", fixed_mode_box, params["evidence"], resolution
            ):
                _record_denial(context, params, "fixed_mode_input_shape")
                return False
            RUN_STORE.increment(params["task_id"], params["action_id"])
            if resource_id is not None:
                RUN_STORE.consume_resource(params["task_id"], resource_id, budget_amount)
            if (
                params["task_id"] == "EAT_STAMINA_FOOD_DAILY"
                and params["action_id"] == "eat_longjing_shrimp"
                and resource_id == "龙井虾仁"
            ):
                results = _sub_results(argv.reco_detail)
                amount_index = _strict_index(params.get("amount_index"))
                if results is None or amount_index is None or amount_index >= len(results):
                    raise RuntimeError("food amount observation is missing")
                before_amount = _ocr_amount(_ocr_text(results[amount_index]) or "")
                if before_amount is None or before_amount <= 0:
                    raise RuntimeError("food amount observation is invalid")
                RUN_STORE.set_marker(
                    params["task_id"], "food.longjing_shrimp.before_amount", before_amount
                )
            diagnostics = diagnostics_for(context, params["task_id"])
            if diagnostics is not None:
                diagnostics.record_action(
                    params["action_id"],
                    {"task_id": params["task_id"], "allowed": True},
                )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            if params is not None:
                _record_denial(context, params, type(exc).__name__)
            return False

        if params["kind"] == "none":
            return True
        if params["kind"] == "click":
            fixed_boxes = _fixed_click_boxes(params)
            if fixed_boxes is not None:
                for box in fixed_boxes:
                    click_box(controller, box, resolution=resolution)
                return True
            fixed_mode_box = _fixed_click_mode_box(params)
            if fixed_mode_box is not None:
                return click_box(controller, fixed_mode_box, resolution=resolution)
            return click_box(
                controller,
                _target_box(argv.reco_detail, params["evidence"], argv.box),
                resolution=resolution,
            )
        evidence = params["evidence"]
        return swipe_box(
            controller,
            _target_box(argv.reco_detail, evidence, argv.box),
            dx=evidence["dx"],
            dy=evidence["dy"],
            duration_ms=evidence["duration_ms"],
            resolution=resolution,
        )


__all__ = ["GuardedInput", "validate_and_evidence"]
