from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_PIPELINES = ROOT / "assets/resource/base/pipeline/daily"


def _entry(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(
        node for node in payload.values() if node.get("custom_action") == "BeginTask"
    )


def test_every_daily_task_has_a_home_boundary_entry() -> None:
    entries = [_entry(path) for path in sorted(DAILY_PIPELINES.glob("*.json"))]
    assert entries
    for entry in entries:
        recognition = entry["recognition"]
        serialized = json.dumps(recognition, ensure_ascii=False)
        assert "公共-游戏主页-页面" in serialized
        assert entry["timeout"] == 8000


def test_missing_home_closes_the_current_task_instead_of_restarting_game() -> None:
    entries = [_entry(path) for path in sorted(DAILY_PIPELINES.glob("*.json"))]
    assert all(entry["action"] == "Custom" for entry in entries)
    assert all(entry["custom_action"] == "BeginTask" for entry in entries)
    assert all(entry["on_error"][0] == "公共-主页边界-失败" for entry in entries)
    assert all(entry["next"] for entry in entries)


def test_home_boundary_failure_force_stops_and_records_the_task() -> None:
    boundary = json.loads(
        (ROOT / "assets/resource/base/pipeline/common/home_boundary.json").read_text(
            encoding="utf-8"
        )
    )["公共-主页边界-失败"]
    assert boundary["custom_action"] == "RecordActiveTaskFailure"
    assert boundary["custom_action_param"]["stop_game_on_failure"] is True
    assert boundary["custom_action_param"]["native_fail_after_record"] is True
