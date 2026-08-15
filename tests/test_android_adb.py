from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from agent.android.adb import AdbDevice
from agent.android.config import AndroidConfig
from agent.android.sdk import SdkPaths
from agent.errors import ErrorCode, MJAError


def _sdk(tmp_path: Path) -> SdkPaths:
    tools = []
    for name in ("sdkmanager", "avdmanager", "adb", "emulator"):
        path = tmp_path / name
        path.write_text("", encoding="utf-8")
        path.chmod(0o755)
        tools.append(path)
    return SdkPaths(tmp_path, *tools)


def test_wait_ready_requires_only_configured_device_and_canonical_size(tmp_path: Path) -> None:
    outputs = iter([
        "List of devices attached\nemulator-5556\tdevice\n",
        "1\n",
        "Physical size: 1280x720\n",
        "35\n",
    ])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
        sleeper=lambda _: None,
    )
    info = device.wait_ready(timeout_seconds=1)

    assert (info.width, info.height) == (1280, 720)


def test_wait_ready_rejects_wrong_size(tmp_path: Path) -> None:
    outputs = iter([
        "List of devices attached\nemulator-5556\tdevice\n",
        "1\n",
        "Physical size: 1051x820\n",
    ])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
        sleeper=lambda _: None,
    )
    with pytest.raises(RuntimeError, match="1280x720"):
        device.wait_ready(timeout_seconds=1)


def test_ensure_selinux_mode_restarts_adbd_and_verifies_permissive(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    enforce_states = iter(["Enforcing\n", "Permissive\n"])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        calls.append(argv)
        if argv[-2:] == ["shell", "getenforce"]:
            return SimpleNamespace(stdout=next(enforce_states), stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
        sleeper=lambda _: None,
    )

    assert device.ensure_selinux_mode() == "permissive"
    assert calls[0][-2:] == ["shell", "getenforce"]
    assert calls[1][-1] == "root"
    assert calls[2][-3:] == ["shell", "id", "-u"]
    assert calls[3][-2:] == ["setenforce", "0"]
    assert calls[4][-2:] == ["shell", "getenforce"]


def test_phantom_process_monitor_is_disabled_and_verified(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    states = iter(["null\n", "false\n"])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        calls.append(argv)
        if argv[-5:] == [
            "shell",
            "settings",
            "get",
            "global",
            "settings_enable_monitor_phantom_procs",
        ]:
            return SimpleNamespace(stdout=next(states), stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
    )

    assert device.ensure_phantom_process_monitor_disabled() == "false"
    assert calls[1][-6:] == [
        "shell",
        "settings",
        "put",
        "global",
        "settings_enable_monitor_phantom_procs",
        "false",
    ]
    assert calls[2][-5:] == calls[0][-5:]


def test_phantom_process_monitor_failure_is_not_silently_ignored(tmp_path: Path) -> None:
    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        output = "true\n" if argv[-3:-1] == ["get", "global"] else ""
        return SimpleNamespace(stdout=output, stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
    )

    with pytest.raises(MJAError) as exc_info:
        device.ensure_phantom_process_monitor_disabled()
    assert exc_info.value.code is ErrorCode.ANDROID_SHARED_RUNTIME_FAILURE


def test_screencap_writes_and_validates_png(tmp_path: Path) -> None:
    image_path = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (1, 2, 3)).save(image_path)
    data = image_path.read_bytes()

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=data, stderr=b"", returncode=0)

    target = tmp_path / "capture.png"
    device = AdbDevice(AndroidConfig(sdk_root=tmp_path / "sdk"), _sdk(tmp_path), runner=runner)

    assert device.screencap(target) == (1280, 720)
    assert target.is_file()


def test_interactive_ready_requires_title_or_home_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import agent.android.adb as module

    frame = Image.new("RGB", (1280, 720), (18, 22, 30))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((560, 638, 650, 660), fill=(90, 100, 120))
    draw.line((560, 682, 740, 638), fill=(130, 140, 160), width=2)
    template = tmp_path / "title.png"
    frame.crop((560, 638, 740, 683)).save(template)
    data = tmp_path / "frame.png"
    frame.save(data)
    monkeypatch.setattr(
        module,
        "_INTERACTIVE_READY_TEMPLATES",
        (("title", template, (560, 638, 180, 45), 0.99),),
    )

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=data.read_bytes(), stderr=b"", returncode=0)

    device = AdbDevice(AndroidConfig(sdk_root=tmp_path / "sdk"), _sdk(tmp_path), runner=runner)

    assert device.interactive_ready()

    frame = Image.new("RGB", (1280, 720), (60, 60, 60))
    frame.save(data)
    assert device.interactive_ready()

    frame = Image.new("RGB", (1280, 720), (1, 2, 3))
    frame.save(data)
    assert not device.interactive_ready()


def test_foreground_package_falls_back_to_resumed_activity_on_android_35(
    tmp_path: Path,
) -> None:
    window_dump = """
    Window #0 Window{123 u0 StatusBar}:
    Window #1 Window{456 u0 com.example.game/com.example.game.MainActivity}:
    mTopFocusedDisplayId=0
    """
    activity_dump = """
    topResumedActivity=ActivityRecord{abc u0 com.example.game/.MainActivity t3}
    ResumedActivity: ActivityRecord{abc u0 com.example.game/.MainActivity t3}
    """
    outputs = iter([window_dump, activity_dump])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
    )

    assert device.foreground_package() == "com.example.game"


def test_restart_force_stops_existing_process_before_starting_it(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        calls.append(argv)
        if argv[-4:] == ["package", "resolve-activity", "--brief", "com.example.game"]:
            return SimpleNamespace(
                stdout="priority=0\ncom.example.game/.MainActivity\n",
                stderr="",
                returncode=0,
            )
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
    )

    device.restart("com.example.game")

    assert calls == [
        [
            str(tmp_path / "adb"),
            "-s",
            "emulator-5556",
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "com.example.game",
        ],
        [
            str(tmp_path / "adb"),
            "-s",
            "emulator-5556",
            "shell",
            "am",
            "force-stop",
            "com.example.game",
        ],
        [
            str(tmp_path / "adb"),
            "-s",
            "emulator-5556",
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            "com.example.game/.MainActivity",
        ],
    ]


def test_start_app_matches_maa_adb_start_app_command(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
    )

    device.start_app("com.example.game")

    assert calls == [
        [
            str(tmp_path / "adb"),
            "-s",
            "emulator-5556",
            "shell",
            "monkey",
            "-p",
            "com.example.game",
            "--pct-syskeys",
            "0",
            "1",
        ]
    ]


def test_ui_xml_retries_a_transient_uiautomator_dump_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    attempts = {"dump": 0}
    sleeps: list[float] = []

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        calls.append(argv)
        if argv[-3:] == ["uiautomator", "dump", "/sdcard/window.xml"]:
            attempts["dump"] += 1
            if attempts["dump"] == 1:
                raise subprocess.CalledProcessError(1, argv)
            return SimpleNamespace(stdout="UI dump written to /sdcard/window.xml", stderr="")
        return SimpleNamespace(stdout="<hierarchy />", stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=runner,
        sleeper=sleeps.append,
    )

    assert device.ui_xml() == "<hierarchy />"
    assert attempts["dump"] == 2
    assert sleeps == [1.0]


def test_runtime_health_rejects_low_userdata_space(tmp_path: Path) -> None:
    outputs = iter(["/dev/block/data 12223704 12000000 223704 99% /data/user/0\n"])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
    )

    with pytest.raises(RuntimeError) as exc_info:
        device.require_runtime_health()
    assert exc_info.value.code is ErrorCode.ANDROID_STORAGE_LOW


def test_runtime_health_rejects_network_probe_failure(tmp_path: Path) -> None:
    outputs = iter(["/dev/block/data 12223704 5000000 7223704 41% /data/user/0\n"])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        if argv[-1] == "223.5.5.5":
            raise subprocess.CalledProcessError(1, argv)
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
    )

    with pytest.raises(RuntimeError) as exc_info:
        device.require_runtime_health()
    assert exc_info.value.code is ErrorCode.ANDROID_NETWORK_UNAVAILABLE


def test_runtime_health_retries_transient_network_probe_failure(tmp_path: Path) -> None:
    image_path = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (40, 40, 40)).save(image_path)
    outputs = iter([
        "/dev/block/data 12223704 5000000 7223704 41% /data/user/0\n",
        "1 packets transmitted, 1 received, 0% packet loss\n",
        "mCurrentFocus=Window{abc u0 com.example.game/.MainActivity}\n",
        image_path.read_bytes(),
    ])
    attempts = 0
    sleeps: list[float] = []

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        nonlocal attempts
        if argv[-1] == "223.5.5.5":
            attempts += 1
            if attempts < 2:
                raise subprocess.CalledProcessError(1, argv)
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
        sleeper=sleeps.append,
    )

    device.require_runtime_health()
    assert attempts == 2
    assert sleeps == [1.0]


def test_runtime_health_rejects_non_game_foreground(tmp_path: Path) -> None:
    outputs = iter([
        "/dev/block/data 12223704 5000000 7223704 41% /data/user/0\n",
        "1 packets transmitted, 1 received, 0% packet loss\n",
        "mCurrentFocus=Window{abc u0 com.android.settings/.Settings}\n",
        "",
    ])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(outputs), stderr="", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
    )

    with pytest.raises(RuntimeError) as exc_info:
        device.require_runtime_health()
    assert exc_info.value.code is ErrorCode.ANDROID_GAME_NOT_FOREGROUND


def test_runtime_health_rejects_wrong_screenshot_size(tmp_path: Path) -> None:
    image_path = tmp_path / "source.png"
    Image.new("RGB", (1, 1), (1, 2, 3)).save(image_path)
    outputs = iter([
        "/dev/block/data 12223704 5000000 7223704 41% /data/user/0\n",
        "1 packets transmitted, 1 received, 0% packet loss\n",
        "mCurrentFocus=Window{abc u0 com.example.game/.MainActivity}\n",
        image_path.read_bytes(),
    ])

    def runner(argv: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(outputs), stderr=b"", returncode=0)

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=runner,
    )

    with pytest.raises(RuntimeError, match="1280x720"):
        device.require_runtime_health()


def test_memory_info_parses_guest_available_and_swap(tmp_path: Path) -> None:
    output = """MemTotal:        4194304 kB
MemAvailable:    1048576 kB
SwapTotal:       2097152 kB
SwapFree:        1572864 kB
"""

    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=lambda *_args, **_kwargs: SimpleNamespace(stdout=output, stderr=""),
    )

    info = device.memory_info()

    assert info.total_bytes == 4 * 1024 * 1024 * 1024
    assert info.available_bytes == 1024 * 1024 * 1024
    assert info.swap_free_bytes == 1536 * 1024 * 1024


def test_require_memory_health_rejects_low_guest_memory(tmp_path: Path) -> None:
    output = """MemTotal: 2621440 kB
MemAvailable: 128000 kB
SwapTotal: 1898988 kB
SwapFree: 64000 kB
"""
    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=lambda *_args, **_kwargs: SimpleNamespace(stdout=output, stderr=""),
    )

    with pytest.raises(RuntimeError) as exc_info:
        device.require_memory_health()

    assert exc_info.value.code is ErrorCode.ANDROID_MEMORY_LOW


def test_require_game_process_reports_process_death(tmp_path: Path) -> None:
    device = AdbDevice(
        AndroidConfig(sdk_root=tmp_path / "sdk", package_name="com.example.game"),
        _sdk(tmp_path),
        runner=lambda *_args, **_kwargs: SimpleNamespace(stdout="", stderr=""),
    )

    with pytest.raises(RuntimeError) as exc_info:
        device.require_game_process()

    assert exc_info.value.code is ErrorCode.ANDROID_GAME_PROCESS_DIED
