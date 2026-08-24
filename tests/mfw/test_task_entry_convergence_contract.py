from __future__ import annotations

import json
from pathlib import Path

from tools.check_mfw_resources import check_resource_tree, check_task_entry_contracts

ROOT = Path("assets/resource/base/pipeline")


def _write_daily(tmp_path: Path, nodes: dict[str, dict]) -> Path:
    pipeline = tmp_path / "pipeline"
    daily = pipeline / "daily"
    daily.mkdir(parents=True)
    (daily / "sample.json").write_text(json.dumps(nodes), encoding="utf-8")
    return pipeline


def test_native_failure_leaf_satisfies_the_task_entry_contract(tmp_path: Path) -> None:
    pipeline = _write_daily(
        tmp_path,
        {
            "TASK_ENTRY": {
                "custom_action": "BeginTask",
                "next": ["TASK_HOME", "TASK_FAIL"],
            },
            "TASK_HOME": {"recognition": "OCR", "action": "DoNothing", "next": ["STOP"]},
            "TASK_FAIL": {
                "action": "Custom",
                "custom_action": "FailTask",
                "Abort": True,
            },
            "STOP": {"action": "StopTask"},
        },
    )
    diagnostics = check_task_entry_contracts(pipeline)
    assert all(item.ok for item in diagnostics)


def test_empty_on_error_is_rejected() -> None:
    from tests.mfw.pipeline_assertions import assert_on_error_contract

    try:
        assert_on_error_contract({"NODE": {"on_error": []}}, local_nodes={"NODE"})
    except AssertionError as exc:
        assert "empty on_error" in str(exc)
    else:
        raise AssertionError("empty on_error was accepted")


def test_native_failure_leaf_rejects_parameters_and_routes() -> None:
    from tests.mfw.pipeline_assertions import assert_native_failure_node

    for node in (
        {
            "action": "Custom",
            "custom_action": "FailTask",
            "Abort": True,
            "custom_action_param": {"reason": "x"},
        },
        {
            "action": "Custom",
            "custom_action": "FailTask",
            "Abort": True,
            "next": ["STOP"],
        },
    ):
        try:
            assert_native_failure_node(node)
        except AssertionError:
            continue
        raise AssertionError("malformed FailTask was accepted")


def test_real_daily_inventory_has_no_task_entry_gate_gaps() -> None:
    diagnostics = check_task_entry_contracts(ROOT)
    gaps = [item.format() for item in diagnostics if not item.ok]
    assert not gaps, "\n".join(gaps)


def test_resource_tree_surfaces_task_gate_errors_only_when_requested() -> None:
    assert not [
        error
        for error in check_resource_tree(Path("assets/resource/base"))
        if error.startswith("task entry gate:")
    ]
    assert not [
        error
        for error in check_resource_tree(Path("assets/resource/base"), task_entry_gate=True)
        if error.startswith("task entry gate:")
    ]
