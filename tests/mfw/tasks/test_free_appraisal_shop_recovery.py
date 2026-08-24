from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_no_custom_outcome_nodes
from tests.mfw.task_contract import TaskContract, load_task_nodes


APPRAISAL = TaskContract(
    "FREE_APPRAISAL_DAILY",
    "daily/free_appraisal_daily.json",
)
ROOT = Path(__file__).parents[3]


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
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "[JumpBack]0499-免费鉴定-额外-弹窗-关闭",
        "[JumpBack]0481-免费鉴定-已知-茶-商店-关闭",
    ]

    recovery = nodes["0481-免费鉴定-已知-茶-商店-关闭"]
    assert recovery["recognition"]["param"] == {
        "all_of": [
            "0506-免费鉴定-鉴定-万用-商店-页面",
            "0507-免费鉴定-鉴定-万用-商店-关闭",
        ],
        "box_index": 1,
    }
    assert recovery["action"] == "Click"
    assert recovery["max_hit"] == 1
    assert recovery["timeout"] == 5000
    assert recovery["retry_times"] == 0
    assert "on_error" not in recovery

    page = nodes["0506-免费鉴定-鉴定-万用-商店-页面"]
    assert page["expected"] == "^玉盟商会$"
    assert _contains(page["roi"], [91, 30, 84, 23])

    close = nodes["0507-免费鉴定-鉴定-万用-商店-关闭"]
    assert close["template"] == "daily/BUY_TEA_DAILY/shop_close.png"
    assert close["roi"] == [1160, 0, 100, 100]
    assert close["threshold"] == 0.39

    scoped = json.loads(
        (ROOT / "assets/resource/base/pipeline" / APPRAISAL.pipeline_file).read_text(
            encoding="utf-8"
        )
    )
    assert_no_custom_outcome_nodes(scoped)
    assert "0517-免费鉴定-记录-失败" not in scoped
