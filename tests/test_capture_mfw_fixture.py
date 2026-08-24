from __future__ import annotations

from pathlib import Path

import pytest

from tools.capture_mfw_fixture import (
    capture_fixture,
    fixture_destination,
    require_new_fixture_path,
)


def test_fixture_destination_is_scoped_and_never_overwrites(tmp_path: Path):
    target = fixture_destination(tmp_path, "MAIL_REWARD_DAILY", "not_eligible")
    assert target == tmp_path / "MAIL_REWARD_DAILY/not_eligible.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        require_new_fixture_path(target)


def test_fixture_destination_rejects_unknown_task_or_case(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown task"):
        fixture_destination(tmp_path, "UNKNOWN", "not_eligible")
    with pytest.raises(ValueError, match="case"):
        fixture_destination(tmp_path, "MAIL_REWARD_DAILY", "completed")


def test_fixture_rejects_macos_controller(tmp_path: Path):
    with pytest.raises(ValueError, match="controller"):
        capture_fixture(
            "MAIL_REWARD_DAILY",
            "not_eligible",
            root=tmp_path,
            controller="macos",
        )
