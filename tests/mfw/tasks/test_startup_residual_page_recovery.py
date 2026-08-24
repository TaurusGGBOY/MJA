import json
from pathlib import Path


STARTUP_PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "resource"
    / "base"
    / "pipeline"
    / "startup"
    / "game_start.json"
)


def test_startup_has_no_business_task_restart_handoff() -> None:
    pipeline = json.loads(STARTUP_PIPELINE.read_text(encoding="utf-8"))
    assert not any("重启" in name for name in pipeline)
    assert "启动-欢迎页-进入游戏" not in pipeline
    assert "启动-世界页-探测" not in pipeline
    assert pipeline["1370-启动-游戏启动后-进入按钮"]["expected"][-1] == "戏"
    assert "启动-游戏启动后-开始按钮" not in pipeline
    assert pipeline["1370-启动-游戏启动后-进入按钮"]["max_hit"] == 2
    assert pipeline["1370-启动-游戏启动后-进入按钮"]["target"] == [
        575,
        620,
        120,
        25,
    ]
    assert pipeline["1370-启动-游戏启动后-进入按钮"]["post_delay"] == 10000
    assert "启动-进入游戏后等待" not in pipeline
    assert pipeline["1356-启动-游戏启动"]["action"] == "StartApp"
    assert pipeline["1356-启动-游戏启动"]["repeat"] == 5
    assert pipeline["1356-启动-游戏启动"]["repeat_delay"] == 1000
    assert pipeline["1356-启动-游戏启动"]["timeout"] == 120000
    assert pipeline["1356-启动-游戏启动"]["next"] == [
        "[JumpBack]1379-启动-关闭装备残留页",
        "[JumpBack]1376-启动-关闭副本残留页",
        "[JumpBack]1373-启动-关闭剑林残留页",
        "[JumpBack]1359-启动-可选关闭公告页",
        "[JumpBack]1360-启动-数据校验失败-继续下载",
        "1357-启动-游戏启动成功-左下12探测",
        "1362-启动-游戏就绪",
    ]
    assert pipeline["1359-启动-可选关闭公告页"] == {
        "recognition": "OCR",
        "expected": "公告|公|告",
        "roi": [0, 0, 420, 520],
        "timeout": 1500,
        "max_hit": 1,
        "action": "Click",
        "target": [1160, 0, 120, 100],
        "post_delay": 1000,
    }
    assert "启动-游戏启动-启动" not in pipeline
    assert pipeline["1357-启动-游戏启动成功-左下12探测"]["expected"] == "^12\\+?$"
    assert pipeline["1357-启动-游戏启动成功-左下12探测"]["timeout"] == 200000
    assert pipeline["1356-启动-游戏启动"]["on_error"] == ["关闭游戏"]
    assert "on_error" not in pipeline["1357-启动-游戏启动成功-左下12探测"]
    assert pipeline["1357-启动-游戏启动成功-左下12探测"]["next"] == [
        "[JumpBack]1361-启动-可选关闭月签到奖励页",
        "[JumpBack]1370-启动-游戏启动后-进入按钮",
        "1362-启动-游戏就绪",
    ]
    assert pipeline["关闭游戏"] == {
        "recognition": "DirectHit",
        "action": "StopApp",
        "package": "com.hanjiasongshu.dr22",
        "max_hit": 1,
        "next": ["1356-启动-游戏启动"],
    }
    assert pipeline["1360-启动-数据校验失败-继续下载"]["expected"] == ["允许下载", "继续下载"]
    assert pipeline["1360-启动-数据校验失败-继续下载"]["roi"] == [630, 450, 330, 80]
    assert pipeline["1360-启动-数据校验失败-继续下载"]["action"] == "Click"
    assert pipeline["1360-启动-数据校验失败-继续下载"]["target"] == [650, 450, 300, 80]
    assert pipeline["1360-启动-数据校验失败-继续下载"]["post_delay"] == 1000
    assert "next" not in pipeline["1360-启动-数据校验失败-继续下载"]
    assert "on_error" not in pipeline["1360-启动-数据校验失败-继续下载"]
    assert "next" not in pipeline["1361-启动-可选关闭月签到奖励页"]
    assert "next" not in pipeline["1370-启动-游戏启动后-进入按钮"]
    assert "on_error" not in pipeline["1370-启动-游戏启动后-进入按钮"]
    assert "ReturnToWorldHome" not in json.dumps(pipeline, ensure_ascii=False)
    residual = pipeline["1373-启动-关闭剑林残留页"]
    assert residual["recognition"]["param"]["all_of"] == [
        "1374-启动-剑林残留页-标题",
        "1375-启动-剑林残留页-关闭",
    ]
    assert residual["recognition"]["param"]["box_index"] == 1
    assert residual["action"] == "Click"
    assert residual["target"] == [1205, 33, 18, 18]
    assert residual["max_hit"] == 1
    assert residual["post_delay"] == 1500
    dungeon_residual = pipeline["1376-启动-关闭副本残留页"]
    assert dungeon_residual["recognition"]["param"] == {
        "all_of": [
            "1377-启动-副本残留页-标题",
            "1378-启动-副本残留页-关闭",
        ],
        "box_index": 1,
    }
    assert dungeon_residual["action"] == "Click"
    assert dungeon_residual["target"] == [1202, 30, 24, 24]
    assert dungeon_residual["max_hit"] == 1
    assert dungeon_residual["post_delay"] == 1500
    equipment_residual = pipeline["1379-启动-关闭装备残留页"]
    assert equipment_residual["recognition"]["param"] == {
        "all_of": [
            "1380-启动-装备残留页-标题",
            "1381-启动-装备残留页-关闭",
        ],
        "box_index": 1,
    }
    assert equipment_residual["action"] == "Click"
    assert equipment_residual["target"] == [1202, 30, 24, 24]
    assert equipment_residual["max_hit"] == 1
