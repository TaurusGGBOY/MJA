from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r27_battle_loop_retains_its_existing_budget() -> None:
    nodes = _nodes()
    battle = nodes["1501-MJA-影之遗迹地图推进-前景三点循环"]
    assert battle["max_hit"] == 160
    assert battle["custom_action_param"]["action_id"] == "advance_shadow_foreground_triplet"


def test_r27_failure_partition_uses_existing_explicit_failure_node() -> None:
    nodes = _nodes()
    for name in ("1180-影之遗迹-战斗未知结果-结果", "1216-影之遗迹-战斗-循环-耗尽", "1221-影之遗迹-记录-失败"):
        assert nodes[name]["custom_action"] == "FailTask"
        assert nodes[name]["Abort"] is True
        assert "next" not in nodes[name] and "on_error" not in nodes[name]
