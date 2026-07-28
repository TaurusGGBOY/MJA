from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_interface_exposes_one_safe_default_task() -> None:
    pi = load(ROOT / "assets/interface.json")
    assert pi["interface_version"] == 2
    assert pi["controller"][0]["type"] == "MacOS"
    assert pi["controller"][0]["display_short_side"] == 720
    assert pi["controller"][0]["macos"] == {
        "title_regex": "^对决！剑之川$",
        "screencap": "ScreenCaptureKit",
        "input": "GlobalEvent",
    }
    assert pi["task"] == [
        {
            "name": "mail_smoke_test",
            "label": "邮件菜单闭环测试",
            "entry": "MJA_Start",
            "default_check": True,
            "resource": ["mja"],
            "controller": ["macos"],
        }
    ]
    assert pi["agent"] == {
        "child_exec": ".venv/bin/python3",
        "child_args": ["agent/main.py"],
        "identifier": "mja-python-agent",
    }


def test_pipeline_has_only_four_box_gated_inputs_and_no_claim_vocabulary() -> None:
    pipeline = load(ROOT / "assets/resource/pipeline/mail_smoke_test.json")
    serialized = json.dumps(pipeline, ensure_ascii=False).lower()
    assert all(term not in serialized for term in ("领取", "claim", "startapp", '"click"'))
    actions = [node for node in pipeline.values() if node.get("action") == "Custom"]
    assert [node["custom_action"] for node in actions] == [
        "MacOSForegroundClick",
        "MacOSForegroundClick",
        "MacOSForegroundClick",
        "MacOSForegroundClick",
    ]
    assert all(node["recognition"] == "TemplateMatch" for node in actions)
    assert all("template" in node for node in actions)
    missing_templates = [
        node["template"]
        for node in pipeline.values()
        if "template" in node
        and not (ROOT / "assets/resource/image" / node["template"]).is_file()
    ]
    if missing_templates:
        pytest.skip("live templates not captured: " + ", ".join(missing_templates))
