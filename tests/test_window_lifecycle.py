from __future__ import annotations

from dataclasses import replace

import pytest

from agent.errors import ErrorCode, MJAError
from agent.macos.window_lifecycle import GameWindow, WindowLifecycle
from agent.macos.window_state import Bounds, WindowSnapshot, WindowStateStore


class FakeBackend:
    def __init__(self) -> None:
        self.window: GameWindow | None = GameWindow(
            41, 902, "对决！剑之川", Bounds(10, 20, 1366, 1024)
        )
        self.running = True
        self.frontmost = "com.apple.Terminal"
        self.calls: list[tuple] = []
        self.snapshot_seen_during_activate: WindowSnapshot | None = None
        self.read_override: GameWindow | None = None

    def find_window(self, title: str, deadline: float) -> GameWindow | None:
        self.calls.append(("find", title, deadline))
        return self.window if self.window and self.window.title == title else None

    def frontmost_bundle_id(self) -> str | None:
        return self.frontmost

    def game_process_running(self) -> bool:
        return self.running

    def activate_pid(self, pid: int) -> None:
        self.snapshot_seen_during_activate = (
            self._store.load_pending() if hasattr(self, "_store") else None
        )
        self.calls.append(("activate", pid))

    def set_bounds(self, window: GameWindow, bounds: Bounds) -> None:
        self.calls.append(("set_bounds", bounds))
        self.window = replace(window, bounds=bounds)

    def read_window(self, window_id: int, pid: int) -> GameWindow | None:
        self.calls.append(("read", window_id, pid))
        return self.read_override if self.read_override is not None else self.window

    def activate_bundle(self, bundle_id: str) -> None:
        self.calls.append(("restore_frontmost", bundle_id))


def make_lifecycle(tmp_path, backend: FakeBackend) -> WindowLifecycle:
    store = WindowStateStore(tmp_path / "window.json")
    backend._store = store
    return WindowLifecycle(backend, store)


def test_prepare_saves_before_resize_and_restore_is_idempotent(tmp_path) -> None:
    backend = FakeBackend()
    lifecycle = make_lifecycle(tmp_path, backend)

    prepared = lifecycle.prepare(timeout_seconds=60)

    assert prepared.bounds == Bounds(10, 20, 1280, 720)
    assert backend.snapshot_seen_during_activate == WindowSnapshot(
        41, 902, Bounds(10, 20, 1366, 1024), "com.apple.Terminal"
    )
    assert [call[:2] for call in backend.calls[:3]] == [
        ("find", "对决！剑之川"),
        ("activate", 902),
        ("set_bounds", Bounds(10, 20, 1280, 720)),
    ]

    lifecycle.restore()
    lifecycle.restore()

    assert backend.calls.count(("set_bounds", Bounds(10, 20, 1366, 1024))) == 1
    assert backend.calls.count(("restore_frontmost", "com.apple.Terminal")) == 1


def test_prepare_accepts_a_fixed_size_game_window(tmp_path) -> None:
    backend = FakeBackend()

    def fixed_set_bounds(window: GameWindow, bounds: Bounds) -> None:
        backend.calls.append(("set_bounds", bounds))

    backend.set_bounds = fixed_set_bounds  # type: ignore[method-assign]
    lifecycle = make_lifecycle(tmp_path, backend)

    prepared = lifecycle.prepare(timeout_seconds=0)

    assert prepared.bounds == Bounds(10, 20, 1366, 1024)
    assert lifecycle.has_pending_restore()


def test_prepare_distinguishes_launch_timeout_from_missing_window(tmp_path) -> None:
    backend = FakeBackend()
    backend.running = False
    backend.window = None
    lifecycle = make_lifecycle(tmp_path, backend)

    with pytest.raises(MJAError) as caught:
        lifecycle.prepare(timeout_seconds=0)

    assert caught.value.code is ErrorCode.APP_LAUNCH_TIMEOUT

    backend.running = True
    with pytest.raises(MJAError) as caught:
        lifecycle.prepare(timeout_seconds=0)

    assert caught.value.code is ErrorCode.WINDOW_NOT_FOUND


def test_prepare_maps_readback_mismatch_to_resize_failure(tmp_path) -> None:
    backend = FakeBackend()
    backend.read_override = replace(backend.window, bounds=Bounds(10, 20, 1279, 720))
    lifecycle = make_lifecycle(tmp_path, backend)

    with pytest.raises(MJAError) as caught:
        lifecycle.prepare(timeout_seconds=0)

    assert caught.value.code is ErrorCode.WINDOW_RESIZE_FAILED
    assert lifecycle.has_pending_restore()


def test_restore_rejects_a_different_window_identity(tmp_path) -> None:
    backend = FakeBackend()
    lifecycle = make_lifecycle(tmp_path, backend)
    lifecycle.prepare(timeout_seconds=0)
    backend.read_override = replace(backend.window, pid=903)

    with pytest.raises(MJAError) as caught:
        lifecycle.restore()

    assert caught.value.code is ErrorCode.WINDOW_RESTORE_FAILED
    assert lifecycle.has_pending_restore()
