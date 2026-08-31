from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_development_doc_keeps_live_release_gate_explicit() -> None:
    document = (ROOT / "docs/mfw-development.md").read_text(encoding="utf-8")

    assert "mfw_profile.py" in document
    assert "failure-contract.json" in document
    assert "candidate-not-releasable" in document
    assert "MacOS" in document
    assert "手动启动" in document
