from __future__ import annotations

from tests.mfw.task_contract import TaskContract, assert_outcome, load_task_nodes


APPRAISAL = TaskContract(
    "FREE_APPRAISAL_DAILY",
    "daily/free_appraisal_daily.json",
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


def test_appraisal_closes_archived_tea_shop_before_probing_appraisal() -> None:
    nodes = load_task_nodes(APPRAISAL)

    start = nodes[APPRAISAL.entry]
    assert start["next"][:3] == [
        "[JumpBack]公共-已知-画卷-关闭",
        "[JumpBack]免费鉴定-额外-弹窗-关闭",
        "[JumpBack]免费鉴定-已知-茶-商店-关闭",
    ]

    recovery = nodes["免费鉴定-已知-茶-商店-关闭"]
    assert recovery["recognition"]["param"] == {
        "all_of": [
            "免费鉴定-鉴定-万用-商店-页面",
            "免费鉴定-鉴定-万用-商店-关闭",
        ],
        "box_index": 1,
    }
    assert recovery["action"] == "Click"
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 5000
    assert recovery["retry_times"] == 0
    assert recovery["on_error"] == ["免费鉴定-记录-失败"]

    page = nodes["免费鉴定-鉴定-万用-商店-页面"]
    assert page["expected"] == "^玉盟商会$"
    assert _contains(page["roi"], [91, 30, 84, 23])

    close = nodes["免费鉴定-鉴定-万用-商店-关闭"]
    assert close["template"] == "daily/BUY_TEA_DAILY/shop_close.png"
    assert close["roi"] == [1160, 0, 100, 100]
    assert close["threshold"] == 0.39

    assert_outcome(
        nodes,
        "免费鉴定-记录-失败",
        "failed",
        "APPRAISAL_POSTCONDITION_MISSING",
    )
    assert nodes["免费鉴定-记录-失败"]["Abort"] is True
