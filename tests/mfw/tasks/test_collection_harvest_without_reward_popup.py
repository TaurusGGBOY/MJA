from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.task_contract import TaskContract


COLLECTION = TaskContract(
    "COLLECTION_DEPLOYMENT_DAILY",
    "daily/collection_deployment_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / COLLECTION.pipeline_file


def test_collected_marker_without_reward_popup_still_reaches_native_success_boundary() -> None:
    nodes = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    assert nodes["0230-采集部署-打开-采集"]["on_error"] == [
        "0237-采集部署-失败-返回主页"
    ]
    assert nodes["0237-采集部署-失败-返回主页"] == {
        "recognition": "DirectHit",
        "timeout": 30000,
        "max_hit": 1,
        "action": "Custom",
        "custom_action": "ReturnToWorldHome",
        "next": ["1365-公共-主页边界-失败"],
        "on_error": ["1365-公共-主页边界-失败"],
    }

    # The 1280x720 failure frame has no reward popup, but OCR reads the green
    # "已采集" labels immediately above the one-click harvest button. That is
    # an explicit successful postcondition and must enter the normal cleanup.
    assert nodes["0233-采集部署-收获-成功"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "next": ["0234-采集部署-关闭-奖励", "0235-采集部署-关闭"],
    }
    assert nodes["0234-采集部署-关闭-奖励"]["next"] == [
        "0235-采集部署-关闭",
        "1371-公共-原生成功-主页边界",
    ]
    assert nodes["0234-采集部署-关闭-奖励"]["on_error"] == [
        "0235-采集部署-关闭"
    ]

    collected = nodes["0251-采集部署-采集-已采集"]
    assert collected["recognition"] == "OCR"
    assert collected["expected"] == "已采集"
    assert collected["roi"] == [800, 450, 420, 150]
    # In the 1280x720 failure frame, full-frame OCR located the complete
    # marker at [830, 492, 55, 20]. The old x=840 boundary clipped its first
    # glyph and produced "巴采集"; the recognition ROI must contain it whole.
    marker_box = [830, 492, 55, 20]
    rx, ry, rw, rh = collected["roi"]
    bx, by, bw, bh = marker_box
    assert rx <= bx and ry <= by
    assert bx + bw <= rx + rw and by + bh <= ry + rh

    close_collection = nodes["0235-采集部署-关闭"]
    assert close_collection["recognition"]["param"] == {
        "all_of": [
            "0244-采集部署-采集-页面",
            "0251-采集部署-采集-已采集",
            "0247-采集部署-采集-关闭",
        ],
        "box_index": 2,
    }
    assert nodes["0235-采集部署-关闭"]["next"] == [
        "0236-采集部署-关闭-画卷"
    ]
    assert "on_error" not in nodes["0235-采集部署-关闭"]
    assert nodes["0236-采集部署-关闭-画卷"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]
    assert "on_error" not in nodes["0236-采集部署-关闭-画卷"]
    assert nodes["0234-采集部署-关闭-奖励"]["next"] == [
        "0235-采集部署-关闭",
        "1371-公共-原生成功-主页边界",
    ]


def test_auto_deploy_prompt_accepts_observed_ocr_variant() -> None:
    nodes = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    assert nodes["0253-采集部署-自动部署-提示"]["expected"] == (
        r"^(?:是否(?:自动|自勘|自劫)部署采集机关[？?]?|是否自脚部)$"
    )
