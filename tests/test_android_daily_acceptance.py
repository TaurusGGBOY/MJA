from __future__ import annotations

import json
from pathlib import Path

from agent.workflows.catalog import TASK_POLICIES, WORKFLOW_DEFINITION_ORDER
from agent.workflows.navigation import load_fixture_manifest
from agent.workflows.registry import WORKFLOW_DEFINITIONS

ROOT = Path(__file__).resolve().parents[1]


def test_daily_all_has_registered_runtime_pipeline():
    pipeline = ROOT / "assets/resource_android/pipeline/daily/daily_all.json"
    payload = json.loads(pipeline.read_text(encoding="utf-8"))
    assert payload["MJA_Daily_All"] == {
        "recognition": "DirectHit",
        "action": "Custom",
        "custom_action": "AggregateDailyWorkflowAction",
        "custom_action_param": {"selection": ["daily_all"]},
    }


def test_every_canonical_daily_task_has_runtime_contract():
    for task_id in WORKFLOW_DEFINITION_ORDER:
        assert task_id in TASK_POLICIES
        assert task_id in WORKFLOW_DEFINITIONS
        pipeline = ROOT / "assets/resource_android/pipeline/daily" / f"{task_id}.json"
        assert pipeline.is_file(), task_id
        payload = json.loads(pipeline.read_text(encoding="utf-8"))
        assert payload, task_id
        assert any(
            node.get("custom_action") == "DailyWorkflowAction"
            and node.get("custom_action_param", {}).get("task_id") == task_id
            for node in payload.values()
            if isinstance(node, dict)
        )


def test_buy_tea_pipeline_matches_native_maa_bbb_style():
    payload = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily/buy_tea_daily.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["MJA_Daily_BUY_TEA_DAILY"]["custom_action"] == (
        "DailyWorkflowAction"
    )
    assert payload["MJA_Daily_BUY_TEA_DAILY"]["custom_action_param"] == {
        "task_id": "BUY_TEA_DAILY"
    }
    assert sum(node.get("action") == "Click" for node in payload.values()) >= 8
    assert payload["MJA_BUY_TEA_DAILY_START_GAME"]["expected"] == [
        "点击开始游戏",
        "进入游戏",
    ]
    assert not any(node.get("action") == "StartApp" for node in payload.values())
    assert "MJA_BUY_TEA_DAILY_START_APP" not in payload
    assert payload["MJA_BUY_TEA_DAILY_START_GAME"]["timeout"] == 15000
    assert payload["MJA_BUY_TEA_DAILY_START_GAME"]["next"][0] == (
        "MJA_BUY_TEA_DAILY_START_GAME"
    )
    assert payload["MJA_BUY_TEA_DAILY_SELECT_TEA"]["recognition"] == (
        "TemplateMatch"
    )
    assert payload["MJA_BUY_TEA_DAILY_SELECT_TEA"]["template"] == (
        "daily/BUY_TEA_DAILY/tea_item.png"
    )
    assert payload["MJA_BUY_TEA_DAILY_UNIVERSAL_SHOP_PAGE"]["template"] == (
        "daily/BUY_TEA_DAILY/tea_item.png"
    )
    assert payload["MJA_BUY_TEA_DAILY_OPEN_PURCHASE"]["template"] == (
        "daily/BUY_TEA_DAILY/purchase_control.png"
    )
    assert payload["MJA_BUY_TEA_DAILY_PURCHASE_RESULT"]["template"] == (
        "daily/BUY_TEA_DAILY/purchase_result.png"
    )
    assert payload["MJA_BUY_TEA_DAILY_CLOSE_PURCHASE_RESULT"]["next"] == (
        "MJA_BUY_TEA_DAILY_TEA_DETAIL"
    )
    assert payload["MJA_BUY_TEA_DAILY_SAFE_RESOURCE"]["expected"] == "文"
    assert payload["MJA_BUY_TEA_DAILY_SOLD_OUT"]["template"] == (
        "daily/BUY_TEA_DAILY/sold_out.png"
    )
    assert payload["MJA_BUY_TEA_DAILY_SOLD_OUT"]["next"] == (
        "MJA_BUY_TEA_DAILY_CLOSE_UNIVERSAL_SHOP"
    )
    assert payload["MJA_BUY_TEA_DAILY_CLOSE_UNIVERSAL_SHOP"]["template"] == (
        "daily/BUY_TEA_DAILY/shop_close.png"
    )


def test_every_canonical_daily_task_has_strict_fixture_and_pending_record():
    for task_id in WORKFLOW_DEFINITION_ORDER:
        manifest = ROOT / "tests/fixtures" / task_id / "manifest.json"
        loaded = load_fixture_manifest(manifest)
        assert loaded.task_id == task_id
        record = ROOT / "verification/tasks" / f"{task_id}.json"
        payload = json.loads(record.read_text(encoding="utf-8"))
        assert payload["task_id"] == task_id
        assert payload["state"] == "live_pending"


def test_aggregate_order_is_stable_and_battle_pass_is_last():
    assert len(WORKFLOW_DEFINITION_ORDER) == 17
    assert WORKFLOW_DEFINITION_ORDER[-1] == "BATTLE_PASS_REWARD_DAILY"


def test_jianlin_confirmation_pipeline_matches_live_prompt_text():
    payload = json.loads(
        (
            ROOT
            / (
                "assets/resource_android/pipeline/daily/"
                "jianlin_resource_condensate_stamina_daily.json"
            )
        ).read_text(encoding="utf-8")
    )
    prompt = payload["jianlin_stamina_confirmation_prompt"]
    assert prompt["recognition"] == "OCR"
    assert "体力将于" in prompt["expected"]
    assert "是否花费" in prompt["expected"]
    assert payload["jianlin_stamina_confirmation_confirm"]["expected"] == "^确认$"
