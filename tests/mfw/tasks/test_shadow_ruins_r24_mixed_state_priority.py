from __future__ import annotations

import json
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r24_active_card_selection_keeps_existing_topology() -> None:
    nodes = _nodes()
    assert nodes["1192-影之遗迹-影-进行中"]["expected"] == ["探索中", "可探索"]
    assert nodes["1172-影之遗迹-打开-影"]["next"] == ["1173-影之遗迹-选择-进行中"]
    assert nodes["1173-影之遗迹-选择-进行中"]["next"] == ["1174-影之遗迹-进入-关卡"]
    assert nodes["1173-影之遗迹-选择-进行中"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["1191-影之遗迹-影-页面", "1192-影之遗迹-影-进行中"], "box_index": 1},
    }


def test_r24_shadow_page_accepts_full_title_or_single_character_ocr() -> None:
    nodes = _nodes()

    for name in (
        "1190-影之遗迹-影-入口",
        "1191-影之遗迹-影-页面",
    ):
        assert nodes[name]["expected"] == ["蜃影武墟", "影", "武"]

    assert nodes["1194-影之遗迹-影-关卡-页面"]["expected"] == [
        "蜃影武墟",
        "影",
        "武",
        "加速",
    ]


def test_r24_terminal_migration_keeps_original_node_set_and_explicit_failure() -> None:
    nodes = _nodes()
    assert all(node.get("custom_action") not in {"RecordTaskOutcome", "RecordActiveTaskFailure"} for node in nodes.values())
    assert nodes["1591-MJA-影之遗迹-关闭-影-页面"]["next"] == [
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "1371-公共-原生成功-主页边界",
    ]
    for name in ("1180-影之遗迹-战斗未知结果-结果", "1216-影之遗迹-战斗-循环-耗尽", "1221-影之遗迹-记录-失败"):
        assert nodes[name] == {
            "recognition": "DirectHit", "action": "Custom", "custom_action": "FailTask", "Abort": True
        }
