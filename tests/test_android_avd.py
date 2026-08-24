from __future__ import annotations

from pathlib import Path

from agent.android.avd import AndroidAvd
from agent.android.config import AndroidConfig
from agent.android.sdk import SdkPaths


def _sdk(tmp_path: Path) -> SdkPaths:
    paths = []
    for name in ("sdkmanager", "avdmanager", "adb", "emulator"):
        path = tmp_path / name
        path.write_text("", encoding="utf-8")
        path.chmod(0o755)
        paths.append(path)
    return SdkPaths(tmp_path, *paths)


def test_existing_avd_receives_contract_without_wipe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path / ".android" / "avd"))
    config = AndroidConfig(avd_name="mja-test", sdk_root=tmp_path / "sdk")
    avd_root = tmp_path / ".android" / "avd" / "mja-test.avd"
    avd_root.mkdir(parents=True)
    (avd_root / "config.ini").write_text(
        "avd.ini.displayname=mja-test\nhw.lcd.width=800\n", encoding="utf-8"
    )

    avd = AndroidAvd(config, _sdk(tmp_path), runner=lambda *_args, **_kwargs: object())
    path = avd.ensure()

    assert path == avd_root / "config.ini"
    text = path.read_text(encoding="utf-8")
    assert "hw.lcd.width=1280" in text
    assert "hw.lcd.height=720" in text
    assert "hw.initialOrientation=landscape" in text
    assert "hw.gpu.enabled=yes" in text
    assert "hw.gpu.mode=host" in text
    assert "hw.ramSize=6144M" in text
    assert "disk.dataPartition.size=12G" in text


def test_configured_avd_home_overrides_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path / "wrong" / "avd"))
    configured_home = tmp_path / "external" / ".android" / "avd"
    avd_root = configured_home / "mja-test.avd"
    avd_root.mkdir(parents=True)
    (avd_root / "config.ini").write_text("", encoding="utf-8")

    avd = AndroidAvd(
        AndroidConfig(
            avd_name="mja-test",
            sdk_root=tmp_path / "sdk",
            avd_home=configured_home,
        ),
        _sdk(tmp_path),
        runner=lambda *_args, **_kwargs: object(),
    )

    assert avd.avd_root == avd_root
    assert avd.ensure() == avd_root / "config.ini"


def test_create_uses_configured_non_play_system_image(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path / ".android" / "avd"))
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> object:
        calls.append(argv)
        avd_root = tmp_path / ".android" / "avd" / "mja-apis.avd"
        avd_root.mkdir(parents=True, exist_ok=True)
        (avd_root / "config.ini").write_text("", encoding="utf-8")
        return object()

    config = AndroidConfig(
        avd_name="mja-apis",
        system_image_package="system-images;android-35;google_apis;arm64-v8a",
        sdk_root=tmp_path / "sdk",
    )
    AndroidAvd(config, _sdk(tmp_path), runner=runner).ensure()

    assert calls
    assert "--package" in calls[0]
    assert "system-images;android-35;google_apis;arm64-v8a" in calls[0]
    assert "google_apis_playstore" not in calls[0]


def test_start_uses_fixed_port_and_no_wipe_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path / ".android" / "avd"))
    avd_root = tmp_path / ".android" / "avd" / "mja-api35-apis.avd"
    avd_root.mkdir(parents=True)
    (avd_root / "config.ini").write_text("", encoding="utf-8")
    calls: list[list[str]] = []
    popen_options: dict[str, object] = {}

    def popen(argv: list[str], **options: object) -> object:
        calls.append(argv)
        popen_options.update(options)
        return object()

    avd = AndroidAvd(
        AndroidConfig(sdk_root=tmp_path / "sdk"),
        _sdk(tmp_path),
        runner=lambda *_args, **_kwargs: object(),
        popen=popen,
    )
    avd.start()

    assert calls
    assert "-port" in calls[0]
    assert "5556" in calls[0]
    assert "-wipe-data" not in calls[0]
    assert "-no-window" not in calls[0]
    assert "-noaudio" in calls[0]
    assert calls[0][calls[0].index("-gpu") + 1] == "host"
    assert calls[0][calls[0].index("-feature") + 1] == "-VulkanQueueSubmitWithCommands"
    assert calls[0][calls[0].index("-selinux") + 1] == "permissive"
    assert calls[0][calls[0].index("-crash-report-mode") + 1] == "never"
    assert "-no-metrics" in calls[0]
    assert calls[0][calls[0].index("-memory") + 1] == "6144"
    assert popen_options["start_new_session"] is True


def test_start_exports_configured_avd_home(tmp_path: Path) -> None:
    configured_home = tmp_path / "external" / ".android" / "avd"
    avd_root = configured_home / "mja-api35-apis.avd"
    avd_root.mkdir(parents=True)
    (avd_root / "config.ini").write_text("", encoding="utf-8")
    popen_options: dict[str, object] = {}

    def popen(_argv: list[str], **options: object) -> object:
        popen_options.update(options)
        return object()

    avd = AndroidAvd(
        AndroidConfig(sdk_root=tmp_path / "sdk", avd_home=configured_home),
        _sdk(tmp_path),
        runner=lambda *_args, **_kwargs: object(),
        popen=popen,
    )
    avd.start()

    environment = popen_options["env"]
    assert isinstance(environment, dict)
    assert environment["ANDROID_AVD_HOME"] == str(configured_home)
    assert environment["ANDROID_USER_HOME"] == str(configured_home.parent)
