from __future__ import annotations

import pytest

from tests.mfw.task_contract import (
    assert_abort_code,
    assert_battle_result_partition,
    assert_condition,
    assert_no_side_effect_retry,
    assert_ordered_actions,
    assert_resource_guard,
    assert_shared_resource_budget,
    assert_terminal_after_loop,
)


def _guarded(action_id: str, *, on_error: list[str] | None = None) -> dict:
    return {
        "action": "Custom",
        "custom_action": "GuardedInput",
        "custom_action_param": {
            "task_id": "BUY_TEA_DAILY",
            "action_id": action_id,
            "kind": "click",
            "resource_id": "文",
            "resource_index": 2,
            "amount_index": 3,
            "observed_amount": 500,
            "budget_amount": 500,
            "evidence": {
                "page_index": 0,
                "target_index": 1,
                "page_name": "tea.purchase",
                "target_name": "tea.buy",
            },
        },
        "next": ["VERIFY"],
        "on_error": on_error or ["ABORT"],
    }


def test_resource_guard_requires_exact_same_frame_budget_fields() -> None:
    nodes = {"BUY": _guarded("buy_tea")}
    assert_resource_guard(nodes, "buy_tea", "文", 500, task_id="BUY_TEA_DAILY")

    nodes["BUY"]["custom_action_param"]["resource_id"] = "凝晶"
    with pytest.raises(AssertionError):
        assert_resource_guard(nodes, "buy_tea", "文", 500)


def test_no_side_effect_retry_rejects_an_error_path_to_same_action() -> None:
    nodes = {"BUY": _guarded("buy_tea"), "ABORT": {"action": "StopTask"}}
    assert_no_side_effect_retry(nodes, "buy_tea")

    nodes["ABORT"] = _guarded("buy_tea")
    with pytest.raises(AssertionError):
        assert_no_side_effect_retry(nodes, "buy_tea")


def test_order_and_abort_helpers_cover_phase_boundaries() -> None:
    nodes = {
        "OPEN": _guarded("open_tea"),
        "BUY": _guarded("buy_tea"),
        "VERIFY": {"recognition": "OCR", "action": "DoNothing"},
        "ABORT": {"action": "DoNothing", "next": ["MJA_COMMON_ABORT"]},
        "MJA_COMMON_ABORT": {"action": "StopTask"},
        "FAIL": {
            "action": "Custom",
            "custom_action": "RecordTaskOutcome",
            "custom_action_param": {
                "status": "failed",
                "error_code": "TEA_PRICE_OR_CURRENCY_UNVERIFIED",
            },
        },
    }
    nodes["OPEN"]["next"] = ["BUY"]
    nodes["BUY"]["next"] = ["VERIFY"]
    assert_ordered_actions(nodes, ["open_tea", "buy_tea"])
    assert_abort_code(nodes, "FAIL", "TEA_PRICE_OR_CURRENCY_UNVERIFIED")


def test_shared_resource_budget_sums_consumptive_phases() -> None:
    first = _guarded("buy_yanwu_currency_max")
    second = _guarded("buy_yunzhou_currency_max")
    first["custom_action_param"]["budget_amount"] = 60_000
    first["custom_action_param"]["observed_amount"] = 60_000
    second["custom_action_param"]["budget_amount"] = 40_000
    second["custom_action_param"]["observed_amount"] = 40_000
    assert_shared_resource_budget(
        {"FIRST": first, "SECOND": second}, "文", 100_000
    )

    second["custom_action_param"]["budget_amount"] = 40_001
    with pytest.raises(AssertionError):
        assert_shared_resource_budget(
            {"FIRST": first, "SECOND": second}, "文", 100_000
        )


def test_terminal_after_loop_requires_bounded_abort_path() -> None:
    nodes = {
        "LOOP": {"max_hit": 3, "next": ["LOOP_EXHAUSTED"]},
        "LOOP_EXHAUSTED": {
            "action": "Custom",
            "custom_action": "RecordTaskOutcome",
            "custom_action_param": {
                "status": "failed",
                "error_code": "LOOP_EXHAUSTED",
            },
            "next": ["ABORT"],
        },
        "ABORT": {"action": "DoNothing", "next": ["MJA_COMMON_ABORT"]},
        "MJA_COMMON_ABORT": {"action": "StopTask"},
        "OTHER": {"action": "StopTask"},
    }
    assert_terminal_after_loop(nodes, "LOOP", 3, "LOOP_EXHAUSTED")
    nodes["LOOP_EXHAUSTED"]["next"] = ["OTHER"]
    with pytest.raises(AssertionError):
        assert_terminal_after_loop(nodes, "LOOP", 3, "LOOP_EXHAUSTED")


def test_battle_result_partition_rejects_missing_unknown_abort_branch() -> None:
    nodes = {
        "MJA_RESULT_VICTORY": {"action": "StopTask"},
        "MJA_RESULT_DEFEAT": {"action": "StopTask"},
        "MJA_RESULT_UNKNOWN_RESULT": {"action": "StopTask"},
        "MJA_COMMON_ABORT": {"action": "StopTask"},
    }
    with pytest.raises(AssertionError):
        assert_battle_result_partition(nodes, "MJA_RESULT")
    nodes["MJA_RESULT_UNKNOWN_RESULT"]["next"] = ["MJA_COMMON_ABORT"]
    assert_battle_result_partition(nodes, "MJA_RESULT")


def test_condition_helper_requires_explicit_semantic_condition() -> None:
    nodes = {
        "SWEEP": {
            "action": "Custom",
            "custom_action_param": {"condition": "master_mode_or_score_gte_5000"},
        }
    }
    assert_condition(nodes, "SWEEP", "master_mode_or_score_gte_5000")
    with pytest.raises(AssertionError):
        assert_condition(nodes, "SWEEP", "anything_else")
