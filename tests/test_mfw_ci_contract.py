from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/mfw-check.yml"


def test_ci_checks_python_resource_and_isolated_candidate() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'python-version: ["3.12", "3.14"]' in workflow
    assert "tools/check_mfw_resources.py" in workflow
    assert "tools/load_mfw_resource.py" in workflow
    assert "tools/mfw_install.py" in workflow
    assert "install/ci-candidate" in workflow
    assert "candidate-not-releasable" in workflow
    assert "uv.lock" not in workflow


def test_development_doc_keeps_live_release_gate_explicit() -> None:
    document = (ROOT / "docs/mfw-development.md").read_text(encoding="utf-8")

    assert "mfw_profile.py" in document
    assert "failure-contract.json" in document
    assert "candidate-not-releasable" in document
    assert "MacOS" in document
    assert "手动启动" in document
