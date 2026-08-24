from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_open_shadow_failure_routes_through_bounded_restart_and_retry() -> None:
    nodes = _nodes()

    assert nodes["0018-影之遗迹-任务入口"]["on_error"] == [
        "MJA-任务入口失败-SHADOW_RUINS_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    close = nodes["1591-MJA-影之遗迹-关闭-影-页面"]
    assert close["custom_action"] == "GuardedInput"
    assert close["custom_action_param"] == {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "close_shadow_page",
        "kind": "click",
        "fixed_click_mode": "shadow_page_close",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1191-影之遗迹-影-页面",
            "target_name": "1590-MJA-影之遗迹-影-关闭-图标",
        },
    }
    assert close["next"] == [
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "1371-公共-原生成功-主页边界",
    ]
