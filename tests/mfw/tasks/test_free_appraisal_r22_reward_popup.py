from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from tests.mfw.pipeline_assertions import (
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import (
    TaskContract,
    assert_native_terminal_contract,
    assert_no_side_effect_retry,
    load_task_nodes,
)


ROOT = Path(__file__).parents[3]
APPRAISAL = TaskContract(
    "FREE_APPRAISAL_DAILY",
    "daily/free_appraisal_daily.json",
)
FIXTURE = ROOT / "tests/fixtures/FREE_APPRAISAL_DAILY/r22_reward_popup.png"
RUNTIME_RECOVERY = "0480-免费鉴定-运行时-恢复-尝试"


def _scoped_nodes() -> dict[str, dict[str, object]]:
    return json.loads(
        (ROOT / "assets/resource/base/pipeline" / APPRAISAL.pipeline_file).read_text(
            encoding="utf-8"
        )
    )


def _contains(roi: list[int], box: list[int]) -> bool:
    x, y, width, height = roi
    box_x, box_y, box_width, box_height = box
    return (
        x <= box_x
        and y <= box_y
        and x + width >= box_x + box_width
        and y + height >= box_y + box_height
    )


def _overlaps(left: list[int], right: list[int]) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return not (
        left_x + left_width <= right_x
        or right_x + right_width <= left_x
        or left_y + left_height <= right_y
        or right_y + right_height <= left_y
    )


def _connected_components(points: list[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(points)
    components: list[set[tuple[int, int]]] = []
    while remaining:
        pending = [remaining.pop()]
        component: set[tuple[int, int]] = set()
        while pending:
            point = pending.pop()
            component.add(point)
            x, y = point
            neighbors = {
                (x + dx, y + dy)
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if (dx, dy) != (0, 0)
            }
            found = neighbors & remaining
            remaining -= found
            pending.extend(found)
        components.append(component)
    return components


def test_r22_fixture_is_the_immutable_archived_reward_popup() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        "5169e237e26b3b85d5c9788c65ccae1ab80ad7c95cddde835f57a3f07a9abf47"
    )
    with Image.open(FIXTURE) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"
        assert image.size == (1280, 720)


def test_r22_popup_uses_top_right_close_template_as_the_result_anchor() -> None:
    nodes = load_task_nodes(APPRAISAL)
    popup = nodes["0510-免费鉴定-鉴定-结果-弹窗"]
    assert popup == {
        "recognition": "OCR",
        "expected": ["鉴宝一次", "鉴宝十次", "恭喜获得", "获得"],
        "roi": [300, 100, 680, 620],
        "action": "DoNothing",
    }


def test_r22_top_right_close_target_is_real_and_cannot_hit_paid_buttons() -> None:
    nodes = load_task_nodes(APPRAISAL)
    target = nodes["0513-免费鉴定-鉴定-弹窗-关闭"]
    assert target == {
        "recognition": "ColorMatch",
        "lower": [150, 150, 130],
        "upper": [255, 255, 255],
        "roi": [1180, 10, 65, 65],
        "connected": True,
        "count": 250,
        "action": "DoNothing",
    }

    with Image.open(FIXTURE) as image:
        x, y, width, height = target["roi"]
        pixels = image.crop((x, y, x + width, y + height)).load()
        lower = target["lower"]
        upper = target["upper"]
        matches = [
            (x + col, y + row)
            for row in range(height)
            for col in range(width)
            if all(
                low <= channel <= high
                for channel, low, high in zip(pixels[col, row], lower, upper)
            )
        ]
    components = _connected_components(matches)
    assert [len(component) for component in components] == [315]
    assert len(components[0]) >= target["count"]
    xs = [point[0] for point in components[0]]
    ys = [point[1] for point in components[0]]
    close_box = [min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1]
    assert close_box == [1198, 30, 29, 25]
    assert _contains(target["roi"], close_box)
    for paid_button in (
        [407, 564, 207, 78],
        [666, 564, 207, 78],
    ):
        assert not _overlaps(target["roi"], paid_button)
        assert not _overlaps(close_box, paid_button)


def test_r22_reward_close_is_same_frame_guarded_and_every_input_is_capped_once() -> None:
    from agent.custom.support.policy import TASK_POLICIES

    nodes = load_task_nodes(APPRAISAL)
    start = nodes["0009-免费鉴定-任务入口"]
    assert start["next"][:2] == [
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "[JumpBack]0499-免费鉴定-额外-弹窗-关闭",
    ]
    assert start["next"][2] == "[JumpBack]0481-免费鉴定-已知-茶-商店-关闭"
    assert start["on_error"] == [
        "MJA-任务入口失败-FREE_APPRAISAL_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]

    for name, box_index in (
        ("0491-免费鉴定-奖励-探测", 0),
        ("0492-免费鉴定-关闭-奖励", 1),
    ):
        assert nodes[name]["recognition"]["param"] == {
            "all_of": ["0510-免费鉴定-鉴定-结果-弹窗", "0513-免费鉴定-鉴定-弹窗-关闭"],
            "box_index": box_index,
        }
        assert "on_error" not in nodes[name]
        assert nodes[name]["timeout"] == 8000

    close = nodes["0492-免费鉴定-关闭-奖励"]
    assert close["max_hit"] == 1
    assert close["retry_times"] == 0
    assert close["custom_action_param"] == {
        "task_id": APPRAISAL.task_id,
        "action_id": "close_appraisal_popup",
        "kind": "click",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0510-免费鉴定-鉴定-结果-弹窗",
            "target_name": "0513-免费鉴定-鉴定-弹窗-关闭",
        },
    }
    assert close["next"] == [
        "[JumpBack]0499-免费鉴定-额外-弹窗-关闭",
        "0493-MJA_APPRAISAL_VERIFY",
        "0496-免费鉴定-主页-之后-奖励",
    ]

    extra = nodes["0499-免费鉴定-额外-弹窗-关闭"]
    assert extra["recognition"]["param"]["all_of"] == [
        "0510-免费鉴定-鉴定-结果-弹窗",
        "0513-免费鉴定-鉴定-弹窗-关闭",
    ]
    assert extra["next"][0] == "[JumpBack]0515-免费鉴定-额外-弹窗-关闭-额外"

    policy = TASK_POLICIES[APPRAISAL.task_id]
    assert policy.action_caps["claim_free_appraisal_once"] == 1
    assert policy.action_caps["close_appraisal_popup"] == 1
    assert policy.action_caps["close_appraisal_page"] == 1
    assert policy.action_caps["close_extra_reward_popup"] == 2
    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if params.get("task_id") == APPRAISAL.task_id and params.get("action_id"):
            assert node["max_hit"] == 1
            assert node["retry_times"] == 0


def test_r22_post_close_accepts_only_used_once_state_or_explicit_home() -> None:
    nodes = load_task_nodes(APPRAISAL)
    assert nodes["0485-免费鉴定-页面-探测"]["next"] == [
        "0486-MJA_APPRAISAL_STATUS_PROBE",
        "0486-MJA_APPRAISAL_TEN_PROBE",
        "0490-免费鉴定-领取",
    ]
    used = nodes["0509-appraisal.used"]
    assert used == {
        "recognition": "OCR",
        "expected": ["^鉴宝一次$", "^80$"],
        "roi": [430, 540, 260, 130],
        "action": "DoNothing",
    }
    assert "免费" not in used["expected"]
    home_entry = nodes["0501-免费鉴定-鉴定-主页-入口"]
    assert home_entry["expected"] == ["^鉴宝$", "^宝$"]
    assert home_entry["roi"] == [850, 30, 130, 70]
    assert nodes["0502-免费鉴定-鉴定-页面"]["roi"] == [0, 0, 300, 100]
    assert nodes["0493-MJA_APPRAISAL_VERIFY"]["recognition"]["param"] == {
        "all_of": ["0502-免费鉴定-鉴定-页面", "0509-appraisal.used"],
        "box_index": 1,
    }
    assert nodes["0493-MJA_APPRAISAL_VERIFY"]["next"] == [
        "0494-免费鉴定-关闭-成功-页面"
    ]
    assert nodes["0494-免费鉴定-关闭-成功-页面"]["next"] == [
        "0495-免费鉴定-主页成功后"
    ]
    assert nodes["0495-免费鉴定-主页成功后"]["next"] == [
        "0498-免费鉴定-成功"
    ]

    reward_home = nodes["0496-免费鉴定-主页-之后-奖励"]
    assert reward_home["recognition"]["param"] == {
        "all_of": ["0026-公共-游戏主页-页面", "0500-免费鉴定-鉴定-主页-页面"],
        "box_index": 0,
    }
    assert reward_home["next"] == ["0497-免费鉴定-主页成功"]
    assert nodes["0497-免费鉴定-主页成功"] == {
        "recognition": "DirectHit",
        "action": "StopTask",
    }

    for name in (
        "0490-免费鉴定-领取",
        "0491-免费鉴定-奖励-探测",
        "0492-免费鉴定-关闭-奖励",
        "0493-MJA_APPRAISAL_VERIFY",
        "0494-免费鉴定-关闭-成功-页面",
        "0495-免费鉴定-主页成功后",
        "0496-免费鉴定-主页-之后-奖励",
    ):
        assert "on_error" not in nodes[name]


def test_r22_accepts_only_scoped_eighty_as_the_free_button_completed_state() -> None:
    nodes = load_task_nodes(APPRAISAL)

    ten = nodes["0518-appraisal.remaining_ten"]
    free_button = nodes["0508-免费鉴定-鉴定-免费-一次"]
    assert ten == {
        "recognition": "OCR",
        "expected": "^80$",
        "roi": free_button["roi"],
        "action": "DoNothing",
    }

    ten_probe = nodes["0486-MJA_APPRAISAL_TEN_PROBE"]
    assert ten_probe["recognition"]["param"] == {
        "all_of": ["0502-免费鉴定-鉴定-页面", "0518-appraisal.remaining_ten"],
        "box_index": 1,
    }
    assert ten_probe["next"] == ["0487-MJA_APPRAISAL_CLOSE_ALREADY_COMPLETE_PAGE"]
    assert nodes["0485-免费鉴定-页面-探测"]["next"] == [
        "0486-MJA_APPRAISAL_STATUS_PROBE",
        "0486-MJA_APPRAISAL_TEN_PROBE",
        "0490-免费鉴定-领取",
    ]

    # The marker is scoped to the free-appraisal page/button and is not a
    # generic numeric success fallback or a trial-sword recognition.
    assert ten["expected"] == "^80$"
    assert "TRIAL_SWORD_DAILY" not in str(ten_probe)


def test_r22_never_targets_either_paid_appraisal_button() -> None:
    nodes = load_task_nodes(APPRAISAL)
    guarded = [
        node
        for node in nodes.values()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == APPRAISAL.task_id
    ]
    target_names = {
        node["custom_action_param"]["evidence"]["target_name"] for node in guarded
    }
    assert "appraisal.result.once_control" not in target_names
    assert "appraisal.result.ten_control" not in target_names
    assert "0509-appraisal.used" not in target_names
    assert "0508-免费鉴定-鉴定-免费-一次" in target_names
    assert "0513-免费鉴定-鉴定-弹窗-关闭" in target_names


def test_r22_runtime_recovery_is_the_only_root_fallback_and_has_no_paid_target() -> None:
    nodes = load_task_nodes(APPRAISAL)
    recovery = nodes[RUNTIME_RECOVERY]

    assert recovery["next"][-1] == "1365-公共-主页边界-失败"
    assert "on_error" not in recovery
    assert "appraisal.result.once_control" not in str(recovery)
    assert "appraisal.result.ten_control" not in str(recovery)
    assert "StartApp" not in str(recovery)


def test_r22_migrated_pipeline_has_native_terminals_and_local_recovery_only() -> None:
    scoped = _scoped_nodes()
    assert_no_custom_outcome_nodes(scoped)
    assert_on_error_contract(
        scoped,
        shared_targets={"1365-公共-主页边界-失败"},
    )
    assert_native_terminal_contract(
        scoped,
        success_nodes=[
            "0489-MJA_APPRAISAL_ALREADY_COMPLETE",
            "0497-免费鉴定-主页成功",
            "0498-免费鉴定-成功",
        ],
        failure_nodes=[],
    )
    assert "0517-免费鉴定-记录-失败" not in scoped
    for action_id in (
        "claim_free_appraisal_once",
        "close_appraisal_popup",
        "close_appraisal_page",
        "close_extra_reward_popup",
    ):
        assert_no_side_effect_retry(scoped, action_id)
