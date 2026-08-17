from __future__ import annotations

from tests.mfw.task_contract import TaskContract, load_task_nodes


COLLECTION = TaskContract(
    "COLLECTION_DEPLOYMENT_DAILY",
    "daily/collection_deployment_daily.json",
)


def test_missing_reward_popup_falls_back_to_closing_collection_page() -> None:
    nodes = load_task_nodes(COLLECTION)

    # A fresh run can successfully click 一键收获 without producing a reward
    # dialog (for example, when every resource is already marked 已采集).  The
    # collection sheet is still a valid intermediate state and must be closed
    # before the shared home boundary is checked.
    assert nodes["采集部署-收获-成功"]["on_error"] == ["采集部署-关闭"]
    assert nodes["采集部署-关闭-奖励"]["on_error"] == ["采集部署-关闭"]
    assert nodes["采集部署-关闭"]["next"] == ["采集部署-奖励-画卷-探测"]
