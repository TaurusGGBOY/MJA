from __future__ import annotations

from pathlib import Path

from PIL import Image

from tools.capture_templates import capture_android_profile


class FakeDevice:
    def wait_ready(self) -> None:
        pass

    def screencap(self, destination: Path) -> tuple[int, int]:
        Image.new("RGB", (1280, 720), "navy").save(destination)
        return (1280, 720)


def test_capture_android_profile_uses_device_screenshot_without_input(tmp_path: Path) -> None:
    outputs = capture_android_profile("home", FakeDevice(), tmp_path / "image")

    assert set(outputs) == {"home_marker", "panel_open"}
    assert Image.open(outputs["home_marker"]).size == (240, 110)
    assert Image.open(outputs["panel_open"]).size == (80, 100)
    assert not (tmp_path / "image/home/.capture-source.png").exists()
