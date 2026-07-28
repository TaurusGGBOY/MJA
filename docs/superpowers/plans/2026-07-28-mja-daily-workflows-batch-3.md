# MJA Daily Workflows Batch 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `SHADOW_RUINS_DAILY`, `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`, and `RING_CHALLENGE_DAILY` on the canonical workflow foundation with bounded, evidence-gated foreground actions.

**Architecture:** Batch 3 contributes three pure `WorkflowDefinition` implementations and their resource pipelines. The existing `run_workflow`, `DailyWorkflowAction`, `authorize_action`, `RunDiagnostics`, ProjectInterface renderer, and CLI lifecycle remain the only runtime, safety, evidence, interface, and process boundaries.

**Tech Stack:** Python, pytest, Ruff, MaaFramework ProjectInterface JSON, MAA capture calibration, macOS foreground input, and PNG fixture validation.

## Global Constraints

- Capture, foundation, Batch 1, and Batch 2 are completed prerequisites.
- Runtime task statuses are exactly `completed`, `already_complete`, `not_eligible`, `blocked_safety`, and `failed`.
- `live_pending` is aggregate verification metadata only and is never a `TaskResult.status`.
- Every side effect requires same-frame page and target evidence, canonical `authorize_action`, a trace, and a postcondition capture.
- Paid, login, verification, unknown-currency, unknown-dialog, and ambiguous-target signals hard stop before input.
- All dimensions and coordinates come from `assets/resource/calibration.json`; no fixed capture size is assumed.
- Shadow historical anchors use `984x768` only as a normalized reference and must be mapped to the current MAA capture.
- The sole business truth is `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py`.
- Legacy calibration/failure evidence is only `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa`.
- Fixtures use `tests/fixtures/{canonical task ID}/manifest.json` plus four exact PNG kinds.
- Diagnostics use `diagnostics/YYYY-MM-DD/TASK_ID/run-id/`.
- Before every live task, record `git rev-parse HEAD` and `git status --short`, rerun setup/install verification from that checkout, and save both full-desktop and Maa-controller before/after captures with digests in diagnostics and the Batch 3 human report. The later aggregate admission plan copies those digests into the machine task record.
- All staged paths use `git add --` with explicit file paths; `AGENTS.md` is never staged.

---

The three Batch 3 daily workflows are:

1. `SHADOW_RUINS_DAILY`
2. `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`
3. `RING_CHALLENGE_DAILY`

The workflows consume the runtime and safety contracts delivered by the macOS capture fallback, workflow foundation, Batch 1, and Batch 2. They do not introduce a second runner, a second state/result model, a second evidence model, or a Batch 3-specific CLI lifecycle.

## Mandatory prerequisites

Batch 3 starts only after all of the following are complete and verified:

- macOS capture fallback plan: `docs/superpowers/plans/2026-07-28-mja-macos-capture-fallback.md`
- workflow foundation plan: `docs/superpowers/plans/2026-07-28-mja-workflow-foundation.md`
- the approved Batch 1 implementation and its focused/full gates
- the approved Batch 2 implementation and its focused/full gates

The capture plan must have produced and validated `assets/resource/calibration.json`. The foundation must provide the canonical model, safety gate, bounded runner, diagnostics, fixture harness, shared navigation, ProjectInterface renderer, and CLI task-selection contract. If a prerequisite is absent, the corresponding Batch 3 task remains blocked before implementation; it is not reimplemented locally.

## Canonical runtime contract

Batch 3 consumes these existing interfaces. The names, signatures, and ownership below are fixed by the workflow foundation plan.

```python
# agent/workflows/models.py
class TaskStatus(StrEnum):
    COMPLETED = "completed"
    ALREADY_COMPLETE = "already_complete"
    NOT_ELIGIBLE = "not_eligible"
    BLOCKED_SAFETY = "blocked_safety"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class TaskPolicy:
    task_id: str
    label: str
    entry: str
    risk_levels: frozenset[RiskLevel]
    max_steps: int
    action_caps: Mapping[str, int]
    approved_resources: frozenset[str]
    eligible_weekdays: frozenset[int] | None = None

@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    postcondition: str
    action_counts: Mapping[str, int]
    error_code: str | None = None

# agent/safety.py
@dataclass(frozen=True, slots=True)
class VisualEvidence:
    frame_id: str
    page_hits: Mapping[str, int]
    target_hits: Mapping[str, int]
    danger_hits: Mapping[str, int]
    recognizer_frame_ids: Mapping[str, str]
    texts: tuple[str, ...]
    resource_hits: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ActionIntent:
    action_id: str
    page_marker: str
    target_marker: str
    approved_resource: str | None = None

def authorize_action(
    evidence: VisualEvidence,
    intent: ActionIntent,
    policy: TaskPolicy,
    action_counts: Mapping[str, int],
) -> SafetyDecision: ...

# agent/workflows/engine.py and agent/actions/daily_workflow.py
@dataclass(frozen=True, slots=True)
class CapturedFrame:
    frame_id: str
    image: Any
    size: tuple[int, int]

@dataclass(frozen=True, slots=True)
class Recognition:
    marker: str
    frame_id: str
    hit_count: int
    boxes: tuple[tuple[int, int, int, int], ...]
    texts: tuple[str, ...] = ()
    resource_hits: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class StateSnapshot:
    state: str
    frame: CapturedFrame
    evidence: VisualEvidence
    recognitions: Mapping[str, Recognition]

@dataclass(frozen=True, slots=True)
class Transition:
    state: str
    intent: ActionIntent
    input_kind: Literal["click", "swipe", "long_press", "none"]
    action_args: Mapping[str, object]
    next_state: str
    postcondition_marker: str

@dataclass(frozen=True, slots=True)
class Decision:
    transition: Transition | None
    status: TaskStatus | None
    postcondition: str
    error_code: str | None = None

    @classmethod
    def act(cls, transition: Transition) -> Self: ...

    @classmethod
    def finish(
        cls,
        status: TaskStatus,
        postcondition: str,
        *,
        error_code: str | None = None,
    ) -> Self: ...

class WorkflowDefinition(Protocol):
    task_id: str
    initial_state: str
    def recognizers(self, state: str) -> tuple[str, ...]: ...
    def decide(self, snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision: ...

def run_workflow(
    definition: WorkflowDefinition,
    driver: WorkflowDriver,
    policy: TaskPolicy,
    diagnostics: RunDiagnostics,
    *,
    day: date | None = None,
) -> TaskResult: ...

class DailyWorkflowAction:
    def run(self, context: Any, argv: Any) -> Any: ...

# agent/diagnostics.py
RunDiagnostics.create(
    root: Path,
    *,
    task_id: str,
    now: TimestampFactory | None = None,
) -> RunDiagnostics: ...
```

The runtime has exactly five `TaskStatus` values: `completed`, `already_complete`, `not_eligible`, `blocked_safety`, and `failed`. Internal workflow state names such as `read_score` or `verify_postcondition` are transition labels, not additional statuses. `live_pending` is permitted only as the status of an aggregate verification record when a live branch cannot safely be exercised; it is never a `TaskResult.status` and never counts as a task pass.

Every side-effecting click, swipe, or long press follows this order:

1. capture one immutable current frame;
2. recognize the expected page and exactly one permitted target in that same frame;
3. create `VisualEvidence` and `ActionIntent`;
4. call `authorize_action` with the canonical `TaskPolicy` and current action counts;
5. record the decision through `RunDiagnostics`;
6. execute at most one input;
7. capture and verify the declared postcondition.

The page evidence and target evidence for every side effect must both point to the same `frame_id` and recognizer frame IDs. A page-only or target-only record is blocked. Paid, login, verification, unknown-currency, unknown-dialog, and ambiguous-target signals hard stop before input.

## Business truth and calibration

The sole business truth is:

`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py`

Its step IDs and safety wording are the source for behavior. The only legacy calibration and failure-evidence source is:

`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa`

Legacy material calibrates recognizers and documents failure modes; it does not override the daily workflow source. No other copy is treated as business truth.

All coordinates and crops are derived from `assets/resource/calibration.json`, which contains the observed logical window size, current MAA capture size, and the applicable reference sizes. No task assumes a fixed capture resolution. A calibration-aware helper reads the current `maa_capture_size` and maps normalized/reference coordinates to that frame, rejecting aspect-ratio drift and stale calibration.

The historical Shadow foreground anchors are defined in a `984x768` reference coordinate system only:

```python
SHADOW_REFERENCE_SIZE = (984, 768)
SHADOW_REFERENCE_ANCHORS = {
    "left": (350, 532),
    "center": (493, 532),
    "right": (636, 532),
}

def map_reference_anchor(
    point: tuple[int, int],
    *,
    reference_size: tuple[int, int],
    capture_size: tuple[int, int],
) -> tuple[int, int]:
    return (
        round(point[0] * capture_size[0] / reference_size[0]),
        round(point[1] * capture_size[1] / reference_size[1]),
    )
```

The actual implementation must read `reference_size` and the current capture size from calibration data, then map all three anchors before authorizing a click on an already recognized Shadow stage page. Each action trace records both `reference_anchor` and `mapped_anchor`, plus `reference_size`, `capture_size`, page marker, target marker, and same-frame decision. It must not treat `(350, 532)`, `(493, 532)`, or `(636, 532)` as current-device pixels.

## Shared fixture and diagnostic contracts

Each canonical task has exactly one fixture directory:

```text
tests/fixtures/SHADOW_RUINS_DAILY/
  manifest.json
  entry.png
  actionable.png
  completed.png
  danger.png
tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/
  manifest.json
  entry.png
  actionable.png
  completed.png
  danger.png
tests/fixtures/RING_CHALLENGE_DAILY/
  manifest.json
  entry.png
  actionable.png
  completed.png
  danger.png
```

The manifest uses the foundation fixture schema and names the expected page marker, target marker set, and expected canonical status for each PNG. The four cases are:

- `entry.png`: recognized task entry and no side effect; expected status is `None`.
- `actionable.png`: recognized page plus exactly one permitted action target; expected status is `None`.
- `completed.png`: recognized task postcondition with zero inputs; expected status is `already_complete`.
- `danger.png`: paid, login, verification, unknown-currency, unknown-dialog, or ambiguous evidence; expected status is `blocked_safety`.

The foundation recognition-only validator must decode all four PNGs and assert zero input calls. No fixture result is live evidence.

All run evidence is created by `RunDiagnostics` at:

`diagnostics/YYYY-MM-DD/TASK_ID/run-id/`

The directory contains `result.json`, `agent.log`, `maafw.log`, `action-trace.jsonl`, and the applicable `before.png`, `after.png`, and `failure.png`. Do not create or document an alternate debug path or a Batch 3-specific diagnostic subtree. Batch 3 writes only its human evidence report; the later aggregate admission plan exclusively writes live acceptance state to `verification/tasks/{TASK_ID}.json`. `live_pending` there is verification metadata and never a `TaskResult`.

### Task 1: Tighten the three canonical Batch 3 policies

**Files:**

- Update: `agent/workflows/catalog.py`
- Create: `tests/workflows/test_batch3_catalog.py`

**Interfaces:**

- Consumes: `TaskPolicy`, `RiskLevel`, and the 17-entry `TASK_POLICIES` mapping from `agent/workflows/models.py` and `agent/workflows/catalog.py`.
- Produces: exact policies for `SHADOW_RUINS_DAILY`, `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`, and `RING_CHALLENGE_DAILY`; each `entry` is `MJA_Daily_{TASK_ID}`.

Do not create `agent/batch3_guards.py`, a Batch 3 runner, a Batch 3 `TaskStatus`, a Batch 3 `TaskResult`, or a Batch 3 `VisualEvidence` type. This task changes only catalog data; workflow definitions and fixtures are created by Tasks 2–4.

### Red-green implementation sequence

- [ ] **Step 1: Write the failing catalog test.** Assert exact entry names, approved resources, and finite caps. The test must contain these checks:

```python
def test_batch3_policies_have_exact_entries_and_caps() -> None:
    shadow = TASK_POLICIES["SHADOW_RUINS_DAILY"]
    assert shadow.entry == "MJA_Daily_SHADOW_RUINS_DAILY"
    assert shadow.action_caps["shadow_stage_round"] == 20
    assert shadow.action_caps["shadow_foreground_anchor"] == 60

    jianlin = TASK_POLICIES["JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"]
    assert jianlin.entry == "MJA_Daily_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"
    assert jianlin.action_caps["buy_stamina_once"] == 1
    assert jianlin.action_caps["challenge_condensate"] == 12
    assert jianlin.approved_resources == frozenset({"紫色魂玉", "体力"})

    ring = TASK_POLICIES["RING_CHALLENGE_DAILY"]
    assert ring.entry == "MJA_Daily_RING_CHALLENGE_DAILY"
    assert ring.action_caps["ring_fight"] == 12
    assert ring.action_caps["ring_sweep"] == 1
    assert ring.approved_resources == frozenset({"擂台券"})
```

- [ ] **Step 2: Run the test and confirm the conservative catalog values fail.**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_batch3_catalog.py -q`

Expected: FAIL because at least one Batch 3 entry or cap still has its conservative foundation value.

- [ ] **Step 3: Replace the three conservative policies with exact policies.** Set action caps to the business limits: Shadow stage rounds `20`, Jianlin challenge cycles `12`, Jianlin stamina purchase `1`, Ring fights `12`, and Ring sweep `1`. Keep every global policy step cap finite.

```python
TASK_POLICIES["SHADOW_RUINS_DAILY"] = TaskPolicy(
    task_id="SHADOW_RUINS_DAILY",
    label="蜃影武墟",
    entry="MJA_Daily_SHADOW_RUINS_DAILY",
    risk_levels=frozenset({RiskLevel.STATEFUL, RiskLevel.COMBAT}),
    max_steps=80,
    action_caps={
        "open_shadow": 1,
        "shadow_direct_forward": 2,
        "shadow_region_fallback": 1,
        "shadow_foreground_anchor": 60,
        "shadow_stage_round": 20,
        "shadow_return_daily": 1,
    },
    approved_resources=frozenset(),
)

TASK_POLICIES["JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"] = TaskPolicy(
    task_id="JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    label="剑林资源凝晶体力",
    entry="MJA_Daily_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE, RiskLevel.COMBAT}),
    max_steps=120,
    action_caps={
        "open_jianlin": 1,
        "open_jianlin_resource": 1,
        "select_condensate": 1,
        "buy_stamina_once": 1,
        "set_safe_count": 12,
        "set_safe_multiplier": 12,
        "challenge_condensate": 12,
        "close_condensate_result": 12,
        "jianlin_return_daily": 1,
    },
    approved_resources=frozenset({"紫色魂玉", "体力"}),
)

TASK_POLICIES["RING_CHALLENGE_DAILY"] = TaskPolicy(
    task_id="RING_CHALLENGE_DAILY",
    label="擂台挑战",
    entry="MJA_Daily_RING_CHALLENGE_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE, RiskLevel.COMBAT}),
    max_steps=120,
    action_caps={
        "open_ring": 1,
        "ring_start": 1,
        "ring_select_opponent": 12,
        "ring_fight": 12,
        "ring_skip": 12,
        "ring_close_result": 12,
        "ring_sweep": 1,
        "ring_confirm_sweep": 1,
        "ring_return_daily": 1,
    },
    approved_resources=frozenset({"擂台券"}),
)
```

- [ ] **Step 4: Run focused tests and Ruff.**

```bash
install/.venv/bin/python -m pytest tests/workflows/test_batch3_catalog.py tests/test_workflow_catalog.py -q
install/.venv/bin/python -m ruff check agent/workflows/catalog.py \
  tests/workflows/test_batch3_catalog.py
```

Expected: PASS, with all three exact entries and caps while the full 17-task catalog order remains unchanged.

### Independent postcondition

Resolving the three IDs returns the exact policies above, no policy approves real money, and the other 14 catalog entries are byte-for-byte unchanged.

- [ ] **Step 5: Commit only the catalog and its focused test.**

```bash
git add -- agent/workflows/catalog.py tests/workflows/test_batch3_catalog.py
git commit -m "feat: register batch 3 workflow policies"
```

### Task 2: Implement SHADOW_RUINS_DAILY with direct navigation and bounded mapped anchors

**Files:**

- Create: `agent/workflows/definitions/shadow_ruins_daily.py`
- Update: `agent/workflows/definitions/__init__.py`
- Update: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/shadow_ruins_daily.json`
- Create from current calibrated captures: `assets/resource/image/daily/SHADOW_RUINS_DAILY/shadow_entry.png`
- Create from current calibrated captures: `assets/resource/image/daily/SHADOW_RUINS_DAILY/shadow_stage.png`
- Create from current calibrated captures: `assets/resource/image/daily/SHADOW_RUINS_DAILY/shadow_daily_complete.png`
- Create: `tests/workflows/test_shadow_ruins_daily.py`
- Create: `tests/fixtures/SHADOW_RUINS_DAILY/manifest.json`
- Create from approved captures: `tests/fixtures/SHADOW_RUINS_DAILY/entry.png`
- Create from approved captures: `tests/fixtures/SHADOW_RUINS_DAILY/actionable.png`
- Create from approved captures: `tests/fixtures/SHADOW_RUINS_DAILY/completed.png`
- Create from approved captures: `tests/fixtures/SHADOW_RUINS_DAILY/danger.png`
- Consume without changing: `assets/resource/calibration.json`
- Consume without changing: `agent/safety.py`
- Consume without changing: `agent/workflows/engine.py`
- Consume without changing: `agent/actions/daily_workflow.py`

**Interfaces:**

- Consumes: `StateSnapshot`, `Decision`, `Transition`, `WorkflowDefinition`, `TaskStatus`, `ActionIntent`, `run_workflow(...)`, `authorize_action(...)`, and calibration fields `maa_capture_size` plus `reference_sizes.shadow`.
- Produces: `decide_shadow_active_branch(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision`, `ShadowRuinsDailyDefinition.recognizers(state: str) -> tuple[str, ...]`, `ShadowRuinsDailyDefinition.decide(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision`, registry key `SHADOW_RUINS_DAILY`, and Pipeline entry `MJA_Daily_SHADOW_RUINS_DAILY`.

The definition exposes the existing protocol method:

```python
class ShadowRuinsDailyDefinition:
    task_id = "SHADOW_RUINS_DAILY"
    initial_state = "daily_entry"

    def recognizers(self, state: str) -> tuple[str, ...]:
        return SHADOW_RECOGNIZERS[state]

    def decide(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        if snapshot.recognitions["shadow_daily_complete"].hit_count == 1:
            status = TaskStatus.COMPLETED if sum(counters.values()) else TaskStatus.ALREADY_COMPLETE
            return Decision.finish(status, "shadow_daily_complete")
        if snapshot.state == "daily_entry":
            return Decision.act(Transition(
                state="daily_entry",
                intent=ActionIntent("open_shadow", "daily_page", "shadow_entry"),
                input_kind="click",
                action_args={},
                next_state="shadow_popup",
                postcondition_marker="shadow_popup",
            ))
        return decide_shadow_active_branch(snapshot, counters)
```

Define `SHADOW_RECOGNIZERS` in the same module as an immutable mapping. Define `decide_shadow_active_branch(...)` in that module to implement only the direct-forward, exact-error fallback, mapped-anchor, exit, and final-verification branches described below; its unknown-state result is `Decision.finish(TaskStatus.FAILED, "", error_code="SHADOW_UNKNOWN_STATE")`.

The pipeline contains recognizer-only page markers, target markers, navigation-error OCR, stage-entry marker, and daily postcondition marker. Mapped foreground-anchor metadata is carried in `Transition.action_args` and `ActionTraceRecord.details`, not as a nonstandard Pipeline property. Side effects are dispatched through the single root `DailyWorkflowAction`, whose same-frame adapter constructs `VisualEvidence` and calls `authorize_action`.

### Red-green implementation sequence

- [ ] **Step 1, 3 minutes: write failing direct-route tests.** Require the first action after the active Shadow popup is `前往`; require manual region selection and stele teleport to be unreachable unless the same-frame result contains the exact navigation-error text `该地区无法导航` or `当前位置暂时无法寻路`. Before implementation, expect a failed transition assertion.

- [ ] **Step 2, 3 minutes: write failing bounded-anchor tests.** Feed a recognized stage snapshot and a current capture size read from a fake calibration. Require the action order `left`, `center`, `right`, at most once per round, at most 20 rounds, and a failed result when all three anchors produce no visible progress. Before implementation, expect missing mapping or cap assertions.

- [ ] **Step 3, 2 minutes: write failing safety tests.** Require no anchor authorization on a popup, map, unknown page, danger page, or ambiguous foreground. Require page and target evidence to share the same frame ID. Before implementation, expect `blocked_safety` assertions.

- [ ] **Step 4: implement direct navigation first.** The state sequence is `daily_entry -> shadow_popup -> direct_forward -> stage_entry`. A navigation-error observation is the only branch to `region_fallback`; an absent or unrecognized error stops with canonical safety/failed result. The fallback must select the matching region, reopen the Shadow card, and use `前往` again. It must not run both routes speculatively.

```json
{
  "MJA_Daily_SHADOW_RUINS_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "SHADOW_RUINS_DAILY"}
  },
  "shadow_direct_forward": {
    "recognition": "OCR",
    "expected": ["前往"],
    "action": "DoNothing"
  },
  "shadow_navigation_error": {
    "recognition": "OCR",
    "expected": ["该地区无法导航", "当前位置暂时无法寻路"],
    "action": "DoNothing"
  }
}
```

Only `MJA_Daily_SHADOW_RUINS_DAILY` starts the custom action. `shadow_direct_forward`, `shadow_navigation_error`, stage, anchor, and postcondition nodes are recognition-only inputs queried by `WorkflowDriver.recognize`; none launches a nested workflow or uses a standard Maa input action.

- [ ] **Step 5: implement calibration-aware anchor mapping.** Load `assets/resource/calibration.json`; use its current MAA capture size and the Shadow reference size. Map the three historical points with the shared helper, verify the page marker `shadow_stage`, recognize the foreground target at the mapped point, then create an `ActionIntent` for exactly that mapped anchor. Trace both coordinate systems. The 20-round cap includes every attempted foreground round, including rounds that make no progress.

- [ ] **Step 6: implement round postconditions.** After each full three-anchor sweep, capture a new frame and require visible stage progress, a recognized exit, or a canonical blocked/failed result. After exit, navigate to the daily page and verify `完成一次蜃影武墟挑战` before returning `completed`. Never click a daily reward in this task.

### Four-state fixture contract

`tests/fixtures/SHADOW_RUINS_DAILY/manifest.json` must reference exactly `entry.png`, `actionable.png`, `completed.png`, and `danger.png` and declare:

```json
{
  "schema_version": 1,
  "task_id": "SHADOW_RUINS_DAILY",
  "reference_size": [923, 720],
  "cases": {
    "entry": {"image": "entry.png", "expected_page": "daily", "expected_targets": ["shadow_entry"], "expected_status": null},
    "actionable": {"image": "actionable.png", "expected_page": "shadow_stage", "expected_targets": ["shadow_foreground_anchor"], "expected_status": null},
    "completed": {"image": "completed.png", "expected_page": "daily", "expected_targets": ["shadow_daily_complete"], "expected_status": "already_complete"},
    "danger": {"image": "danger.png", "expected_page": "shadow_popup", "expected_targets": ["unknown_dialog"], "expected_status": "blocked_safety"}
  }
}
```

The actionable image must exercise same-frame page plus target evidence. The danger image must contain a stop signal and must prove zero input calls.

### 2–5 minute foreground checklist

Run: `install/.venv/bin/python -m tools.run_cli --task shadow_ruins_daily`

- [ ] 0:00–0:45: bring the game to the foreground through the existing lifecycle and record the prepared window ID and current MAA capture size from calibration.
- [ ] 0:45–1:30: open the daily row and Shadow popup; capture the popup before input and verify the `前往` target is uniquely labeled.
- [ ] 1:30–2:15: click direct `前往` only after page+target authorization; save same-frame before evidence and after-navigation evidence.
- [ ] 2:15–3:15: on the recognized stage page, execute one complete left/center/right mapped-anchor round; record reference and mapped anchors and the visible result after each anchor.
- [ ] 3:15–4:00: stop after one round for this calibration check, return safely, and verify the daily row or record the exact blocked branch. Do not claim task completion from this calibration check unless the daily postcondition is visible.

### Live evidence, no-op, and independent postcondition

The live run uses a fresh run created by `RunDiagnostics`, with evidence at `diagnostics/YYYY-MM-DD/SHADOW_RUINS_DAILY/run-id/`. Every side-effect record must include page and target evidence from one frame; each round trace includes `reference_anchor`, `mapped_anchor`, `reference_size`, `capture_size`, and the result after `left`, `center`, and `right`. The final success evidence includes stage exit plus the daily-row completion marker.

If direct navigation is unavailable and the exact navigation-error text cannot be observed, runtime returns `failed` with `error_code="SHADOW_NAVIGATION_UNCONFIRMED"`; the later aggregate admission record at `verification/tasks/SHADOW_RUINS_DAILY.json` must remain `live_pending`, and no fallback input is allowed. If the task is already complete, re-run when conditions allow; expected result is `already_complete`, zero anchor actions, and a visible daily postcondition. If the live game is unavailable, keep the deterministic fixture result separate from live verification.

Independent postcondition: with a fake driver, the definition plus canonical runner performs no more than 20 rounds, never invokes fallback without the exact error, and returns `completed` only when the daily postcondition is recognized after stage exit.

```bash
install/.venv/bin/python -m pytest tests/workflows/test_shadow_ruins_daily.py \
  tests/test_fixture_contract.py \
  tests/test_validate_fixtures.py -q
install/.venv/bin/python -m ruff check agent/workflows/definitions/shadow_ruins_daily.py \
  tests/workflows/test_shadow_ruins_daily.py
git diff --check
```

```bash
git add -- agent/workflows/definitions/shadow_ruins_daily.py \
  agent/workflows/definitions/__init__.py agent/workflows/registry.py \
  assets/resource/pipeline/daily/shadow_ruins_daily.json \
  assets/resource/image/daily/SHADOW_RUINS_DAILY/shadow_entry.png \
  assets/resource/image/daily/SHADOW_RUINS_DAILY/shadow_stage.png \
  assets/resource/image/daily/SHADOW_RUINS_DAILY/shadow_daily_complete.png \
  tests/workflows/test_shadow_ruins_daily.py \
  tests/fixtures/SHADOW_RUINS_DAILY/manifest.json \
  tests/fixtures/SHADOW_RUINS_DAILY/entry.png \
  tests/fixtures/SHADOW_RUINS_DAILY/actionable.png \
  tests/fixtures/SHADOW_RUINS_DAILY/completed.png \
  tests/fixtures/SHADOW_RUINS_DAILY/danger.png
git commit -m "feat: add bounded Shadow Ruins daily workflow"
```

### Task 3: Implement JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY with one purchase and safe-count planning

**Files:**

- Create: `agent/workflows/definitions/jianlin_resource_condensate_stamina_daily.py`
- Update: `agent/workflows/definitions/__init__.py`
- Update: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`
- Create from current calibrated captures: `assets/resource/image/daily/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/jianlin_entry.png`
- Create from current calibrated captures: `assets/resource/image/daily/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/jianlin_resource_page.png`
- Create from current calibrated captures: `assets/resource/image/daily/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/jianlin_daily_complete.png`
- Create: `tests/workflows/test_jianlin_resource_condensate_stamina_daily.py`
- Create: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/manifest.json`
- Create from approved captures: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/entry.png`
- Create from approved captures: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/actionable.png`
- Create from approved captures: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/completed.png`
- Create from approved captures: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/danger.png`
- Consume without changing: `agent/workflows/models.py`, `agent/safety.py`, `agent/workflows/engine.py`, `agent/actions/daily_workflow.py`, `agent/diagnostics.py`, `assets/resource/calibration.json`

**Interfaces:**

- Consumes: `StateSnapshot`, `Decision`, `Transition`, `WorkflowDefinition`, `TaskStatus`, `ActionIntent`, `run_workflow(...)`, and the exact `紫色魂玉` exception in `authorize_action(...)`.
- Produces: `JianlinResourceCondensateStaminaDailyDefinition.recognizers(state: str) -> tuple[str, ...]`, `JianlinResourceCondensateStaminaDailyDefinition.decide(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision`, `plan_safe_challenge(stamina: int, cost: int, visible_max: int, safe_multipliers: tuple[int, ...]) -> ChallengePlan`, `decide_jianlin_active_branch(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision`, registry key `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`, and Pipeline entry `MJA_Daily_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`.

```python
@dataclass(frozen=True, slots=True)
class ChallengePlan:
    count: int
    multiplier: int

def plan_safe_challenge(
    stamina: int,
    cost: int,
    visible_max: int,
    safe_multipliers: tuple[int, ...],
) -> ChallengePlan:
    if stamina < 0 or cost <= 0 or visible_max <= 0 or not safe_multipliers:
        raise ValueError("unsafe challenge inputs")
    count = min(stamina // cost, visible_max)
    if count < 1:
        raise ValueError("insufficient stamina")
    return ChallengePlan(count=count, multiplier=max(safe_multipliers))

class JianlinResourceCondensateStaminaDailyDefinition:
    task_id = "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"
    initial_state = "daily_entry"

    def recognizers(self, state: str) -> tuple[str, ...]:
        return JIANLIN_RECOGNIZERS[state]

    def decide(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        completed = snapshot.recognitions["jianlin_daily_complete"].hit_count == 1
        if completed:
            status = TaskStatus.COMPLETED if sum(counters.values()) else TaskStatus.ALREADY_COMPLETE
            return Decision.finish(status, "jianlin_daily_complete")
        return decide_jianlin_active_branch(snapshot, counters)
```

Define `JIANLIN_RECOGNIZERS` and `decide_jianlin_active_branch(...)` in the same module. The active branch emits only policy-listed `ActionIntent` values, including shared navigation plus `buy_stamina_once` with `approved_resource="紫色魂玉"`, `set_safe_count`, `set_safe_multiplier`, `challenge_condensate` with `approved_resource="体力"`, and `close_condensate_result`; it rejects a second purchase, calls `plan_safe_challenge` before every cycle, and returns `JIANLIN_CHALLENGE_CAP` when 12 cycles are exhausted without the daily postcondition. Final daily verification is recognition-only and emits no intent. The definition never performs input directly or invents a purchase result type.

### Red-green implementation sequence

- [ ] **Step 1, 3 minutes: write failing purchase tests.** Require exactly one authorized purchase intent, target text containing `+80` and `10 紫色魂玉`, an approved resource of `紫色魂玉`, and a postcondition that stamina increased by 80. Before implementation, expect a failure for missing one-purchase guard.

- [ ] **Step 2, 3 minutes: write failing planner tests.** Given current stamina, per-run cost, visible maximum count, and visible safe multipliers, require `count = min(floor(stamina / cost), visible_max)` and the highest safe multiplier. Require no `x1` fallback when the bar cannot be confirmed changed; require a hard stop at 12 challenge cycles. Before implementation, expect count/multiplier assertion failures.

- [ ] **Step 3, 2 minutes: write failing danger tests.** A recharge, purchase, unknown-currency, login, verification, or ambiguous control snapshot must return canonical `blocked_safety` without input. Before implementation, expect the fake driver to observe an unauthorized action.

- [ ] **Step 4: implement the minimum resource policy.** Open the daily entry, enter 剑林 / 养成, select 资源 and 凝晶. Authorize the stamina plus target only when the same frame proves the prompt says exactly `+80` for exactly `10 紫色魂玉`; increment `buy_stamina_once` once and reject a second attempt. The one purchase is performed once per task run when the prompt is available, including when stamina is already sufficient.

```json
{
  "MJA_Daily_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY"}
  },
  "jianlin_stamina_amount": {
    "recognition": "OCR",
    "expected": ["+80"],
    "action": "DoNothing"
  },
  "jianlin_stamina_cost": {
    "recognition": "OCR",
    "expected": ["10"],
    "action": "DoNothing"
  },
  "jianlin_stamina_resource": {
    "recognition": "OCR",
    "expected": ["紫色魂玉"],
    "action": "DoNothing"
  }
}
```

The driver queries all three OCR nodes against the same immutable prompt frame and builds one `VisualEvidence` record. Only the root node starts `DailyWorkflowAction`; the OCR, count-control, multiplier-control, result, and daily-postcondition nodes remain `DoNothing` recognizers.

- [ ] **Step 5: implement safe count and multiplier selection.** Read the current stamina and `消耗体力` from the recognized resource page. Compute the maximum safe count, capped by the page maximum and 12 total challenge cycles. Set the count bar, recapture, and confirm the displayed `xN`; then set the highest safe multiplier bar, recapture, and confirm the displayed multiplier. If either control does not change after one latest-frame retry, return `blocked_safety` or `failed` according to the canonical safety decision; never issue repeated `x1` runs.

- [ ] **Step 6: implement bounded repetition and postcondition.** Before every challenge cycle, recompute safe count and multiplier. Challenge only when the same frame proves sufficient stamina and no paid/refill/unknown prompt. Stop when remaining stamina is below the next safe cost, when the daily postcondition is visible, or at 12 cycles. Reaching a cap without a verified daily postcondition is `failed`, not `completed`. Return to daily and verify the stamina row; do not claim the row reward.

### Four-state fixture contract

`tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/manifest.json` uses the same exact four filenames and declares:

```json
{
  "schema_version": 1,
  "task_id": "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
  "reference_size": [923, 720],
  "cases": {
    "entry": {"image": "entry.png", "expected_page": "daily", "expected_targets": ["jianlin_entry"], "expected_status": null},
    "actionable": {"image": "actionable.png", "expected_page": "jianlin_resource", "expected_targets": ["buy_plus_80_for_10_purple_soul_jade", "safe_count", "safe_multiplier"], "expected_status": null},
    "completed": {"image": "completed.png", "expected_page": "daily", "expected_targets": ["jianlin_daily_complete"], "expected_status": "already_complete"},
    "danger": {"image": "danger.png", "expected_page": "jianlin_stamina_purchase", "expected_targets": ["unknown_currency_or_refill"], "expected_status": "blocked_safety"}
  }
}
```

The actionable fixture must prove the purchase amount/resource and the displayed count/multiplier labels. It must not be used as evidence that a purchase happened.

### 2–5 minute foreground checklist

Run: `install/.venv/bin/python -m tools.run_cli --task jianlin_resource_condensate_stamina_daily`

- [ ] 0:00–0:45: foreground the game, open the daily entry, and capture the Jianlin resource page before any purchase or challenge input.
- [ ] 0:45–1:30: open the stamina prompt and verify the same frame contains `+80` and `10 紫色魂玉`; stop immediately if either is missing.
- [ ] 1:30–2:30: authorize exactly one purchase, capture the stamina delta, then read the current per-run cost and visible count/multiplier limits.
- [ ] 2:30–3:30: set the maximum safe count and highest safe multiplier, recapture after each bar action, and record displayed `xN`, multiplier, cost, and remaining stamina.
- [ ] 3:30–4:30: execute at most one challenge cycle for calibration, verify the result page, and return to the daily row without claiming its reward.

### Live evidence, no-op, and independent postcondition

Evidence is under `diagnostics/YYYY-MM-DD/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/run-id/`. Each purchase, bar change, and challenge has same-frame page+target evidence and a postcondition frame. The purchase trace must show one `+80` event, `10 紫色魂玉`, before/after stamina, and purchase count one. Each challenge trace records safe count, multiplier, per-run cost, remaining stamina, cycle number, and result page. A second purchase, refill, unknown currency, login, or verification prompt is a hard stop.

When the daily row is already complete, a no-op rerun must return `already_complete` with zero purchase and challenge inputs and a visible daily postcondition. A paid/refill/unknown/ambiguous prompt returns `blocked_safety`; a count or multiplier control that fails its one-retry postcondition returns `failed` with `error_code="JIANLIN_CONTROL_UNCHANGED"`. In either unverified live branch, the later aggregate admission record at `verification/tasks/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json` must remain `live_pending`; do not report a `TaskResult` pass from fixtures.

Independent postcondition: fake-driver execution proves one purchase maximum, no `x1` fallback, maximum 12 challenge cycles, no challenge below safe cost, and `completed` only after the daily stamina postcondition.

```bash
install/.venv/bin/python -m pytest tests/workflows/test_jianlin_resource_condensate_stamina_daily.py \
  tests/test_fixture_contract.py \
  tests/test_validate_fixtures.py -q
install/.venv/bin/python -m ruff check agent/workflows/definitions/jianlin_resource_condensate_stamina_daily.py \
  tests/workflows/test_jianlin_resource_condensate_stamina_daily.py
git diff --check
```

```bash
git add -- agent/workflows/definitions/jianlin_resource_condensate_stamina_daily.py \
  agent/workflows/definitions/__init__.py agent/workflows/registry.py \
  assets/resource/pipeline/daily/jianlin_resource_condensate_stamina_daily.json \
  assets/resource/image/daily/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/jianlin_entry.png \
  assets/resource/image/daily/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/jianlin_resource_page.png \
  assets/resource/image/daily/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/jianlin_daily_complete.png \
  tests/workflows/test_jianlin_resource_condensate_stamina_daily.py \
  tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/manifest.json \
  tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/entry.png \
  tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/actionable.png \
  tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/completed.png \
  tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/danger.png
git commit -m "feat: add bounded Jianlin stamina workflow"
```

### Task 4: Implement RING_CHALLENGE_DAILY with labeled score branching

**Files:**

- Create: `agent/workflows/definitions/ring_challenge_daily.py`
- Update: `agent/workflows/definitions/__init__.py`
- Update: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/ring_challenge_daily.json`
- Create from current calibrated captures: `assets/resource/image/daily/RING_CHALLENGE_DAILY/ring_entry.png`
- Create from current calibrated captures: `assets/resource/image/daily/RING_CHALLENGE_DAILY/ring_page.png`
- Create from current calibrated captures: `assets/resource/image/daily/RING_CHALLENGE_DAILY/ring_daily_complete.png`
- Create: `tests/workflows/test_ring_challenge_daily.py`
- Create: `tests/fixtures/RING_CHALLENGE_DAILY/manifest.json`
- Create from approved captures: `tests/fixtures/RING_CHALLENGE_DAILY/entry.png`
- Create from approved captures: `tests/fixtures/RING_CHALLENGE_DAILY/actionable.png`
- Create from approved captures: `tests/fixtures/RING_CHALLENGE_DAILY/completed.png`
- Create from approved captures: `tests/fixtures/RING_CHALLENGE_DAILY/danger.png`
- Consume without changing: `agent/workflows/models.py`, `agent/safety.py`, `agent/workflows/engine.py`, `agent/actions/daily_workflow.py`, `agent/diagnostics.py`, `assets/resource/calibration.json`

**Interfaces:**

- Consumes: `StateSnapshot`, `Decision`, `Transition`, `WorkflowDefinition`, `TaskStatus`, `ActionIntent`, `run_workflow(...)`, and `authorize_action(...)`.
- Produces: `RingMode(StrEnum)`, `choose_ring_mode(*, master_mode: bool, master_rank: bool, labeled_score: int | None) -> RingMode`, `decide_ring_active_branch(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision`, `RingChallengeDailyDefinition.recognizers(state: str) -> tuple[str, ...]`, `RingChallengeDailyDefinition.decide(snapshot: StateSnapshot, counters: Mapping[str, int]) -> Decision`, registry key `RING_CHALLENGE_DAILY`, and Pipeline entry `MJA_Daily_RING_CHALLENGE_DAILY`.

```python
class RingMode(StrEnum):
    FIGHT = "fight"
    SWEEP = "sweep"

def choose_ring_mode(
    *,
    master_mode: bool,
    master_rank: bool,
    labeled_score: int | None,
) -> RingMode:
    if master_mode and master_rank:
        return RingMode.SWEEP
    if labeled_score is None:
        raise ValueError("labeled ring score required")
    return RingMode.FIGHT if labeled_score < 5000 else RingMode.SWEEP

class RingChallengeDailyDefinition:
    task_id = "RING_CHALLENGE_DAILY"
    initial_state = "daily_entry"

    def recognizers(self, state: str) -> tuple[str, ...]:
        return RING_RECOGNIZERS[state]

    def decide(
        self,
        snapshot: StateSnapshot,
        counters: Mapping[str, int],
    ) -> Decision:
        completed = snapshot.recognitions["ring_daily_complete"].hit_count == 1
        if completed:
            status = TaskStatus.COMPLETED if sum(counters.values()) else TaskStatus.ALREADY_COMPLETE
            return Decision.finish(status, "ring_daily_complete")
        return decide_ring_active_branch(snapshot, counters)
```

Define `RING_RECOGNIZERS` and `decide_ring_active_branch(...)` in the same module. The active branch parses only the OCR group attached to `labeled_ring_score`, calls `choose_ring_mode`, emits `ring_fight` until all 12 visible attempts are consumed or emits one `ring_sweep`, and returns `RING_SCORE_UNLABELED` or `RING_ACTION_CAP` instead of guessing.

### Red-green implementation sequence

- [ ] **Step 1, 3 minutes: write failing score tests.** Supply snapshots containing a labeled `擂台积分` value, a top-right currency value, and a ticket count. Require the labeled score to control the branch and the currency to be rejected. Before implementation, expect a score-source assertion failure.

- [ ] **Step 2, 2 minutes: write failing mode tests.** Require `大师赛模式` plus `大师排名` to authorize sweep even when the top-right currency has an unrelated value. Require absent mode and labeled score below 5000 to select fight, and labeled score at least 5000 to select sweep.

- [ ] **Step 3, 3 minutes: write failing cap and safety tests.** Require fight attempts `12 -> 0`, sweep cap one, no input when score is unlabeled/ambiguous, and no input on paid, login, verification, or unknown-currency evidence. Before implementation, expect cap and blocked-safety failures.

- [ ] **Step 4: implement the minimum score recognizer and branch.** Enter the ring page, read the lower-left mode/rank first, then read only an explicitly labeled current ring score. Never parse a top-right currency or ticket count as score.

```json
{
  "MJA_Daily_RING_CHALLENGE_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "RING_CHALLENGE_DAILY"}
  },
  "ring_read_labeled_score": {
    "recognition": "OCR",
    "expected": ["擂台积分", "当前擂台积分", "积分"],
    "action": "DoNothing"
  },
  "ring_master_mode": {
    "recognition": "OCR",
    "expected": ["大师赛模式", "大师排名"],
    "action": "DoNothing"
  }
}
```

The calibrated labeled-score OCR region excludes top-right currency and ticket counters. Python parses digits only from the OCR item that contains the accepted score label. Fight, sweep, opponent, result, and daily-row nodes are also recognition-only; the root is the sole `DailyWorkflowAction` node.

- [ ] **Step 5: implement fight and sweep branches.** If `大师赛模式` with `大师排名` is recognized, choose sweep. Otherwise, if labeled score is below 5000, repeatedly select a visible opponent and challenge until `0/12`; close only expected non-purchase result overlays and verify each attempt transition. If labeled score is at least 5000, choose sweep with `ActionIntent.approved_resource="擂台券"` only when the same frame proves the exact ticket counter, then verify its decrease. A missing labeled score is `blocked_safety`, not a guess.

- [ ] **Step 6: implement final daily verification.** Return to the daily page and verify `挑战一次擂台` complete or claimable without pressing its reward button. A 12-fight cap without that postcondition is `failed`; a successful sweep also requires the sweep result and daily-row evidence.

### Four-state fixture contract

`tests/fixtures/RING_CHALLENGE_DAILY/manifest.json` uses exactly four PNGs:

```json
{
  "schema_version": 1,
  "task_id": "RING_CHALLENGE_DAILY",
  "reference_size": [923, 720],
  "cases": {
    "entry": {"image": "entry.png", "expected_page": "daily", "expected_targets": ["ring_entry"], "expected_status": null},
    "actionable": {"image": "actionable.png", "expected_page": "ring_page", "expected_targets": ["labeled_ring_score", "ring_fight_or_sweep"], "expected_status": null},
    "completed": {"image": "completed.png", "expected_page": "daily", "expected_targets": ["ring_daily_complete"], "expected_status": "already_complete"},
    "danger": {"image": "danger.png", "expected_page": "ring_page", "expected_targets": ["unlabeled_currency_only_or_unknown_dialog"], "expected_status": "blocked_safety"}
  }
}
```

The actionable fixture must contain a labeled score and a visually separate currency/ticket region so the test proves the recognizer does not use currency as score. The danger fixture must be rejected before any fight or sweep.

### 2–5 minute foreground checklist

Run: `install/.venv/bin/python -m tools.run_cli --task ring_challenge_daily`

- [ ] 0:00–0:45: foreground the game and open `挑战一次擂台` from the daily page; capture the ring page before input.
- [ ] 0:45–1:30: inspect lower-left mode/rank and locate the explicit score label; record the top-right currency as a rejected non-score field.
- [ ] 1:30–2:15: authorize exactly the branch selected by mode or labeled score; do not click fight or sweep if the score label is absent.
- [ ] 2:15–3:30: for the fight branch, complete one opponent selection and one match, recording attempt count and result; for the sweep branch, verify the sweep target and result.
- [ ] 3:30–4:30: return to daily and verify the row without claiming it; record `live_pending` if the current mode/score branch cannot be safely confirmed.

### Live evidence, no-op, and independent postcondition

Evidence is under `diagnostics/YYYY-MM-DD/RING_CHALLENGE_DAILY/run-id/`. Each fight or sweep has same-frame ring-page plus opponent/action target evidence, a post-action result frame, and an updated attempt or ticket count. The trace must explicitly include `score_source="labeled_ring_score"`; the top-right currency and ticket count are recorded as rejected fields when visible. Fight evidence must show all transitions from `12/12` to `0/12`.

If score OCR is unavailable or ambiguous outside the independently proven master-mode branch, runtime returns `blocked_safety` with `error_code="RING_SCORE_UNLABELED"`; the later aggregate admission record at `verification/tasks/RING_CHALLENGE_DAILY.json` must remain `live_pending`, and no fight or sweep input occurs. When the daily row is already complete, a no-op rerun returns `already_complete` with zero fight/sweep inputs and a visible row postcondition.

Independent postcondition: fake-driver tests prove labeled-score-only branching, master-mode precedence, 12-fight maximum, one sweep maximum, and canonical `failed` when a cap is reached without daily verification.

```bash
install/.venv/bin/python -m pytest tests/workflows/test_ring_challenge_daily.py \
  tests/test_fixture_contract.py \
  tests/test_validate_fixtures.py -q
install/.venv/bin/python -m ruff check agent/workflows/definitions/ring_challenge_daily.py \
  tests/workflows/test_ring_challenge_daily.py
git diff --check
```

```bash
git add -- agent/workflows/definitions/ring_challenge_daily.py \
  agent/workflows/definitions/__init__.py agent/workflows/registry.py \
  assets/resource/pipeline/daily/ring_challenge_daily.json \
  assets/resource/image/daily/RING_CHALLENGE_DAILY/ring_entry.png \
  assets/resource/image/daily/RING_CHALLENGE_DAILY/ring_page.png \
  assets/resource/image/daily/RING_CHALLENGE_DAILY/ring_daily_complete.png \
  tests/workflows/test_ring_challenge_daily.py \
  tests/fixtures/RING_CHALLENGE_DAILY/manifest.json \
  tests/fixtures/RING_CHALLENGE_DAILY/entry.png \
  tests/fixtures/RING_CHALLENGE_DAILY/actionable.png \
  tests/fixtures/RING_CHALLENGE_DAILY/completed.png \
  tests/fixtures/RING_CHALLENGE_DAILY/danger.png
git commit -m "feat: add labeled-score Ring challenge workflow"
```

### Task 5: Register the three tasks incrementally through ProjectInterface and the existing CLI contract

**Files:**

- Update: `assets/interface.json`
- Update: `tests/test_project_interface_generation.py`
- Update: `tests/test_run_cli.py`
- Update: `tests/test_verify_install.py`
- Consume without changing: `tools/project_interface.py`
- Consume without changing: `tools/run_cli.py`
- Consume without changing: `agent/actions/daily_workflow.py`
- Consume without changing: `agent/workflows/catalog.py`
- Consume without changing: `agent/workflows/registry.py`

**Interfaces:**

- Consumes: `task_entry(policy: TaskPolicy) -> dict[str, Any]`, `render_interface(base: Mapping[str, Any], *, implemented_task_ids: Sequence[str]) -> dict[str, Any]`, `verify_workflow_assets(project_root: Path) -> list[str]`, and `run_cli(lifecycle: Lifecycle, *, install_root: str | Path = Path("install"), task_name: str = "mail_smoke_test", launch: Callable[[], None] | None = None, spawn: Callable[[Sequence[str]], ChildProcess] | None = None) -> int` from the foundation.
- Produces: three reviewed task objects in `assets/interface.json`; no new Python runtime interface.

Do not redefine `run_cli`, add a `no_op_if_complete` parameter, append raw JSON by hand, add hidden task registrations, or create another custom action signature. The existing `--task` selection contract validates the selected assembled ProjectInterface entry before lifecycle preparation, while preserving `prepare`, `SIGINT`, and `finally` restoration behavior.

### Red-green implementation sequence

- [ ] **Step 1, 3 minutes: add failing renderer tests.** Pass the three canonical IDs to `render_interface` and require deterministic catalog order, exact task names, `default_check: false` until live verification, `mja`/`macos` resource/controller references, and pipeline names beginning with `MJA_Daily_` followed by the canonical ID. Before implementation or catalog registration, expect missing-entry assertions.

```python
def test_render_batch3_entries_in_catalog_order(base_interface: dict[str, object]) -> None:
    rendered = render_interface(
        base_interface,
        implemented_task_ids=[
            "SHADOW_RUINS_DAILY",
            "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
            "RING_CHALLENGE_DAILY",
        ],
    )
    entries = {item["name"]: item for item in rendered["task"]}
    assert entries["shadow_ruins_daily"]["entry"] == "MJA_Daily_SHADOW_RUINS_DAILY"
    assert entries["jianlin_resource_condensate_stamina_daily"]["default_check"] is False
    assert entries["ring_challenge_daily"]["resource"] == ["mja"]
    assert entries["ring_challenge_daily"]["controller"] == ["macos"]
```

- [ ] **Step 2, 2 minutes: add failing CLI contract tests.** Exercise the already defined `run_cli(lifecycle, task_name="ring_challenge_daily", install_root=tmp_path)` with each registered task and an unknown task. Expected precondition failure is an interface validation error for the unknown task; no new signature test is required because this task must not change `tools/run_cli.py`.

- [ ] **Step 3: render incrementally.** Invoke `tools.project_interface.render_interface` with the existing interface as `base` and exactly the three implemented canonical IDs. Review the generated mapping and write the reviewed result into `assets/interface.json` using the project’s normal explicit file-update path. The plan must not direct an implementer to append entries after `mail_smoke_test` manually.

```python
base = json.loads(Path("assets/interface.json").read_text(encoding="utf-8"))
rendered = render_interface(
    base,
    implemented_task_ids=[
        "SHADOW_RUINS_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "RING_CHALLENGE_DAILY",
    ],
)
assert [item["name"] for item in rendered["task"]][-3:] == [
    "shadow_ruins_daily",
    "jianlin_resource_condensate_stamina_daily",
    "ring_challenge_daily",
]
```

- [ ] **Step 4: verify task selection and install assets.** Run the existing CLI with `--task` for each canonical task after reassembling the install. Verify that task selection occurs before launch, `maa_pi_config.json` uses the selected pipeline, and `MaaPiCli -d` remains launched from the install cwd through the existing lifecycle implementation. This task does not alter `tools/run_cli.py`.

- [ ] **Step 5: run focused integration tests.**

```bash
install/.venv/bin/python -m pytest tests/test_project_interface_generation.py \
  tests/test_run_cli.py tests/test_verify_install.py \
  tests/workflows/test_batch3_catalog.py -q
install/.venv/bin/python -m tools.verify_install install
install/.venv/bin/python -m ruff check tests/test_project_interface_generation.py \
  tests/test_run_cli.py tests/test_verify_install.py
```

Expected: all registered tasks resolve through the canonical registry and the existing CLI contract; no `run_cli` source diff is needed.

### Live selection and no-op

For each task, launch from the foreground host with `--task` and record the selected canonical ID in `diagnostics/YYYY-MM-DD/TASK_ID/run-id/result.json`. If a task is already complete, selection must still run through the same interface and return canonical `already_complete` without task input. If a branch is unavailable, record aggregate `live_pending` only.

Independent postcondition: a clean install lists exactly the three new registered tasks, each task selects the matching `MJA_Daily_` pipeline, an unknown task is rejected before launch, and the mail default remains unchanged.

```bash
git add -- assets/interface.json tests/test_project_interface_generation.py \
  tests/test_run_cli.py tests/test_verify_install.py
git commit -m "feat: register batch 3 through ProjectInterface"
```

### Task 6: Batch 3 focused gate, live evidence review, and handoff

**Files:**

- Create: `docs/verification/mja-daily-workflows-batch-3.md`
- Verify without modifying: `agent/workflows/models.py`
- Verify without modifying: `agent/safety.py`
- Verify without modifying: `agent/workflows/engine.py`
- Verify without modifying: `agent/actions/daily_workflow.py`
- Verify without modifying: `agent/diagnostics.py`
- Verify without modifying: `tools/project_interface.py`
- Verify without modifying: `tools/run_cli.py`

**Interfaces:** none.

### Red-green and gate sequence

- [ ] **Step 1, 5 minutes: run the complete focused red-green gate.**

```bash
install/.venv/bin/python -m pytest \
  tests/workflows/test_batch3_catalog.py \
  tests/workflows/test_shadow_ruins_daily.py \
  tests/workflows/test_jianlin_resource_condensate_stamina_daily.py \
  tests/workflows/test_ring_challenge_daily.py \
  tests/test_project_interface_generation.py \
  tests/test_run_cli.py tests/test_verify_install.py \
  tests/test_fixture_contract.py tests/test_validate_fixtures.py -q
install/.venv/bin/python -m tools.validate_fixtures --all-implemented
install/.venv/bin/python -m tools.verify_install install
install/.venv/bin/python -m ruff check agent tools tests
git diff --check
```

Expected: all deterministic checks pass; every fixture uses the four exact PNG kinds; no standard input action, hidden registration, or extra runtime status is present.

- [ ] **Step 2: review live evidence by task.** Confirm each side-effect page and target has same-frame double evidence, each result has an after frame, failures have a failure frame, and each final task has a daily postcondition. Confirm Shadow traces both reference and mapped anchors and never use stale coordinates; Jianlin proves one purchase and safe count/multiplier; Ring proves labeled score rather than currency.

- [ ] **Step 3: run foreground acceptance only when safe.** Use the prepared foreground game and the existing lifecycle. Run each selected task once, never in parallel. Do not claim success when a required branch cannot be observed. Document the unavailable branch in prose so the later aggregate admission task creates or keeps `verification/tasks/{TASK_ID}.json` at `live_pending`; the Markdown document never becomes a second machine record.

- [ ] **Step 4: perform no-op reruns when conditions allow.** Re-run each task after its daily row is already visibly complete. Expected status is `already_complete`, zero side effects, and a visible completed-row postcondition. Record this in the task’s canonical diagnostics directory.

- [ ] **Step 5: document exact evidence and limitations.** Write commands, checkout revision, current calibration size, task ID, run ID, result status, action trace path, fixture path, live evidence path, and any `live_pending` reason into `docs/verification/mja-daily-workflows-batch-3.md`. A fixture result must never be described as live success.

### Final acceptance matrix

| Task ID | Required branch | Required cap | Required final evidence | Unsafe branch |
|---|---|---:|---|---|
| `SHADOW_RUINS_DAILY` | direct popup `前往`; fallback only after exact navigation error; mapped left/center/right anchors | 20 rounds | stage exit plus `完成一次蜃影武墟挑战` | unknown page, missing stage, navigation ambiguity |
| `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | one `+80` for `10 紫色魂玉`; maximum safe count and multiplier; no `x1` fallback | 12 challenge cycles | stamina delta, each challenge result, daily stamina row | paid/refill/unknown currency or unconfirmed controls |
| `RING_CHALLENGE_DAILY` | labeled score; `<5000` fights all attempts; master mode or `>=5000` sweeps | 12 fights or 1 sweep | labeled score/mode, attempts or ticket delta, daily ring row | currency-only score, unlabeled OCR, unknown prompt |

### Exact evidence paths and commit

Every run path has the form:

`diagnostics/YYYY-MM-DD/TASK_ID/run-id/`

The verification document may link to those run directories and to the four-state fixture directories. It must state that `live_pending` is aggregate verification metadata only and does not appear in `TaskResult.status`.

```bash
git add -- docs/verification/mja-daily-workflows-batch-3.md
git commit -m "test: record Batch 3 workflow verification"
```

## Self-review checklist before execution handoff

- [ ] Capture, foundation, Batch 1, and Batch 2 are explicit prerequisites.
- [ ] The only runtime statuses are `completed`, `already_complete`, `not_eligible`, `blocked_safety`, and `failed`; `live_pending` appears only in aggregate verification records.
- [ ] All three workflows consume `TaskPolicy`, `TaskStatus`, `TaskResult`, `VisualEvidence`, `ActionIntent`, `authorize_action`, `run_workflow`, `DailyWorkflowAction`, and `RunDiagnostics`.
- [ ] There is no Batch 3 runner, state enum, result type, evidence type, or custom replacement for `run_cli`.
- [ ] No fixed capture resolution appears; calibration data drives every crop and mapped input.
- [ ] Shadow uses `984x768` only as reference size, maps all three historical anchors, records reference and mapped values, and authorizes only on a recognized stage page.
- [ ] Business truth is only `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py`; calibration evidence is only `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa`.
- [ ] Fixtures use exactly `tests/fixtures/{canonical task ID}/manifest.json` plus `entry.png`, `actionable.png`, `completed.png`, and `danger.png`.
- [ ] Diagnostics use exactly `diagnostics/YYYY-MM-DD/TASK_ID/run-id/`.
- [ ] Every side effect has same-frame page and target evidence, a postcondition, and a failure path.
- [ ] Every task has a 2–5 minute foreground checklist, red-green tests, minimum code or JSON, four-state fixtures, live evidence, independent postcondition, and no-op rerun.
- [ ] Every `git add` uses `git add --` with explicit file paths; no command stages `AGENTS.md` or a broad directory.
- [ ] No claim of live success is made for an unavailable branch.
