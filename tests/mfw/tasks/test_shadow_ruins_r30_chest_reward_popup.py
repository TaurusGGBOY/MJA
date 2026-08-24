from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r30_reward_popup_recognition_and_dismiss_action_are_preserved() -> None:
    nodes = _nodes()
    assert nodes["1546-MJA-影之遗迹地图推进-识别-胜利宝箱奖励"]["expected"] == "^恭喜获得$"
    dismiss = nodes["1515-MJA-影之遗迹地图推进-关闭胜利宝箱奖励"]
    assert dismiss["custom_action"] == "GuardedInput"
    assert dismiss["custom_action_param"]["action_id"] == "dismiss_shadow_reward_popup"
    assert dismiss["custom_action_param"]["fixed_click_mode"] == "shadow_reward_blank"
    assert dismiss["next"] == ["1501-MJA-影之遗迹地图推进-前景三点循环"]


def test_r30_popup_has_no_recorder_only_error_route() -> None:
    nodes = _nodes()
    assert "on_error" not in nodes["1515-MJA-影之遗迹地图推进-关闭胜利宝箱奖励"]
    assert "on_error" not in nodes["1511-MJA-影之遗迹地图推进-战斗胜利"]
    assert nodes["1591-MJA-影之遗迹-关闭-影-页面"]["next"][-1] == "1371-公共-原生成功-主页边界"
