from __future__ import annotations

import json
from pathlib import Path

from agent.android.config import AndroidConfig
from tools.android_maa_config import build_android_maa_config

ROOT = Path(__file__).resolve().parents[1]


def test_acceptance_contract_is_android_only() -> None:
    interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
    assert interface["controller"][0]["name"] == "android"
    assert [item["name"] for item in interface["controller"]] == ["android"]
    assert [item["name"] for item in interface["resource"]] == ["mja_android"]
    assert interface["task"] == []
    assert interface["resource"][0]["path"] == ["./resource/base"]
    assert interface["import"]
    assert all(
        task["name"] != "GAME_STOP"
        for preset in interface["preset"]
        for task in preset["task"]
    )


def test_acceptance_config_and_maa_config_are_canonical() -> None:
    config = AndroidConfig.load(ROOT / "config/android.json")
    maa_config = build_android_maa_config(
        Path("/sdk/platform-tools/adb"),
        config.serial,
        "mail_smoke_test",
    )
    assert config.display_size == (1280, 720)
    assert maa_config["controller"]["name"] == "android"
    assert maa_config["resource"] == "mja_android"
