from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r29_timer_roi_and_ocr_pattern_are_unchanged() -> None:
    timer = _nodes()["1199-影之遗迹-影-战斗-中-进度-计时器"]
    assert timer["expected"] == r"^\d{2}:\d{2}$"
    assert timer["roi"] == [190, 10, 85, 50]


def test_r29_wait_keeps_existing_bounded_result_recovery() -> None:
    wait = _nodes()["1509-MJA-影之遗迹地图推进-战斗等待"]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["1538-MJA-影之遗迹地图推进-识别-战斗中"]},
    }
    assert wait["timeout"] == 240000
    assert wait["next"] == [
        "1511-MJA-影之遗迹地图推进-战斗胜利",
        "1512-MJA-影之遗迹地图推进-战斗失败",
    ]
