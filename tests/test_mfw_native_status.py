from __future__ import annotations

from tools.mfw_native_status import NativeTerminalEvent, parse_native_terminal_events


def test_parser_returns_selected_native_terminals_and_ignores_nonterminals() -> None:
    log = "\n".join(
        [
            '[msg=Tasker.Task.Pending] [details={"task_id":1,"entry":"MJA_START"}]',
            '[msg=Tasker.Task.Running] [details={"task_id":1,"entry":"MJA_START"}]',
            '[msg=Tasker.Task.Succeeded] [details={"task_id":1,"entry":"OTHER"}]',
            '[msg=Tasker.Task.Succeeded] [details={"task_id":1,"entry":"MJA_START"}]',
            '[msg=Tasker.Task.Failed] [details={"task_id":2,"entry":"MJA_MAIL"}]',
            '[msg=Tasker.Task.Invalid] [details={"task_id":2,"entry":"MJA_MAIL"}]',
        ]
    )

    events = parse_native_terminal_events(
        log,
        {"GAME_START": "MJA_START", "MAIL": "MJA_MAIL"},
    )

    assert events == (
        NativeTerminalEvent(1, "MJA_START", "Succeeded", 1),
        NativeTerminalEvent(2, "MJA_MAIL", "Failed", 2),
    )


def test_parser_does_not_invent_native_task_id_or_entry() -> None:
    log = '[msg=Tasker.Task.Succeeded] [details={"entry":"MJA_START"}]\n'

    assert parse_native_terminal_events(log, {"GAME_START": "MJA_START"}) == ()


def test_parser_preserves_unicode_entry_names() -> None:
    log = (
        '[msg=Tasker.Task.Succeeded] '
        '[details={"task_id":7,"entry":"0023-启动-游戏入口"}]\n'
    )

    assert parse_native_terminal_events(log, {"GAME_START": "0023-启动-游戏入口"})[0].entry == (
        "0023-启动-游戏入口"
    )
