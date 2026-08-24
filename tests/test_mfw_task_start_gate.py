from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_native_failure_node

ROOT = Path(__file__).resolve().parents[1]
DAILY_PIPELINES = ROOT / "assets/resource/base/pipeline/daily"


def _entry(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(
        node for node in payload.values() if node.get("custom_action") == "BeginTask"
    )


def test_every_daily_task_has_a_native_begin_task_entry() -> None:
    entries = [_entry(path) for path in sorted(DAILY_PIPELINES.glob("*.json"))]
    assert len(entries) == 22
    for entry in entries:
        assert entry["action"] == "Custom"
        assert entry["custom_action"] == "BeginTask"
        assert isinstance(entry.get("custom_action_param", {}).get("task_id"), str)
        assert entry["next"]


def test_begin_task_failures_are_native_failures_or_local_recovery() -> None:
    for path in sorted(DAILY_PIPELINES.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry = _entry(path)
        for target in entry.get("on_error", []):
            target = target.removeprefix("[JumpBack]")
            assert target in payload or target in {
                "1365-公共-主页边界-失败",
                "1366-公共-通用中止",
            }, (path.name, target)
        for name, node in payload.items():
            if name in {"1365-公共-主页边界-失败"} or node.get("custom_action") == "FailTask":
                if node.get("custom_action") == "FailTask":
                    assert_native_failure_node(node)


def test_shared_home_failure_endpoint_is_stateless() -> None:
    boundary = json.loads(
        (ROOT / "assets/resource/base/pipeline/common/home_boundary.json").read_text(
            encoding="utf-8"
        )
    )["1365-公共-主页边界-失败"]
    assert_native_failure_node(boundary)
