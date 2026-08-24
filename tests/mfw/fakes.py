from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeController:
    connected: bool = True
    actions: list[tuple[str, Any]] = field(default_factory=list)

    def post_click(self, x: int, y: int):
        self.actions.append(("click", (x, y)))
        return SimpleNamespace(wait=lambda: True)

    def post_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int):
        self.actions.append(("swipe", (x1, y1, x2, y2, duration)))
        return SimpleNamespace(wait=lambda: True)


class FailingController(FakeController):
    def __init__(self, error: Exception):
        super().__init__()
        self.error = error

    def post_click(self, x: int, y: int):
        raise self.error


@dataclass
class FakeTasker:
    controller: FakeController


class FakeContext:
    def __init__(
        self,
        controller: FakeController | None = None,
        nodes: set[str] | None = None,
    ):
        self.controller = controller or FakeController()
        self.tasker = FakeTasker(self.controller)
        self.nodes = set(nodes or ())
        self.next_overrides: list[tuple[str, list[str]]] = []

    def get_node_data(self, name: str) -> dict[str, str] | None:
        return {"name": name} if name in self.nodes else None

    def override_next(self, name: str, next_list: list[str]) -> bool:
        self.next_overrides.append((name, list(next_list)))
        return True


@dataclass
class FakeArgv:
    custom_action_param: str
    node_name: str = "MJA_TEST_AND_NODE"
    box: tuple[int, int, int, int] = (100, 200, 40, 20)
    reco_detail: Any = None


def and_reco(*sub_results: Any) -> Any:
    return SimpleNamespace(
        hit=True,
        algorithm="And",
        best_result=SimpleNamespace(sub_results=list(sub_results)),
    )


def hit_reco(name: str, box: Any = None) -> Any:
    return SimpleNamespace(name=name, hit=True, box=box, filtered_results=[])


def miss_reco(name: str) -> Any:
    return SimpleNamespace(name=name, hit=False, filtered_results=[])
