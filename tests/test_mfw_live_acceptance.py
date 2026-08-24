from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mfw_live_acceptance import (
    begin_acceptance,
    finish_acceptance,
    formal_task_order,
    main,
    parse_expected_terminals,
)

ENTRIES = {
    "GAME_START": "MJA_START",
    "MAIL_REWARD_DAILY": "MJA_MAIL",
    "SHOP_FREE_GIFT_DAILY": "MJA_SHOP",
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    imports = []
    for task_id in ENTRIES:
        relative = Path(f"tasks/{task_id}.json")
        imports.append(str(relative))
        write_json(
            candidate / relative,
            {"task": [{"name": task_id, "entry": ENTRIES[task_id], "default_check": True}]},
        )
    write_json(candidate / "interface.json", {"import": imports})
    executable = candidate / "MFW"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    (candidate / "debug").mkdir()
    (candidate / "debug/gui.log").write_text("", encoding="utf-8")
    (candidate / "debug/maafw.log").write_text("", encoding="utf-8")
    return candidate


def append_native_run(
    candidate: Path,
    task_ids: tuple[str, ...],
    states: dict[str, str] | None = None,
) -> None:
    with (candidate / "debug/gui.log").open("a", encoding="utf-8") as gui:
        for task_id in task_ids:
            gui.write(f"任务 '{task_id}' 的执行信息: {{}}\n")
    with (candidate / "debug/maafw.log").open("a", encoding="utf-8") as maafw:
        for native_id, task_id in enumerate(task_ids, start=10):
            state = (states or {}).get(task_id, "Succeeded")
            maafw.write(
                f'[msg=Tasker.Task.{state}] '
                f'[details={{"task_id":{native_id},"entry":"{ENTRIES[task_id]}"}}]\n'
            )


def test_formal_order_comes_from_imported_declarations(candidate: Path) -> None:
    assert formal_task_order(candidate) == (
        "GAME_START",
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
    )


def test_expected_terminal_defaults_to_succeeded_and_allows_one_failure() -> None:
    assert parse_expected_terminals(
        ("MAIL_REWARD_DAILY=Failed",),
        ("GAME_START", "MAIL_REWARD_DAILY"),
    ) == {"GAME_START": "Succeeded", "MAIL_REWARD_DAILY": "Failed"}


def test_begin_cli_persists_predeclared_expectation(
    candidate: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(
        [
            "begin",
            "--candidate",
            str(candidate),
            "--owner",
            "worker:mail-failure",
            "--task",
            "MAIL_REWARD_DAILY",
            "--expect-terminal",
            "MAIL_REWARD_DAILY=Failed",
        ]
    ) == 0
    ticket = Path(capsys.readouterr().out.strip())
    payload = load_json(ticket)
    assert payload["expected_terminals"]["MAIL_REWARD_DAILY"] == "Failed"


@pytest.mark.parametrize(
    "value",
    ["MAIL_REWARD_DAILY", "MAIL_REWARD_DAILY=success", "UNKNOWN=Failed"],
)
def test_expected_terminal_requires_selected_native_state(value: str) -> None:
    with pytest.raises(ValueError):
        parse_expected_terminals((value,), ("GAME_START", "MAIL_REWARD_DAILY"))


def test_pair_acceptance_uses_only_native_terminal_and_writes_native_summary(
    candidate: Path,
) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    (candidate / "debug/mfw-old/MAIL_REWARD_DAILY").mkdir(parents=True)
    (candidate / "debug/mfw-old/MAIL_REWARD_DAILY/result.json").write_text(
        "not JSON and must not be opened", encoding="utf-8"
    )
    append_native_run(candidate, ("GAME_START", "MAIL_REWARD_DAILY"))

    summary = finish_acceptance(ticket)
    payload = load_json(summary)
    assert payload["expected_terminals"] == {
        "GAME_START": "Succeeded",
        "MAIL_REWARD_DAILY": "Succeeded",
    }
    assert payload["tasks"]["MAIL_REWARD_DAILY"] == {
        "task_id": "MAIL_REWARD_DAILY",
        "entry": "MJA_MAIL",
        "native_terminal": "Succeeded",
    }
    assert "status" not in json.dumps(payload)
    assert "postcondition" not in json.dumps(payload)
    assert "result_path" not in json.dumps(payload)


def test_acceptance_accepts_predeclared_failed_business_task(candidate: Path) -> None:
    ticket = begin_acceptance(
        candidate,
        "worker:mail-failure",
        "MAIL_REWARD_DAILY",
        expected_terminals=("MAIL_REWARD_DAILY=Failed",),
    )
    append_native_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "Failed"},
    )

    payload = load_json(finish_acceptance(ticket))
    assert payload["tasks"]["MAIL_REWARD_DAILY"]["native_terminal"] == "Failed"


def test_acceptance_rejects_duplicate_native_terminal(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_native_run(candidate, ("GAME_START", "MAIL_REWARD_DAILY"))
    with (candidate / "debug/maafw.log").open("a", encoding="utf-8") as maafw:
        maafw.write(
            '[msg=Tasker.Task.Succeeded] '
            '[details={"task_id":12,"entry":"MJA_MAIL"}]\n'
        )

    with pytest.raises(ValueError, match="native terminal events"):
        finish_acceptance(ticket)


def test_acceptance_ignores_stale_log_prefix(candidate: Path) -> None:
    append_native_run(candidate, ("GAME_START", "MAIL_REWARD_DAILY"))
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_native_run(candidate, ("GAME_START", "MAIL_REWARD_DAILY"))

    assert finish_acceptance(ticket).is_file()


def test_acceptance_requires_expected_terminal_before_observing_run(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_native_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "Failed"},
    )

    with pytest.raises(ValueError, match="expected native terminal"):
        finish_acceptance(ticket)
