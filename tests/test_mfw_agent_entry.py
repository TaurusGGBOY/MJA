from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest


def test_agent_entry_imports_only_narrow_registration_modules():
    source = Path("agent/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "agent.custom.action.guarded_input" in imported
    assert "agent.custom.action.jianlin_planner" in imported
    assert "agent.custom.action.task_lifecycle" in imported
    assert "agent.custom.action.convergence_lifecycle" in imported
    assert "agent.custom.action.runtime_health" in imported
    assert "agent.custom.action.restart_game" in imported
    assert ".".join(("agent", "workflows", "aggregate")) not in imported
    assert ".".join(("agent", "workflows", "maa_android")) not in imported
    assert "MJA_CONTROLLER" not in source


def test_agent_entry_accepts_one_socket_and_shuts_down(monkeypatch):
    if importlib.util.find_spec("maa") is None:
        pytest.skip("MaaFramework Python binding is not installed in this environment")
    from agent import main as agent_main

    class Server:
        calls: list[object] = []

        @classmethod
        def start_up(cls, socket_id: str) -> bool:
            cls.calls.append(("start_up", socket_id))
            return True

        @classmethod
        def join(cls) -> None:
            cls.calls.append("join")

        @classmethod
        def shut_down(cls) -> None:
            cls.calls.append("shut_down")

    monkeypatch.setattr(agent_main, "AgentServer", Server)

    assert agent_main.main("socket-1") == 0
    assert Server.calls == [("start_up", "socket-1"), "join", "shut_down"]
