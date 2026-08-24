from __future__ import annotations

import json
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[3] / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_shadow_cards_are_selected_before_prepare_checkbox() -> None:
    nodes = _nodes()

    assert nodes["1172-影之遗迹-打开-影"]["next"] == ["1173-影之遗迹-选择-进行中"]
    assert nodes["1173-影之遗迹-选择-进行中"]["next"] == ["1174-影之遗迹-进入-关卡"]
    assert nodes["1192-影之遗迹-影-进行中"]["expected"] == ["探索中", "可探索"]
    assert nodes["1192-影之遗迹-影-进行中"]["roi"] == [80, 430, 720, 270]
    assert nodes["1173-影之遗迹-选择-进行中"]["on_error"] == ["1369-公共-通用停止"]


def test_forward_waits_for_stage_page_then_checks_unchecked_prepare_box() -> None:
    nodes = _nodes()

    forward = nodes["1174-影之遗迹-进入-关卡"]
    wait = nodes["1592-MJA-影之遗迹-自动寻路-等待-关卡"]
    prepare = nodes["1208-影之遗迹-跳过-准备-点击"]

    assert forward["next"] == [
        "1176-影之遗迹-跨图-确认",
        "1593-MJA-影之遗迹-进入-探索页",
        "1592-MJA-影之遗迹-自动寻路-等待-关卡",
    ]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["1194-影之遗迹-影-关卡-页面"], "box_index": 0},
    }
    assert wait["timeout"] == 120000
    assert wait["on_error"] == ["1221-影之遗迹-记录-失败"]
    assert prepare["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "1194-影之遗迹-影-关卡-页面",
                "1224-影之遗迹-影-跳过-准备",
                "1226-影之遗迹-影-跳过-准备-未勾选",
            ],
            "box_index": 2,
        },
    }
    assert prepare["custom_action_param"]["evidence"]["target_index"] == 2
    assert prepare["custom_action_param"]["evidence"]["target_name"] == "1226-影之遗迹-影-跳过-准备-未勾选"
    assert prepare["next"] == ["1501-MJA-影之遗迹地图推进-前景三点循环"]


def test_unchecked_prepare_marker_is_visual_and_scoped_to_checkbox() -> None:
    marker = _nodes()["1226-影之遗迹-影-跳过-准备-未勾选"]

    assert marker["recognition"] == "ColorMatch"
    assert marker["roi"] == [1045, 430, 35, 35]
    assert marker["lower"] == [80, 80, 80]
    assert marker["upper"] == [120, 120, 120]
    assert marker["connected"] is True
    assert marker["action"] == "DoNothing"


def test_stage_start_text_is_not_guessed_in_first_stage_repair() -> None:
    nodes = _nodes()

    assert nodes["1534-MJA-影之遗迹地图推进-识别-战斗目标"]["expected"] == "开战"
    assert nodes["1223-影之遗迹-影-挑战-目标"]["expected"] == ["挑战"]
    assert "1534-MJA-影之遗迹地图推进-识别-战斗目标" not in nodes["1208-影之遗迹-跳过-准备-点击"].get("next", [])
    assert "1223-影之遗迹-影-挑战-目标" not in nodes["1208-影之遗迹-跳过-准备-点击"].get("next", [])
