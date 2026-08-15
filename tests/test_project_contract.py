import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_pinned_contract_and_ignored_runtime_paths() -> None:
    requirements = (ROOT / "requirements.lock").read_text()
    assert requirements.splitlines() == [
        "MaaFw==5.12.2",
        "Pillow==12.1.1",
        "pyobjc-core==12.2.1",
        "pyobjc-framework-Cocoa==12.2.1",
        "pyobjc-framework-ApplicationServices==12.2.1",
        "pyobjc-framework-Quartz==12.2.1",
        "pytest==9.1.1",
        "ruff==0.16.0",
    ]
    manifest = json.loads((ROOT / "runtime-manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert {item["id"] for item in manifest["artifacts"]} == {"maafw", "mfa"}
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for path in (
        ".venv/",
        "install/",
        "downloads/",
        "debug/",
        "diagnostics/",
        ".mja-state/",
    ):
        assert path in ignored


def test_android_pipeline_uses_verified_live_1280x720_contract() -> None:
    calibration = json.loads(
        (ROOT / "assets/resource_android/calibration.json").read_text()
    )
    assert calibration["template_contract"]["profile"] == "android_live_capture"
    assert calibration["template_contract"]["capture_size"] == [1280, 720]
    assert calibration["template_contract"]["status"] == "live_capture_verified"
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/mail_smoke_test.json").read_text()
    )
    for name, node in pipeline.items():
        x, y, width, height = node["roi"]
        assert 0 <= x and 0 <= y and width > 0 and height > 0, name
        assert x + width <= 1280 and y + height <= 720, name
