from __future__ import annotations

import json
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)

FIRST = "影之遗迹-领取-胜利-宝箱-首个"
RETRY = "影之遗迹-领取-胜利-宝箱-重试"
WAIT = "影之遗迹-胜利-宝箱-之后-重试-等待"
FINAL = "影之遗迹-最终-探测"
REWARD = "影之遗迹-奖励-探测"
CHEST_REWARD = "影之遗迹-胜利-宝箱-奖励-探测"
FAILURE = "影之遗迹-记录-失败"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r27_each_victory_has_two_fresh_global_claim_budgets() -> None:
    """Maa max_hit is global, so each claim phase needs the full battle budget."""

    nodes = _nodes()
    battle_cap = nodes["影之遗迹-战斗-循环"]["max_hit"]
    victory = nodes["影之遗迹-战斗-结果-胜利"]

    assert victory["next"] == [FIRST]
    claim_names = [
        name
        for name, node in nodes.items()
        if name.startswith("MJA_SHADOW_CLAIM_VICTORY_CHEST")
        and node.get("custom_action_param", {}).get("action_id")
        == "advance_shadow_foreground_triplet"
    ]
    assert claim_names == [FIRST, RETRY], (
        "a single self-recursing claim node spends its global max_hit on the "
        "first victory and cannot service later floors"
    )

    claims = {name: nodes[name] for name in claim_names}
    for name, claim in claims.items():
        assert claim["max_hit"] == battle_cap
        assert claim["retry_times"] == 0
        assert name not in claim["next"]

    assert [branch for branch in claims[FIRST]["next"] if branch in claims] == [
        RETRY
    ]
    assert [branch for branch in claims[RETRY]["next"] if branch in claims] == []

    # Model the Maa task-context counters across every allowed victory.  Each
    # victory traverses FIRST then RETRY at most once; neither global counter
    # is exhausted before the battle loop's own cap.
    hits = {name: 0 for name in claim_names}
    for _ in range(battle_cap):
        for name in (FIRST, RETRY):
            hits[name] += 1
            assert hits[name] <= claims[name]["max_hit"]
    assert hits == {FIRST: battle_cap, RETRY: battle_cap}


def test_r27_claim_phases_share_safe_triplet_and_prioritize_terminal_results() -> None:
    nodes = _nodes()
    battle_cap = nodes["影之遗迹-战斗-循环"]["max_hit"]
    first = nodes[FIRST]
    retry = nodes[RETRY]
    wait = nodes[WAIT]
    foreground = nodes["影之遗迹-前台-循环"]

    assert first["next"] == [FINAL, REWARD, CHEST_REWARD, RETRY]
    assert retry["next"] == [FINAL, REWARD, CHEST_REWARD, WAIT]

    for claim in (first, retry):
        action = claim["custom_action_param"]
        assert claim["custom_action"] == "GuardedInput"
        assert action["action_id"] == "advance_shadow_foreground_triplet"
        assert action["fixed_click_boxes"] == foreground["custom_action_param"][
            "fixed_click_boxes"
        ]
        assert action["fixed_click_boxes"] == [
            [436, 536, 24, 24],
            [629, 536, 24, 24],
            [822, 536, 24, 24],
        ]
        assert action["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": "影之遗迹-影-探索-页面",
            "target_name": "影之遗迹-影-前台-就绪",
        }
        claim_contract = json.dumps(claim, ensure_ascii=False)
        assert "transfer_shadow_stage" not in claim_contract
        assert "MJA_SHADOW_TRANSFER" not in claim_contract
        assert "shadow.transfer" not in claim_contract

    assert wait["recognition"] == "DirectHit"
    assert wait["action"] == "DoNothing"
    assert wait["post_delay"] == 1000
    assert wait["max_hit"] == battle_cap
    assert wait["retry_times"] == 0
    assert wait["next"] == [FINAL, REWARD, CHEST_REWARD, FAILURE]
    assert wait["on_error"] == [FAILURE]
