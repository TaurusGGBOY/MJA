from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mfw_profile import (
    build_run_argv,
    profile_task_order,
    resolve_config_id,
    run_profile,
    verify_profile_tasks,
)


def test_resolve_config_id_uses_saved_profile_name(tmp_path: Path):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_mail.json").write_text(
        json.dumps({"name": "live-MAIL_REWARD_DAILY"}),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_mail"]}),
        encoding="utf-8",
    )
    assert resolve_config_id(tmp_path, "live-MAIL_REWARD_DAILY") == "c_mail"


def test_resolve_config_id_rejects_saved_profile_not_in_config_list(tmp_path: Path):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_mail.json").write_text(
        json.dumps({"name": "live-mail"}),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_other"]}),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"c_mail.*multi_config\.json\.config_list.*c_other",
    ):
        resolve_config_id(tmp_path, "live-mail")


def test_resolve_config_id_rejects_missing_or_duplicate_name(tmp_path: Path):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    with pytest.raises(ValueError, match="exactly one"):
        resolve_config_id(tmp_path, "missing")
    for name in ("c_a.json", "c_b.json"):
        (configs / name).write_text(json.dumps({"name": "duplicate"}), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        resolve_config_id(tmp_path, "duplicate")


def test_direct_run_is_boolean_flag_not_task_argument(tmp_path: Path):
    argv = build_run_argv(tmp_path, "c_mail")
    assert argv == [str(tmp_path / "MFW"), "--config-id=c_mail", "--direct-run"]


def test_profile_task_order_reads_only_checked_business_tasks(tmp_path: Path):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_batch.json").write_text(
        json.dumps(
            {
                "name": "live-batch",
                "tasks": [
                    {"name": "PreTask", "is_checked": True},
                    {"name": "Controller", "is_checked": True},
                    {"name": "Resource", "is_checked": True},
                    {"name": "GAME_START", "is_checked": True},
                    {"name": "MAIL_REWARD_DAILY", "is_checked": True},
                    {"name": "SHOP_FREE_GIFT_DAILY", "is_checked": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_batch"]}), encoding="utf-8"
    )
    assert profile_task_order(tmp_path, "c_batch") == (
        "GAME_START",
        "MAIL_REWARD_DAILY",
    )
    assert verify_profile_tasks(
        tmp_path,
        "live-batch",
        ("GAME_START", "MAIL_REWARD_DAILY"),
    ) == ("GAME_START", "MAIL_REWARD_DAILY")


def test_profile_verification_rejects_wrong_checked_order(tmp_path: Path):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_batch.json").write_text(
        json.dumps(
            {
                "name": "live-batch",
                "tasks": [
                    {"name": "GAME_START", "is_checked": True},
                    {"name": "MAIL_REWARD_DAILY", "is_checked": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_batch"]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="profile task order mismatch"):
        verify_profile_tasks(
            tmp_path,
            "live-batch",
            ("GAME_START", "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
        )


def test_run_profile_uses_direct_argv_without_shell(tmp_path: Path, monkeypatch):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_mail.json").write_text(
        json.dumps({"name": "live-mail"}),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_mail"]}),
        encoding="utf-8",
    )
    calls: list[tuple[list[str], Path, bool]] = []

    class Completed:
        returncode = 17

    def fake_run(argv, *, cwd, check):
        calls.append((argv, cwd, check))
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    assert run_profile(tmp_path, "live-mail") == 17
    assert calls == [
        ([str(tmp_path / "MFW"), "--config-id=c_mail", "--direct-run"], tmp_path, False)
    ]


def test_run_profile_resolves_relative_install_before_changing_directory(
    tmp_path: Path, monkeypatch
):
    configs = tmp_path / "install/mfw/config/configs"
    configs.mkdir(parents=True)
    (configs / "c_mail.json").write_text(
        json.dumps({"name": "live-mail"}),
        encoding="utf-8",
    )
    (tmp_path / "install/mfw/config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_mail"]}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[list[str], Path, bool]] = []

    class Completed:
        returncode = 0

    def fake_run(argv, *, cwd, check):
        calls.append((argv, cwd, check))
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    assert run_profile(Path("install/mfw"), "live-mail") == 0
    expected_root = (tmp_path / "install/mfw").resolve()
    assert calls == [
        ([str(expected_root / "MFW"), "--config-id=c_mail", "--direct-run"], expected_root, False)
    ]


def test_run_profile_rejects_unregistered_saved_profile_before_direct_run(
    tmp_path: Path, monkeypatch
):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_mail.json").write_text(
        json.dumps({"name": "live-mail"}),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_other"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: pytest.fail("unregistered config must not be run"),
    )

    with pytest.raises(
        ValueError,
        match=r"c_mail.*multi_config\.json\.config_list.*c_other",
    ):
        run_profile(tmp_path, "live-mail")
