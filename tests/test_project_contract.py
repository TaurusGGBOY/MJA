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
        "pyobjc-framework-Quartz==12.2.1",
        "pytest==9.1.1",
        "ruff==0.16.0",
    ]
    manifest = json.loads((ROOT / "runtime-manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert {item["id"] for item in manifest["artifacts"]} == {"maafw", "mfa"}
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for path in (".venv/", "install/", "downloads/", "debug/", ".mja-state/"):
        assert path in ignored
