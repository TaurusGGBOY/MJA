"""Parse MaaFramework's native terminal task notifications."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Mapping

NativeTaskState = Literal["Succeeded", "Failed"]


@dataclass(frozen=True, slots=True)
class NativeTerminalEvent:
    native_task_id: int
    entry: str
    state: NativeTaskState
    sequence: int


_TERMINAL_LINE = re.compile(r"Tasker\.Task\.(Succeeded|Failed)")
_TASK_ID = re.compile(r'(?:(?:"task_id")|(?:\btask_id\b))\s*[:=]\s*"?(\d+)"?')
_ENTRY = re.compile(r'"entry"\s*:\s*"((?:\\.|[^"\\])*)"')


def _unescape_entry(value: str) -> str:
    return str(json.loads(f'"{value}"'))


def parse_native_terminal_events(
    log_text: str, selected_entries: Mapping[str, str]
) -> tuple[NativeTerminalEvent, ...]:
    """Return selected native terminal notifications in log order.

    ``selected_entries`` maps task names to their declared pipeline entries.
    Pending/running/invalid states and terminal events for other entries are
    intentionally ignored; the caller keeps the raw logs for diagnostics.
    """

    entries = {str(value) for value in selected_entries.values()}
    events: list[NativeTerminalEvent] = []
    terminal_sequence = 0
    for line in log_text.splitlines():
        match = _TERMINAL_LINE.search(line)
        if match is None:
            continue
        sequence = terminal_sequence
        terminal_sequence += 1
        task_match = _TASK_ID.search(line)
        entry_match = _ENTRY.search(line)
        if task_match is None or entry_match is None:
            continue
        entry = _unescape_entry(entry_match.group(1))
        if entry not in entries:
            continue
        state: NativeTaskState = match.group(1)  # type: ignore[assignment]
        events.append(
            NativeTerminalEvent(
                native_task_id=int(task_match.group(1)),
                entry=entry,
                state=state,
                sequence=sequence,
            )
        )
    return tuple(events)


__all__ = ["NativeTaskState", "NativeTerminalEvent", "parse_native_terminal_events"]
