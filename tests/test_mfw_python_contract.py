import tomllib
from pathlib import Path

from tests.mfw.fakes import FakeContext


def test_python_floor_and_ruff_target_are_312():
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.12,<3.15"
    assert data["tool"]["ruff"]["target-version"] == "py312"


def test_fake_context_exposes_only_current_controller():
    context = FakeContext()
    assert context.tasker.controller is context.controller
    assert not hasattr(context, "controller_env")
