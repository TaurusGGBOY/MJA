from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r28_final_home_chain_uses_existing_nodes_until_native_success() -> None:
    nodes = _nodes()
    assert nodes["1591-MJA-影之遗迹-关闭-影-页面"]["next"] == [
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "1371-公共-原生成功-主页边界",
    ]


def test_r28_return_home_failure_stops_without_custom_failure_status() -> None:
    nodes = _nodes()
    assert nodes["1178-影之遗迹-离开-关卡"]["next"] == [
        "1591-MJA-影之遗迹-关闭-影-页面"
    ]
    assert nodes["1591-MJA-影之遗迹-关闭-影-页面"]["custom_action"] == "GuardedInput"
