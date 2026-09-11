from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
DAILY_PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline/daily"
SHARED_HOME_PROBES = {
    "0137-破阵武学-突破-阵法-主页",
    "0181-买茶-主页-探测",
    "0210-买茶-茶-主页-页面",
    "0238-采集部署-采集-主页-页面",
    "0699-帮派捐献-帮派-捐献-主页-页面",
    "1045-邮件奖励-主页-页面",
    "1129-擂台挑战-擂台-主页",
    "1181-影之遗迹-影-主页-页面",
    "1281-消耗凝结体-凝结体-主页-页面",
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
                    "all_of": ["0026-公共-游戏主页-页面"],
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


def test_public_home_surface_uses_bottom_right_victory_text_only() -> None:
    resource = json.loads(
        (ROOT / "assets/resource/base/pipeline/common/home_recovery.json").read_text(
            encoding="utf-8"
        )
    )

    public_home = resource["0026-公共-游戏主页-页面"]
    assert public_home == {
        "recognition": "OCR",
        "expected": ["已击破", "侠客", "道具", "载具", "成就"],
        "roi": [920, 540, 220, 100],
        "action": "DoNothing",
    }
    assert "^" not in public_home["expected"]
    assert "$" not in public_home["expected"]

    # The world/map surface remains a separate startup-recovery marker.
    world_page = resource["0025-公共-游戏世界-页面"]
    assert world_page["recognition"] == "TemplateMatch"
    assert world_page["template"] == "home/home_marker.png"
    assert world_page["roi"] == [1040, 0, 240, 110]
    assert world_page != public_home
