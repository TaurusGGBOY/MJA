from dataclasses import FrozenInstanceError

import pytest

from agent.workflows.models import (
    ActionIntent,
    CapturedFrame,
    Decision,
    RiskLevel,
    TaskPolicy,
    TaskResult,
    TaskStatus,
    Transition,
)


def policy(**overrides) -> TaskPolicy:
    values = {
        "task_id": "MAIL_REWARD_DAILY",
        "label": "邮件奖励",
        "entry": "MJA_Daily_MAIL_REWARD_DAILY",
        "risk_levels": frozenset({RiskLevel.PROTECTED_CLAIM}),
        "max_steps": 8,
        "action_caps": {"click": 4, "none": 1},
        "approved_resources": frozenset(),
    }
    values.update(overrides)
    return TaskPolicy(**values)


def test_task_status_has_only_runtime_values() -> None:
    assert {item.value for item in TaskStatus} == {
        "completed",
        "already_complete",
        "not_eligible",
        "failed",
    }


def test_models_are_frozen_and_slot_based() -> None:
    current = policy()
    assert current.__dataclass_params__.frozen
    assert hasattr(current, "__slots__")
    with pytest.raises(FrozenInstanceError):
        current.max_steps = 9


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("task_id", "", "task_id"),
        ("max_steps", 0, "max_steps"),
        ("max_steps", True, "max_steps"),
        ("action_caps", {"click": -1}, "cap"),
        ("action_caps", {"unknown": 1}, "action"),
        ("action_caps", {"click": True}, "cap"),
    ],
)
def test_task_policy_rejects_invalid_values(field, value, message) -> None:
    with pytest.raises(ValueError, match=message):
        policy(**{field: value})


def test_task_policy_normalizes_ids_and_freezes_mappings() -> None:
    current = policy(task_id=" mail_reward_daily ", entry="MJA_Daily_MAIL_REWARD_DAILY")
    assert current.task_id == "MAIL_REWARD_DAILY"
    with pytest.raises(TypeError):
        current.action_caps["click"] = 5


def test_action_intent_accepts_only_supported_input_kinds() -> None:
    assert ActionIntent("claim", "home", "mail", input_kind="click").input_kind.value == "click"
    with pytest.raises(ValueError, match="input_kind"):
        ActionIntent("claim", "home", "mail", input_kind="teleport")


def test_captured_frame_rejects_empty_id_and_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="frame_id"):
        CapturedFrame("", (1280, 720))
    with pytest.raises(ValueError, match="size"):
        CapturedFrame("frame-1", (0, 720))


def test_decision_act_requires_transition() -> None:
    transition = Transition(
        intent=ActionIntent("claim", "mail", "claim_button"),
        postcondition="mail_claimed",
    )
    assert Decision.act(transition).transition is transition
    with pytest.raises(ValueError, match="transition"):
        Decision.act()


def test_decision_finish_requires_a_runtime_status() -> None:
    assert Decision.finish(TaskStatus.COMPLETED).status is TaskStatus.COMPLETED
    with pytest.raises(ValueError, match="status"):
        Decision.finish("live_verified")


def test_task_result_rejects_unknown_status_aliases() -> None:
    with pytest.raises(ValueError, match="status"):
        TaskResult(
            task_id="MAIL_REWARD_DAILY",
            status="completed",
            postcondition="mail_closed",
            action_counts={},
        )


def test_task_result_normalizes_task_id_and_freezes_counts() -> None:
    result = TaskResult(
        task_id=" mail_reward_daily ",
        status=TaskStatus.COMPLETED,
        postcondition="mail_closed",
        action_counts={"click": 2},
    )
    assert result.task_id == "MAIL_REWARD_DAILY"
    with pytest.raises(TypeError):
        result.action_counts["click"] = 3


def test_policy_and_result_have_explicit_json_serialization() -> None:
    current = policy()
    assert current.as_dict()["risk_levels"] == ["protected_claim"]
    assert current.as_dict()["action_caps"] == {"click": 4, "none": 1}

    result = TaskResult(
        task_id="MAIL_REWARD_DAILY",
        status=TaskStatus.ALREADY_COMPLETE,
        postcondition="mail_closed",
        action_counts={"click": 1},
    )
    assert result.as_dict() == {
        "task_id": "MAIL_REWARD_DAILY",
        "status": "already_complete",
        "postcondition": "mail_closed",
        "action_counts": {"click": 1},
        "error_code": None,
    }
