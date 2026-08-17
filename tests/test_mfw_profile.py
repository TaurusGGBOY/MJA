from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mfw_profile import (
    build_run_argv,
    ensure_pair_profiles,
    profile_task_order,
    resolve_config_id,
    run_profile,
    verify_profile_tasks,
)


def test_ensure_pair_profiles_materializes_and_registers_every_active_task(
    tmp_path: Path,
):
    config_dir = tmp_path / "config/configs"
    config_dir.mkdir(parents=True)
    (tmp_path / "interface.json").write_text(
        json.dumps(
            {
                "task": [
                    {"name": "GAME_START", "entry": "start"},
                    {"name": "MAIL_REWARD_DAILY", "entry": "mail"},
                    {"name": "WEEKLY_FREE_GIFT_MONDAY", "entry": "weekly"},
                    {"name": "EQUIPMENT_DECOMPOSE_DAILY", "entry": "equipment"},
                    {"name": "GAME_STOP", "entry": "stop"},
                ]
            }
        ),
        encoding="utf-8",
    )
    template = {
        "name": "full",
        "item_id": "c_full",
        "tasks": [
            {"name": "PreTask", "is_checked": True},
            {"name": "Controller", "is_checked": True},
            {"name": "Resource", "is_checked": True},
            {"name": "GAME_START", "is_checked": True},
            {"name": "MAIL_REWARD_DAILY", "is_checked": True},
            {"name": "WEEKLY_FREE_GIFT_MONDAY", "is_checked": True},
            {"name": "EQUIPMENT_DECOMPOSE_DAILY", "is_checked": True},
        ],
    }
    (config_dir / "c_full.json").write_text(
        json.dumps(template), encoding="utf-8"
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_full"]}), encoding="utf-8"
    )

    profiles = ensure_pair_profiles(tmp_path)

    assert set(profiles) == {
        "MAIL_REWARD_DAILY",
        "WEEKLY_FREE_GIFT_MONDAY",
        "EQUIPMENT_DECOMPOSE_DAILY",
    }
    for task_id, profile_name in profiles.items():
        config_id = resolve_config_id(tmp_path, profile_name)
        assert profile_task_order(tmp_path, config_id) == ("GAME_START", task_id)
    registry = json.loads(
        (tmp_path / "config/multi_config.json").read_text(encoding="utf-8")
    )
    assert set(registry["config_list"]) == {
        "c_full",
        "c_mja_pair_mail_reward_daily",
        "c_mja_pair_weekly_free_gift_monday",
        "c_mja_pair_equipment_decompose_daily",
    }


def test_ensure_pair_profiles_is_idempotent(tmp_path: Path):
    config_dir = tmp_path / "config/configs"
    config_dir.mkdir(parents=True)
    (tmp_path / "interface.json").write_text(
        json.dumps(
            {
                "task": [
                    {"name": "GAME_START", "entry": "start"},
                    {"name": "MAIL_REWARD_DAILY", "entry": "mail"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "c_full.json").write_text(
        json.dumps(
            {
                "name": "full",
                "tasks": [
                    {"name": "PreTask", "is_checked": True},
                    {"name": "Controller", "is_checked": True},
                    {"name": "Resource", "is_checked": True},
                    {"name": "GAME_START", "is_checked": True},
                    {"name": "MAIL_REWARD_DAILY", "is_checked": True},
                    {"name": "SHOP_FREE_GIFT_DAILY", "is_checked": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_full"]}), encoding="utf-8"
    )

    first = ensure_pair_profiles(tmp_path)
    generated = (config_dir / "c_mja_pair_mail_reward_daily.json").read_text()
    second = ensure_pair_profiles(tmp_path)

    assert first == second
    assert (config_dir / "c_mja_pair_mail_reward_daily.json").read_text() == generated


def test_ensure_pair_profiles_synthesizes_missing_task_item(tmp_path: Path):
    config_dir = tmp_path / "config/configs"
    config_dir.mkdir(parents=True)
    (tmp_path / "interface.json").write_text(
        json.dumps(
            {
                "task": [
                    {"name": "GAME_START", "entry": "start"},
                    {"name": "EQUIPMENT_DECOMPOSE_DAILY", "entry": "equipment"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "c_start.json").write_text(
        json.dumps(
            {
                "name": "start-only",
                "tasks": [
                    {"name": "PreTask", "is_checked": True},
                    {"name": "Controller", "is_checked": True},
                    {"name": "Resource", "is_checked": True},
                    {"name": "GAME_START", "is_checked": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config/multi_config.json").write_text(
        json.dumps({"config_list": ["c_start"]}), encoding="utf-8"
    )

    profiles = ensure_pair_profiles(tmp_path)

    assert profiles == {
        "EQUIPMENT_DECOMPOSE_DAILY": "MJA auto GAME_START+EQUIPMENT_DECOMPOSE_DAILY"
    }
    config_id = resolve_config_id(
        tmp_path, "MJA auto GAME_START+EQUIPMENT_DECOMPOSE_DAILY"
    )
    assert profile_task_order(tmp_path, config_id) == (
        "GAME_START",
        "EQUIPMENT_DECOMPOSE_DAILY",
    )
    generated = json.loads(
        (config_dir / "c_mja_pair_equipment_decompose_daily.json").read_text(
            encoding="utf-8"
        )
    )
    names = {item["name"] for item in generated["tasks"]}
    assert "EQUIPMENT_DECOMPOSE_DAILY" in names


def test_ensure_pair_profiles_creates_config_tree_without_historical_profiles(
    tmp_path: Path,
):
    (tmp_path / "interface.json").write_text(
        json.dumps(
            {
                "controller": [{"name": "android"}],
                "resource": [{"name": "mja_android"}],
                "retired_tasks": ["RETIRED_DAILY"],
                "task": [
                    {"name": "GAME_START", "entry": "start"},
                    {"name": "WEEKLY_FREE_GIFT_MONDAY", "entry": "weekly"},
                    {"name": "EQUIPMENT_DECOMPOSE_DAILY", "entry": "equipment"},
                    {"name": "RETIRED_DAILY", "entry": "retired"},
                    {"name": "GAME_STOP", "entry": "stop"},
                ],
            }
        ),
        encoding="utf-8",
    )

    profiles = ensure_pair_profiles(tmp_path)

    assert set(profiles) == {
        "WEEKLY_FREE_GIFT_MONDAY",
        "EQUIPMENT_DECOMPOSE_DAILY",
    }
    registry = json.loads(
        (tmp_path / "config/multi_config.json").read_text(encoding="utf-8")
    )
    for task_id, profile_name in profiles.items():
        config_id = resolve_config_id(tmp_path, profile_name)
        assert config_id in registry["config_list"]
        assert profile_task_order(tmp_path, config_id) == ("GAME_START", task_id)
    assert not any(
        json.loads(path.read_text(encoding="utf-8")).get("name")
        == "MJA auto GAME_START+RETIRED_DAILY"
        for path in (tmp_path / "config/configs").glob("c_*.json")
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
    calls: list[tuple[list[str], Path]] = []

    class Process:
        returncode = 17
        def poll(self):
            return self.returncode

    def fake_popen(argv, *, cwd):
        calls.append((argv, cwd))
        return Process()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    assert run_profile(tmp_path, "live-mail") == 17
    assert calls == [
        ([str(tmp_path / "MFW"), "--config-id=c_mail", "--direct-run"], tmp_path)
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
    calls: list[tuple[list[str], Path]] = []

    class Process:
        returncode = 0
        def poll(self):
            return self.returncode

    def fake_popen(argv, *, cwd):
        calls.append((argv, cwd))
        return Process()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    assert run_profile(Path("install/mfw"), "live-mail") == 0
    expected_root = (tmp_path / "install/mfw").resolve()
    assert calls == [
        ([str(expected_root / "MFW"), "--config-id=c_mail", "--direct-run"], expected_root)
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
