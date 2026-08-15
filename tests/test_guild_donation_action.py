from __future__ import annotations

from pathlib import Path
def test_guild_donation_action_is_task_local_and_has_no_direct_process_input():
    source = Path("agent/custom/action/guild_donation_daily.py").read_text(
        encoding="utf-8"
    )
    assert "subprocess" not in source
    assert "post_click" not in source
    assert "GUILD_DONATION_DAILY" in source
