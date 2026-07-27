from __future__ import annotations

import json

import pytest

from tools.configure_mfa import configure_instance


def test_configuration_preserves_unknown_fields_and_backs_up(tmp_path) -> None:
    path = tmp_path / "default.json"
    path.write_text(json.dumps({"theme": "dark", "startup": {"keep": 1}}), encoding="utf-8")

    backup = configure_instance(
        path,
        install_root=tmp_path / "install",
        now=lambda: "20260727T120000",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["theme"] == "dark"
    assert payload["startup"]["keep"] == 1
    assert payload["startup"]["program"] == "/usr/bin/open"
    assert payload["startup"]["args"] == ["-a", "对决！剑之川"]
    assert payload["startup"]["wait_seconds"] == 60
    assert payload["controller"]["name"] == "macos"
    assert payload["controller"]["auto_detect_window"] is True
    assert payload["project"] == str(tmp_path / "install" / "interface.json")
    assert payload["pretask"] == {
        "program": str(tmp_path / "install" / ".venv" / "bin" / "python"),
        "args": ["-m", "agent.pretask"],
    }
    assert backup.name == "default.json.20260727T120000.bak"
    assert json.loads(backup.read_text(encoding="utf-8")) == {
        "theme": "dark",
        "startup": {"keep": 1},
    }


def test_dry_run_prints_patch_without_backup_or_write(tmp_path, capsys) -> None:
    path = tmp_path / "default.json"
    original = json.dumps({"theme": "dark"})
    path.write_text(original, encoding="utf-8")

    result = configure_instance(
        path,
        install_root=tmp_path / "install",
        now=lambda: "20260727T120000",
        dry_run=True,
    )

    assert result is None
    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.bak")) == []
    printed = json.loads(capsys.readouterr().out)
    assert printed["startup"]["program"] == "/usr/bin/open"
    assert printed["controller"]["auto_detect_window"] is True


def test_invalid_json_is_rejected_before_backup(tmp_path) -> None:
    path = tmp_path / "default.json"
    path.write_text('{"broken":', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        configure_instance(path, install_root=tmp_path / "install")

    assert list(tmp_path.glob("*.bak")) == []

