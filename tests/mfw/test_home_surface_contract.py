from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
DAILY_PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline/daily"
SHARED_HOME_PROBES = {
    "break_array.home",
    "MJA_TEA_HOME_PROBE",
    "tea.home.page",
    "collection.home.page",
    "dungeon.home",
    "food.home.page",
    "equipment.home",
    "MJA_GUILD_ALREADY_COMPLETE_EXIT_HOME_PROBE",
    "MJA_GUILD_SUCCESS_EXIT_HOME_PROBE",
    "MJA_GUILD_ACTIVITY_CHALLENGE_DAILY_HOME_PROBE",
    "MJA_GUILD_AFFAIRS_DAILY_HOME_PROBE",
    "MJA_GUILD_AFFAIRS_DAILY_HOME_AFTER_CLOSE_PROBE",
    "guild.affairs.daily.home.page",
    "MJA_GUILD_DONATION_HOME_PROBE",
    "MJA_GUILD_DONATION_ALREADY_COMPLETE_HOME_PROBE",
    "MJA_GUILD_DONATION_SUCCESS_HOME_PROBE",
    "guild.donation.home.page",
    "MJA_JIANLIN_HOME_PROBE",
    "MJA_JIANLIN_CLEANUP_HOME_PROBE",
    "jianlin.home.page",
    "home.page",
    "MJA_MAIL_HOME_PROBE",
    "martial.home",
    "ring.home",
    "shadow.home.page",
    "MJA_SHOP_HOME_PROBE",
    "MJA_SHOP_POST_CLAIM_HOME_PROBE",
    "MJA_SHOP_HOME_RETURN_PROBE",
    "MJA_SHOP_HOME_RETURN_PROBE_ALREADY_COMPLETE",
    "MJA_CONDENSATE_HOME_PROBE",
    "condensate.home.page",
    "MJA_WEEKLY_HOME_PROBE",
}


def test_daily_home_probes_share_the_startup_task_ready_surface() -> None:
    for path in sorted(DAILY_PIPELINE_ROOT.glob("*.json")):
        pipeline = json.loads(path.read_text(encoding="utf-8"))
        for name, node in pipeline.items():
            if name not in SHARED_HOME_PROBES:
                continue
            assert isinstance(node, dict)
            assert node["recognition"] == {
                "type": "And",
                "param": {
                    "all_of": ["MJA_GAME_HOME_PAGE"],
                    "box_index": 0,
                },
            }, f"{path.name}:{name} bypasses the shared task-ready home surface"
            assert not {"template", "roi", "threshold"}.intersection(node), (
                f"{path.name}:{name} retains stale strict home-marker fields"
            )

    discovered = {
        name
        for path in DAILY_PIPELINE_ROOT.glob("*.json")
        for name in json.loads(path.read_text(encoding="utf-8"))
        if name in SHARED_HOME_PROBES
    }
    assert discovered == SHARED_HOME_PROBES
