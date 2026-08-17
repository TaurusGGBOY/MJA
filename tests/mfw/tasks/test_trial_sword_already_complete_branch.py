from __future__ import annotations

from tests.mfw.task_contract import TaskContract, load_task_nodes


TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")


def test_trial_free_claim_branch_precedes_already_complete_fallback() -> None:
    nodes = load_task_nodes(TRIAL)

    open_trial = nodes["试剑-打开-试炼"]
    assert open_trial["next"] == ["试剑-领取-奖励"]

    probe = nodes["试剑-已完成-探测"]
    assert probe["recognition"]["param"] == {
        "all_of": [
            "试剑-试炼-页面",
            "试剑-试炼-敬请期待",
        ],
        "box_index": 1,
    }
    assert probe["on_error"] == ["试剑-领取-免费"]

    completed = nodes["试剑-已完成"]
    assert completed["custom_action_param"] == {
        "task_id": "TRIAL_SWORD_DAILY",
        "status": "already_complete",
        "postcondition": "trial.free_waiting",
        "defer_home_boundary": True,
    }
    assert completed["next"] == ["试剑-关闭-成功"]

    assert nodes["试剑-领取-奖励"]["on_error"] == ["试剑-领取-免费"]
    assert nodes["试剑-关闭-奖励"]["next"] == ["试剑-领取-免费"]
    assert nodes["试剑-领取-免费"]["on_error"] == ["试剑-已完成-探测"]


def test_trial_completion_markers_are_bounded_to_their_visible_controls() -> None:
    nodes = load_task_nodes(TRIAL)
    assert nodes["试剑-试炼-敬请期待"] == {
        "recognition": "OCR",
        "expected": r"^敬\s*请\s*期\s*待$",
        "roi": [930, 600, 320, 100],
        "action": "DoNothing",
    }
