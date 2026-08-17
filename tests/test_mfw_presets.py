from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_mfw_imports_startup_and_batch_a_tasks_separately() -> None:
    interface = json.loads(
        (ROOT / "assets/interface.json").read_text(encoding="utf-8")
    )
    assert interface["task"] == []
    assert interface["import"] == [
        "tasks/游戏启动.json",
        "tasks/日常/MAIL_REWARD_DAILY.json",
        "tasks/日常/SHOP_FREE_GIFT_DAILY.json",
        "tasks/日常/BUY_TEA_DAILY.json",
        "tasks/日常/FREE_APPRAISAL_DAILY.json",
        "tasks/日常/TRIAL_SWORD_DAILY.json",
        "tasks/日常/HERO_DISPATCH_DAILY.json",
        "tasks/日常/COLLECTION_DEPLOYMENT_DAILY.json",
        "tasks/日常/WEEKLY_FREE_GIFT_MONDAY.json",
        "tasks/日常/SHADOW_RUINS_DAILY.json",
        "tasks/日常/SPEND_CONDENSATE_DAILY.json",
        "tasks/日常/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json",
        "tasks/日常/EAT_STAMINA_FOOD_DAILY.json",
        "tasks/日常/EQUIPMENT_DECOMPOSE_DAILY.json",
        "tasks/日常/DUNGEON_SWEEP_DAILY.json",
        "tasks/日常/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json",
        "tasks/日常/RING_CHALLENGE_DAILY.json",
        "tasks/日常/BREAK_ARRAY_MARTIAL_DAILY.json",
        "tasks/日常/GUILD_ACTIVITY_CHALLENGE_DAILY.json",
        "tasks/日常/GUILD_AFFAIRS_DAILY.json",
        "tasks/日常/GUILD_DONATION_DAILY.json",
        "tasks/日常/DAILY_TASK_REWARD_CLAIM_DAILY.json",
        "tasks/日常/BATTLE_PASS_REWARD_DAILY.json",
    ]
    expected = {
        "日常-简化版": [
            "MAIL_REWARD_DAILY",
            "SHOP_FREE_GIFT_DAILY",
            "FREE_APPRAISAL_DAILY",
            "TRIAL_SWORD_DAILY",
            "HERO_DISPATCH_DAILY",
            "COLLECTION_DEPLOYMENT_DAILY",
            "WEEKLY_FREE_GIFT_MONDAY",
            "DAILY_TASK_REWARD_CLAIM_DAILY",
            "BATTLE_PASS_REWARD_DAILY",
        ],
        "日常-完整版": [
            "MAIL_REWARD_DAILY",
            "SHOP_FREE_GIFT_DAILY",
            "BUY_TEA_DAILY",
            "FREE_APPRAISAL_DAILY",
            "TRIAL_SWORD_DAILY",
            "HERO_DISPATCH_DAILY",
            "COLLECTION_DEPLOYMENT_DAILY",
            "WEEKLY_FREE_GIFT_MONDAY",
            "SHADOW_RUINS_DAILY",
            "SPEND_CONDENSATE_DAILY",
            "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
            "EAT_STAMINA_FOOD_DAILY",
            "EQUIPMENT_DECOMPOSE_DAILY",
            "DUNGEON_SWEEP_DAILY",
            "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
            "RING_CHALLENGE_DAILY",
            "BREAK_ARRAY_MARTIAL_DAILY",
            "GUILD_ACTIVITY_CHALLENGE_DAILY",
            "GUILD_AFFAIRS_DAILY",
            "GUILD_DONATION_DAILY",
            "DAILY_TASK_REWARD_CLAIM_DAILY",
            "BATTLE_PASS_REWARD_DAILY",
        ],
    }
    for preset in interface["preset"]:
        assert [task["name"] for task in preset["task"]] == expected[preset["name"]]


def test_imported_ids_preserve_final_canonical_order() -> None:
    interface = json.loads(
        (ROOT / "assets/interface.json").read_text(encoding="utf-8")
    )
    final = [
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
        "BUY_TEA_DAILY",
        "FREE_APPRAISAL_DAILY",
        "TRIAL_SWORD_DAILY",
        "HERO_DISPATCH_DAILY",
        "COLLECTION_DEPLOYMENT_DAILY",
        "WEEKLY_FREE_GIFT_MONDAY",
        "SHADOW_RUINS_DAILY",
        "SPEND_CONDENSATE_DAILY",
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "EAT_STAMINA_FOOD_DAILY",
        "EQUIPMENT_DECOMPOSE_DAILY",
        "DUNGEON_SWEEP_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "RING_CHALLENGE_DAILY",
        "BREAK_ARRAY_MARTIAL_DAILY",
        "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "GUILD_AFFAIRS_DAILY",
        "GUILD_DONATION_DAILY",
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "BATTLE_PASS_REWARD_DAILY",
    ]
    imported = [path.rsplit("/", 1)[-1][:-5] for path in interface["import"][1:]]
    assert len(imported) == len(set(imported))
    assert imported == [task_id for task_id in final if task_id in imported]


def test_presets_contain_business_tasks_only_and_never_close_the_game() -> None:
    interface = json.loads(
        (ROOT / "assets/interface.json").read_text(encoding="utf-8")
    )
    for preset in interface["preset"]:
        names = [task["name"] for task in preset["task"]]
        assert "GAME_START" not in names
        assert "GAME_STOP" not in names
        assert "daily_all" not in names
