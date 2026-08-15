import json

import pytest

from tools.project_interface import render_interface

ROOT = "/Users/gaoguobin/project/MJA"


def test_formal_interface_uses_imported_native_tasks_instead_of_legacy_rendering():
    base = json.loads(open(f"{ROOT}/assets/interface.json", encoding="utf-8").read())
    assert base["task"] == []
    assert base["import"]
    assert base["resource"][0]["path"] == ["./resource/base"]
    assert "daily_all" not in json.dumps(base, ensure_ascii=False).casefold()


def test_interface_renderer_is_deterministic_and_rejects_duplicate_ids():
    base = {
        "controller": [{"name": "android"}],
        "resource": [{"name": "mja_android"}],
        "task": [],
    }
    first = render_interface(["MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"], base=base)
    second = render_interface(["MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"], base=base)
    assert first == second
    with pytest.raises(ValueError, match="unique"):
        render_interface(["MAIL_REWARD_DAILY", "MAIL_REWARD_DAILY"], base=base)


def test_interface_renderer_rejects_legacy_macos_controller():
    base = {
        "controller": [{"name": "android"}, {"name": "macos"}],
        "resource": [{"name": "mja_android"}],
        "task": [],
    }

    with pytest.raises(ValueError, match="only the android controller"):
        render_interface(["MAIL_REWARD_DAILY"], base=base)
