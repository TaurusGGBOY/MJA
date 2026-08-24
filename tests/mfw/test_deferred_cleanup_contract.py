from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_native_success_node

ROOT = Path(__file__).parents[2]
PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline"


def test_all_success_paths_use_the_shared_native_cleanup() -> None:
    violations: list[str] = []
    for path in sorted((PIPELINE_ROOT / "daily").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, node in payload.items():
            if not isinstance(node, dict):
                continue
            if node.get("custom_action") in {
                "RecordTaskOutcome",
                "CompleteTaskBoundary",
                "RecordActiveTaskFailure",
            }:
                violations.append(f"{path}:{name}")
    assert not violations, "legacy outcome nodes remain: " + ", ".join(violations)


def test_native_success_cleanup_does_not_persist_a_business_outcome() -> None:
    home = json.loads(
        (PIPELINE_ROOT / "common/home_boundary.json").read_text(encoding="utf-8")
    )
    terminal = json.loads(
        (PIPELINE_ROOT / "common/terminal.json").read_text(encoding="utf-8")
    )
    assert home["1372-公共-原生成功-尝试返回"]["on_error"] == [
        "1369-公共-通用停止"
    ]
    assert_native_success_node(terminal["1369-公共-通用停止"])
