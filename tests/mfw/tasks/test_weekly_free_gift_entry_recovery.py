import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_nodes(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_weekly_entry_tries_reward_shop_and_home_states() -> None:
    nodes = _load_nodes(
        "assets/resource/base/pipeline/daily/weekly_free_gift_monday.json"
    )
    assert nodes["周一免费礼包-任务入口"]["next"] == [
        "周一免费礼包-恢复继续-奖励-探测",
        "周一免费礼包-初始-页面-探测",
        "周一免费礼包-主页-探测",
    ]


def test_home_boundary_waits_for_slow_return_action_and_marker() -> None:
    nodes = _load_nodes("assets/resource/base/pipeline/common/home_boundary.json")
    assert nodes["公共-主页边界-尝试返回"]["timeout"] >= 30000


def test_weekly_page_tries_claimed_paid_and_free_states() -> None:
    nodes = _load_nodes(
        "assets/resource/base/pipeline/daily/weekly_free_gift_monday.json"
    )
    assert nodes["周一免费礼包-打开-每周"]["next"] == [
        "周一免费礼包-状态-已领取-探测",
        "周一免费礼包-付费-探测",
        "周一免费礼包-免费-领取",
    ]


def test_weekly_cleanup_closes_function_panel_at_fixed_close_button() -> None:
    nodes = _load_nodes(
        "assets/resource/base/pipeline/daily/weekly_free_gift_monday.json"
    )
    close_panel = nodes["周一免费礼包-完成-关闭-面板"]["custom_action_param"]
    assert close_panel["action_id"] == "close_function_panel"
    assert close_panel["fixed_click_mode"] == "function_panel_close"


def test_abort_recovery_returns_to_world_before_boundary_failure() -> None:
    nodes = _load_nodes("assets/resource/base/pipeline/common/terminal.json")
    assert nodes["公共-通用中止"]["on_error"] == ["公共-失败-返回主页"]
    assert nodes["公共-失败-返回主页"]["custom_action"] == "ReturnToWorldHome"
