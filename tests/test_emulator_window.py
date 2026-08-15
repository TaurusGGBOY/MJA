from __future__ import annotations

from agent.android.emulator_window import EmulatorWindow, ensure_emulator_foreground


class FakeBackend:
    def __init__(self, windows: list[EmulatorWindow | None], *, activated: bool = True) -> None:
        self.windows = windows
        self.activated = activated
        self.find_calls: list[str] = []
        self.activated_pids: list[int] = []

    def find_standard_window(self, avd_name: str) -> EmulatorWindow | None:
        self.find_calls.append(avd_name)
        return self.windows.pop(0) if self.windows else None

    def activate_pid(self, pid: int) -> bool:
        self.activated_pids.append(pid)
        return self.activated


def test_stage_manager_emulator_is_activated_by_standard_window() -> None:
    backend = FakeBackend([EmulatorWindow(40536, "Android Emulator - mja:5556")])

    assert ensure_emulator_foreground("mja", backend=backend, timeout_seconds=0)
    assert backend.find_calls == ["mja"]
    assert backend.activated_pids == [40536]


def test_missing_window_times_out_without_activation() -> None:
    backend = FakeBackend([None])

    assert not ensure_emulator_foreground("mja", backend=backend, timeout_seconds=0)
    assert backend.activated_pids == []


def test_activation_failure_is_reported_for_retry() -> None:
    backend = FakeBackend(
        [EmulatorWindow(40536, "Android Emulator - mja:5556")], activated=False
    )

    assert not ensure_emulator_foreground("mja", backend=backend, timeout_seconds=0)
