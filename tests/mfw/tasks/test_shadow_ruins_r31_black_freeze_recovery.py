from __future__ import annotations

import json
from pathlib import Path

PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r31_existing_cross_page_recovery_remains_bounded_and_specific() -> None:
    recovery = _nodes()["1176-影之遗迹-跨图-确认"]
    assert recovery["custom_action"] == "GuardedInput"
    assert recovery["retry_times"] == 0
    assert recovery["custom_action_param"]["action_id"] == "confirm_shadow_teleport"
    assert recovery["custom_action_param"]["fixed_click_mode"] == "shadow_teleport_confirm"


def test_r31_recovery_edges_stay_inside_existing_shadow_task() -> None:
    nodes = _nodes()
    recovery = nodes["1176-影之遗迹-跨图-确认"]
    assert recovery["next"] == [
        "1593-MJA-影之遗迹-进入-探索页",
        "1592-MJA-影之遗迹-自动寻路-等待-关卡",
    ]
    assert "on_error" not in recovery
