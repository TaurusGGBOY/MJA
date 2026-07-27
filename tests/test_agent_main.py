from __future__ import annotations

from agent import main as agent_main
from agent.errors import ErrorCode, MJAError


class FakeLifecycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def restore(self) -> None:
        self.calls.append("restore")


class FakeAgentServer:
    def __init__(
        self,
        *,
        start_result: bool = True,
        join_error: BaseException | None = None,
    ) -> None:
        self.start_result = start_result
        self.join_error = join_error
        self.calls: list[object] = []

    def start_up(self, socket_id: str) -> bool:
        self.calls.append(("start_up", socket_id))
        return self.start_result

    def join(self) -> None:
        self.calls.append("join")
        if self.join_error is not None:
            raise self.join_error

    def shut_down(self) -> None:
        self.calls.append("shut_down")


def test_agent_server_shutdown_and_window_restore_run_on_interrupt(monkeypatch) -> None:
    server = FakeAgentServer(join_error=KeyboardInterrupt())
    lifecycle = FakeLifecycle()
    monkeypatch.setattr(agent_main, "AgentServer", server)
    monkeypatch.setattr(agent_main, "build_lifecycle", lambda: lifecycle)

    assert agent_main.main(["socket-17"]) == 130
    assert server.calls == [("start_up", "socket-17"), "join", "shut_down"]
    assert lifecycle.calls == ["restore"]


def test_agent_start_failure_records_stable_controller_error_before_restore(monkeypatch) -> None:
    server = FakeAgentServer(start_result=False)
    lifecycle = FakeLifecycle()
    diagnostics: list[tuple[ErrorCode, str]] = []

    def record(error: MJAError) -> None:
        diagnostics.append((error.code, error.args[0]))
        assert lifecycle.calls == []

    monkeypatch.setattr(agent_main, "AgentServer", server)
    monkeypatch.setattr(agent_main, "build_lifecycle", lambda: lifecycle)
    monkeypatch.setattr(agent_main, "_write_failure_diagnostics", record)

    assert agent_main.main(["socket-18"]) == 3
    assert diagnostics[0][0] is ErrorCode.CONTROLLER_CONNECT_FAILED
    assert server.calls == [("start_up", "socket-18"), "shut_down"]
    assert lifecycle.calls == ["restore"]


def test_agent_requires_exactly_one_socket_argument(monkeypatch, capsys) -> None:
    monkeypatch.setattr(agent_main, "AgentServer", FakeAgentServer())

    assert agent_main.main([]) == 2
    assert "Usage" in capsys.readouterr().err
