from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_PIPELINES = ROOT / "assets/resource/base/pipeline/daily"
TERMINAL = ROOT / "assets/resource/base/pipeline/common/terminal.json"


def _entry(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(
        node for node in payload.values() if node.get("custom_action") == "BeginTask"
    )


def test_every_daily_task_starts_with_a_shared_home_page_gate() -> None:
    entries = [_entry(path) for path in sorted(DAILY_PIPELINES.glob("*.json"))]

    assert entries
    assert all(
        entry["recognition"] == {
            "type": "And",
            "param": {"all_of": ["公共-游戏主页-页面"], "box_index": 0},
        }
        for entry in entries
    )
    assert all(entry["timeout"] == 8000 for entry in entries)


def test_task_start_home_gate_restarts_through_game_start_when_home_is_missing() -> None:
    terminal = json.loads(TERMINAL.read_text(encoding="utf-8"))
    restart = terminal["公共-通用-启动恢复-重启"]

    entries = [_entry(path) for path in sorted(DAILY_PIPELINES.glob("*.json"))]
    assert all(entry["action"] == "Custom" for entry in entries)
    assert all(entry["custom_action"] == "BeginTask" for entry in entries)
    assert all(entry["on_error"][0] == "[JumpBack]启动-游戏启动" for entry in entries)
    assert all(entry["next"] for entry in entries)
    assert restart["custom_action"] == "RestartGameSurface"
    assert restart["custom_action_param"]["start_repeat"] == 5
    assert restart["custom_action_param"]["start_repeat_delay_ms"] == 1000
