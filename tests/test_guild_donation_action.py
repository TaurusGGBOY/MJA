from __future__ import annotations

from pathlib import Path


def test_guild_donation_legacy_action_is_retired():
    assert not Path("agent/custom/action/guild_donation_daily.py").exists()
