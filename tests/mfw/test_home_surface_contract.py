from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
DAILY_PIPELINE_ROOT = ROOT / "assets/resource/base/pipeline/daily"
SHARED_HOME_PROBES = {
    "破阵武学-突破-阵法-主页",
    "买茶-主页-探测",
    "买茶-茶-主页-页面",
    "采集部署-采集-主页-页面",
    "副本扫荡-副本-主页",
    "吃体力食物-食物-主页-页面",
    "分解装备-装备-主页",
    "帮派活动挑战-帮派-已完成-退出-主页-探测",
    "帮派活动挑战-帮派-成功-退出-主页-探测",
    "帮派活动挑战-主页-探测",
    "帮派事务-主页-探测",
    "帮派事务-主页-之后-关闭-探测",
    "帮派事务-帮派事务-主页-页面",
    "帮派捐献-主页-探测",
    "帮派捐献-已完成-主页-探测",
    "帮派捐献-成功-主页-探测",
    "帮派捐献-帮派-捐献-主页-页面",
    "剑林凝结体体力-主页-探测",
    "剑林凝结体体力-清理-主页-探测",
    "剑林凝结体体力-剑林-主页-页面",
    "邮件奖励-主页-页面",
    "邮件奖励-主页-探测",
    "武学突破-武学-主页",
    "擂台挑战-擂台-主页",
    "影之遗迹-影-主页-页面",
    "商店免费礼包-主页-探测",
    "商店免费礼包-领取后-主页-探测",
    "商店免费礼包-主页-返回-探测",
    "商店免费礼包-主页-返回-探测-已完成",
    "消耗凝结体-主页-探测",
    "消耗凝结体-凝结体-主页-页面",
    "周一免费礼包-主页-探测",
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
                    "all_of": ["公共-游戏主页-页面"],
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
