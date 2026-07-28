from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from agent.errors import ErrorCode, MJAError
from tools.verify_macos_controller import FALLBACK_MARKER, main, probe_controller


class FakeJob:
    succeeded = True

    def __init__(self, result=None) -> None:
        self.result = result

    def wait(self) -> FakeJob:
        return self

    def get(self):
        return self.result


class FakeController:
    def __init__(self, frames=None, connection_succeeded: bool = True) -> None:
        self.frames = iter(frames or ())
        self.connection_succeeded = connection_succeeded
        self.post_connection_calls = 0
        self.post_screencap_calls = 0
        self.short_side = None
        self.actions: list[str] = []

    def post_connection(self) -> FakeJob:
        self.post_connection_calls += 1
        job = FakeJob()
        job.succeeded = self.connection_succeeded
        return job

    def set_screenshot_target_short_side(self, short_side: int) -> bool:
        self.short_side = short_side
        return True

    def post_screencap(self) -> FakeJob:
        self.post_screencap_calls += 1
        return FakeJob(next(self.frames))

    def click(self, *args, **kwargs) -> None:
        self.actions.append("click")

    def swipe(self, *args, **kwargs) -> None:
        self.actions.append("swipe")

    def key_down(self, *args, **kwargs) -> None:
        self.actions.append("key_down")

    def key_up(self, *args, **kwargs) -> None:
        self.actions.append("key_up")

    def start(self, *args, **kwargs) -> None:
        self.actions.append("start")


def _frame(width: int = 923, height: int = 720, color: str = "navy") -> Image.Image:
    image = Image.new("RGB", (width, height), color)
    image.putpixel((0, 0), (255, 255, 255))
    return image


def _factory(controller: FakeController):
    return lambda window_id: controller


def test_probe_captures_50_stable_nonempty_frames_without_input(tmp_path: Path) -> None:
    controller = FakeController([_frame() for _ in range(50)])
    log_path = tmp_path / "maa.log"
    log_path.write_text("capture started\n", encoding="utf-8")

    result = probe_controller(42, controller_factory=_factory(controller), log_path=log_path)

    assert result.frames == 50
    assert result.nonempty_frames == 50
    assert (result.width, result.height) == (923, 720)
    assert result.backend == "ScreenCaptureKit"
    assert controller.post_connection_calls == 1
    assert controller.post_screencap_calls == 50
    assert controller.short_side == 720
    assert controller.actions == []


def test_probe_rejects_first_empty_frame() -> None:
    controller = FakeController([None] + [_frame() for _ in range(49)])

    with pytest.raises(MJAError) as raised:
        probe_controller(42, controller_factory=_factory(controller))

    assert raised.value.code is ErrorCode.CONTROLLER_PROBE_FAILED
    assert controller.post_screencap_calls == 1


def test_probe_rejects_dimension_drift() -> None:
    controller = FakeController([_frame() for _ in range(3)] + [_frame(922)])

    with pytest.raises(MJAError, match="dimensions changed") as raised:
        probe_controller(42, frames=4, controller_factory=_factory(controller))

    assert raised.value.code is ErrorCode.CONTROLLER_PROBE_FAILED
    assert controller.post_screencap_calls == 4


def test_probe_rejects_a_frame_that_ignores_the_720_short_side() -> None:
    controller = FakeController([_frame(1280, 800)])

    with pytest.raises(MJAError, match="short side is not 720"):
        probe_controller(42, controller_factory=_factory(controller))


def test_probe_maps_invalid_window_to_stable_error_code() -> None:
    with pytest.raises(MJAError) as raised:
        probe_controller(0, controller_factory=lambda window_id: None)

    assert raised.value.code is ErrorCode.WINDOW_NOT_FOUND


def test_probe_maps_connection_failure_to_stable_error_code() -> None:
    controller = FakeController([_frame()], connection_succeeded=False)

    with pytest.raises(MJAError) as raised:
        probe_controller(42, controller_factory=_factory(controller))

    assert raised.value.code is ErrorCode.CONTROLLER_CONNECT_FAILED
    assert controller.post_screencap_calls == 0


def test_probe_reports_one_fallback_transition(tmp_path: Path) -> None:
    log_path = tmp_path / "maa.log"
    log_path.write_text(f"initial failure\n{FALLBACK_MARKER}\n", encoding="utf-8")
    controller = FakeController([_frame() for _ in range(2)])

    result = probe_controller(
        42,
        frames=2,
        controller_factory=_factory(controller),
        log_path=log_path,
    )

    assert result.backend == "CoreGraphicsRegion"


def test_probe_rejects_repeated_transition(tmp_path: Path) -> None:
    log_path = tmp_path / "maa.log"
    log_path.write_text(f"{FALLBACK_MARKER}\n{FALLBACK_MARKER}\n", encoding="utf-8")
    controller = FakeController([_frame()])

    with pytest.raises(MJAError, match="more than once") as raised:
        probe_controller(42, frames=1, controller_factory=_factory(controller), log_path=log_path)

    assert raised.value.code is ErrorCode.CONTROLLER_PROBE_FAILED


def test_probe_rejects_screen_capture_kit_retry_after_fallback(tmp_path: Path) -> None:
    log_path = tmp_path / "maa.log"
    log_path.write_text(
        f"{FALLBACK_MARKER}\nScreenCaptureKit capture failed again\n",
        encoding="utf-8",
    )
    controller = FakeController([_frame()])

    with pytest.raises(MJAError, match="retried after") as raised:
        probe_controller(42, frames=1, controller_factory=_factory(controller), log_path=log_path)

    assert raised.value.code is ErrorCode.CONTROLLER_PROBE_FAILED


def test_cli_writes_success_as_json_stdout(monkeypatch, capsys, tmp_path: Path) -> None:
    controller = FakeController([_frame()])
    monkeypatch.setattr(
        "tools.verify_macos_controller._default_controller_factory",
        lambda window_id: controller,
    )

    log_path = tmp_path / "maa.log"
    log_path.write_text("capture started\n", encoding="utf-8")
    assert main(["--window-id", "42", "--frames", "1", "--log-path", str(log_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["window_id"] == 42
    assert payload["frames"] == 1


def test_cli_evidence_root_writes_result_and_uses_log(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    controller = FakeController([_frame()])
    monkeypatch.setattr(
        "tools.verify_macos_controller._default_controller_factory",
        lambda window_id: controller,
    )
    evidence = tmp_path / "evidence"
    (evidence / "maafw.log").parent.mkdir(parents=True)
    (evidence / "maafw.log").write_text("capture started\n", encoding="utf-8")

    assert main(["--window-id", "42", "--frames", "1", "--evidence-root", str(evidence)]) == 0

    output = capsys.readouterr().out
    assert json.loads(output)["backend"] == "ScreenCaptureKit"
    assert (evidence / "probe-result.json").is_file()


def test_cli_writes_stable_failure_as_json_stdout(capsys) -> None:
    assert main(["--window-id", "0"]) == 3

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "code": ErrorCode.WINDOW_NOT_FOUND.value,
        "message": "window_id must be a positive integer",
    }
