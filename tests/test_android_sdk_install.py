from __future__ import annotations

from pathlib import Path

from agent.android.config import AndroidConfig
from agent.android.sdk import AndroidSdk


def test_install_mode_can_install_components_before_adb_exists(tmp_path: Path) -> None:
    root = tmp_path / "sdk"
    manager = root / "cmdline-tools/latest/bin/sdkmanager"
    manager.parent.mkdir(parents=True)
    manager.write_text("", encoding="utf-8")
    manager.chmod(0o755)
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> object:
        calls.append(argv)
        return object()

    sdk = AndroidSdk(AndroidConfig(sdk_root=root), runner=runner)
    sdk._install_components_from_toolchain()

    assert calls
    assert str(manager) == calls[0][0]
