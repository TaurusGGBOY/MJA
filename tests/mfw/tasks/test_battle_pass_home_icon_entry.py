from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline/daily/battle_pass_reward_daily.json"
TEMPLATE = ROOT / "assets/resource/base/image/daily/BATTLE_PASS_REWARD_DAILY/battle_pass_icon.png"


def test_battle_pass_home_entry_uses_live_label_ocr() -> None:
    nodes = json.loads(PIPELINE.read_text(encoding="utf-8"))
    entry = nodes["0075-战令奖励-战斗-战令-打开"]

    assert entry == {
        "recognition": "OCR",
        "expected": "^战令$",
        "roi": [820, 40, 120, 60],
        "action": "DoNothing",
    }

    page = nodes["0070-战令奖励-战斗-战令-主页-页面"]
    assert page["recognition"]["param"]["all_of"] == ["0026-公共-游戏主页-页面"]
