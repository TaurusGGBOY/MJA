from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_native_success_node,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)

ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline/daily/mail_reward_daily.json"


def _mail_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_mail_reward_has_explicit_empty_and_claim_candidates() -> None:
    nodes = _mail_nodes()

    assert nodes["1035-邮件奖励-打开-邮件"]["next"] == [
        "1036-邮件奖励-领取",
        "1050-邮件奖励-邮件-空",
    ]
    assert "on_error" not in nodes["1035-邮件奖励-打开-邮件"]
    assert "on_error" not in nodes["1036-邮件奖励-领取"]

    empty = nodes["1050-邮件奖励-邮件-空"]
    assert empty["recognition"] == "OCR"
    assert empty["expected"] == ["删除已读", "除已读", "暂无可领取"]
    assert empty["next"] == ["1041-邮件奖励-关闭"]


def test_mail_reward_confirmed_claim_and_empty_state_reach_native_success() -> None:
    nodes = _mail_nodes()

    assert nodes["1039-邮件奖励-领取-成功"]["action"] == "DoNothing"
    assert nodes["1039-邮件奖励-领取-成功"]["next"] == [
        "1040-邮件奖励-关闭-奖励"
    ]
    assert nodes["1040-邮件奖励-关闭-奖励"]["next"] == [
        "1041-邮件奖励-关闭"
    ]
    assert nodes["1043-邮件奖励-主页边界-探测"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]

    assert_native_success_node(nodes["1044-邮件奖励-边界-失败"])


def test_mail_reward_uses_stateless_failure_and_no_legacy_outcomes() -> None:
    nodes = _mail_nodes()

    assert_native_failure_node(nodes["1034-邮件奖励-记录-失败"])
    assert nodes["1033-邮件奖励-打开-面板"]["on_error"] == [
        "1034-邮件奖励-记录-失败"
    ]
    assert "1037-邮件奖励-已完成" not in nodes
    assert_no_custom_outcome_nodes(nodes)
    assert_on_error_contract(nodes, local_nodes=set(nodes))


def test_mail_reward_preserves_bounded_claim_and_cleanup_actions() -> None:
    nodes = _mail_nodes()

    assert nodes["1036-邮件奖励-领取"]["max_hit"] == 1
    assert nodes["1036-邮件奖励-领取"]["timeout"] == 5000
    assert nodes["1040-邮件奖励-关闭-奖励"]["max_hit"] == 1
    assert nodes["1041-邮件奖励-关闭"]["max_hit"] == 1
    assert nodes["1042-邮件奖励-关闭-面板"]["max_hit"] == 1
    assert nodes["1038-邮件奖励-奖励-探测"].get("on_error") is None


def test_mail_reward_close_roi_is_tight_around_live_close_button() -> None:
    nodes = _mail_nodes()

    # The live reward-mail close button is near (1075, 145).  A broad
    # recognition box lets MAA choose a point below the actual button.
    close = nodes["1053-邮件奖励-邮件-关闭"]
    assert close["template"] == "daily/MAIL_REWARD_DAILY/mail_close_live_tight.png"
    assert close["roi"] == [1053, 115, 45, 45]
