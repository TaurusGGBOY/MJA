# MJA Daily Workflow Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide the typed catalog, same-frame safety gate, bounded workflow runner, safe foreground inputs, shared navigation, structured diagnostics, fixture harness, and ProjectInterface generation needed to implement and independently verify all 17 Jianzhichuan daily tasks.

**Architecture:** Keep recognition declarative in Maa pipeline JSON and execute every input through a Python custom action that reuses the recognizer's source frame. A task catalog describes permitted pages, actions, postconditions, resource counters, and hard limits. Simple tasks use a shared state-machine runner backed by pipeline recognizers; dynamic tasks plug deterministic transition functions into the same runner. Diagnostics and fixture validation use the same result/status model as live runs.

**Tech Stack:** Python 3.14, MaaFramework Python Agent API 5.12.2, ProjectInterface V2 JSON, Maa pipeline JSON, Pillow/NumPy, PyObjC/AppKit/Quartz, cliclick, pytest, Ruff.

## Global Constraints

- Complete the macOS capture-fallback plan before running this plan's live checks.
- Never stage or commit `AGENTS.md`; use the exact path-scoped `git add` commands in each task.
- `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py` is the business source of truth. The old `jianzhichuan_maa` implementation supplies only calibration and failure evidence.
- No action may run unless one immutable screenshot proves both the expected page and exactly one permitted target state.
- `¥`, `￥`, Apple Pay, payment, recharge, paid/premium bundles, login/security verification, and unknown currency are hard stops. Generic `购买` text is treated as unknown currency unless the task policy names the exact stored resource and the same frame proves that resource; unconditional paid signals can never be overridden.
- Do not send keyboard events. Do not use global absolute game coordinates; stable relative anchors are allowed only after the owning page marker is recognized and must be recorded in the action trace.
- Every loop has a task-level maximum step count and action-specific counters. Reaching a cap without the postcondition returns `failed` and produces evidence.
- Runtime statuses are exactly `completed`, `already_complete`, `not_eligible`, `blocked_safety`, and `failed`.
- Generated diagnostics remain ignored under `diagnostics/`; committed fixture manifests and fixture PNGs live under `tests/fixtures/`.
- Use one repository layout across all batches: definitions in `agent/workflows/definitions/{lowercase task ID}.py`, pipelines in `assets/resource/pipeline/daily/{lowercase task ID}.json`, templates in `assets/resource/image/daily/{canonical task ID}/`, fixtures in `tests/fixtures/{canonical task ID}/`, and focused tests in `tests/workflows/test_{lowercase task ID}.py`.

---

### Task 1: Add the canonical workflow catalog and result types

**Files:**

- Create: `agent/workflows/__init__.py`
- Create: `agent/workflows/models.py`
- Create: `agent/workflows/catalog.py`
- Create: `tests/test_workflow_models.py`
- Create: `tests/test_workflow_catalog.py`

**Interfaces:**

```python
class TaskStatus(StrEnum):
    COMPLETED = "completed"
    ALREADY_COMPLETE = "already_complete"
    NOT_ELIGIBLE = "not_eligible"
    BLOCKED_SAFETY = "blocked_safety"
    FAILED = "failed"

class RiskLevel(StrEnum):
    NORMAL = "normal"
    PROTECTED_CLAIM = "protected_claim"
    CONSUMPTIVE = "consumptive"
    STATEFUL = "stateful"
    COMBAT = "combat"

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
```

- [ ] **Step 1: Write failing enum and validation tests**

Assert the exact five serialized statuses; reject an empty task ID, a nonpositive `max_steps`, negative or Boolean caps, unknown action-cap keys, and an approved resource not used by the task. Assert `TaskResult` accepts no status aliases.

- [ ] **Step 2: Run the model tests and confirm import failure**

Run: `install/.venv/bin/python -m pytest tests/test_workflow_models.py -q`

Expected: FAIL because `agent.workflows.models` does not exist.

- [ ] **Step 3: Implement immutable models with constructor validation**

Use `MappingProxyType` for stored cap/action mappings and normalize all task IDs to their canonical uppercase form. Keep JSON serialization in an explicit `as_dict()` method so enums serialize to their values and mappings serialize to ordinary dictionaries.

- [ ] **Step 4: Write the 17-entry catalog test**

Assert this exact order:

```python
EXPECTED_TASK_IDS = (
    "MAIL_REWARD_DAILY",
    "SHOP_FREE_GIFT_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "TRIAL_SWORD_DAILY",
    "FREE_APPRAISAL_DAILY",
    "BUY_TEA_DAILY",
    "COLLECTION_DEPLOYMENT_DAILY",
    "HERO_DISPATCH_DAILY",
    "SHADOW_RUINS_DAILY",
    "SPEND_CONDENSATE_DAILY",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "EAT_STAMINA_FOOD_DAILY",
    "DUNGEON_SWEEP_DAILY",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "RING_CHALLENGE_DAILY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
)
```

Also assert weekly eligibility is `{0}`, every consumptive/combat task has relevant action caps, and no task approves a real-money resource.

- [ ] **Step 5: Run the catalog test and confirm the absent catalog failure**

Run: `install/.venv/bin/python -m pytest tests/test_workflow_catalog.py -q`

Expected: FAIL because the catalog is not implemented.

- [ ] **Step 6: Implement the catalog with conservative initial caps**

Set every catalog entry to `MJA_Daily_{TASK_ID}`. Use exact known limits where authoritative: dispatch `6`, food `6`, ring challenge `12`, stamina purchase `1`, martial study retry per slot `3`. Give every remaining repeatable action a finite cap derived from the stable workflow and make later batch plans tighten it before live execution. `max_steps` must also be finite for every task.

- [ ] **Step 7: Run focused tests and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_workflow_models.py tests/test_workflow_catalog.py -q
install/.venv/bin/python -m ruff check agent/workflows tests/test_workflow_models.py tests/test_workflow_catalog.py
```

Expected: all checks pass.

- [ ] **Step 8: Commit the canonical types and catalog**

```bash
git add -- agent/workflows/__init__.py agent/workflows/models.py \
  agent/workflows/catalog.py tests/test_workflow_models.py tests/test_workflow_catalog.py
git commit -m "feat: define daily workflow catalog and results"
```

### Task 2: Implement same-frame payment and target safety decisions

**Files:**

- Create: `agent/safety.py`
- Create: `tests/test_safety.py`

**Interfaces:**

```python
class SafetyReason(StrEnum):
    ALLOWED = "allowed"
    PAGE_MISSING = "page_missing"
    TARGET_MISSING = "target_missing"
    TARGET_AMBIGUOUS = "target_ambiguous"
    FRAME_MISMATCH = "frame_mismatch"
    PAID_SIGNAL = "paid_signal"
    VERIFICATION_SIGNAL = "verification_signal"
    UNKNOWN_CURRENCY = "unknown_currency"
    UNKNOWN_DIALOG = "unknown_dialog"
    ACTION_CAP_REACHED = "action_cap_reached"

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

@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    reason: SafetyReason
    findings: tuple[str, ...]

def authorize_action(
    evidence: VisualEvidence,
    intent: ActionIntent,
    policy: TaskPolicy,
    action_counts: Mapping[str, int],
) -> SafetyDecision: ...
```

- [ ] **Step 1: Add failing parameterized safety tests**

Cover each reason above and danger strings including `¥`, `￥`, `Apple Pay`, `支付`, `充值`, `月卡`, `付费礼包`, `典藏版`, `登录`, `验证码`, `安全验证`, and account/password/biometric prompts. Add a same-frame `danger_hits["unknown_dialog"] == 1` case and reject it before action authorization. Add cases proving `购买` is blocked unless the task policy and same frame identify one exact approved stored resource with no paid signal.

- [ ] **Step 2: Run the safety tests**

Run: `install/.venv/bin/python -m pytest tests/test_safety.py -q`

Expected: FAIL because the safety module is absent.

- [ ] **Step 3: Implement normalized OCR scanning**

Normalize Unicode width and whitespace, retain original text in findings, deduplicate identical findings, and treat generic purchase/currency-like text that is neither an approved stored resource nor explicitly free as `UNKNOWN_CURRENCY`. Classify `¥`, `￥`, Apple Pay, payment, recharge, paid/premium bundles, and login/security signals separately as unconditional blocks.

- [ ] **Step 4: Implement page/target/resource authorization**

Require a hit count of exactly one for `page_marker` and `target_marker`, and require both entries in `recognizer_frame_ids` to equal `evidence.frame_id`. Reject every nonzero `danger_hits` entry and require its recognizer frame ID to match before classifying it; a mismatched danger recognizer is itself `FRAME_MISMATCH`. Check unconditional paid/verification/unknown-dialog findings first. Resolve generic purchase/unknown-currency findings only when `approved_resource` is in both `policy.approved_resources` and `evidence.resource_hits` and that resource recognizer's frame ID also equals `evidence.frame_id`; the exception never overrides an unconditional finding.

- [ ] **Step 5: Implement action-cap enforcement**

Reject an action when `action_counts[action_id] >= policy.action_caps[action_id]`; reject intents whose action ID is absent from policy instead of treating them as unlimited.

- [ ] **Step 6: Run focused and full tests**

```bash
install/.venv/bin/python -m pytest tests/test_safety.py -q
install/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the safety gate**

```bash
git add -- agent/safety.py tests/test_safety.py
git commit -m "feat: gate workflow actions with same-frame evidence"
```

### Task 3: Generalize safe foreground input to click, swipe, and long press

**Files:**

- Create: `agent/actions/macos_foreground_input.py`
- Update: `agent/actions/macos_foreground_click.py`
- Update: `agent/actions/__init__.py`
- Update: `agent/main.py`
- Create: `tests/test_macos_foreground_input.py`
- Update: `tests/test_macos_foreground_click.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class PreparedInput:
    window_id: int
    pid: int
    capture_size: tuple[int, int]
    window_bounds: tuple[int, int, int, int]

class ForegroundInputExecutor:
    def click(self, box: Sequence[int], prepared: PreparedInput) -> None: ...
    def swipe(
        self,
        start_box: Sequence[int],
        end_box: Sequence[int],
        duration_ms: int,
        prepared: PreparedInput,
    ) -> None: ...
    def long_press(
        self,
        box: Sequence[int],
        duration_ms: int,
        prepared: PreparedInput,
    ) -> None: ...
```

Registered Maa names remain `MacOSForegroundClick`, `MacOSForegroundSwipe`, and `MacOSForegroundLongPress`.

- [ ] **Step 1: Add failing coordinate and no-input tests**

Cover logical window sizes other than 1280x720, invalid boxes, stale/mismatched window IDs, changed bounds, invalid durations, subprocess failure, pointer restoration, and confirmation that no activation or cliclick command occurs before all validation succeeds.

- [ ] **Step 2: Run the focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_macos_foreground_input.py tests/test_macos_foreground_click.py -q`

Expected: FAIL because only fixed-size click is implemented.

- [ ] **Step 3: Extract dimension-agnostic mapping**

Allow any validated positive prepared bounds and map capture coordinates by independent X/Y ratios. Before every command, call `current_prepared_window()`, require the same window ID/PID/bounds, activate the game, wait 150 ms, and then issue input.

- [ ] **Step 4: Implement bounded gestures**

Require swipe duration `200..2000 ms` and long-press duration `300..2000 ms`. Use explicit mouse-down, timed move/wait, and mouse-up commands; ensure a `finally` path releases the button and restores the original pointer even when a middle command fails.

- [ ] **Step 5: Bind Maa custom actions to the same-frame safety gate**

Each custom action receives `argv.image`, runs the named page and target recognizers through `context.run_recognition` on that same image, builds `VisualEvidence`, calls `authorize_action`, and only then invokes the executor. A denied action records `blocked_safety`/`failed` evidence and returns a failed `CustomAction.RunResult` without input.

- [ ] **Step 6: Keep click compatibility**

Make the old module re-export `MacOSForegroundClick`, `ForegroundInputExecutor`, and mapping helpers so existing mail pipeline imports and tests continue to pass. Import the new registration module once in `agent/main.py`.

- [ ] **Step 7: Run tests and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_macos_foreground_input.py tests/test_macos_foreground_click.py -q
install/.venv/bin/python -m ruff check agent/actions agent/main.py tests/test_macos_foreground_input.py tests/test_macos_foreground_click.py
```

Expected: all checks pass.

- [ ] **Step 8: Commit the safe input layer**

```bash
git add -- agent/actions/macos_foreground_input.py agent/actions/macos_foreground_click.py \
  agent/actions/__init__.py agent/main.py tests/test_macos_foreground_input.py \
  tests/test_macos_foreground_click.py
git commit -m "feat: add safety-gated foreground gestures"
```

### Task 4: Upgrade diagnostics to task-scoped evidence bundles

**Files:**

- Update: `agent/diagnostics.py`
- Update: `agent/errors.py`
- Create: `agent/evidence.py`
- Update: `tests/test_diagnostics.py`
- Create: `tests/test_evidence.py`
- Update: `.gitignore`

**Interfaces:**

```python
class RunDiagnostics:
    @classmethod
    def create(cls, root: Path, *, task_id: str, now: TimestampFactory = ...) -> Self: ...
    def record_backend(self, backend: str) -> None: ...
    def record_action(self, record: ActionTraceRecord) -> None: ...
    def save_image(self, name: Literal["before", "after", "failure"], image: Any) -> Path: ...
    def finish(self, result: TaskResult) -> None: ...

class MaaLogSession:
    @classmethod
    def start(cls, tasker: Any, run_directory: Path) -> Self: ...
    def close(self) -> Path: ...  # returns run_directory / "maafw.log"

@dataclass(frozen=True, slots=True)
class ActionTraceRecord:
    sequence: int
    state: str
    frame_id: str
    page_marker: str
    target_marker: str
    action_id: str
    input_kind: Literal["click", "swipe", "long_press", "none"]
    mapped_points: tuple[tuple[int, int], ...]
    decision: str
    details: Mapping[str, object]
```

- [ ] **Step 1: Add failing path/schema/atomicity tests**

Require `diagnostics/YYYY-MM-DD/TASK_ID/run-id/`, `result.json`, `agent.log`, `maafw.log`, `action-trace.jsonl`, and optional `before.png`, `after.png`, `failure.png`. Verify atomic result replacement, ordered trace sequence, image name allowlist, status serialization, Maa log finalization from an injected fake Tasker, idempotent `close()`, and rejection of non-JSON values in `ActionTraceRecord.details`.

- [ ] **Step 2: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_diagnostics.py tests/test_evidence.py -q`

Expected: FAIL because diagnostics are timestamp-only and write `run.json` schema v1.

- [ ] **Step 3: Implement schema v2**

Record controller backend, window ID/PID, screenshot size, task status, postcondition, action counts, node durations, stable error code, and evidence filenames. Keep the generic Agent startup-failure path by assigning task ID `RUNTIME`.

- [ ] **Step 4: Implement append-only action traces and PNG evidence**

Validate `ActionTraceRecord.details` recursively as JSON scalars/lists/objects, copy mappings before storage, serialize one compact JSON object per line, fsync after each side-effecting action, and use Pillow to write temporary PNGs followed by atomic replacement. Refuse symlinks and paths outside the run directory.

- [ ] **Step 5: Implement task-local Maa log capture**

Before the task starts, point Maa logging at the run directory through the injected Tasker API. On every terminal path, close/finalize the session and atomically consolidate the produced Maa log files into `maafw.log`. If Maa log finalization fails, keep the task's original status but attach a stable diagnostics error and make the verification gate fail.

- [ ] **Step 6: Update ignore rules**

Ignore `/diagnostics/` while keeping `docs/verification/` and `tests/fixtures/` trackable.

- [ ] **Step 7: Run focused and full tests**

```bash
install/.venv/bin/python -m pytest tests/test_diagnostics.py tests/test_evidence.py -q
install/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit task-scoped diagnostics**

```bash
git add -- agent/diagnostics.py agent/errors.py agent/evidence.py \
  tests/test_diagnostics.py tests/test_evidence.py .gitignore
git commit -m "feat: record task-scoped workflow evidence"
```

### Task 5: Implement the bounded deterministic workflow runner

**Files:**

- Create: `agent/workflows/engine.py`
- Create: `agent/workflows/registry.py`
- Create: `agent/workflows/definitions/__init__.py`
- Create: `agent/actions/daily_workflow.py`
- Update: `agent/actions/__init__.py`
- Update: `agent/main.py`
- Create: `tests/test_workflow_engine.py`
- Create: `tests/test_daily_workflow_action.py`

**Interfaces:**

```python
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

class WorkflowDriver(Protocol):
    def capture(self) -> CapturedFrame: ...
    def recognize(self, frame: CapturedFrame, recognizer: str) -> Recognition: ...
    def execute(self, transition: Transition, frame: CapturedFrame) -> None: ...

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
```

- [ ] **Step 1: Add failing state-machine tests**

Cover normal completion, already complete without input, weekday ineligibility, safety block, unknown state, conflicting targets, postcondition timeout, per-action cap, global `max_steps`, driver exception, and a deterministic transition sequence on repeated identical snapshots.

- [ ] **Step 2: Run the engine tests**

Run: `install/.venv/bin/python -m pytest tests/test_workflow_engine.py -q`

Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Implement the capture-decide-act-verify loop**

Resolve `day` once at entry (`date.today()` only when the caller omitted it), then check `policy.eligible_weekdays` before the first capture. For each eligible step: capture once, build the immutable snapshot, stop on danger, ask the definition for one decision, authorize that decision, record it, execute at most one input, increment one counter, then capture a new frame and verify the declared postcondition. Never execute a second candidate from the same snapshot.

Validate every `Recognition.frame_id` against `CapturedFrame.frame_id`; construct `VisualEvidence` only from those recognitions. `Decision.act(...)` must contain exactly one transition and no terminal status, while `Decision.finish(...)` must contain one terminal status and no transition. Reject any other combination as `failed` with `error_code="INVALID_DECISION"`. Before dispatching an input, derive the safety intent from `transition.intent`; after dispatch, pass the unchanged source frame to `WorkflowDriver.execute` and require a fresh capture for the postcondition.

- [ ] **Step 4: Implement terminal status rules**

Only a verified task postcondition may return `completed`; a verified pre-existing postcondition with zero inputs returns `already_complete`; a planned weekday/feature branch returns `not_eligible`; safety reasons return `blocked_safety`; all technical/cap/unknown failures return `failed`.

- [ ] **Step 5: Register one generic Maa custom action**

`DailyWorkflowAction.run(context, argv)` accepts a canonical task ID, resolves its definition and policy, creates task-scoped diagnostics and a `MaaLogSession`, adapts the Maa controller/context to `WorkflowDriver`, and returns success only for `completed`, `already_complete`, or planned `not_eligible`. Finalize the Maa log and diagnostics in `finally` before returning.

- [ ] **Step 6: Run action and engine tests**

```bash
install/.venv/bin/python -m pytest tests/test_workflow_engine.py tests/test_daily_workflow_action.py -q
install/.venv/bin/python -m ruff check agent/workflows agent/actions/daily_workflow.py tests/test_workflow_engine.py tests/test_daily_workflow_action.py
```

Expected: all checks pass.

- [ ] **Step 7: Commit the bounded runner**

```bash
git add -- agent/workflows/engine.py agent/workflows/registry.py \
  agent/workflows/definitions/__init__.py \
  agent/actions/daily_workflow.py agent/actions/__init__.py agent/main.py \
  tests/test_workflow_engine.py tests/test_daily_workflow_action.py
git commit -m "feat: add bounded daily workflow runner"
```

### Task 6: Add shared page navigation contracts and recognizers

**Files:**

- Create: `agent/navigation.py`
- Create: `assets/resource/pipeline/common/navigation.json`
- Create: `assets/resource/pipeline/common/safety.json`
- Create: `assets/resource/image/common/README.md`
- Create: `tests/test_navigation.py`
- Create: `tests/test_common_pipeline.py`

**Interfaces:**

```python
class PageId(StrEnum):
    HOME = "home"
    FUNCTION_PANEL = "function_panel"
    MAIL = "mail"
    SHOP = "shop"
    BAG = "bag"
    DAILY = "daily"
    MARTIAL = "martial"
    PAINTING_SCROLL = "painting_scroll"
    YANWU_WORLD = "yanwu_world"
    YUNZHOU = "yunzhou"
    UNIVERSAL_SHOP = "universal_shop"
    COLLECTION = "collection"
    DISPATCH = "dispatch"
    SHADOW_RUINS = "shadow_ruins"
    TRIAL_SWORD = "trial_sword"
    APPRAISAL = "appraisal"
    DUNGEON = "dungeon"
    BATTLE_PASS = "battle_pass"
    JIANLIN_RESOURCE = "jianlin_resource"
    RING = "ring"

@dataclass(frozen=True, slots=True)
class NavigationEdge:
    source: PageId
    destination: PageId
    page_marker: str
    target_marker: str
    action_id: str
    postcondition_marker: str
```

- [ ] **Step 1: Add failing graph and pipeline tests**

Require routes from home to every page, no keyboard action, no standard Maa `Click`/`Swipe`/`Key`/`Input`/`StartApp`, no edge without source and destination markers, and no ambiguous duplicate route from one source to one destination.

- [ ] **Step 2: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_navigation.py tests/test_common_pipeline.py -q`

Expected: FAIL because common navigation files do not exist.

- [ ] **Step 3: Implement the navigation graph**

Encode known parent hierarchy: home to direct pages; home to function panel and its children; home to painting scroll and its regions/features. Return home only through recognized close/back/home controls. Reuse an already-recognized parent page instead of closing and reopening it.

- [ ] **Step 4: Add recognizer-only pipeline nodes**

Provide stable names for each page marker, entry target, paid signal, login/security signal, unknown dialog, normal close, and normal back control. Every node in `common/safety.json` uses `DoNothing`; these nodes never produce input.

- [ ] **Step 5: Document live template acquisition**

The image README records required source page, exact marker meaning, allowed crop contents, reference capture size, and the rule that a template containing a claim/reward/payment control cannot serve as a generic page marker.

- [ ] **Step 6: Run common pipeline and install validation**

```bash
install/.venv/bin/python -m pytest tests/test_navigation.py tests/test_common_pipeline.py -q
install/.venv/bin/python -m tools.verify_install install
```

Expected: tests pass. Re-run setup first if the assembled install does not yet contain the new common resources.

- [ ] **Step 7: Commit shared navigation**

```bash
git add -- agent/navigation.py assets/resource/pipeline/common/navigation.json \
  assets/resource/pipeline/common/safety.json assets/resource/image/common/README.md \
  tests/test_navigation.py tests/test_common_pipeline.py
git commit -m "feat: add shared Jianzhichuan navigation contracts"
```

### Task 7: Add fixture manifests and input-free recognition validation

**Files:**

- Create: `agent/recognizers/__init__.py`
- Create: `agent/recognizers/fixtures.py`
- Create: `tools/validate_fixtures.py`
- Create: `tests/test_fixture_contract.py`
- Create: `tests/test_validate_fixtures.py`
- Create: `tests/fixtures/README.md`

**Interfaces:**

```python
class FixtureKind(StrEnum):
    ENTRY = "entry"
    ACTIONABLE = "actionable"
    COMPLETED = "completed"
    DANGER = "danger"

@dataclass(frozen=True, slots=True)
class FixtureCase:
    task_id: str
    kind: FixtureKind
    image: Path
    expected_page: str
    expected_targets: tuple[str, ...]
    expected_status: TaskStatus | None

def validate_fixture_case(
    case: FixtureCase,
    recognizer: FixtureRecognizer,
    input_spy: InputSpy,
) -> FixtureValidation: ...
```

- [ ] **Step 1: Add failing manifest and no-input tests**

Require exactly one `entry`, `actionable`, `completed`, and `danger` fixture per implemented task; verify PNG decoding, path containment, expected marker existence, and zero click/swipe/long-press/keyboard calls during fixture recognition.

- [ ] **Step 2: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_fixture_contract.py tests/test_validate_fixtures.py -q`

Expected: FAIL because the fixture loader and validator are absent.

- [ ] **Step 3: Implement strict fixture loading**

Use `tests/fixtures/{canonical task ID}/manifest.json` and relative PNG names. Reject symlinks, duplicate kinds, unknown task IDs, unexpected fields, non-RGB/RGBA images, and images outside the task directory.

The only accepted manifest shape is:

```json
{
  "schema_version": 1,
  "task_id": "MAIL_REWARD_DAILY",
  "reference_size": [923, 720],
  "cases": {
    "entry": {
      "image": "entry.png",
      "expected_page": "home_page",
      "expected_targets": ["mail_entry"],
      "expected_status": null
    },
    "actionable": {
      "image": "actionable.png",
      "expected_page": "mail_page",
      "expected_targets": ["claim_all_mail"],
      "expected_status": null
    },
    "completed": {
      "image": "completed.png",
      "expected_page": "mail_page",
      "expected_targets": ["mail_empty"],
      "expected_status": "already_complete"
    },
    "danger": {
      "image": "danger.png",
      "expected_page": "mail_page",
      "expected_targets": ["paid_or_verification_signal"],
      "expected_status": "blocked_safety"
    }
  }
}
```

`reference_size` must equal every decoded PNG's actual pixel size and the applicable `maa_capture_size` in `assets/resource/calibration.json`; `923x720` above is the observed example, not a fixed requirement. Do not accept aliases such as `page`, `targets`, `status`, `page_marker`, or `target_markers`.

- [ ] **Step 4: Implement recognition-only validation**

Run page/target/safety recognizers against each immutable image and compare the full result with the manifest. Install an input spy that raises immediately if any input API is called.

- [ ] **Step 5: Add foundation-only synthetic cases**

Create temporary test images inside pytest for page hit, unique target, completed state, and paid danger state. Task batch plans will add real per-task fixture directories only after live templates are captured.

- [ ] **Step 6: Run tests and CLI help**

```bash
install/.venv/bin/python -m pytest tests/test_fixture_contract.py tests/test_validate_fixtures.py -q
install/.venv/bin/python -m tools.validate_fixtures --help
```

Expected: tests pass and help lists `--task-id` plus `--all-implemented`.

- [ ] **Step 7: Commit the fixture harness**

```bash
git add -- agent/recognizers/__init__.py agent/recognizers/fixtures.py \
  tools/validate_fixtures.py tests/test_fixture_contract.py \
  tests/test_validate_fixtures.py tests/fixtures/README.md
git commit -m "test: add input-free workflow fixture harness"
```

### Task 8: Generate and validate ProjectInterface task entries incrementally

**Files:**

- Create: `tools/project_interface.py`
- Create: `tests/test_project_interface_generation.py`
- Update: `tools/verify_install.py`
- Update: `tests/test_verify_install.py`
- Update: `tools/run_cli.py`
- Update: `tests/test_run_cli.py`
- Update: `assets/interface.json`

**Interfaces:**

```python
def task_entry(policy: TaskPolicy) -> dict[str, Any]: ...

def render_interface(
    base: Mapping[str, Any],
    *,
    implemented_task_ids: Sequence[str],
) -> dict[str, Any]: ...

def verify_workflow_assets(project_root: Path) -> list[str]: ...

def run_cli(
    lifecycle: Lifecycle,
    *,
    install_root: str | Path = Path("install"),
    task_name: str = "mail_smoke_test",
    launch: Callable[[], None] | None = None,
    spawn: Callable[[Sequence[str]], ChildProcess] | None = None,
) -> int: ...
```

- [ ] **Step 1: Add failing generation tests**

Require the singular ProjectInterface `task` array, deterministic catalog order, lowercase canonical task names, unique names/entries, `default_check: false` for every new task until live verification, `resource: ["mja"]`, `controller: ["macos"]`, and an entry named by the exact rule `MJA_Daily_` plus the canonical task ID. Add CLI tests proving `--task` accepts only a lowercase task name currently registered in the assembled ProjectInterface and keeps `mail_smoke_test` as the default.

- [ ] **Step 2: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_project_interface_generation.py tests/test_verify_install.py -q`

Expected: FAIL because no renderer or daily asset checks exist.

- [ ] **Step 3: Implement deterministic rendering without hidden registrations**

Keep the existing `mail_smoke_test`. Add only task IDs explicitly passed as implemented. Rendering must be pure and must not edit files; the caller writes reviewed JSON via `apply_patch` or an explicit formatting command.

```python
def task_entry(policy: TaskPolicy) -> dict[str, Any]:
    return {
        "name": policy.task_id.lower(),
        "label": policy.label,
        "entry": policy.entry,
        "default_check": False,
        "resource": ["mja"],
        "controller": ["macos"],
    }

def render_interface(
    base: Mapping[str, Any],
    *,
    implemented_task_ids: Sequence[str],
) -> dict[str, Any]:
    rendered = deepcopy(dict(base))
    catalog_names = {task_id.lower(): task_id for task_id in TASK_POLICIES}
    existing_ids = {
        catalog_names[item["name"]]
        for item in rendered["task"]
        if item.get("name") in catalog_names
    }
    selected_ids = existing_ids | set(implemented_task_ids)
    unknown = selected_ids - set(TASK_POLICIES)
    if unknown:
        raise ValueError(f"unknown task ids: {sorted(unknown)}")
    non_daily = [item for item in rendered["task"] if item.get("name") not in catalog_names]
    rendered["task"] = non_daily + [
        task_entry(policy)
        for task_id, policy in TASK_POLICIES.items()
        if task_id in selected_ids
    ]
    return rendered
```

Reject duplicate existing names before building `existing_ids`, and validate that every catalog `entry` equals `f"MJA_Daily_{task_id}"`. Because the renderer unions already registered daily tasks with the explicit IDs and then re-sorts by catalog order, later batches may pass only their newly implemented IDs without losing or misordering earlier entries.

- [ ] **Step 4: Extend install verification**

For each registered daily task, require its pipeline entry, workflow registry definition, task policy, four fixture kinds, and no forbidden standard input action. Reject every aggregate preset in this foundation version; the aggregate plan replaces that unconditional rejection with its 17-record admission gate after the verification-record module exists.

- [ ] **Step 5: Add validated single-task CLI selection**

Pass lowercase `task_name` into `_maa_config`, validate it against the singular `task` array in `install/interface.json` before launching or preparing the game, and expose `--task` in the parser. Preserve the old lifecycle order, SIGINT forwarding, `finally` restoration, and the mail smoke default.

- [ ] **Step 6: Keep the interface unchanged except metadata**

Update the project description from mail-only wording to safe foreground daily automation foundation, but do not register unimplemented daily tasks in this plan.

- [ ] **Step 7: Run generation, interface, CLI, and install tests**

```bash
install/.venv/bin/python -m pytest tests/test_project_interface_generation.py \
  tests/test_project_interface.py tests/test_verify_install.py tests/test_run_cli.py -q
install/.venv/bin/python -m tools.verify_install install
```

Expected: all checks pass after reassembling the install from the current checkout.

- [ ] **Step 8: Commit ProjectInterface and CLI foundation**

```bash
git add -- tools/project_interface.py tests/test_project_interface_generation.py \
  tools/verify_install.py tests/test_verify_install.py tools/run_cli.py tests/test_run_cli.py \
  assets/interface.json
git commit -m "feat: validate incremental daily task registration"
```

### Task 9: Foundation quality gate and read-only live navigation calibration

**Files:**

- Create: `docs/verification/workflow-foundation.md`
- Update only if calibration is proven: `assets/resource/image/common/*.png`

**Interfaces:** none.

- [ ] **Step 1: Run every automated gate**

```bash
git diff --check
install/.venv/bin/python -m pytest -q
install/.venv/bin/python -m ruff check agent tools tests
install/.venv/bin/python -m tools.setup --root "$PWD"
install/.venv/bin/python -m tools.verify_install "$PWD/install"
```

Expected: all commands pass.

- [ ] **Step 2: Capture page markers without task side effects**

From the freshly assembled checkout and an authorized foreground host, navigate only through home, function panel, painting scroll, and safe close/back controls. Capture before/after full-screen and MAA images for each shared edge. Do not click claim, purchase, dispatch, battle, food, sweep, or resource controls.

- [ ] **Step 3: Validate all captured common markers**

Run the recognizers against each capture, require one correct parent marker and one intended navigation target, and confirm danger recognizers produce no false safe result on a separately captured paid/verification fixture.

- [ ] **Step 4: Verify failure and restoration**

Inject a stale window ID in a unit/live-safe probe, confirm no input, then confirm cancellation and normal completion both restore the game bounds and the prior foreground application.

- [ ] **Step 5: Record exact evidence paths and current limitations**

The verification document records commands, checkout commit, controller backend, window ID/size, fixture paths, diagnostic paths, and any page whose live marker remains unavailable. An unavailable page remains unimplemented; it is not marked verified.

- [ ] **Step 6: Commit the verified foundation evidence and proven templates**

```bash
git add -- docs/verification/workflow-foundation.md assets/resource/image/common
git commit -m "test: verify shared workflow foundation"
```

- [ ] **Step 7: Confirm a clean handoff to batch plans**

Run: `git status --short`

Expected: only the user's pre-existing `AGENTS.md` modification and ignored local diagnostics remain. Batch 1 may start only after this condition and all foundation tests pass.
