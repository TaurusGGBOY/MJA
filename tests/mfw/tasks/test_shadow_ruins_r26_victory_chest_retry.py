from __future__ import annotations

import json
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def _first_matching_branch(
    branches: list[str], matches: dict[str, bool]
) -> str | None:
    return next((branch for branch in branches if matches.get(branch, False)), None)


def test_r26_victory_chest_claim_has_one_distinct_retry_after_result_probes() -> None:
    """The first triplet can select the chest; the second opens its reward."""

    nodes = _nodes()
    first = nodes["影之遗迹-领取-胜利-宝箱-首个"]
    retry = nodes["影之遗迹-领取-胜利-宝箱-重试"]
    foreground = nodes["影之遗迹-前台-循环"]
    battle_cap = nodes["影之遗迹-战斗-循环"]["max_hit"]

    assert first["max_hit"] == retry["max_hit"] == battle_cap
    assert first["retry_times"] == retry["retry_times"] == 0
    branches = first["next"]
    assert branches == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-领取-胜利-宝箱-重试",
    ]
    assert _first_matching_branch(
        branches,
        {
            "影之遗迹-最终-探测": True,
            "影之遗迹-奖励-探测": True,
            "影之遗迹-胜利-宝箱-奖励-探测": True,
            "影之遗迹-领取-胜利-宝箱-重试": True,
        },
    ) == "影之遗迹-最终-探测"
    assert _first_matching_branch(
        branches,
        {
            "影之遗迹-最终-探测": False,
            "影之遗迹-奖励-探测": True,
            "影之遗迹-胜利-宝箱-奖励-探测": True,
            "影之遗迹-领取-胜利-宝箱-重试": True,
        },
    ) == "影之遗迹-奖励-探测"
    assert _first_matching_branch(
        branches,
        {
            "影之遗迹-最终-探测": False,
            "影之遗迹-奖励-探测": False,
            "影之遗迹-胜利-宝箱-奖励-探测": True,
            "影之遗迹-领取-胜利-宝箱-重试": True,
        },
    ) == "影之遗迹-胜利-宝箱-奖励-探测"
    assert _first_matching_branch(
        branches,
        {
            "影之遗迹-最终-探测": False,
            "影之遗迹-奖励-探测": False,
            "影之遗迹-胜利-宝箱-奖励-探测": False,
            "影之遗迹-领取-胜利-宝箱-重试": True,
        },
    ) == "影之遗迹-领取-胜利-宝箱-重试"
    assert first["on_error"] == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-记录-失败",
    ]
    assert retry["next"] == [
        "影之遗迹-最终-探测",
        "影之遗迹-奖励-探测",
        "影之遗迹-胜利-宝箱-奖励-探测",
        "影之遗迹-胜利-宝箱-之后-重试-等待",
    ]
    assert "影之遗迹-领取-胜利-宝箱-首个" not in retry["next"]
    assert "影之遗迹-领取-胜利-宝箱-重试" not in retry["next"]

    foreground_action = foreground["custom_action_param"]
    for claim in (first, retry):
        claim_action = claim["custom_action_param"]
        assert claim_action["action_id"] == "advance_shadow_foreground_triplet"
        assert claim_action["fixed_click_boxes"] == foreground_action["fixed_click_boxes"]
        assert claim_action["fixed_click_boxes"] == [
            [436, 536, 24, 24],
            [629, 536, 24, 24],
            [822, 536, 24, 24],
        ]

        claim_contract = json.dumps(claim, ensure_ascii=False)
        assert "transfer_shadow_stage" not in claim_contract
        assert "MJA_SHADOW_TRANSFER" not in claim_contract
        assert "shadow.transfer" not in claim_contract
