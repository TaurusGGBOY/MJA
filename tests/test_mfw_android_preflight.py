from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.android.config import AndroidConfig
from agent.errors import ErrorCode, MJAError
from tools.mfw_android_preflight import run_preflight


@pytest.mark.parametrize("transient_failures", [0, 1, 2])
def test_mfw_preflight_applies_shared_runtime_contract_before_game_start(
    tmp_path: Path,
    transient_failures: int,
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

        def shell(self, *args):
            assert args == ("dumpsys", "connectivity")
            return "Active default network: 100"

        def ensure_phantom_process_monitor_disabled(self):
            events.append("phantom_monitor")
            if events.count("phantom_monitor") <= transient_failures:
                raise MJAError(
                    ErrorCode.ADB_DEVICE_FAILED, "settings service temporarily unavailable"
                )
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

    assert events == ["sdk", "ready"] + ["phantom_monitor"] * (1 + transient_failures) + ["selinux"]
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


@pytest.mark.parametrize(
    "code,attempts",
    [(ErrorCode.ADB_DEVICE_FAILED, 3), (ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED, 1)],
)
def test_preflight_probe_preserves_persistent_and_contract_failures(code, attempts):
    from tools.mfw_android_preflight import _retry_preflight_probe

    calls = []
    failure = MJAError(code, "probe unavailable")

    def probe():
        calls.append(1)
        raise failure

    with pytest.raises(MJAError) as exc:
        _retry_preflight_probe(probe)
    assert exc.value is failure
    assert len(calls) == attempts


@pytest.mark.parametrize("connected", [True, False])
def test_missing_network_is_reconnected_or_fails_before_game_start(monkeypatch, connected):
    from tools.mfw_android_preflight import ensure_default_network

    monkeypatch.setattr("tools.mfw_android_preflight.sleep", lambda _: None)
    commands = []

    def shell(*args):
        commands.append(args)
        if args == ("dumpsys", "connectivity"):
            return "Active default network: 100" if connected and len(commands) > 3 else (
                "Active default network: none"
            )
        if args == ("cmd", "wifi", "list-scan-results"):
            return "00:13:10:85:fe:01 2447 -50 0.0 AndroidWifi [ESS]"
        return ""

    if connected:
        ensure_default_network(SimpleNamespace(shell=shell))
    else:
        with pytest.raises(MJAError, match="no default network"):
            ensure_default_network(SimpleNamespace(shell=shell))
    assert commands.count(("cmd", "wifi", "connect-network", "AndroidWifi", "open")) == 1


def test_network_scan_can_become_ready_after_framework_boot(monkeypatch):
    from tools.mfw_android_preflight import ensure_default_network

    monkeypatch.setattr("tools.mfw_android_preflight.sleep", lambda _: None)
    scans = 0
    connections = 0

    def shell(*args):
        nonlocal scans, connections
        if args == ("dumpsys", "connectivity"):
            return f"Active default network: {100 if connections else 'none'}"
        if args == ("cmd", "wifi", "list-scan-results"):
            scans += 1
            return "AndroidWifi [ESS]" if scans >= 3 else ""
        if args == ("cmd", "wifi", "connect-network", "AndroidWifi", "open"):
            connections += 1
        return ""

    ensure_default_network(SimpleNamespace(shell=shell))
    assert scans == 3
    assert connections == 1
