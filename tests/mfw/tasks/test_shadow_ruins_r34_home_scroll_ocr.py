from __future__ import annotations

import json
import re
from pathlib import Path

PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)


def test_shadow_home_scroll_accepts_only_the_observed_ocr_aliases() -> None:
    nodes = json.loads(PIPELINE.read_text(encoding="utf-8"))
    entry = nodes["1182-影之遗迹-影-画卷-入口"]
    parent = nodes["1170-影之遗迹-打开-画卷"]

    assert entry["expected"] == ["^画卷$", "^画碧铺$", "^画磨铺$"]
    assert entry["roi"] == [1095, 45, 85, 40]
    assert parent["recognition"]["param"]["all_of"] == [
        "1181-影之遗迹-影-主页-页面",
        "1182-影之遗迹-影-画卷-入口",
    ]
    assert parent["action"] == "Custom"
    assert parent["custom_action"] == "GuardedInput"

    patterns = [re.compile(pattern) for pattern in entry["expected"]]
    assert any(pattern.fullmatch("画卷") for pattern in patterns)
    assert any(pattern.fullmatch("画碧铺") for pattern in patterns)
    assert any(pattern.fullmatch("画磨铺") for pattern in patterns)
    assert not any(pattern.fullmatch("药铺") for pattern in patterns)
    assert not any(pattern.fullmatch("画卷药铺") for pattern in patterns)
