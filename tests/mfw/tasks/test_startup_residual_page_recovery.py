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
    assert pipeline["启动-游戏启动后-进入按钮"]["expected"][-1] == "戏"
    assert "启动-游戏启动后-开始按钮" not in pipeline
    assert pipeline["启动-游戏启动后-进入按钮"]["max_hit"] == 5
    assert "启动-进入游戏后等待" not in pipeline
    assert pipeline["启动-游戏启动"]["action"] == "StartApp"
    assert pipeline["启动-游戏启动"]["repeat"] == 5
    assert pipeline["启动-游戏启动"]["repeat_delay"] == 1000
    assert pipeline["启动-游戏启动"]["next"] == [
        "[JumpBack]启动-可选关闭公告页",
        "启动-游戏启动成功-左下12探测",
    ]
    assert pipeline["启动-可选关闭公告页"] == {
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
    assert pipeline["启动-游戏启动成功-左下12探测"]["expected"] == "^12\\+?$"
    assert pipeline["启动-游戏启动成功-左下12探测"]["timeout"] == 200000
    assert pipeline["启动-游戏启动成功-左下12探测"]["on_error"] == [
        "公共-游戏启动失败"
    ]
    assert pipeline["启动-游戏启动成功-左下12探测"]["next"] == [
        "[JumpBack]启动-数据校验失败-继续下载",
        "[JumpBack]启动-可选关闭月签到奖励页",
        "[JumpBack]启动-游戏启动后-进入按钮",
        "启动-游戏就绪",
    ]
    assert "next" not in pipeline["启动-数据校验失败-继续下载"]
    assert "on_error" not in pipeline["启动-数据校验失败-继续下载"]
    assert "next" not in pipeline["启动-可选关闭月签到奖励页"]
    assert "next" not in pipeline["启动-游戏启动后-进入按钮"]
    assert "on_error" not in pipeline["启动-游戏启动后-进入按钮"]
    assert "ReturnToWorldHome" not in json.dumps(pipeline, ensure_ascii=False)
