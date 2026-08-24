from __future__ import annotations

import pytest

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
    load_nodes,
)
from tests.mfw.task_contract import assert_native_terminal_contract


def test_common_terminals_are_native_and_legacy_routes_are_gone() -> None:
    nodes = load_nodes("assets/resource/base/pipeline")

    assert_native_terminal_contract(
        nodes,
        success_nodes=["1369-公共-通用停止"],
        failure_nodes=[],
    )
    assert "1371-公共-原生成功-主页边界" in nodes
    assert "1372-公共-原生成功-尝试返回" in nodes
    assert nodes["1363-公共-主页边界"]["action"] == "DoNothing"
    assert nodes["1365-公共-主页边界-失败"]["custom_action"] == "FailTask"
    assert nodes["1366-公共-通用中止"]["custom_action"] == "FailTask"
    assert "1364-公共-主页边界-尝试返回" not in nodes
    assert "1367-公共-失败-主页-探测" not in nodes
    assert "1368-公共-失败-返回主页" not in nodes


def test_native_terminal_helpers_accept_only_framework_owned_endpoints() -> None:
    assert_native_success_node({"action": "DoNothing"})
    assert_native_success_node({"action": "StopTask"})
    assert_native_failure_node(
        {"action": "Custom", "custom_action": "FailTask", "Abort": True}
    )

    with pytest.raises(AssertionError):
        assert_native_success_node(
            {"action": "Custom", "custom_action": "RecordTaskOutcome"}
        )
    with pytest.raises(AssertionError):
        assert_native_failure_node(
            {
                "action": "Custom",
                "custom_action": "FailTask",
                "Abort": True,
                "custom_action_param": {"status": "failed"},
            }
        )
    with pytest.raises(AssertionError):
        assert_native_failure_node(
            {
                "action": "Custom",
                "custom_action": "FailTask",
                "Abort": True,
                "next": ["1369-公共-通用停止"],
            }
        )


def test_migrated_pipeline_is_checked_against_native_terminal_topology() -> None:
    migrated = {
        "TASK_DONE": {"action": "StopTask"},
        "TASK_FAILED": {
            "action": "Custom",
            "custom_action": "FailTask",
            "Abort": True,
        },
        "TASK_RETRY": {
            "action": "DoNothing",
            "next": ["TASK_DONE"],
            "on_error": ["TASK_RETRY"],
            "max_hit": 1,
        },
    }
    assert_no_custom_outcome_nodes(migrated)
    assert_on_error_contract(migrated, local_nodes=set(migrated))
    assert_native_terminal_contract(
        migrated,
        success_nodes=["TASK_DONE"],
        failure_nodes=["TASK_FAILED"],
    )


@pytest.mark.parametrize(
    ("node", "message"),
    [
        ({"action": "DoNothing", "on_error": []}, "empty on_error"),
        ({"action": "DoNothing", "on_error": ["external:result"]}, "external"),
        ({"action": "DoNothing", "on_error": ["OTHER_TASK"]}, "cross-task"),
    ],
)
def test_on_error_contract_rejects_empty_external_and_cross_task_edges(
    node: dict[str, object], message: str
) -> None:
    with pytest.raises(AssertionError, match=message):
        assert_on_error_contract(
            {"TASK_NODE": node},
            local_nodes={"TASK_NODE"},
            shared_targets={"1369-公共-通用停止"},
        )
