from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from tools.verify_install import verify_install


def test_missing_required_file_is_reported(tmp_path: Path) -> None:
    errors = verify_install(tmp_path, run_runtime_checks=False)
    assert "missing interface.json" in errors
    assert "missing .venv/bin/python3" in errors
    assert "missing MaaPiCli" in errors


def _make_complete_install(root: Path) -> None:
    (root / ".venv/bin").mkdir(parents=True)
    python = root / ".venv/bin/python3"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(python.stat().st_mode | os.X_OK)
    (root / "MaaPiCli").write_text("binary")
    (root / "MaaPiCli").chmod(0o755)
    (root / "MFAAvalonia.app/Contents/MacOS").mkdir(parents=True)
    (root / "MFAAvalonia.app/Contents/MacOS/MFAAvalonia").write_text("binary")
    (root / "interface.json").write_text(json.dumps({"resource": "resource"}))
    (root / "resource").mkdir()
    (root / "agent").mkdir()
    (root / "runtime/maafw").mkdir(parents=True)
    (root / "runtime/mfa").mkdir(parents=True)
    (root / "runtime/maafw/VERSION").write_text("5.12.2\n")
    (root / "runtime/mfa/VERSION").write_text("2.13.0-beta.5\n")


def test_complete_install_passes_static_checks(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    result = verify_install(
        tmp_path,
        run_runtime_checks=False,
        cliclick_path=tmp_path / "cliclick",
    )
    assert result == []


def test_interface_template_reference_is_reported(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    (tmp_path / "interface.json").write_text(
        json.dumps({"resource": "resource", "pipeline": "resource/pipeline.json"})
    )
    assert "missing resource/pipeline.json" in verify_install(
        tmp_path,
        run_runtime_checks=False,
        cliclick_path=tmp_path / "cliclick",
    )


def test_pipeline_forbids_unapproved_input_actions(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    pipeline = tmp_path / "resource/pipeline.json"
    pipeline.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_text(json.dumps({"click": {"action": "Click"}}))

    errors = verify_install(
        tmp_path,
        run_runtime_checks=False,
        cliclick_path=tmp_path / "cliclick",
    )
    assert any("forbidden input action" in item for item in errors)


def test_runtime_checks_use_injected_runner(tmp_path: Path) -> None:
    _make_complete_install(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    cliclick = tmp_path / "cliclick"
    cliclick.write_text("binary")
    cliclick.chmod(0o755)
    assert verify_install(tmp_path, runner=runner, cliclick_path=cliclick) == []
    assert any("import maa" in " ".join(argv) for argv in calls)
