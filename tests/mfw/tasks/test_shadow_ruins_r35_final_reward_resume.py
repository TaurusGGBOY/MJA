from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHADOW = ROOT / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_final_reward_prompt_can_resume_without_startup_dismissing_it() -> None:
    shadow = json.loads(SHADOW.read_text(encoding="utf-8"))
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    marker = "1596-MJA-影之遗迹-退出确认-文案"

    assert shadow[marker]["expected"] == "是否领取最终奖励"
    assert shadow[marker]["roi"] == [360, 300, 600, 100]
    ready = startup["1362-启动-游戏就绪"]["recognition"]
    assert ready["type"] == "Or"
    assert ready["param"]["any_of"] == ["0026-公共-游戏主页-页面", marker]
    assert startup["1362-启动-游戏就绪"]["action"] == "DoNothing"
    assert startup["启动-游戏就绪复核"]["custom_action"] == "RuntimeHealth"
    assert startup["启动-游戏就绪复核"]["recognition"] == ready


def test_shadow_task_confirms_pending_reward_and_avoids_generic_page_hits() -> None:
    shadow = json.loads(SHADOW.read_text(encoding="utf-8"))
    marker = "1596-MJA-影之遗迹-退出确认-文案"

    entry = shadow["0018-影之遗迹-任务入口"]
    assert marker in entry["recognition"]["param"]["any_of"]
    assert entry["next"][0] == "1595-MJA-影之遗迹-确认退出"
    confirm = shadow["1595-MJA-影之遗迹-确认退出"]
    assert confirm["recognition"]["param"]["all_of"] == [marker]
    assert confirm["custom_action_param"]["action_id"] == "confirm_shadow_completion"
    assert confirm["custom_action_param"]["fixed_click_mode"] == "shadow_completion_confirm"

    explore = shadow["1528-MJA-影之遗迹地图推进-识别-探索页"]
    assert explore["expected"] == "^第[一二三四五六七八九十百0-9]+层$"
    assert explore["roi"] == [500, 0, 300, 120]
    assert "1595-MJA-影之遗迹-确认退出" in shadow["1592-MJA-影之遗迹-自动寻路-等待-关卡"]["next"]
