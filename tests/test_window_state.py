import json

import pytest

from agent.macos.window_state import Bounds, WindowSnapshot, WindowStateStore


def test_state_round_trip_and_consumed_marker(tmp_path) -> None:
    store = WindowStateStore(tmp_path / "window.json")
    snapshot = WindowSnapshot(41, 902, Bounds(10, 20, 1280, 720), "com.apple.Terminal")

    store.save(snapshot)

    assert store.load_pending() == snapshot
    store.mark_restored()
    assert store.load_pending() is None


def test_partial_json_is_rejected(tmp_path) -> None:
    path = tmp_path / "window.json"
    path.write_text('{"window_id":', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid window state"):
        WindowStateStore(path).load_pending()


def test_unknown_schema_version_is_rejected(tmp_path) -> None:
    path = tmp_path / "window.json"
    path.write_text(
        json.dumps({"schema_version": 2, "restored": False, "snapshot": None}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid window state"):
        WindowStateStore(path).load_pending()


def test_boolean_schema_version_is_rejected(tmp_path) -> None:
    path = tmp_path / "window.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": True,
                "restored": False,
                "snapshot": {
                    "window_id": 41,
                    "pid": 902,
                    "bounds": {"x": 10, "y": 20, "width": 1280, "height": 720},
                    "previous_frontmost_bundle_id": None,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid window state"):
        WindowStateStore(path).load_pending()


def test_invalid_bounds_are_rejected(tmp_path) -> None:
    path = tmp_path / "window.json"
    store = WindowStateStore(path)

    with pytest.raises(ValueError, match="positive"):
        store.save(WindowSnapshot(41, 902, Bounds(10, 20, 0, 720), None))


def test_save_and_mark_restored_leave_no_temporary_file(tmp_path) -> None:
    path = tmp_path / "nested" / "window.json"
    store = WindowStateStore(path)
    snapshot = WindowSnapshot(41, 902, Bounds(10, 20, 1280, 720), None)

    store.save(snapshot)
    store.mark_restored()

    assert path.exists()
    assert not path.with_name(f"{path.name}.tmp").exists()
