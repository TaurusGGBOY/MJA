from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r25_battle_recognition_and_roi_are_preserved() -> None:
    nodes = _nodes()
    assert nodes["1195-影之遗迹-影-战斗-页面"] == {
        "recognition": "OCR", "expected": ["阵容", "挑战"], "roi": [0, 0, 500, 120], "action": "DoNothing"
    }
    assert nodes["1196-影之遗迹-影-战斗-中-进度"]["recognition"] == {
        "type": "And", "param": {"all_of": ["1197-影之遗迹-影-战斗-中-进度-统计", "1198-影之遗迹-影-战斗-中-进度-状态", "1199-影之遗迹-影-战斗-中-进度-计时器"]}
    }
    assert nodes["1199-影之遗迹-影-战斗-中-进度-计时器"]["roi"] == [190, 10, 85, 50]


def test_r25_battle_wait_keeps_existing_bounded_edges() -> None:
    nodes = _nodes()
    battle = nodes["1509-MJA-影之遗迹地图推进-战斗等待"]
    assert battle["timeout"] == 240000
    assert battle["next"] == [
        "1511-MJA-影之遗迹地图推进-战斗胜利",
        "1512-MJA-影之遗迹地图推进-战斗失败",
    ]
    assert "on_error" not in battle
    assert nodes["1501-MJA-影之遗迹地图推进-前景三点循环"]["next"] == [
        "1595-MJA-影之遗迹-确认退出",
        "1594-MJA-影之遗迹-开始战斗",
        "[JumpBack]1509-MJA-影之遗迹地图推进-战斗等待",
        "[JumpBack]1515-MJA-影之遗迹地图推进-关闭胜利宝箱奖励",
        "1178-影之遗迹-离开-关卡",
        "[JumpBack]1501-MJA-影之遗迹地图推进-前景三点循环",
    ]


def test_r25_battle_failure_is_dismissed_with_same_frame_evidence() -> None:
    node = _nodes()["1512-MJA-影之遗迹地图推进-战斗失败"]
    assert node["recognition"]["param"]["all_of"] == [
        "1539-MJA-影之遗迹地图推进-识别-战斗结果页面",
        "1541-MJA-影之遗迹地图推进-识别-战斗失败",
    ]
    assert node["custom_action"] == "GuardedInput"
    assert node["custom_action_param"]["action_id"] == (
        "dismiss_shadow_battle_failure"
    )
    assert node["custom_action_param"]["fixed_click_mode"] == (
        "shadow_result_blank"
    )
    assert node["next"] == ["1501-MJA-影之遗迹地图推进-前景三点循环"]
