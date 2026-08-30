from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline/daily/battle_pass_reward_daily.json"
TEMPLATE = ROOT / "assets/resource/base/image/daily/BATTLE_PASS_REWARD_DAILY/battle_pass_icon.png"


def test_battle_pass_home_entry_uses_icon_template_when_label_is_occluded() -> None:
    nodes = json.loads(PIPELINE.read_text(encoding="utf-8"))
    entry = nodes["0075-战令奖励-战斗-战令-打开"]

    assert entry == {
        "recognition": "TemplateMatch",
        "template": "daily/BATTLE_PASS_REWARD_DAILY/battle_pass_icon.png",
        "roi": [735, 10, 100, 90],
        "threshold": 0.8,
        "green_mask": True,
        "action": "DoNothing",
    }
    assert TEMPLATE.is_file()

    page = nodes["0070-战令奖励-战斗-战令-主页-页面"]
    assert page["recognition"]["param"]["all_of"] == [
        "0071-战令奖励-战斗-战令-主页-活动",
        "0072-战令奖励-战斗-战令-主页-祈福",
        "0073-战令奖励-战斗-战令-主页-副本",
        "0074-战令奖励-战斗-战令-主页-画卷",
    ]
