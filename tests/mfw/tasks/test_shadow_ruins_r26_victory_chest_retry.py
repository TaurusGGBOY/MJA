from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r26_victory_path_keeps_existing_result_and_reward_order() -> None:
    nodes = _nodes()
    assert nodes["1511-MJA-影之遗迹地图推进-战斗胜利"]["next"] == []
    assert nodes["1515-MJA-影之遗迹地图推进-关闭胜利宝箱奖励"]["next"] == []


def test_r26_reward_popup_action_and_retry_setting_are_unchanged() -> None:
    node = _nodes()["1515-MJA-影之遗迹地图推进-关闭胜利宝箱奖励"]
    assert node["custom_action"] == "GuardedInput"
    assert node["custom_action_param"]["action_id"] == "dismiss_shadow_reward_popup"
    assert node["custom_action_param"]["fixed_click_mode"] == "shadow_reward_blank"
    assert node["retry_times"] == 0 and node["post_delay"] == 750
