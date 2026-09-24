import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agent.custom.recognition.weekly_receipt import find_weekly_native_receipt, weekly_start

ZONE = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 9, 9, 0, 10, tzinfo=ZONE)
ENTRY = "0022-每周免费礼包-任务入口"


def events(account="12345", state="Succeeded"):
    return [
        ("Tasker.Task.Starting", {"entry": ENTRY}),
        ("Node.Recognition.Succeeded", {"name": "1340-每周免费礼包-免费-领取",
          "reco_details": {"detail": {"all": [{"text": f"UID:{account}"}]}}}),
        ("Node.Action.Succeeded", {"name": "1340-每周免费礼包-免费-领取"}),
        ("Node.Recognition.Succeeded", {"name": "1342-每周免费礼包-关闭-奖励",
          "reco_details": {"detail": {"all": [
              {"text": "恭喜获得"}, {"text": "点击空白处关闭"}]}}}),
        ("Node.Action.Succeeded", {"name": "1342-每周免费礼包-关闭-奖励"}),
        (f"Tasker.Task.{state}", {"entry": ENTRY}),
    ]


def write_log(path, records, day="2026-09-07"):
    path.write_text("\n".join(
        f"[{day} 07:40:{index:02}.000][INF] !!!OnEventNotify!!! [msg={event}] "
        f"[details={json.dumps(dict(data, task_id=200000001), ensure_ascii=False)}]"
        for index, (event, data) in enumerate(records)
    ))
    return path


def test_current_week_same_account_native_reward_receipt_is_accepted(tmp_path):
    path = write_log(tmp_path / "maafw.log", events())
    receipt = find_weekly_native_receipt([path], "12345", NOW)
    assert receipt["source"] == str(path)
    assert receipt["same_account"] is True
    assert "12345" not in json.dumps(receipt)


@pytest.mark.parametrize("missing", range(6))
def test_each_native_proof_component_is_required(tmp_path, missing):
    records = events()
    del records[missing]
    path = write_log(tmp_path / "maafw.log", records)
    assert find_weekly_native_receipt([path], "12345", NOW) is None


@pytest.mark.parametrize("account,state,day", [
    ("99999", "Succeeded", "2026-09-07"),
    ("12345", "Failed", "2026-09-07"),
    ("12345", "Succeeded", "2026-09-06"),
])
def test_wrong_account_failed_or_previous_week_cannot_satisfy_today(tmp_path, account, state, day):
    path = write_log(tmp_path / "maafw.log", events(account, state), day)
    assert find_weekly_native_receipt([path], "12345", NOW) is None


def test_week_rolls_at_monday_five_am():
    assert weekly_start(datetime(2026, 9, 7, 4, 59, tzinfo=ZONE)).day == 31
    assert weekly_start(datetime(2026, 9, 7, 5, 0, tzinfo=ZONE)).day == 7


def test_unrelated_ocr_payloads_are_not_decoded(tmp_path, monkeypatch):
    import agent.custom.recognition.weekly_receipt as receipt_module

    path = write_log(tmp_path / "maafw.log", events())
    unrelated = (
        '[2026-09-07 07:39:00.000][INF] !!!OnEventNotify!!! '
        '[msg=Node.Recognition.Succeeded] '
        '[details={"task_id": 999, "unrelated_payload": true}]\n'
    )
    path.write_text(unrelated * 100 + path.read_text())
    original = json.loads
    decoded = []

    def decode(value):
        assert "unrelated_payload" not in value
        decoded.append(value)
        return original(value)

    monkeypatch.setattr(receipt_module.json, "loads", decode)
    assert find_weekly_native_receipt([path], "12345", NOW)
    assert len(decoded) == 6


def test_reused_native_task_id_cannot_join_separate_runs(tmp_path):
    records = events()[:-1]
    records.extend([
        ("Tasker.Task.Starting", {"entry": "some-other-business-task"}),
        ("Tasker.Task.Succeeded", {"entry": ENTRY}),
    ])
    path = write_log(tmp_path / "maafw.log", records)
    assert find_weekly_native_receipt([path], "12345", NOW) is None


def test_embedded_runtime_can_import_without_zoneinfo(monkeypatch):
    import importlib.util
    import sys

    from maa.agent.agent_server import AgentServer

    import agent.custom.recognition.weekly_receipt as receipt_module

    monkeypatch.setitem(sys.modules, "zoneinfo", None)
    # This test isolates Python import availability, not native registration.
    monkeypatch.setattr(AgentServer, "custom_recognition", lambda _name: lambda cls: cls)
    spec = importlib.util.spec_from_file_location(
        "receipt_without_zoneinfo", receipt_module.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.weekly_start(NOW) == weekly_start(NOW)
