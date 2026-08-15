from types import SimpleNamespace

from agent.errors import ErrorCode, MJAError
from agent.workflows.engine import run_workflow
from agent.workflows.models import (
    ActionIntent,
    CapturedFrame,
    Decision,
    RiskLevel,
    TaskPolicy,
    TaskStatus,
    Transition,
    VisualEvidence,
)

POLICY = TaskPolicy(
    task_id="ENGINE_TEST",
    label="引擎测试",
    entry="MJA_Daily_ENGINE_TEST",
    risk_levels=frozenset({RiskLevel.NORMAL}),
    max_steps=4,
    action_caps={"click": 2},
    approved_resources=frozenset(),
)


def evidence(frame_id, *, done=False):
    return VisualEvidence(
        frame_id,
        {"page": 1},
        {"target": 1, "done": 1 if done else 0},
        {},
        {"page": frame_id, "target": frame_id, "done": frame_id},
    )


class Driver:
    def __init__(self, *, done_after=True, fail=False):
        self.frames = 0
        self.executions = 0
        self.done_after = done_after
        self.fail = fail

    def capture(self):
        self.frames += 1
        return CapturedFrame(f"frame-{self.frames}", (1280, 720))

    def recognize(self, frame, names):
        if self.fail:
            raise RuntimeError("device failed")
        return evidence(frame.frame_id, done=self.executions > 0 and self.done_after)

    def execute(self, intent):
        self.executions += 1


class Definition:
    task_id = "ENGINE_TEST"
    initial_state = "entry"

    def __init__(self, decision):
        self.decision = decision

    def recognizers(self, state):
        return ("page", "target")

    def decide(self, snapshot, counters):
        return self.decision(snapshot, counters) if callable(self.decision) else self.decision


def test_engine_authorizes_executes_and_verifies_postcondition():
    driver = Driver()
    definition = Definition(
        lambda snapshot, counters: Decision.act(
            Transition(
                ActionIntent("click", "page", "target", input_kind="none"),
                "done",
            )
        )
        if not counters
        else Decision.finish(TaskStatus.COMPLETED)
    )
    result = run_workflow(definition, driver, POLICY, SimpleNamespace())
    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 1
    assert driver.frames == 3


def test_engine_accepts_an_alternate_postcondition_from_the_same_action():
    class HomeAfterClaimDriver(Driver):
        def recognize(self, frame, names):
            if self.executions > 0:
                return VisualEvidence(
                    frame.frame_id,
                    {"home": 1},
                    {"home": 1},
                    {},
                    {"home": frame.frame_id},
                )
            return super().recognize(frame, names)

    driver = HomeAfterClaimDriver()
    definition = Definition(
        lambda snapshot, counters: (
            Decision.finish(TaskStatus.COMPLETED)
            if snapshot.state == "reward_popup"
            and snapshot.evidence.target_hits.get("home", 0) == 1
            else Decision.act(
                Transition(
                    ActionIntent("claim", "trial", "reward", input_kind="none"),
                    "reward",
                    "reward_popup",
                    ("home",),
                )
            )
        )
        if not counters
        else Decision.finish(TaskStatus.COMPLETED)
    )

    result = run_workflow(definition, driver, POLICY, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert result.action_counts == {"claim": 1}


def test_engine_uses_next_state_recognizers_for_derived_postcondition():
    class DerivedPostconditionDriver(Driver):
        def __init__(self):
            super().__init__()
            self.recognizer_requests = []

        def recognize(self, frame, names):
            requested = tuple(names)
            self.recognizer_requests.append(requested)
            if self.executions > 0:
                derived = {"next.component_a", "next.component_b"} <= set(requested)
                hits = {"derived.done": 1 if derived else 0}
                return VisualEvidence(
                    frame.frame_id,
                    hits,
                    hits,
                    {},
                    {"derived.done": frame.frame_id},
                )
            return super().recognize(frame, names)

    class DerivedDefinition(Definition):
        def recognizers(self, state):
            if state == "next":
                return ("next.component_a", "next.component_b")
            return ("page", "target")

    driver = DerivedPostconditionDriver()
    definition = DerivedDefinition(
        lambda snapshot, counters: Decision.finish(TaskStatus.COMPLETED)
        if counters
        else Decision.act(
            Transition(
                ActionIntent("click", "page", "target", input_kind="none"),
                "derived.done",
                "next",
            )
        )
    )

    result = run_workflow(definition, driver, POLICY, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert {"next.component_a", "next.component_b"} <= set(
        driver.recognizer_requests[1]
    )


def test_engine_stops_battle_polling_on_failure_alternative(monkeypatch):
    waits: list[float] = []

    class FailedBattleDriver(Driver):
        def recognize(self, frame, names):
            if self.executions > 0:
                return VisualEvidence(
                    frame.frame_id,
                    {"shadow_stage_any": 1, "shadow_battle_failure": 1},
                    {"shadow_battle_target": 1, "shadow_battle_failure": 1},
                    {},
                    {
                        "shadow_stage_any": frame.frame_id,
                        "shadow_battle_target": frame.frame_id,
                        "shadow_battle_failure": frame.frame_id,
                    },
                )
            return super().recognize(frame, names)

    monkeypatch.setattr("agent.workflows.engine.sleep", waits.append)
    policy = TaskPolicy(
        task_id="SHADOW_RUINS_DAILY",
        label="蜃影武墟",
        entry="MJA_Daily_SHADOW_RUINS_DAILY",
        risk_levels=frozenset({RiskLevel.NORMAL}),
        max_steps=4,
        action_caps={"battle": 1},
        approved_resources=frozenset(),
    )
    definition = Definition(
        lambda snapshot, counters: (
            Decision.finish(TaskStatus.FAILED)
            if counters
            else Decision.act(
                Transition(
                    ActionIntent(
                        "battle",
                        "shadow_stage_any",
                        "shadow_battle_target",
                        input_kind="none",
                    ),
                    "shadow_battle_result",
                    "battle_done",
                    ("shadow_battle_failure",),
                )
            )
        )
    )
    driver = FailedBattleDriver()

    result = run_workflow(definition, driver, policy, SimpleNamespace())

    assert result.status is TaskStatus.FAILED
    assert result.error_code == "WORKFLOW_POSTCONDITION_MISSING"
    assert driver.executions == 1
    assert driver.frames == 3
    assert waits == []


def test_engine_finishes_from_terminal_evidence_before_next_timeout_check(monkeypatch):
    clock = iter((0.0, 0.1, 1.0))
    monkeypatch.setattr("agent.workflows.engine.monotonic", lambda: next(clock))

    definition = Definition(
        lambda snapshot, counters: (
            Decision.finish(TaskStatus.ALREADY_COMPLETE)
            if snapshot.state == "done"
            and snapshot.evidence.target_hits.get("done", 0) == 1
            else Decision.act(
                Transition(
                    ActionIntent("click", "page", "target", input_kind="none"),
                    "done",
                    "done",
                )
            )
        )
    )

    driver = Driver()
    result = run_workflow(
        definition,
        driver,
        POLICY,
        SimpleNamespace(),
        timeout_seconds=0.5,
    )

    assert result.status is TaskStatus.ALREADY_COMPLETE
    assert result.postcondition == "done"
    assert driver.executions == 1
    assert driver.frames == 2


def test_shadow_battle_polls_ocr_until_victory_without_fixed_wait(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("agent.workflows.engine.sleep", waits.append)

    policy = TaskPolicy(
        task_id="SHADOW_RUINS_DAILY",
        label="蜃影武墟",
        entry="MJA_Daily_SHADOW_RUINS_DAILY",
        risk_levels=frozenset({RiskLevel.NORMAL}),
        max_steps=4,
        action_caps={"battle": 1},
        approved_resources=frozenset(),
    )

    class BattleDriver(Driver):
        def __init__(self):
            super().__init__()
            self.after_recognitions = 0

        def recognize(self, frame, names):
            if self.executions > 0:
                self.after_recognitions += 1
            won = self.after_recognitions >= 4
            return VisualEvidence(
                frame.frame_id,
                {"shadow_stage_any": 1, "shadow_battle_result": 1 if won else 0},
                {"shadow_battle_target": 1, "shadow_battle_result": 1 if won else 0},
                {},
                {
                    "shadow_stage_any": frame.frame_id,
                    "shadow_battle_target": frame.frame_id,
                    "shadow_battle_result": frame.frame_id,
                },
            )

    definition = Definition(
        lambda snapshot, counters: Decision.act(
            Transition(
                ActionIntent(
                    "battle",
                    "shadow_stage_any",
                    "shadow_battle_target",
                    input_kind="none",
                ),
                "shadow_battle_result",
                "battle_done",
            )
        )
        if not counters
        else Decision.finish(TaskStatus.COMPLETED)
    )
    driver = BattleDriver()

    result = run_workflow(definition, driver, policy, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 1
    assert driver.after_recognitions == 4
    assert waits == [3.0, 3.0, 3.0]


def test_engine_maps_terminal_states_and_does_not_block_safety_markers():
    for status in (TaskStatus.ALREADY_COMPLETE, TaskStatus.NOT_ELIGIBLE):
        definition = Definition(Decision.finish(status))
        result = run_workflow(definition, Driver(), POLICY, SimpleNamespace())
        assert result.status is status

    definition = Definition(
        lambda snapshot, counters: Decision.act(
            Transition(
                ActionIntent("click", "missing", "target", input_kind="none"),
                "done",
            )
        )
        if not counters
        else Decision.finish(TaskStatus.COMPLETED)
    )
    driver = Driver()
    result = run_workflow(definition, driver, POLICY, SimpleNamespace())
    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 1


def test_engine_maps_driver_failure_and_step_cap():
    failed = Definition(
        Decision.act(Transition(ActionIntent("click", "page", "target"), "done"))
    )
    assert (
        run_workflow(failed, Driver(fail=True), POLICY, SimpleNamespace()).status
        is TaskStatus.FAILED
    )
    endless = Definition(
        Decision.act(Transition(ActionIntent("click", "page", "target", input_kind="none"), "done"))
    )
    no_postcondition = run_workflow(endless, Driver(done_after=False), POLICY, SimpleNamespace())
    assert no_postcondition.status is TaskStatus.FAILED

    class TypedFailureDriver(Driver):
        def recognize(self, frame, names):
            raise MJAError(ErrorCode.MAIL_OPEN_TIMEOUT, "mail marker missing")

    typed = run_workflow(failed, TypedFailureDriver(), POLICY, SimpleNamespace())
    assert typed.error_code == "MAIL_OPEN_TIMEOUT"


def test_engine_maps_after_action_full_bag_to_not_eligible():
    class FullBagAfterDriver(Driver):
        def recognize(self, frame, names):
            if self.executions > 0:
                return VisualEvidence(
                    frame.frame_id,
                    {"page": 1},
                    {"target": 1, "done": 0, "dungeon_bag_full": 1},
                    {},
                    {
                        "page": frame.frame_id,
                        "target": frame.frame_id,
                        "done": frame.frame_id,
                        "dungeon_bag_full": frame.frame_id,
                    },
                )
            return evidence(frame.frame_id)

    definition = Definition(
        Decision.act(
            Transition(
                ActionIntent("click", "page", "target", input_kind="none"),
                "done",
            )
        )
    )
    result = run_workflow(definition, FullBagAfterDriver(), POLICY, SimpleNamespace())

    assert result.status is TaskStatus.NOT_ELIGIBLE
    assert result.error_code is None


def test_shadow_entry_retries_only_while_fresh_ocr_popup_remains():
    policy = TaskPolicy(
        task_id="SHADOW_RUINS_DAILY",
        label="蜃影武墟",
        entry="MJA_Daily_SHADOW_RUINS_DAILY",
        risk_levels=frozenset({RiskLevel.NORMAL}),
        max_steps=4,
        action_caps={"enter_shadow_stage": 2},
        approved_resources=frozenset(),
    )

    class ShadowDriver(Driver):
        def recognize(self, frame, names):
            entered = self.executions >= 2
            return VisualEvidence(
                frame.frame_id,
                {"shadow_popup": 0 if entered else 1, "shadow_stage_any": 1 if entered else 0},
                {"shadow_go": 0 if entered else 1, "shadow_stage_any": 1 if entered else 0},
                {},
                {
                    "shadow_popup": frame.frame_id,
                    "shadow_go": frame.frame_id,
                    "shadow_stage_any": frame.frame_id,
                },
            )

    class ShadowDefinition:
        task_id = "SHADOW_RUINS_DAILY"
        initial_state = "popup"

        def recognizers(self, state):
            return ("shadow_popup", "shadow_go", "shadow_stage_any")

        def decide(self, snapshot, counters):
            if snapshot.evidence.page_hits.get("shadow_stage_any", 0) == 1:
                return Decision.finish(TaskStatus.COMPLETED)
            return Decision.act(
                Transition(
                    ActionIntent(
                        "enter_shadow_stage",
                        "shadow_popup",
                        "shadow_go",
                        input_kind="none",
                    ),
                    "shadow_stage_any",
                    "exploration",
                )
            )

    driver = ShadowDriver(done_after=False)
    result = run_workflow(ShadowDefinition(), driver, policy, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 2


def test_engine_retries_only_idempotent_navigation_after_missing_postcondition():
    class NavigationDriver(Driver):
        def __init__(self):
            super().__init__()
            self.recoveries = 0

        def recognize(self, frame, names):
            return VisualEvidence(
                frame.frame_id,
                {"page": 1, "done": 1 if self.executions >= 2 else 0},
                {"target": 1, "done": 1 if self.executions >= 2 else 0},
                {},
                {name: frame.frame_id for name in names},
            )

        def recover_game_ready(self, *, restart_if_needed=True):
            del restart_if_needed
            self.recoveries += 1
            return True

    definition = Definition(
        lambda snapshot, counters: (
            Decision.finish(TaskStatus.COMPLETED)
            if snapshot.evidence is not None
            and snapshot.evidence.target_hits.get("done", 0) == 1
            else Decision.act(
                Transition(
                    ActionIntent(
                        "open_function_panel",
                        "page",
                        "target",
                        input_kind="none",
                    ),
                    "done",
                    "panel",
                )
            )
        )
    )
    driver = NavigationDriver()

    result = run_workflow(definition, driver, POLICY, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 2
    assert driver.recoveries == 1


def test_engine_uses_bounded_boundary_cleanup_before_lifecycle_recovery():
    class BoundedBoundaryDriver(Driver):
        def __init__(self):
            super().__init__()
            self.boundary_calls = 0

        def recognize(self, frame, names):
            return VisualEvidence(
                frame.frame_id,
                {"page": 1, "done": 1 if self.boundary_calls else 0},
                {"target": 1, "done": 1 if self.boundary_calls else 0},
                {},
                {name: frame.frame_id for name in names},
            )

        def return_to_home(self, *, max_steps=8, check_foreground=False):
            assert max_steps == 8
            assert check_foreground is False
            self.boundary_calls += 1
            return True

        def recover_game_ready(self, *, restart_if_needed=True):
            raise AssertionError("navigation retry must not enter lifecycle recovery")

    definition = Definition(
        lambda snapshot, counters: (
            Decision.finish(TaskStatus.COMPLETED)
            if snapshot.evidence is not None
            and snapshot.evidence.target_hits.get("done", 0) == 1
            else Decision.act(
                Transition(
                    ActionIntent(
                        "open_painting_scroll",
                        "page",
                        "target",
                        input_kind="none",
                    ),
                    "done",
                    "painting",
                )
            )
        )
    )
    driver = BoundedBoundaryDriver()

    result = run_workflow(definition, driver, POLICY, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 1
    assert driver.boundary_calls == 1


def test_engine_recovers_after_shadow_auto_route_kills_game_process():
    class ShadowRouteDriver(Driver):
        def __init__(self):
            super().__init__()
            self.recoveries = 0

        def recognize(self, frame, names):
            del names
            if self.recoveries == 0 and self.executions == 0:
                return VisualEvidence(
                    frame.frame_id,
                    {"shadow_auto_route_prompt": 1},
                    {"shadow_auto_route_confirm": 1},
                    {},
                    {},
                )
            if self.recoveries == 0:
                # Model the Unity process disappearing and Maa seeing the
                # launcher after the cross-map confirmation click.
                return VisualEvidence(frame.frame_id, {}, {}, {}, {})
            if self.executions >= 2:
                return VisualEvidence(
                    frame.frame_id,
                    {"shadow_stage_any": 1, "done": 1},
                    {"shadow_stage_any": 1, "done": 1},
                    {},
                    {},
                )
            return VisualEvidence(
                frame.frame_id,
                {"shadow_auto_route_prompt": 1},
                {"shadow_auto_route_confirm": 1},
                {},
                {},
            )

        def recover_game_ready(self, *, restart_if_needed=True):
            del restart_if_needed
            self.recoveries += 1
            return True

    definition = Definition(
        lambda snapshot, counters: (
            Decision.finish(TaskStatus.COMPLETED)
            if snapshot.evidence is not None
            and snapshot.evidence.target_hits.get("done", 0) == 1
            else Decision.act(
                Transition(
                    ActionIntent(
                        "confirm_shadow_auto_route",
                        "shadow_auto_route_prompt",
                        "shadow_auto_route_confirm",
                        input_kind="none",
                    ),
                    "done",
                    "stage",
                )
            )
        )
    )
    driver = ShadowRouteDriver()

    result = run_workflow(definition, driver, POLICY, SimpleNamespace())

    assert result.status is TaskStatus.COMPLETED
    assert driver.executions == 2
    assert driver.recoveries == 1
