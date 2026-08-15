import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTERFACE_PATH = ROOT / "assets/interface.json"
START_TASK_PATH = ROOT / "assets/tasks/游戏启动.json"
CFA_SETTING_PATH = ROOT / "CFA_setting.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_interface_targets_the_android_emulator_through_adb_controller() -> None:
    interface = _read_json(INTERFACE_PATH)

    assert interface["interface_version"] == 2
    assert interface["task"] == []
    assert [item["name"] for item in interface["controller"]] == ["android"]
    controller = interface["controller"][0]
    assert controller["type"] == "Adb"
    assert controller["display_short_side"] == 720
    assert [item["name"] for item in interface["resource"]] == ["mja_android"]
    assert interface["resource"][0]["path"] == ["./resource/base"]
    assert interface["resource"][0]["controller"] == ["android"]
    assert [item["name"] for item in interface["group"]] == [
        "启动",
        "日常",
        "周常",
        "工具",
    ]
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
    assert interface["agent"]["child_args"] == ["{PROJECT_DIR}/agent/main.py"]

    preset_tasks = [task for preset in interface["preset"] for task in preset["task"]]
    assert preset_tasks
    assert all(isinstance(task, dict) for task in preset_tasks)
    assert all(
        task["name"]
        in {
            "GAME_START",
            "MAIL_REWARD_DAILY",
            "SHOP_FREE_GIFT_DAILY",
            "FREE_APPRAISAL_DAILY",
            "TRIAL_SWORD_DAILY",
            "HERO_DISPATCH_DAILY",
            "COLLECTION_DEPLOYMENT_DAILY",
            "WEEKLY_FREE_GIFT_MONDAY",
            "SHADOW_RUINS_DAILY",
            "DAILY_TASK_REWARD_CLAIM_DAILY",
            "BATTLE_PASS_REWARD_DAILY",
            "BUY_TEA_DAILY",
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
        }
        for task in preset_tasks
    )

    interface_text = INTERFACE_PATH.read_text(encoding="utf-8").lower()
    assert "adb" in interface_text
    assert "android" in interface_text
    assert "daily_all" not in interface_text
    assert "speedrun" not in interface_text
    assert "mfaavalonia" not in interface_text


def test_start_task_is_declared_exactly_once_with_mja_entry() -> None:
    task_file = _read_json(START_TASK_PATH)
    tasks = task_file["task"]

    assert len(tasks) == 2
    assert tasks[0]["name"] == "GAME_START"
    assert tasks[0]["entry"] == "MJA_GAME_START_ENTRY"
    assert tasks[0]["default_check"] is True
    assert tasks[0]["group"] == ["启动"]
    assert "option" not in tasks[0]
    assert "option" not in task_file
    assert tasks[1] == {
        "name": "GAME_STOP",
        "label": "退出/关闭游戏",
        "default_check": False,
        "group": ["启动"],
        "entry": "MJA_GAME_STOP",
    }


def test_game_start_entry_is_a_native_probe_and_restart_owns_start_app() -> None:
    startup = _read_json(ROOT / "assets/resource/base/pipeline/startup/game_start.json")
    entry = startup["MJA_GAME_START_ENTRY"]

    assert entry["recognition"] == "DirectHit"
    assert entry["action"] == "DoNothing"
    assert entry["max_hit"] == 1
    assert entry["timeout"] == 1000
    assert "package" not in entry


def test_cfa_setting_has_exact_embedded_contract() -> None:
    content = CFA_SETTING_PATH.read_text(encoding="utf-8")
    assert content.rstrip("\n") == '{"update_flag":"1","embedded":true}'
