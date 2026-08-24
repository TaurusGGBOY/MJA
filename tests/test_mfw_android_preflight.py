from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.android.config import AndroidConfig
from tools.mfw_android_preflight import run_preflight


def test_mfw_preflight_applies_shared_runtime_contract_before_game_start(
    tmp_path: Path,
) -> None:
    events: list[str] = []

    class FakeSdk:
        def __init__(self, config: AndroidConfig) -> None:
            assert config.sdk_root == tmp_path / "sdk"

        def ensure(self):
            events.append("sdk")
            return SimpleNamespace(adb=tmp_path / "adb")

    class FakeDevice:
        def __init__(self, config: AndroidConfig, paths) -> None:
            assert config.serial == "emulator-5556"
            assert paths.adb == tmp_path / "adb"

        def wait_ready(self):
            events.append("ready")
            return SimpleNamespace(width=1280, height=720, sdk_version="35")

        def ensure_phantom_process_monitor_disabled(self):
            events.append("phantom_monitor")
            return "false"

        def ensure_selinux_mode(self, mode: str):
            assert mode == "permissive"
            events.append("selinux")
            return "permissive"

    result = run_preflight(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        sdk_factory=FakeSdk,
        device_factory=FakeDevice,
        emulator_contract=lambda _config: {
            "emulator_pid": "1234",
            "qemu_gpu_backend": "host",
            "vulkan_queue_submit_with_commands": "disabled",
            "qemu_command": "qemu-system-aarch64 -gpu host",
            "avd_gpu_enabled": "yes",
            "avd_gpu_mode": "host",
        },
    )

    assert events == ["sdk", "ready", "phantom_monitor", "selinux"]
    assert result == {
        "serial": "emulator-5556",
        "display": "1280x720",
        "sdk_version": "35",
        "phantom_process_monitor": "false",
        "selinux": "permissive",
        "emulator_pid": "1234",
        "qemu_gpu_backend": "host",
        "vulkan_queue_submit_with_commands": "disabled",
        "qemu_command": "qemu-system-aarch64 -gpu host",
        "avd_gpu_enabled": "yes",
        "avd_gpu_mode": "host",
    }
