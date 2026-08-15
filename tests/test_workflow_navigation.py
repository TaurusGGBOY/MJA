import json

import pytest

from agent.workflows.navigation import PAGE_MARKERS, load_fixture_manifest, recognize_fixture
from tests.workflows.support import write_fixture_manifest


def test_shared_page_markers_are_unique():
    assert len(PAGE_MARKERS) == 18
    assert len(set(PAGE_MARKERS.values())) == len(PAGE_MARKERS)


def test_fixture_loader_rejects_unknown_keys_and_old_sizes(tmp_path):
    path = write_fixture_manifest(tmp_path, [{"name": "home", "image": "frame.png"}])
    assert recognize_fixture(load_fixture_manifest(path), "home").frame.size == (1280, 720)

    payload = json.loads(path.read_text())
    payload["unexpected"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unknown keys"):
        load_fixture_manifest(path)


def test_fixture_loader_rejects_legacy_capture_dimensions(tmp_path):
    path = write_fixture_manifest(tmp_path, [{"name": "home", "image": "frame.png"}])
    payload = json.loads(path.read_text())
    payload["capture_size"] = [923, 720]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="1280x720"):
        load_fixture_manifest(path)
