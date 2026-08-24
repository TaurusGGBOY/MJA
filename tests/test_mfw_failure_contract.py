from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _failure_probe() -> dict[str, dict]:
    return json.loads(
        (ROOT / "tests/mfw/probes/resource/pipeline/failure_contract.json").read_text(
            encoding="utf-8"
        )
    )


def test_failure_probe_uses_stateless_native_fail_task() -> None:
    nodes = _failure_probe()
    failure = nodes["MJA_PROBE_BUSINESS_FAILURE"]

    assert failure["action"] == "Custom"
    assert failure["custom_action"] == "FailTask"
    assert failure["custom_action_param"] == {}
    assert failure["Abort"] is True
    assert failure["recognition"] == "DirectHit"
    assert "result.json" not in json.dumps(nodes, ensure_ascii=False)


def test_failure_probe_sentinel_is_a_following_native_task() -> None:
    nodes = _failure_probe()

    assert nodes["MJA_PROBE_SENTINEL"]["next"] == ["1369-公共-通用停止"]


def test_production_interface_and_tasks_never_contain_probe_names() -> None:
    paths = [ROOT / "assets/interface.json"]
    paths.extend(sorted((ROOT / "assets/tasks").glob("*.json")))
    for path in paths:
        assert "MJA_PROBE_" not in path.read_text(encoding="utf-8")
