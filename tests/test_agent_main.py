from __future__ import annotations

from agent import main as agent_main


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


def test_agent_server_shutdown_runs_on_interrupt(monkeypatch) -> None:
    server = FakeAgentServer(join_error=KeyboardInterrupt())
    monkeypatch.setattr(agent_main, "AgentServer", server)

    assert agent_main.main("socket-17") == 130
    assert server.calls == [("start_up", "socket-17"), "join", "shut_down"]


def test_agent_start_failure_shuts_down_server(monkeypatch, capsys) -> None:
    server = FakeAgentServer(start_result=False)
    monkeypatch.setattr(agent_main, "AgentServer", server)

    assert agent_main.main("socket-18") == 3
    assert server.calls == [("start_up", "socket-18"), "shut_down"]
    assert "AgentServer.start_up returned false" in capsys.readouterr().err


def test_agent_requires_exactly_one_socket_argument(monkeypatch, capsys) -> None:
    monkeypatch.setattr(agent_main, "AgentServer", FakeAgentServer())

    assert agent_main.main("") == 2
    assert "Usage" in capsys.readouterr().err
