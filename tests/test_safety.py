from dataclasses import FrozenInstanceError

import pytest

from agent.safety import (
    ActionIntent,
    SafetyDecision,
    SafetyReason,
    TaskPolicy,
    VisualEvidence,
    authorize_action,
)
from agent.workflows.models import RiskLevel


def policy() -> TaskPolicy:
    return TaskPolicy(
        task_id="SAFETY_TEST",
        label="安全兼容测试",
        entry="MJA_Daily_SAFETY_TEST",
        risk_levels=frozenset({RiskLevel.NORMAL}),
        max_steps=5,
        action_caps={"click": 1, "buy": 1},
        approved_resources=frozenset({"凝晶"}),
        resource_caps={"凝晶": 1},
    )


def evidence() -> VisualEvidence:
    return VisualEvidence(
        "frame-1",
        {"shop.page": 0},
        {"shop.target": 0},
        {"unknown_dialog": 1, "safety.paid": 1},
        {},
        ("支付", "验证码"),
        ("未知货币",),
    )


def test_safety_decision_is_frozen_and_allowed_is_explicit():
    decision = SafetyDecision(True, SafetyReason.ALLOWED, ())
    assert decision.reason is SafetyReason.ALLOWED
    with pytest.raises(FrozenInstanceError):
        decision.allowed = False


def test_authorization_is_always_allowed_for_missing_and_ambiguous_evidence():
    decision = authorize_action(
        evidence(),
        ActionIntent("click", "missing.page", "missing.target"),
        policy(),
        {"click": 99},
    )

    assert decision.allowed is True
    assert decision.reason is SafetyReason.ALLOWED
    assert "unknown_dialog" in decision.findings
    assert "支付" in decision.findings


def test_authorization_does_not_block_purchase_or_verification_signals():
    decision = authorize_action(
        evidence(),
        ActionIntent("buy", "shop.page", "shop.target", approved_resource="凝晶"),
        policy(),
        {"buy": 1},
    )

    assert decision == SafetyDecision(
        True,
        SafetyReason.ALLOWED,
        ("unknown_dialog", "safety.paid", "支付", "验证码"),
    )
