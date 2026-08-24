from __future__ import annotations

import json
from pathlib import Path

from agent.android.config import AndroidConfig


def test_checked_in_android_config_is_canonical() -> None:
    path = Path("config/android.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = AndroidConfig.load(path)

    assert payload["avd_name"] == "mja-api35-apis"
    assert payload["system_image_package"] == "system-images;android-35;google_apis;arm64-v8a"
    assert payload["selinux_mode"] == "permissive"
    assert payload["data_partition_size_gb"] >= 12
    assert config.display_size == (1280, 720)
    assert config.sdk_root == (Path("install/android-sdk").resolve())
