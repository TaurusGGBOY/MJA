from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import (
    assert_native_failure_node,
    assert_native_success_node,
)

ROOT = Path(__file__).parents[2]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"


def _load(relative: str) -> dict[str, dict]:
    payload = json.loads((PIPELINE_ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_native_home_success_is_a_bounded_best_effort_cleanup() -> None:
    home = _load("common/home_boundary.json")
    boundary = home["1371-公共-原生成功-主页边界"]
    returning = home["1372-公共-原生成功-尝试返回"]

    assert boundary["timeout"] == 5000
    assert boundary["max_hit"] == 1
    assert boundary["next"] == ["1369-公共-通用停止"]
    assert boundary["on_error"] == ["1372-公共-原生成功-尝试返回"]
    assert returning["custom_action"] == "ReturnToWorldHome"
    assert returning["timeout"] == 30000
    assert returning["max_hit"] == 1
    assert returning["next"] == ["1369-公共-通用停止"]
    assert returning["on_error"] == ["1369-公共-通用停止"]


def test_success_cleanup_never_persists_a_business_outcome() -> None:
    home = _load("common/home_boundary.json")
    terminal = _load("common/terminal.json")
    serialized = json.dumps({**home, **terminal}, ensure_ascii=False)
    assert "RecordTaskOutcome" not in serialized
    assert "CompleteTaskBoundary" not in serialized
    assert "RecordActiveTaskFailure" not in serialized
    assert '"status"' not in serialized
    assert_native_success_node(terminal["1369-公共-通用停止"])


def test_compatibility_failure_endpoints_are_stateless_native_failures() -> None:
    home = _load("common/home_boundary.json")
    terminal = _load("common/terminal.json")
    assert_native_failure_node(home["1365-公共-主页边界-失败"])
    assert_native_failure_node(terminal["1366-公共-通用中止"])


def test_known_painting_surface_cleanup_clicks_the_real_close_anchor() -> None:
    resource = _load("common/known_popups.json")
    close = resource["1277-公共-已知-画卷-关闭"]
    assert close["action"] == "Custom"
    assert close["custom_action"] == "CloseKnownPaintingSurface"
    assert close["post_delay"] == 1000
