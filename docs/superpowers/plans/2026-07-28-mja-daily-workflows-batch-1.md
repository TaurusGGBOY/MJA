# MJA Batch 1 Daily Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and independently verify the eight free/ordinary-claim Jianzhichuan daily workflows that form Batch 1, with safe foreground input and MFAAvalonia-visible single-task entries.

**Architecture:** Each workflow adds one canonical catalog policy, one `WorkflowDefinition`, one registry export, one Maa Pipeline entry, task-specific recognition templates, four immutable fixture states, and one lowercase ProjectInterface task. Definitions return only foundation `Decision`/`Transition` values; the existing `run_workflow` engine owns same-frame `authorize_action`, bounded execution, `TaskResult`, and `RunDiagnostics`, while the existing `DailyWorkflowAction` is the only Pipeline custom action.

**Tech Stack:** Python 3.14, MaaFramework Python Agent API 5.12.2, ProjectInterface V2 JSON, MFAAvalonia, Maa Pipeline JSON, Pillow/NumPy, PyObjC/AppKit/Quartz, pytest, Ruff.

## Global Constraints

- Complete `docs/superpowers/plans/2026-07-28-mja-macos-capture-fallback.md` and `docs/superpowers/plans/2026-07-28-mja-workflow-foundation.md` before implementation or live input.
- Never modify, stage, or commit `AGENTS.md`; every commit below uses an exact path-scoped `git add --` command.
- `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py` is the business source of truth. `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa` supplies only calibration and failure evidence.
- `agent/workflows/catalog.py` remains the only business truth for `TASK_POLICIES`. A definition reads `TASK_POLICIES[task_id]`; it must not create a second policy constant or a parallel status/runtime type.
- Every definition consumes foundation `StateSnapshot`, `Decision`, `Transition`, `WorkflowDefinition`, `TaskStatus`, and `ActionIntent`. The registered execution path consumes `authorize_action`, `run_workflow`, `DailyWorkflowAction`, and `RunDiagnostics` exactly as completed by the foundation plan.
- Runtime statuses are exactly `completed`, `already_complete`, `not_eligible`, `blocked_safety`, and `failed`. `live_pending` and `live_verified` may appear only in `verification/tasks/{TASK_ID}.json`, never in `result.json` or an alternate machine record under `docs/verification/`.
- Every side effect requires one immutable frame proving the expected page, exactly one permitted target, and all required free/basic-track text. `run_workflow` calls `authorize_action` before dispatching the existing foreground click, swipe, or long-press input.
- `¥`, `￥`, Apple Pay, payment, recharge, paid/premium bundles, unknown currency, login, account, password, verification-code, real-name, security, and biometric prompts are unconditional hard stops.
- Every nonzero same-frame `VisualEvidence.danger_hits` entry is a hard stop. In particular, `danger_hits["unknown_dialog"] == 1` returns `SafetyReason.UNKNOWN_DIALOG` before any action.
- Read `assets/resource/calibration.json` as the only coordinate calibration source. The observed logical `1051x820` game window producing a `923x720` Maa frame is an example, not a fixed size or implementation assumption.
- Definitions and tests use this exact layout: `agent/workflows/definitions/{lowercase task ID}.py`, `assets/resource/pipeline/daily/{lowercase task ID}.json`, `assets/resource/image/daily/{TASK_ID}/`, `tests/fixtures/{TASK_ID}/manifest.json`, four fixture PNGs named `entry.png`, `actionable.png`, `completed.png`, and `danger.png`, and `tests/workflows/test_{lowercase task ID}.py`.
- Each ProjectInterface object lives under the singular `task` array and has lowercase canonical `name`, `entry: MJA_Daily_{TASK_ID}`, `resource: ["mja"]`, `controller: ["macos"]`, and `default_check: false`. CLI `--task` receives that lowercase name.
- `RunDiagnostics.create(...)` alone creates `diagnostics/YYYY-MM-DD/TASK_ID/run-id/`; do not pass `--debug-dir` and do not create diagnostics directories manually.
- Each task has finite `max_steps` and `action_caps`. A reached cap without the independently recognized postcondition returns `failed` with a stable cap error code.
- Fixture recognition is input-free and covers normal/actionable, already-complete, cap, and safety behavior. Each live check lasts 2–5 minutes, runs in the foreground, verifies an independent visual postcondition, then performs a safe no-op rerun when the task is rerunnable.
- Before every live task, record `git rev-parse HEAD` and `git status --short`, reassemble and verify the install from that checkout, and save both full-desktop and Maa-controller before/after captures with digests in the human verification report.
- Rewards exposed by other daily task rows are not claimed inside those tasks. They are deferred to `DAILY_TASK_REWARD_CLAIM_DAILY`.
- `BATTLE_PASS_REWARD_DAILY` touches only ordinary task rewards and the basic/free track. It remains last in the final aggregate order.

## Canonical Foundation Interfaces

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

def authorize_action(
    evidence: VisualEvidence,
    intent: ActionIntent,
    policy: TaskPolicy,
    action_counts: Mapping[str, int],
) -> SafetyDecision: ...

def run_workflow(
    definition: WorkflowDefinition,
    driver: WorkflowDriver,
    policy: TaskPolicy,
    diagnostics: RunDiagnostics,
    *,
    day: date | None = None,
) -> TaskResult: ...
```

Every definition follows one deterministic rule: return `Decision.act(...)` for exactly one recognized transition; return `Decision.finish(...)` only for an independently recognized postcondition, planned weekday ineligibility, or a stable failure; never execute input directly. The engine converts a safety denial to `blocked_safety`, a cap/postcondition/technical error to `failed`, and a pre-existing postcondition with no protected claim to `already_complete`.

Every task manifest uses exactly this key shape; the only per-task changes are `task_id`, actual `reference_size`, page/target marker values, and the four image paths shown here:

```json
{
  "schema_version": 1,
  "task_id": "MAIL_REWARD_DAILY",
  "reference_size": [923, 720],
  "cases": {
    "entry": {
      "image": "entry.png",
      "expected_page": "home",
      "expected_targets": ["function_panel.open"],
      "expected_status": null
    },
    "actionable": {
      "image": "actionable.png",
      "expected_page": "mail.page",
      "expected_targets": ["mail.claim_all"],
      "expected_status": null
    },
    "completed": {
      "image": "completed.png",
      "expected_page": "mail.page",
      "expected_targets": ["mail.empty"],
      "expected_status": "already_complete"
    },
    "danger": {
      "image": "danger.png",
      "expected_page": "mail.page",
      "expected_targets": ["unknown_dialog"],
      "expected_status": "blocked_safety"
    }
  }
}
```

`reference_size` must equal each decoded fixture PNG's actual dimensions and the applicable `maa_capture_size` in `assets/resource/calibration.json`; `[923, 720]` is only the observed example. Reject every unknown field and aliases including `page`, `targets`, `status`, `page_marker`, and `target_markers`.

---

### Task 1: Implement MAIL_REWARD_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/mail_reward_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/mail_reward_daily.json`
- Create: `assets/resource/image/daily/MAIL_REWARD_DAILY/mail_page.png`
- Create: `assets/resource/image/daily/MAIL_REWARD_DAILY/mail_claim_all.png`
- Create: `assets/resource/image/daily/MAIL_REWARD_DAILY/mail_empty.png`
- Create: `assets/resource/image/daily/MAIL_REWARD_DAILY/mail_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/MAIL_REWARD_DAILY/manifest.json`
- Create: `tests/fixtures/MAIL_REWARD_DAILY/entry.png`
- Create: `tests/fixtures/MAIL_REWARD_DAILY/actionable.png`
- Create: `tests/fixtures/MAIL_REWARD_DAILY/completed.png`
- Create: `tests/fixtures/MAIL_REWARD_DAILY/danger.png`
- Create: `tests/workflows/support.py`
- Create: `tests/workflows/test_mail_reward_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(definition, state, markers, counters=None, texts=(), danger_markers=()) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `MAIL_REWARD_DAILY_DEFINITION: WorkflowDefinition`; `WORKFLOW_DEFINITIONS["MAIL_REWARD_DAILY"]`; Pipeline entry `MJA_Daily_MAIL_REWARD_DAILY`; ProjectInterface task `mail_reward_daily`; test-only `snapshot(...) -> StateSnapshot`, `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`, and `NoCaptureDriver` in `tests/workflows/support.py`.

- [ ] **Step 1: Write the failing policy, decision, fixture, cap, and safety tests**

Create the test-only support with canonical objects only:

```python
def snapshot(
    state: str,
    *markers: str,
    texts: tuple[str, ...] = (),
    danger_markers: tuple[str, ...] = (),
) -> StateSnapshot:
    frame_id = "fixture-frame"
    hits = {marker: 1 for marker in markers}
    danger_hits = {marker: 1 for marker in danger_markers}
    all_markers = (*markers, *danger_markers)
    recognitions = {
        marker: Recognition(marker, frame_id, 1, ((0, 0, 1, 1),), texts)
        for marker in all_markers
    }
    evidence = VisualEvidence(
        frame_id,
        hits,
        hits,
        danger_hits,
        {marker: frame_id for marker in all_markers},
        texts,
        (),
    )
    return StateSnapshot(state, CapturedFrame(frame_id, object(), (1, 1)), evidence, recognitions)

def evaluate_decision(
    definition: WorkflowDefinition,
    state: str,
    markers: tuple[str, ...],
    counters: Mapping[str, int] | None = None,
    texts: tuple[str, ...] = (),
    danger_markers: tuple[str, ...] = (),
) -> tuple[Decision, SafetyDecision | None]:
    counts = {} if counters is None else counters
    state_snapshot = snapshot(state, *markers, texts=texts, danger_markers=danger_markers)
    decision = definition.decide(state_snapshot, counts)
    safety = None if decision.transition is None else authorize_action(
        state_snapshot.evidence,
        decision.transition.intent,
        TASK_POLICIES[definition.task_id],
        counts,
    )
    return decision, safety

class NoCaptureDriver:
    def __init__(self) -> None:
        self.capture_count = 0
        self.executed: list[Transition] = []

    def capture(self) -> CapturedFrame:
        self.capture_count += 1
        raise AssertionError("ineligible workflow captured a frame")

    def recognize(self, frame: CapturedFrame, recognizer: str) -> Recognition:
        raise AssertionError((frame.frame_id, recognizer))

    def execute(self, transition: Transition, frame: CapturedFrame) -> None:
        self.executed.append(transition)
        raise AssertionError(frame.frame_id)
```

Then write the mail assertions without an undefined runner helper:

```python
def test_mail_contract_and_actionable_decision() -> None:
    policy = TASK_POLICIES["MAIL_REWARD_DAILY"]
    assert (policy.entry, policy.max_steps, policy.action_caps["claim_all_mail"]) == ("MJA_Daily_MAIL_REWARD_DAILY", 12, 1)
    decision, safety = evaluate_decision(MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.claim_all"))
    assert decision.transition is not None and decision.transition.intent.action_id == "claim_all_mail"
    assert safety is not None and safety.allowed

def test_mail_completed_is_already_complete() -> None:
    decision, _ = evaluate_decision(MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.empty"))
    assert decision.status is TaskStatus.ALREADY_COMPLETE

def test_mail_cap_and_payment_fail_before_input() -> None:
    _, capped = evaluate_decision(MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.claim_all"), {"claim_all_mail": 1})
    _, paid = evaluate_decision(MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.claim_all"), texts=("Apple Pay",))
    _, unknown = evaluate_decision(MAIL_REWARD_DAILY_DEFINITION, "mail", ("mail.page", "mail.claim_all"), danger_markers=("unknown_dialog",))
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

- [ ] **Step 2: Run the focused test and verify the intended failure**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_mail_reward_daily.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.mail_reward_daily'`.

- [ ] **Step 3: Add the canonical policy and deterministic definition**

Add this exact policy value inside the existing `TASK_POLICIES` construction in catalog order:

```python
"MAIL_REWARD_DAILY": TaskPolicy(
    task_id="MAIL_REWARD_DAILY",
    label="邮件奖励",
    entry="MJA_Daily_MAIL_REWARD_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}),
    max_steps=12,
    action_caps={"open_function_panel": 1, "open_mail": 1, "claim_all_mail": 1, "close_mail": 1},
    approved_resources=frozenset(),
),
```

Implement `MailRewardDailyDefinition` with `initial_state = "home"` and these exact transitions:

```python
TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_function_panel", "home", "function_panel.open"), "click", {}, "function_panel", "function_panel.page"),
    "function_panel": Transition("function_panel", ActionIntent("open_mail", "function_panel.page", "mail.entry"), "click", {}, "mail", "mail.page"),
    "mail": Transition("mail", ActionIntent("claim_all_mail", "mail.page", "mail.claim_all"), "click", {}, "mail_after_claim", "mail.empty"),
    "mail_after_claim": Transition("mail_after_claim", ActionIntent("close_mail", "mail.page", "mail.close"), "click", {}, "home_done", "home"),
}
```

`recognizers(state)` returns the state page marker, transition target, `mail.empty`, `safety.paid`, `safety.verification`, and `unknown_dialog`. `decide(...)` returns `already_complete` when `mail.empty` is present before `claim_all_mail`, `completed` when `home` is recognized in `home_done`, the table transition when its target hit count is exactly one, and `failed`/`TARGET_NOT_UNIQUE` otherwise. Export one `MAIL_REWARD_DAILY_DEFINITION`, re-export it from `definitions/__init__.py`, and register that instance in `WORKFLOW_DEFINITIONS`.

- [ ] **Step 4: Add exact Pipeline, templates, fixtures, and interface entry**

```json
{
  "MJA_Daily_MAIL_REWARD_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "MAIL_REWARD_DAILY"}
  },
  "mail.page": {"recognition":"TemplateMatch","template":"daily/MAIL_REWARD_DAILY/mail_page.png","action":"DoNothing"},
  "mail.claim_all": {"recognition":"TemplateMatch","template":"daily/MAIL_REWARD_DAILY/mail_claim_all.png","action":"DoNothing"},
  "mail.empty": {"recognition":"TemplateMatch","template":"daily/MAIL_REWARD_DAILY/mail_empty.png","action":"DoNothing"},
  "mail.close": {"recognition":"TemplateMatch","template":"daily/MAIL_REWARD_DAILY/mail_close.png","action":"DoNothing"}
}
```

The fixture manifest uses the exact canonical keys above, references only `entry.png`, `actionable.png`, `completed.png`, and `danger.png`, records the actual calibrated PNG dimensions, maps them respectively to `home/function_panel.open`, `mail.page/mail.claim_all`, `mail.page/mail.empty`, and `mail.page/unknown_dialog`, and expects `null`, `null`, `already_complete`, and `blocked_safety`. Capture/crop the four exact template filenames listed in **Files:** from the same calibrated coordinate system.

Render and assert the exact ProjectInterface object:

```json
{"name":"mail_reward_daily","label":"邮件奖励","entry":"MJA_Daily_MAIL_REWARD_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 5: Run focused verification**

```bash
install/.venv/bin/python -m pytest tests/workflows/test_mail_reward_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q
install/.venv/bin/python -m tools.validate_fixtures --task-id MAIL_REWARD_DAILY
install/.venv/bin/python -m ruff check agent/workflows/definitions/mail_reward_daily.py tests/workflows/test_mail_reward_daily.py
```

Expected: PASS; the normal path claims at most once, completed is input-free, a preloaded cap fails, and danger blocks before input.

- [ ] **Step 6: Perform the 2–5 minute foreground check and safe rerun**

Run: `install/.venv/bin/python -m tools.run_cli --task mail_reward_daily`

Independently verify that the mail page changes to `mail.empty`, then closes to the recognized home page. Run the same command again; accept `already_complete` with zero `claim_all_mail` actions. Confirm `RunDiagnostics` created `diagnostics/YYYY-MM-DD/MAIL_REWARD_DAILY/run-id/` containing result, logs, before/after images, and action trace. A paid/verification prompt must produce `blocked_safety` and `failure.png` without a click.

- [ ] **Step 7: Commit only Task 1 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/mail_reward_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/mail_reward_daily.json assets/resource/image/daily/MAIL_REWARD_DAILY/mail_page.png assets/resource/image/daily/MAIL_REWARD_DAILY/mail_claim_all.png assets/resource/image/daily/MAIL_REWARD_DAILY/mail_empty.png assets/resource/image/daily/MAIL_REWARD_DAILY/mail_close.png assets/interface.json tests/fixtures/MAIL_REWARD_DAILY/manifest.json tests/fixtures/MAIL_REWARD_DAILY/entry.png tests/fixtures/MAIL_REWARD_DAILY/actionable.png tests/fixtures/MAIL_REWARD_DAILY/completed.png tests/fixtures/MAIL_REWARD_DAILY/danger.png tests/workflows/support.py tests/workflows/test_mail_reward_daily.py
git commit -m "feat: add daily mail reward workflow"
```

### Task 2: Implement SHOP_FREE_GIFT_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/shop_free_gift_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/shop_free_gift_daily.json`
- Create: `assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/shop_page.png`
- Create: `assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/period_benefits_tab.png`
- Create: `assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/period_benefits_page.png`
- Create: `assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/daily_free_gift.png`
- Create: `assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/daily_free_gift_claimed.png`
- Create: `assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/shop_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/SHOP_FREE_GIFT_DAILY/manifest.json`
- Create: `tests/fixtures/SHOP_FREE_GIFT_DAILY/entry.png`
- Create: `tests/fixtures/SHOP_FREE_GIFT_DAILY/actionable.png`
- Create: `tests/fixtures/SHOP_FREE_GIFT_DAILY/completed.png`
- Create: `tests/fixtures/SHOP_FREE_GIFT_DAILY/danger.png`
- Create: `tests/workflows/test_shop_free_gift_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `SHOP_FREE_GIFT_DAILY_DEFINITION: WorkflowDefinition`; `WORKFLOW_DEFINITIONS["SHOP_FREE_GIFT_DAILY"]`; Pipeline entry `MJA_Daily_SHOP_FREE_GIFT_DAILY`; ProjectInterface task `shop_free_gift_daily`.

- [ ] **Step 1: Write and run the failing normal/already-complete/cap/safety test**

```python
def test_shop_policy_is_free_and_bounded() -> None:
    policy = TASK_POLICIES["SHOP_FREE_GIFT_DAILY"]
    assert policy.entry == "MJA_Daily_SHOP_FREE_GIFT_DAILY"
    assert policy.action_caps["claim_free_gift"] == 1
    assert policy.approved_resources == frozenset()

def test_shop_actionable_and_completed_decisions() -> None:
    action, safety = evaluate_decision(SHOP_FREE_GIFT_DAILY_DEFINITION, "benefits", ("shop.period_benefits.page", "shop.daily_free_gift"), texts=("每日特惠", "免费"))
    complete, _ = evaluate_decision(SHOP_FREE_GIFT_DAILY_DEFINITION, "benefits", ("shop.period_benefits.page", "shop.daily_free_gift_claimed"))
    assert action.transition is not None and action.transition.intent.action_id == "claim_free_gift"
    assert safety is not None and safety.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE

def test_shop_cap_and_payment_are_denied() -> None:
    markers = ("shop.period_benefits.page", "shop.daily_free_gift")
    _, capped = evaluate_decision(SHOP_FREE_GIFT_DAILY_DEFINITION, "benefits", markers, {"claim_free_gift": 1}, ("每日特惠", "免费"))
    _, paid = evaluate_decision(SHOP_FREE_GIFT_DAILY_DEFINITION, "benefits", markers, texts=("每日特惠", "免费", "￥6"))
    _, unknown = evaluate_decision(SHOP_FREE_GIFT_DAILY_DEFINITION, "benefits", markers, danger_markers=("unknown_dialog",))
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_shop_free_gift_daily.py -q`

Expected: FAIL with `ModuleNotFoundError` for `agent.workflows.definitions.shop_free_gift_daily`.

- [ ] **Step 2: Add the catalog policy and concrete transition table**

```python
"SHOP_FREE_GIFT_DAILY": TaskPolicy(
    task_id="SHOP_FREE_GIFT_DAILY", label="商城每日免费礼包", entry="MJA_Daily_SHOP_FREE_GIFT_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=15,
    action_caps={"open_function_panel": 1, "open_shop": 1, "open_period_benefits": 1, "claim_free_gift": 1, "close_shop": 1},
    approved_resources=frozenset(),
),

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_function_panel", "home", "function_panel.open"), "click", {}, "function_panel", "function_panel.page"),
    "function_panel": Transition("function_panel", ActionIntent("open_shop", "function_panel.page", "shop.entry"), "click", {}, "shop", "shop.page"),
    "shop": Transition("shop", ActionIntent("open_period_benefits", "shop.page", "shop.period_benefits"), "click", {}, "benefits", "shop.period_benefits.page"),
    "benefits": Transition("benefits", ActionIntent("claim_free_gift", "shop.period_benefits.page", "shop.daily_free_gift"), "click", {}, "claimed", "shop.daily_free_gift_claimed"),
    "claimed": Transition("claimed", ActionIntent("close_shop", "shop.page", "shop.close"), "click", {}, "home_done", "home"),
}
```

Implement recognizers and `decide(...)` with the Task 1 deterministic rule. Require same-frame `免费` and `每日特惠` text for `shop.daily_free_gift`; generic `购买`, prices, premium text, or any payment signal must not become a target. Treat `shop.daily_free_gift_claimed` as the no-op postcondition.

- [ ] **Step 3: Add Pipeline, exact assets, fixtures, registry, and interface**

```json
{
  "MJA_Daily_SHOP_FREE_GIFT_DAILY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"SHOP_FREE_GIFT_DAILY"}},
  "shop.page":{"recognition":"TemplateMatch","template":"daily/SHOP_FREE_GIFT_DAILY/shop_page.png","action":"DoNothing"},
  "shop.period_benefits":{"recognition":"TemplateMatch","template":"daily/SHOP_FREE_GIFT_DAILY/period_benefits_tab.png","action":"DoNothing"},
  "shop.period_benefits.page":{"recognition":"TemplateMatch","template":"daily/SHOP_FREE_GIFT_DAILY/period_benefits_page.png","action":"DoNothing"},
  "shop.daily_free_gift":{"recognition":"TemplateMatch","template":"daily/SHOP_FREE_GIFT_DAILY/daily_free_gift.png","action":"DoNothing"},
  "shop.daily_free_gift_claimed":{"recognition":"TemplateMatch","template":"daily/SHOP_FREE_GIFT_DAILY/daily_free_gift_claimed.png","action":"DoNothing"},
  "shop.close":{"recognition":"TemplateMatch","template":"daily/SHOP_FREE_GIFT_DAILY/shop_close.png","action":"DoNothing"}
}
```

The manifest uses only the canonical keys and maps `entry/actionable/completed/danger` to `home/shop.entry`, `shop.period_benefits.page/shop.daily_free_gift`, `shop.period_benefits.page/shop.daily_free_gift_claimed`, and `shop.period_benefits.page/unknown_dialog`; statuses are `null`, `null`, `already_complete`, and `blocked_safety`. Register/export the one definition instance and render:

```json
{"name":"shop_free_gift_daily","label":"商城每日免费礼包","entry":"MJA_Daily_SHOP_FREE_GIFT_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_shop_free_gift_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id SHOP_FREE_GIFT_DAILY`

Run: `install/.venv/bin/python -m ruff check agent/workflows/definitions/shop_free_gift_daily.py tests/workflows/test_shop_free_gift_daily.py`

Expected: PASS with one free claim maximum, an input-free completed path, cap failure, and safety denial before input.

- [ ] **Step 5: Perform the live foreground check and no-op rerun**

Run: `install/.venv/bin/python -m tools.run_cli --task shop_free_gift_daily`

Within 2–5 minutes, independently confirm `每日特惠` shows the free gift changed to claimed/unavailable and the task returns home. Rerun and require `already_complete` with zero `claim_free_gift`. Inspect the automatically created SHOP diagnostic bundle; do not claim a daily-task row reward.

- [ ] **Step 6: Commit only Task 2 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/shop_free_gift_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/shop_free_gift_daily.json assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/shop_page.png assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/period_benefits_tab.png assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/period_benefits_page.png assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/daily_free_gift.png assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/daily_free_gift_claimed.png assets/resource/image/daily/SHOP_FREE_GIFT_DAILY/shop_close.png assets/interface.json tests/fixtures/SHOP_FREE_GIFT_DAILY/manifest.json tests/fixtures/SHOP_FREE_GIFT_DAILY/entry.png tests/fixtures/SHOP_FREE_GIFT_DAILY/actionable.png tests/fixtures/SHOP_FREE_GIFT_DAILY/completed.png tests/fixtures/SHOP_FREE_GIFT_DAILY/danger.png tests/workflows/test_shop_free_gift_daily.py
git commit -m "feat: add daily shop free gift workflow"
```

### Task 3: Implement WEEKLY_FREE_GIFT_MONDAY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/weekly_free_gift_monday.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/weekly_free_gift_monday.json`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/gift_tab.png`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/gift_tab_page.png`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_must_buy.png`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_page.png`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_lucky_bag_free.png`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_lucky_bag_claimed.png`
- Create: `assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/shop_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/manifest.json`
- Create: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/entry.png`
- Create: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/actionable.png`
- Create: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/completed.png`
- Create: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/danger.png`
- Create: `tests/workflows/test_weekly_free_gift_monday.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; `TaskPolicy.eligible_weekdays`; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]` and `NoCaptureDriver`.
- Produces: `WEEKLY_FREE_GIFT_MONDAY_DEFINITION: WorkflowDefinition`; registry entry; Pipeline `MJA_Daily_WEEKLY_FREE_GIFT_MONDAY`; ProjectInterface task `weekly_free_gift_monday`.

- [ ] **Step 1: Write and run the failing Monday/no-open, fixture, cap, and safety tests**

```python
def test_non_monday_does_not_capture_or_open_shop(tmp_path: Path) -> None:
    driver = NoCaptureDriver()
    diagnostics = RunDiagnostics.create(
        tmp_path,
        task_id="WEEKLY_FREE_GIFT_MONDAY",
        now=lambda: datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
    )
    result = run_workflow(
        WEEKLY_FREE_GIFT_MONDAY_DEFINITION,
        driver,
        TASK_POLICIES["WEEKLY_FREE_GIFT_MONDAY"],
        diagnostics,
    )
    assert result.status is TaskStatus.NOT_ELIGIBLE
    assert driver.capture_count == 0
    assert driver.executed == []

def test_weekly_actionable_completed_cap_and_safety() -> None:
    markers = ("shop.weekly.page", "shop.weekly_lucky_bag_free")
    action, allowed = evaluate_decision(WEEKLY_FREE_GIFT_MONDAY_DEFINITION, "weekly", markers, texts=("每周福袋", "免费"))
    complete, _ = evaluate_decision(WEEKLY_FREE_GIFT_MONDAY_DEFINITION, "weekly", ("shop.weekly.page", "shop.weekly_lucky_bag_claimed"))
    _, capped = evaluate_decision(WEEKLY_FREE_GIFT_MONDAY_DEFINITION, "weekly", markers, {"claim_weekly_lucky_bag": 1}, ("每周福袋", "免费"))
    _, paid = evaluate_decision(WEEKLY_FREE_GIFT_MONDAY_DEFINITION, "weekly", markers, texts=("每周福袋", "免费", "Apple Pay"))
    _, unknown = evaluate_decision(WEEKLY_FREE_GIFT_MONDAY_DEFINITION, "weekly", markers, danger_markers=("unknown_dialog",))
    assert action.transition is not None and allowed is not None and allowed.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_weekly_free_gift_monday.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.weekly_free_gift_monday'`.

- [ ] **Step 2: Add the Monday policy and concrete definition**

```python
"WEEKLY_FREE_GIFT_MONDAY": TaskPolicy(
    task_id="WEEKLY_FREE_GIFT_MONDAY", label="周一免费福袋", entry="MJA_Daily_WEEKLY_FREE_GIFT_MONDAY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=15,
    action_caps={"open_function_panel": 1, "open_shop": 1, "open_gift_tab": 1, "open_weekly_must_buy": 1, "claim_weekly_lucky_bag": 1, "close_shop": 1},
    approved_resources=frozenset(), eligible_weekdays=frozenset({0}),
),

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_function_panel", "home", "function_panel.open"), "click", {}, "function_panel", "function_panel.page"),
    "function_panel": Transition("function_panel", ActionIntent("open_shop", "function_panel.page", "shop.entry"), "click", {}, "shop", "shop.page"),
    "shop": Transition("shop", ActionIntent("open_gift_tab", "shop.page", "shop.gift_tab"), "click", {}, "gift_tab", "shop.gift_tab.page"),
    "gift_tab": Transition("gift_tab", ActionIntent("open_weekly_must_buy", "shop.gift_tab.page", "shop.weekly_must_buy"), "click", {}, "weekly", "shop.weekly.page"),
    "weekly": Transition("weekly", ActionIntent("claim_weekly_lucky_bag", "shop.weekly.page", "shop.weekly_lucky_bag_free"), "click", {}, "claimed", "shop.weekly_lucky_bag_claimed"),
    "claimed": Transition("claimed", ActionIntent("close_shop", "shop.page", "shop.close"), "click", {}, "home_done", "home"),
}
```

The runner must return `not_eligible` from the policy clock before capture on Tuesday–Sunday. On Monday, require same-frame `每周福袋` and `免费`; a price, purchase confirmation, or ambiguous currency is blocked.

- [ ] **Step 3: Add exact assets, registration, and interface**

```json
{
  "MJA_Daily_WEEKLY_FREE_GIFT_MONDAY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"WEEKLY_FREE_GIFT_MONDAY"}},
  "shop.gift_tab":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/gift_tab.png","action":"DoNothing"},
  "shop.gift_tab.page":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/gift_tab_page.png","action":"DoNothing"},
  "shop.weekly_must_buy":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/weekly_must_buy.png","action":"DoNothing"},
  "shop.weekly.page":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/weekly_page.png","action":"DoNothing"},
  "shop.weekly_lucky_bag_free":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/weekly_lucky_bag_free.png","action":"DoNothing"},
  "shop.weekly_lucky_bag_claimed":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/weekly_lucky_bag_claimed.png","action":"DoNothing"},
  "shop.close":{"recognition":"TemplateMatch","template":"daily/WEEKLY_FREE_GIFT_MONDAY/shop_close.png","action":"DoNothing"}
}
```

Use only canonical manifest keys. Map the four fixtures to `home/shop.entry`, `shop.weekly.page/shop.weekly_lucky_bag_free`, `shop.weekly.page/shop.weekly_lucky_bag_claimed`, and `shop.weekly.page/unknown_dialog`, with statuses `null`, `null`, `already_complete`, and `blocked_safety`. Render:

```json
{"name":"weekly_free_gift_monday","label":"周一免费福袋","entry":"MJA_Daily_WEEKLY_FREE_GIFT_MONDAY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_weekly_free_gift_monday.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id WEEKLY_FREE_GIFT_MONDAY`

Expected: PASS, including non-Monday zero capture/input, Monday normal/already/cap/safety branches, and the exact lowercase interface name.

- [ ] **Step 5: Perform the 2–5 minute foreground checks**

On a non-Monday run: `install/.venv/bin/python -m tools.run_cli --task weekly_free_gift_monday`

Verify `not_eligible` and no shop capture/input. On the next real Monday, run the same command, independently verify the free weekly bag changed to claimed, and rerun for `already_complete` with zero protected claim. If Monday is unavailable during implementation, do not substitute fixtures for live proof and do not write any machine record in Batch 1; describe the unavailable branch in the human report so the later aggregate admission plan creates `verification/tasks/WEEKLY_FREE_GIFT_MONDAY.json` as `live_pending`.

- [ ] **Step 6: Commit only Task 3 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/weekly_free_gift_monday.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/weekly_free_gift_monday.json assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/gift_tab.png assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/gift_tab_page.png assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_must_buy.png assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_page.png assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_lucky_bag_free.png assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/weekly_lucky_bag_claimed.png assets/resource/image/daily/WEEKLY_FREE_GIFT_MONDAY/shop_close.png assets/interface.json tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/manifest.json tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/entry.png tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/actionable.png tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/completed.png tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/danger.png tests/workflows/test_weekly_free_gift_monday.py
git commit -m "feat: add Monday free gift workflow"
```

### Task 4: Implement TRIAL_SWORD_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/trial_sword_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/trial_sword_daily.json`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/trial_page.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/trial_reward_claim.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/free_trial.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/trial_reward_claimed.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/free_trial_used.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/reward_popup.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/free_popup.png`
- Create: `assets/resource/image/daily/TRIAL_SWORD_DAILY/popup_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/TRIAL_SWORD_DAILY/manifest.json`
- Create: `tests/fixtures/TRIAL_SWORD_DAILY/entry.png`
- Create: `tests/fixtures/TRIAL_SWORD_DAILY/actionable.png`
- Create: `tests/fixtures/TRIAL_SWORD_DAILY/completed.png`
- Create: `tests/fixtures/TRIAL_SWORD_DAILY/danger.png`
- Create: `tests/workflows/test_trial_sword_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `TRIAL_SWORD_DAILY_DEFINITION: WorkflowDefinition`; registry entry; Pipeline `MJA_Daily_TRIAL_SWORD_DAILY`; ProjectInterface task `trial_sword_daily`.

- [ ] **Step 1: Write and run failing normal/already/cap/safety tests**

```python
def test_trial_actionable_and_completed_decisions() -> None:
    reward, reward_safety = evaluate_decision(TRIAL_SWORD_DAILY_DEFINITION, "trial", ("trial.page", "trial.reward_claim"))
    free, free_safety = evaluate_decision(TRIAL_SWORD_DAILY_DEFINITION, "free_trial", ("trial.page", "trial.free_claim"), texts=("免费",))
    skipped_reward, skipped_safety = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "trial",
        ("trial.page", "trial.reward_claimed", "trial.free_claim"),
        texts=("免费",),
    )
    complete, _ = evaluate_decision(
        TRIAL_SWORD_DAILY_DEFINITION,
        "trial",
        ("trial.page", "trial.reward_claimed", "trial.free_used"),
    )
    assert reward.transition is not None and reward_safety is not None and reward_safety.allowed
    assert free.transition is not None and free_safety is not None and free_safety.allowed
    assert skipped_reward.transition is not None
    assert skipped_reward.transition.intent.action_id == "claim_free_trial"
    assert skipped_safety is not None and skipped_safety.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE

def test_trial_cap_and_payment_fail_closed() -> None:
    markers = ("trial.page", "trial.free_claim")
    _, capped = evaluate_decision(TRIAL_SWORD_DAILY_DEFINITION, "free_trial", markers, {"claim_free_trial": 1}, ("免费",))
    _, paid = evaluate_decision(TRIAL_SWORD_DAILY_DEFINITION, "free_trial", markers, texts=("免费", "￥30"))
    _, unknown = evaluate_decision(TRIAL_SWORD_DAILY_DEFINITION, "free_trial", markers, danger_markers=("unknown_dialog",))
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_trial_sword_daily.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.trial_sword_daily'`.

- [ ] **Step 2: Add the policy and exact two-claim flow**

```python
"TRIAL_SWORD_DAILY": TaskPolicy(
    task_id="TRIAL_SWORD_DAILY", label="每日试剑", entry="MJA_Daily_TRIAL_SWORD_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=14,
    action_caps={"open_trial_sword": 1, "claim_trial_sword_reward": 1, "close_reward_popup": 1, "claim_free_trial": 1, "close_free_popup": 1},
    approved_resources=frozenset(),
),

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_trial_sword", "home", "trial.open"), "click", {}, "trial", "trial.page"),
    "trial": Transition("trial", ActionIntent("claim_trial_sword_reward", "trial.page", "trial.reward_claim"), "click", {}, "reward_popup", "trial.reward_popup"),
    "reward_popup": Transition("reward_popup", ActionIntent("close_reward_popup", "trial.reward_popup", "trial.popup_close"), "click", {}, "free_trial", "trial.page"),
    "free_trial": Transition("free_trial", ActionIntent("claim_free_trial", "trial.page", "trial.free_claim"), "click", {}, "free_popup", "trial.free_popup"),
    "free_popup": Transition("free_popup", ActionIntent("close_free_popup", "trial.free_popup", "trial.popup_close"), "click", {}, "home_done", "home"),
}
```

In state `trial`, choose `trial.reward_claim` when present; if `trial.reward_claimed` is present but `trial.free_claim` is still visible, skip directly to the free transition. Return `already_complete` only when the same frame proves both `trial.reward_claimed` and `trial.free_used`. `trial.free_claim` requires exact same-frame `免费`. Reward popups close only through `trial.popup_close`. Do not claim the corresponding daily-task row here.

- [ ] **Step 3: Add Pipeline, exact assets, fixtures, registry, and interface**

```json
{
  "MJA_Daily_TRIAL_SWORD_DAILY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"TRIAL_SWORD_DAILY"}},
  "trial.page":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/trial_page.png","action":"DoNothing"},
  "trial.reward_claim":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/trial_reward_claim.png","action":"DoNothing"},
  "trial.free_claim":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/free_trial.png","action":"DoNothing"},
  "trial.reward_claimed":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/trial_reward_claimed.png","action":"DoNothing"},
  "trial.free_used":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/free_trial_used.png","action":"DoNothing"},
  "trial.reward_popup":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/reward_popup.png","action":"DoNothing"},
  "trial.free_popup":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/free_popup.png","action":"DoNothing"},
  "trial.popup_close":{"recognition":"TemplateMatch","template":"daily/TRIAL_SWORD_DAILY/popup_close.png","action":"DoNothing"}
}
```

Using only canonical manifest keys, fixtures map to `home/trial.open`, `trial.page/trial.reward_claim+trial.free_claim`, `trial.page/trial.reward_claimed+trial.free_used`, and `trial.page/unknown_dialog`, with statuses `null`, `null`, `already_complete`, and `blocked_safety`. Render:

```json
{"name":"trial_sword_daily","label":"每日试剑","entry":"MJA_Daily_TRIAL_SWORD_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_trial_sword_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id TRIAL_SWORD_DAILY`

Expected: PASS for the ordered two-claim normal path, already-complete path, each cap, and danger with no input.

- [ ] **Step 5: Run live and no-op checks**

Run: `install/.venv/bin/python -m tools.run_cli --task trial_sword_daily`

Within 2–5 minutes, verify the ordinary reward and explicitly free trial each change state, both popups close through recognized controls, and the final home marker is present. Rerun for `already_complete` with zero protected claims and inspect the automatically created diagnostic bundle.

- [ ] **Step 6: Commit only Task 4 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/trial_sword_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/trial_sword_daily.json assets/resource/image/daily/TRIAL_SWORD_DAILY/trial_page.png assets/resource/image/daily/TRIAL_SWORD_DAILY/trial_reward_claim.png assets/resource/image/daily/TRIAL_SWORD_DAILY/free_trial.png assets/resource/image/daily/TRIAL_SWORD_DAILY/trial_reward_claimed.png assets/resource/image/daily/TRIAL_SWORD_DAILY/free_trial_used.png assets/resource/image/daily/TRIAL_SWORD_DAILY/reward_popup.png assets/resource/image/daily/TRIAL_SWORD_DAILY/free_popup.png assets/resource/image/daily/TRIAL_SWORD_DAILY/popup_close.png assets/interface.json tests/fixtures/TRIAL_SWORD_DAILY/manifest.json tests/fixtures/TRIAL_SWORD_DAILY/entry.png tests/fixtures/TRIAL_SWORD_DAILY/actionable.png tests/fixtures/TRIAL_SWORD_DAILY/completed.png tests/fixtures/TRIAL_SWORD_DAILY/danger.png tests/workflows/test_trial_sword_daily.py
git commit -m "feat: add daily trial sword workflow"
```

### Task 5: Implement FREE_APPRAISAL_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/free_appraisal_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/free_appraisal_daily.json`
- Create: `assets/resource/image/daily/FREE_APPRAISAL_DAILY/appraisal_page.png`
- Create: `assets/resource/image/daily/FREE_APPRAISAL_DAILY/free_appraisal_once.png`
- Create: `assets/resource/image/daily/FREE_APPRAISAL_DAILY/appraisal_used.png`
- Create: `assets/resource/image/daily/FREE_APPRAISAL_DAILY/result_popup.png`
- Create: `assets/resource/image/daily/FREE_APPRAISAL_DAILY/result_popup_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/FREE_APPRAISAL_DAILY/manifest.json`
- Create: `tests/fixtures/FREE_APPRAISAL_DAILY/entry.png`
- Create: `tests/fixtures/FREE_APPRAISAL_DAILY/actionable.png`
- Create: `tests/fixtures/FREE_APPRAISAL_DAILY/completed.png`
- Create: `tests/fixtures/FREE_APPRAISAL_DAILY/danger.png`
- Create: `tests/workflows/test_free_appraisal_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `FREE_APPRAISAL_DAILY_DEFINITION: WorkflowDefinition`; registry entry; Pipeline `MJA_Daily_FREE_APPRAISAL_DAILY`; ProjectInterface task `free_appraisal_daily`.

- [ ] **Step 1: Write and run failing normal/already/cap/safety tests**

```python
def test_appraisal_policy_allows_one_free_use() -> None:
    policy = TASK_POLICIES["FREE_APPRAISAL_DAILY"]
    assert policy.action_caps["claim_free_appraisal_once"] == 1
    assert policy.approved_resources == frozenset()

def test_appraisal_actionable_and_completed_decisions() -> None:
    action, allowed = evaluate_decision(FREE_APPRAISAL_DAILY_DEFINITION, "appraisal", ("appraisal.page", "appraisal.free_once"), texts=("免费鉴宝",))
    complete, _ = evaluate_decision(FREE_APPRAISAL_DAILY_DEFINITION, "appraisal", ("appraisal.page", "appraisal.used"))
    assert action.transition is not None and allowed is not None and allowed.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE

def test_appraisal_cap_and_payment_fail() -> None:
    markers = ("appraisal.page", "appraisal.free_once")
    _, capped = evaluate_decision(FREE_APPRAISAL_DAILY_DEFINITION, "appraisal", markers, {"claim_free_appraisal_once": 1}, ("免费鉴宝",))
    _, paid = evaluate_decision(FREE_APPRAISAL_DAILY_DEFINITION, "appraisal", markers, texts=("免费鉴宝", "充值"))
    _, unknown = evaluate_decision(FREE_APPRAISAL_DAILY_DEFINITION, "appraisal", markers, danger_markers=("unknown_dialog",))
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_free_appraisal_daily.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.free_appraisal_daily'`.

- [ ] **Step 2: Add the policy and exact free-once definition**

```python
"FREE_APPRAISAL_DAILY": TaskPolicy(
    task_id="FREE_APPRAISAL_DAILY", label="每日免费鉴宝", entry="MJA_Daily_FREE_APPRAISAL_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=10,
    action_caps={"open_appraisal": 1, "claim_free_appraisal_once": 1, "close_appraisal_popup": 1},
    approved_resources=frozenset(),
),

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_appraisal", "home", "appraisal.open"), "click", {}, "appraisal", "appraisal.page"),
    "appraisal": Transition("appraisal", ActionIntent("claim_free_appraisal_once", "appraisal.page", "appraisal.free_once"), "click", {}, "result_popup", "appraisal.result_popup"),
    "result_popup": Transition("result_popup", ActionIntent("close_appraisal_popup", "appraisal.result_popup", "appraisal.popup_close"), "click", {}, "home_done", "home"),
}
```

Require exact same-frame `免费鉴宝` for the one protected action. `appraisal.used` is the no-op marker. Any replacement purchase, extra draw, price, premium currency, or generic purchase text is blocked.

- [ ] **Step 3: Add Pipeline, exact assets, fixtures, registry, and interface**

```json
{
  "MJA_Daily_FREE_APPRAISAL_DAILY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"FREE_APPRAISAL_DAILY"}},
  "appraisal.page":{"recognition":"TemplateMatch","template":"daily/FREE_APPRAISAL_DAILY/appraisal_page.png","action":"DoNothing"},
  "appraisal.free_once":{"recognition":"TemplateMatch","template":"daily/FREE_APPRAISAL_DAILY/free_appraisal_once.png","action":"DoNothing"},
  "appraisal.used":{"recognition":"TemplateMatch","template":"daily/FREE_APPRAISAL_DAILY/appraisal_used.png","action":"DoNothing"},
  "appraisal.result_popup":{"recognition":"TemplateMatch","template":"daily/FREE_APPRAISAL_DAILY/result_popup.png","action":"DoNothing"},
  "appraisal.popup_close":{"recognition":"TemplateMatch","template":"daily/FREE_APPRAISAL_DAILY/result_popup_close.png","action":"DoNothing"}
}
```

Using only canonical manifest keys, fixtures map to `home/appraisal.open`, `appraisal.page/appraisal.free_once`, `appraisal.page/appraisal.used`, and `appraisal.page/unknown_dialog`, with statuses `null`, `null`, `already_complete`, and `blocked_safety`. Render:

```json
{"name":"free_appraisal_daily","label":"每日免费鉴宝","entry":"MJA_Daily_FREE_APPRAISAL_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_free_appraisal_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id FREE_APPRAISAL_DAILY`

Expected: PASS with exactly one free use, no-op completion, cap failure, and payment danger denial.

- [ ] **Step 5: Run live and no-op checks**

Run: `install/.venv/bin/python -m tools.run_cli --task free_appraisal_daily`

Within 2–5 minutes, verify the free-once marker changes to used, close the result popup through its recognized control, and confirm home. Rerun for `already_complete` with zero appraisal actions. Do not accept an extra appraisal that consumes any resource.

- [ ] **Step 6: Commit only Task 5 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/free_appraisal_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/free_appraisal_daily.json assets/resource/image/daily/FREE_APPRAISAL_DAILY/appraisal_page.png assets/resource/image/daily/FREE_APPRAISAL_DAILY/free_appraisal_once.png assets/resource/image/daily/FREE_APPRAISAL_DAILY/appraisal_used.png assets/resource/image/daily/FREE_APPRAISAL_DAILY/result_popup.png assets/resource/image/daily/FREE_APPRAISAL_DAILY/result_popup_close.png assets/interface.json tests/fixtures/FREE_APPRAISAL_DAILY/manifest.json tests/fixtures/FREE_APPRAISAL_DAILY/entry.png tests/fixtures/FREE_APPRAISAL_DAILY/actionable.png tests/fixtures/FREE_APPRAISAL_DAILY/completed.png tests/fixtures/FREE_APPRAISAL_DAILY/danger.png tests/workflows/test_free_appraisal_daily.py
git commit -m "feat: add daily free appraisal workflow"
```

### Task 6: Implement COLLECTION_DEPLOYMENT_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/collection_deployment_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/collection_deployment_daily.json`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/painting_scroll_page.png`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/yanwu_world.png`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/yanwu_page.png`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/collection_deployment.png`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/harvest_all.png`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/harvested.png`
- Create: `assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/collection_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/manifest.json`
- Create: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/entry.png`
- Create: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/actionable.png`
- Create: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/completed.png`
- Create: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/danger.png`
- Create: `tests/workflows/test_collection_deployment_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; foundation painting-scroll navigation markers; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `COLLECTION_DEPLOYMENT_DAILY_DEFINITION: WorkflowDefinition`; registry entry; Pipeline `MJA_Daily_COLLECTION_DEPLOYMENT_DAILY`; ProjectInterface task `collection_deployment_daily`.

- [ ] **Step 1: Write and run failing world-gated normal/already/cap/safety tests**

```python
def test_harvest_requires_yanwu_world_on_same_frame() -> None:
    decision, safety = evaluate_decision(COLLECTION_DEPLOYMENT_DAILY_DEFINITION, "collection", ("collection.page", "collection.harvest_all"))
    assert decision.status is TaskStatus.FAILED
    assert safety is None

def test_collection_actionable_completed_cap_and_safety() -> None:
    markers = ("collection.page", "collection.yanwu_world", "collection.harvest_all")
    action, allowed = evaluate_decision(COLLECTION_DEPLOYMENT_DAILY_DEFINITION, "collection", markers)
    complete, _ = evaluate_decision(COLLECTION_DEPLOYMENT_DAILY_DEFINITION, "collection", ("collection.page", "collection.yanwu_world", "collection.harvested"))
    _, capped = evaluate_decision(COLLECTION_DEPLOYMENT_DAILY_DEFINITION, "collection", markers, {"claim_all_collection": 1})
    _, paid = evaluate_decision(COLLECTION_DEPLOYMENT_DAILY_DEFINITION, "collection", markers, texts=("Apple Pay",))
    _, unknown = evaluate_decision(COLLECTION_DEPLOYMENT_DAILY_DEFINITION, "collection", markers, danger_markers=("unknown_dialog",))
    assert action.transition is not None and allowed is not None and allowed.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_collection_deployment_daily.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.collection_deployment_daily'`.

- [ ] **Step 2: Add the policy and exact world-gated transition table**

```python
"COLLECTION_DEPLOYMENT_DAILY": TaskPolicy(
    task_id="COLLECTION_DEPLOYMENT_DAILY", label="采集部署收获", entry="MJA_Daily_COLLECTION_DEPLOYMENT_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=16,
    action_caps={"open_painting_scroll": 1, "select_yanwu_world": 1, "open_collection_deployment": 1, "claim_all_collection": 1, "close_collection_deployment": 1},
    approved_resources=frozenset(),
),

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_painting_scroll", "home", "painting_scroll.open"), "click", {}, "painting_scroll", "painting_scroll.page"),
    "painting_scroll": Transition("painting_scroll", ActionIntent("select_yanwu_world", "painting_scroll.page", "collection.yanwu_world"), "click", {}, "yanwu", "yanwu.page"),
    "yanwu": Transition("yanwu", ActionIntent("open_collection_deployment", "yanwu.page", "collection.open"), "click", {}, "collection", "collection.page"),
    "collection": Transition("collection", ActionIntent("claim_all_collection", "collection.page", "collection.harvest_all"), "click", {}, "harvested", "collection.harvested"),
    "harvested": Transition("harvested", ActionIntent("close_collection_deployment", "collection.page", "collection.close"), "click", {}, "home_done", "home"),
}
```

The harvest evidence must contain `collection.page`, `collection.yanwu_world`, and exactly one `collection.harvest_all` on the same frame. `collection.harvested` is independently recognized. Do not claim the daily-task row generated by this action.

- [ ] **Step 3: Add Pipeline, exact assets, fixtures, registry, and interface**

```json
{
  "MJA_Daily_COLLECTION_DEPLOYMENT_DAILY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"COLLECTION_DEPLOYMENT_DAILY"}},
  "painting_scroll.page":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/painting_scroll_page.png","action":"DoNothing"},
  "collection.yanwu_world":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/yanwu_world.png","action":"DoNothing"},
  "yanwu.page":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/yanwu_page.png","action":"DoNothing"},
  "collection.page":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/collection_deployment.png","action":"DoNothing"},
  "collection.harvest_all":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/harvest_all.png","action":"DoNothing"},
  "collection.harvested":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/harvested.png","action":"DoNothing"},
  "collection.close":{"recognition":"TemplateMatch","template":"daily/COLLECTION_DEPLOYMENT_DAILY/collection_close.png","action":"DoNothing"}
}
```

Using only canonical manifest keys, fixtures map to `painting_scroll.page/collection.yanwu_world`, `collection.page/collection.harvest_all`, `collection.page/collection.harvested`, and `collection.page/unknown_dialog`, with statuses `null`, `null`, `already_complete`, and `blocked_safety`. Render:

```json
{"name":"collection_deployment_daily","label":"采集部署收获","entry":"MJA_Daily_COLLECTION_DEPLOYMENT_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_collection_deployment_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id COLLECTION_DEPLOYMENT_DAILY`

Expected: PASS; wrong-world evidence fails without input, harvest occurs once, completed is no-op, cap fails, and danger blocks.

- [ ] **Step 5: Run live and no-op checks**

Run: `install/.venv/bin/python -m tools.run_cli --task collection_deployment_daily`

Within 2–5 minutes, independently verify `画卷 → 偃武世界 → 采集部署`, one harvest state change, recognized close, and home. Confirm every mapped point in `action-trace.jsonl` derives from the current recognition box and calibration. Rerun for `already_complete` with zero harvest actions.

- [ ] **Step 6: Commit only Task 6 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/collection_deployment_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/collection_deployment_daily.json assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/painting_scroll_page.png assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/yanwu_world.png assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/yanwu_page.png assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/collection_deployment.png assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/harvest_all.png assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/harvested.png assets/resource/image/daily/COLLECTION_DEPLOYMENT_DAILY/collection_close.png assets/interface.json tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/manifest.json tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/entry.png tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/actionable.png tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/completed.png tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/danger.png tests/workflows/test_collection_deployment_daily.py
git commit -m "feat: add daily collection deployment workflow"
```

### Task 7: Implement DAILY_TASK_REWARD_CLAIM_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/daily_task_reward_claim_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/daily_task_reward_claim_daily.json`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/daily_page.png`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/completed_row_claim.png`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/claimed_row.png`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/unlocked_activity_chest.png`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/green_checked_chest.png`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/no_claimable_row.png`
- Create: `assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/reward_popup_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/manifest.json`
- Create: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/entry.png`
- Create: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/actionable.png`
- Create: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/completed.png`
- Create: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/danger.png`
- Create: `tests/workflows/test_daily_task_reward_claim_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]`; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION: WorkflowDefinition`; registry entry; Pipeline `MJA_Daily_DAILY_TASK_REWARD_CLAIM_DAILY`; ProjectInterface task `daily_task_reward_claim_daily`.

- [ ] **Step 1: Write and run failing row/chest normal, already, cap, and safety tests**

```python
def test_daily_reward_counters_are_separate() -> None:
    caps = TASK_POLICIES["DAILY_TASK_REWARD_CLAIM_DAILY"].action_caps
    assert caps["claim_completed_daily_row"] == 50
    assert caps["claim_unlocked_activity_chest"] == 10
    assert "claim_everything" not in caps

def test_daily_reward_row_first_and_completed_decisions() -> None:
    markers = ("daily.page", "daily.completed_row_claim", "daily.unlocked_activity_chest")
    action, allowed = evaluate_decision(DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION, "daily", markers)
    complete, _ = evaluate_decision(DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION, "daily", ("daily.page", "daily.no_claimable_row", "daily.green_checked_chest"))
    assert action.transition is not None and action.transition.intent.action_id == "claim_completed_daily_row"
    assert allowed is not None and allowed.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE

@pytest.mark.parametrize(("action", "target", "cap"), [
    ("claim_completed_daily_row", "daily.completed_row_claim", 50),
    ("claim_unlocked_activity_chest", "daily.unlocked_activity_chest", 10),
])
def test_daily_reward_caps_and_payment_fail(action: str, target: str, cap: int) -> None:
    markers = ("daily.page", target)
    _, capped = evaluate_decision(DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION, "daily", markers, {action: cap})
    _, paid = evaluate_decision(DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION, "daily", markers, texts=("￥98",))
    _, unknown = evaluate_decision(DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION, "daily", markers, danger_markers=("unknown_dialog",))
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert paid is not None and paid.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_daily_task_reward_claim_daily.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.daily_task_reward_claim_daily'`.

- [ ] **Step 2: Add the policy and bounded row/chest loops**

```python
"DAILY_TASK_REWARD_CLAIM_DAILY": TaskPolicy(
    task_id="DAILY_TASK_REWARD_CLAIM_DAILY", label="日常任务奖励领取", entry="MJA_Daily_DAILY_TASK_REWARD_CLAIM_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=70,
    action_caps={"open_function_panel": 1, "open_daily_tasks": 1, "claim_completed_daily_row": 50, "close_reward_popup": 60, "claim_unlocked_activity_chest": 10, "close_daily_tasks": 1},
    approved_resources=frozenset(),
),

ROW = Transition("daily", ActionIntent("claim_completed_daily_row", "daily.page", "daily.completed_row_claim"), "click", {}, "daily", "daily.row_claimed")
CHEST = Transition("daily", ActionIntent("claim_unlocked_activity_chest", "daily.page", "daily.unlocked_activity_chest"), "click", {}, "daily", "daily.green_checked_chest")
```

The definition opens function panel then daily tasks. In `daily`, it chooses exactly one visible orange completed-row claim first; after no row remains, exactly one unlocked activity chest; after neither remains and `daily.no_claimable_row` plus all visible `daily.green_checked_chest` markers are recognized, it returns `completed` or `already_complete`. Expected reward popups close only through `daily.reward_popup_close`. It never targets global `一键领取`, locked chests, or incomplete rows.

- [ ] **Step 3: Add Pipeline, exact assets, fixtures, registry, and interface**

```json
{
  "MJA_Daily_DAILY_TASK_REWARD_CLAIM_DAILY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"DAILY_TASK_REWARD_CLAIM_DAILY"}},
  "daily.page":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/daily_page.png","action":"DoNothing"},
  "daily.completed_row_claim":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/completed_row_claim.png","action":"DoNothing"},
  "daily.row_claimed":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/claimed_row.png","action":"DoNothing"},
  "daily.unlocked_activity_chest":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/unlocked_activity_chest.png","action":"DoNothing"},
  "daily.green_checked_chest":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/green_checked_chest.png","action":"DoNothing"},
  "daily.no_claimable_row":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/no_claimable_row.png","action":"DoNothing"},
  "daily.reward_popup_close":{"recognition":"TemplateMatch","template":"daily/DAILY_TASK_REWARD_CLAIM_DAILY/reward_popup_close.png","action":"DoNothing"}
}
```

The canonical-key manifest's actionable fixture contains both an orange row claim and an unlocked chest so deterministic row-first behavior is asserted. The completed fixture contains no claimable row and green checked chests. The danger fixture has `expected_page: "daily.page"`, `expected_targets: ["unknown_dialog"]`, and `expected_status: "blocked_safety"`. Render:

```json
{"name":"daily_task_reward_claim_daily","label":"日常任务奖励领取","entry":"MJA_Daily_DAILY_TASK_REWARD_CLAIM_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_daily_task_reward_claim_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id DAILY_TASK_REWARD_CLAIM_DAILY`

Expected: PASS; row and chest counters remain separate, each loop terminates, completed is no-op, both caps fail closed, and danger sends no input.

- [ ] **Step 5: Run live and no-op checks**

Run: `install/.venv/bin/python -m tools.run_cli --task daily_task_reward_claim_daily`

Within 2–5 minutes, independently verify each claimed orange row changes state, every claimed unlocked activity chest becomes a green check, and the final inspected region contains neither target. Confirm counts in `result.json`, close safely, rerun for `already_complete`, and keep all other workflows from claiming these rows themselves.

- [ ] **Step 6: Commit only Task 7 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/daily_task_reward_claim_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/daily_task_reward_claim_daily.json assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/daily_page.png assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/completed_row_claim.png assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/claimed_row.png assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/unlocked_activity_chest.png assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/green_checked_chest.png assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/no_claimable_row.png assets/resource/image/daily/DAILY_TASK_REWARD_CLAIM_DAILY/reward_popup_close.png assets/interface.json tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/manifest.json tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/entry.png tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/actionable.png tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/completed.png tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/danger.png tests/workflows/test_daily_task_reward_claim_daily.py
git commit -m "feat: add daily task reward workflow"
```

### Task 8: Implement BATTLE_PASS_REWARD_DAILY

**Files:**

- Modify: `agent/workflows/catalog.py`
- Create: `agent/workflows/definitions/battle_pass_reward_daily.py`
- Modify: `agent/workflows/definitions/__init__.py`
- Modify: `agent/workflows/registry.py`
- Create: `assets/resource/pipeline/daily/battle_pass_reward_daily.json`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/battle_pass_page.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/tasks_tab.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/task_reward_claim.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/task_reward_claimed.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/no_task_reward.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/rewards_tab.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_track_label.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_red_dot_reward.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_reward_claimed.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_all_claimed.png`
- Create: `assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/battle_pass_close.png`
- Modify: `assets/interface.json`
- Create: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/manifest.json`
- Create: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/entry.png`
- Create: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/actionable.png`
- Create: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/completed.png`
- Create: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/danger.png`
- Create: `tests/workflows/test_battle_pass_reward_daily.py`

**Interfaces:**

- Consumes: `TASK_POLICIES: Mapping[str, TaskPolicy]` in canonical order; `StateSnapshot`; `Decision.act(transition: Transition) -> Decision`; `Decision.finish(status: TaskStatus, postcondition: str, *, error_code: str | None = None) -> Decision`; `Transition`; `WorkflowDefinition`; `TaskStatus`; exact `VisualEvidence(frame_id, page_hits, target_hits, danger_hits, recognizer_frame_ids, texts, resource_hits)`; `ActionIntent`; `authorize_action(...) -> SafetyDecision`; `run_workflow(...) -> TaskResult`; `DailyWorkflowAction`; `RunDiagnostics.create(...) -> RunDiagnostics`; test-only `evaluate_decision(...) -> tuple[Decision, SafetyDecision | None]`.
- Produces: `BATTLE_PASS_REWARD_DAILY_DEFINITION: WorkflowDefinition`; registry entry; Pipeline `MJA_Daily_BATTLE_PASS_REWARD_DAILY`; ProjectInterface task `battle_pass_reward_daily`.

- [ ] **Step 1: Write and run failing free-track normal/already/cap/safety tests**

```python
def test_battle_pass_is_basic_track_only_and_last() -> None:
    caps = TASK_POLICIES["BATTLE_PASS_REWARD_DAILY"].action_caps
    assert caps["claim_task_reward"] == 50
    assert caps["claim_basic_red_dot_reward"] == 50
    assert "one_click_claim" not in caps
    assert tuple(TASK_POLICIES)[-1] == "BATTLE_PASS_REWARD_DAILY"

def test_battle_pass_normal_and_completed_decisions() -> None:
    task, task_allowed = evaluate_decision(BATTLE_PASS_REWARD_DAILY_DEFINITION, "tasks", ("battle_pass.tasks", "battle_pass.task_reward_claim"))
    basic, basic_allowed = evaluate_decision(BATTLE_PASS_REWARD_DAILY_DEFINITION, "rewards", ("battle_pass.rewards", "battle_pass.basic_track_label", "battle_pass.basic_red_dot_reward"))
    complete, _ = evaluate_decision(BATTLE_PASS_REWARD_DAILY_DEFINITION, "rewards", ("battle_pass.rewards", "battle_pass.no_task_reward", "battle_pass.basic_all_claimed"))
    assert task.transition is not None and task_allowed is not None and task_allowed.allowed
    assert basic.transition is not None and basic_allowed is not None and basic_allowed.allowed
    assert complete.status is TaskStatus.ALREADY_COMPLETE

@pytest.mark.parametrize(("state", "action", "target", "cap"), [
    ("tasks", "claim_task_reward", "battle_pass.task_reward_claim", 50),
    ("rewards", "claim_basic_red_dot_reward", "battle_pass.basic_red_dot_reward", 50),
])
def test_battle_pass_caps_and_premium_fail(state: str, action: str, target: str, cap: int) -> None:
    markers = (f"battle_pass.{state}", target)
    _, capped = evaluate_decision(BATTLE_PASS_REWARD_DAILY_DEFINITION, state, markers, {action: cap})
    _, premium = evaluate_decision(BATTLE_PASS_REWARD_DAILY_DEFINITION, state, markers, texts=("高级战令", "￥68"))
    _, unknown = evaluate_decision(BATTLE_PASS_REWARD_DAILY_DEFINITION, state, markers, danger_markers=("unknown_dialog",))
    assert capped is not None and capped.reason is SafetyReason.ACTION_CAP_REACHED
    assert premium is not None and premium.reason is SafetyReason.PAID_SIGNAL
    assert unknown is not None and unknown.reason is SafetyReason.UNKNOWN_DIALOG
```

Run: `install/.venv/bin/python -m pytest tests/workflows/test_battle_pass_reward_daily.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent.workflows.definitions.battle_pass_reward_daily'`.

- [ ] **Step 2: Add the policy and separate ordinary/basic-track loops**

```python
"BATTLE_PASS_REWARD_DAILY": TaskPolicy(
    task_id="BATTLE_PASS_REWARD_DAILY", label="战令基础奖励领取", entry="MJA_Daily_BATTLE_PASS_REWARD_DAILY",
    risk_levels=frozenset({RiskLevel.PROTECTED_CLAIM}), max_steps=65,
    action_caps={"open_battle_pass": 1, "open_battle_pass_tasks": 1, "claim_task_reward": 50, "open_battle_pass_rewards": 1, "claim_basic_red_dot_reward": 50, "close_battle_pass": 1},
    approved_resources=frozenset(),
),

TASK_REWARD = Transition("tasks", ActionIntent("claim_task_reward", "battle_pass.tasks", "battle_pass.task_reward_claim"), "click", {}, "tasks", "battle_pass.task_reward_claimed")
BASIC_REWARD = Transition("rewards", ActionIntent("claim_basic_red_dot_reward", "battle_pass.rewards", "battle_pass.basic_red_dot_reward"), "click", {}, "rewards", "battle_pass.basic_reward_claimed")
```

The definition opens battle pass and the tasks tab, loops exactly one ordinary task-row reward per frame, opens rewards, then loops one reward only when the same frame contains `battle_pass.basic_track_label` and `battle_pass.basic_red_dot_reward`. It finishes on `battle_pass.no_task_reward` plus `battle_pass.basic_all_claimed`, then uses the recognized close. `一键领取`,高级/典藏/豪华/尊享 tracks, locked cards, recharge, purchase, and price signals are never action targets.

- [ ] **Step 3: Add Pipeline, exact assets, fixtures, registry, and interface**

```json
{
  "MJA_Daily_BATTLE_PASS_REWARD_DAILY":{"recognition":"DirectHit","action":"Custom","custom_action":"DailyWorkflowAction","custom_action_param":{"task_id":"BATTLE_PASS_REWARD_DAILY"}},
  "battle_pass.page":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/battle_pass_page.png","action":"DoNothing"},
  "battle_pass.tasks_tab":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/tasks_tab.png","action":"DoNothing"},
  "battle_pass.task_reward_claim":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/task_reward_claim.png","action":"DoNothing"},
  "battle_pass.task_reward_claimed":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/task_reward_claimed.png","action":"DoNothing"},
  "battle_pass.no_task_reward":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/no_task_reward.png","action":"DoNothing"},
  "battle_pass.rewards_tab":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/rewards_tab.png","action":"DoNothing"},
  "battle_pass.basic_track_label":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/basic_track_label.png","action":"DoNothing"},
  "battle_pass.basic_red_dot_reward":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/basic_red_dot_reward.png","action":"DoNothing"},
  "battle_pass.basic_reward_claimed":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/basic_reward_claimed.png","action":"DoNothing"},
  "battle_pass.basic_all_claimed":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/basic_all_claimed.png","action":"DoNothing"},
  "battle_pass.close":{"recognition":"TemplateMatch","template":"daily/BATTLE_PASS_REWARD_DAILY/battle_pass_close.png","action":"DoNothing"}
}
```

The canonical-key manifest's actionable fixture proves both a normal task claim and a basic-track red-dot target; completed proves no task reward and `basic_all_claimed`; danger has `expected_page: "battle_pass.rewards"`, `expected_targets: ["unknown_dialog"]`, and `expected_status: "blocked_safety"`. Render:

```json
{"name":"battle_pass_reward_daily","label":"战令基础奖励领取","entry":"MJA_Daily_BATTLE_PASS_REWARD_DAILY","resource":["mja"],"controller":["macos"],"default_check":false}
```

- [ ] **Step 4: Run focused verification**

Run: `install/.venv/bin/python -m pytest tests/workflows/test_battle_pass_reward_daily.py tests/test_fixture_contract.py tests/test_project_interface_generation.py -q`

Run: `install/.venv/bin/python -m tools.validate_fixtures --task-id BATTLE_PASS_REWARD_DAILY`

Expected: PASS; ordinary/basic loops are separately bounded, no premium target is serialized or executed, completed is no-op, both caps fail, and danger blocks before input.

- [ ] **Step 5: Run live last and verify a no-op rerun**

After all other daily workflows and `DAILY_TASK_REWARD_CLAIM_DAILY`, run: `install/.venv/bin/python -m tools.run_cli --task battle_pass_reward_daily`

Within 2–5 minutes, independently verify ordinary task rows and only basic/free-track red dots change state, no premium control appears in the action trace, the battle-pass page closes, and home is restored. Rerun for `already_complete` with zero reward claims. Any premium, payment, or ambiguous prompt returns `blocked_safety` and saves `failure.png`.

- [ ] **Step 6: Commit only Task 8 files**

```bash
git add -- agent/workflows/catalog.py agent/workflows/definitions/battle_pass_reward_daily.py agent/workflows/definitions/__init__.py agent/workflows/registry.py assets/resource/pipeline/daily/battle_pass_reward_daily.json assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/battle_pass_page.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/tasks_tab.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/task_reward_claim.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/task_reward_claimed.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/no_task_reward.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/rewards_tab.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_track_label.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_red_dot_reward.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_reward_claimed.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/basic_all_claimed.png assets/resource/image/daily/BATTLE_PASS_REWARD_DAILY/battle_pass_close.png assets/interface.json tests/fixtures/BATTLE_PASS_REWARD_DAILY/manifest.json tests/fixtures/BATTLE_PASS_REWARD_DAILY/entry.png tests/fixtures/BATTLE_PASS_REWARD_DAILY/actionable.png tests/fixtures/BATTLE_PASS_REWARD_DAILY/completed.png tests/fixtures/BATTLE_PASS_REWARD_DAILY/danger.png tests/workflows/test_battle_pass_reward_daily.py
git commit -m "feat: add safe battle pass reward workflow"
```

### Task 9: Run the Batch 1 quality gate and write its human verification report

**Files:**

- Create: `docs/verification/2026-07-28-mja-daily-workflows-batch-1.md`

**Interfaces:**

- Consumes: the eight registered definitions, eight canonical policies, eight Pipeline entries, eight lowercase ProjectInterface tasks, fixture validator, install verifier, runtime `TaskResult`, and local task-scoped diagnostics.
- Produces: a human-readable command/result/evidence index only; it does not define `verification_state` and is not a substitute for `verification/tasks/{TASK_ID}.json`.

- [ ] **Step 1: Run the full automated Batch 1 gate**

```bash
install/.venv/bin/python -m pytest tests/test_workflow_models.py tests/test_workflow_catalog.py tests/test_safety.py tests/test_workflow_engine.py tests/test_daily_workflow_action.py tests/test_fixture_contract.py tests/test_validate_fixtures.py tests/test_project_interface_generation.py tests/workflows/test_mail_reward_daily.py tests/workflows/test_shop_free_gift_daily.py tests/workflows/test_weekly_free_gift_monday.py tests/workflows/test_trial_sword_daily.py tests/workflows/test_free_appraisal_daily.py tests/workflows/test_collection_deployment_daily.py tests/workflows/test_daily_task_reward_claim_daily.py tests/workflows/test_battle_pass_reward_daily.py -q
install/.venv/bin/python -m ruff check agent tools tests
install/.venv/bin/python -m tools.verify_install install
git diff --check
```

Expected: PASS. All eight fixture sets contain exactly four PNGs, all runtime values belong to the five canonical statuses, and every daily Pipeline calls only `DailyWorkflowAction`.

- [ ] **Step 2: Verify exact interface names and entries**

```python
import json
from pathlib import Path

EXPECTED = {
    "mail_reward_daily": "MJA_Daily_MAIL_REWARD_DAILY",
    "shop_free_gift_daily": "MJA_Daily_SHOP_FREE_GIFT_DAILY",
    "weekly_free_gift_monday": "MJA_Daily_WEEKLY_FREE_GIFT_MONDAY",
    "trial_sword_daily": "MJA_Daily_TRIAL_SWORD_DAILY",
    "free_appraisal_daily": "MJA_Daily_FREE_APPRAISAL_DAILY",
    "collection_deployment_daily": "MJA_Daily_COLLECTION_DEPLOYMENT_DAILY",
    "daily_task_reward_claim_daily": "MJA_Daily_DAILY_TASK_REWARD_CLAIM_DAILY",
    "battle_pass_reward_daily": "MJA_Daily_BATTLE_PASS_REWARD_DAILY",
}
interface = json.loads(Path("assets/interface.json").read_text(encoding="utf-8"))
tasks = {item["name"]: item for item in interface["task"]}
for name, entry in EXPECTED.items():
    assert tasks[name] == {"name": name, "label": tasks[name]["label"], "entry": entry, "resource": ["mja"], "controller": ["macos"], "default_check": False}
```

Run this assertion through `tests/test_project_interface_generation.py`; do not create a second ad-hoc renderer.

Then run this read-only canonical-manifest audit for all eight fixture sets:

```bash
install/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from PIL import Image

task_ids = (
    "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY", "WEEKLY_FREE_GIFT_MONDAY",
    "TRIAL_SWORD_DAILY", "FREE_APPRAISAL_DAILY", "COLLECTION_DEPLOYMENT_DAILY",
    "DAILY_TASK_REWARD_CLAIM_DAILY", "BATTLE_PASS_REWARD_DAILY",
)
case_keys = {"image", "expected_page", "expected_targets", "expected_status"}
for task_id in task_ids:
    root = Path("tests/fixtures") / task_id
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"schema_version", "task_id", "reference_size", "cases"}
    assert manifest["schema_version"] == 1 and manifest["task_id"] == task_id
    assert set(manifest["cases"]) == {"entry", "actionable", "completed", "danger"}
    for case in manifest["cases"].values():
        assert set(case) == case_keys
        assert list(Image.open(root / case["image"]).size) == manifest["reference_size"]
    danger = manifest["cases"]["danger"]
    assert danger["expected_targets"] == ["unknown_dialog"]
    assert danger["expected_status"] == "blocked_safety"
PY
```

Expected: PASS; no alias key is accepted and every unknown-dialog fixture is input-free and safety-blocked.

- [ ] **Step 3: Run the eight foreground tasks independently**

Run each lowercase name once, in task order, with a separate 2–5 minute foreground observation:

```bash
install/.venv/bin/python -m tools.run_cli --task mail_reward_daily
install/.venv/bin/python -m tools.run_cli --task shop_free_gift_daily
install/.venv/bin/python -m tools.run_cli --task weekly_free_gift_monday
install/.venv/bin/python -m tools.run_cli --task trial_sword_daily
install/.venv/bin/python -m tools.run_cli --task free_appraisal_daily
install/.venv/bin/python -m tools.run_cli --task collection_deployment_daily
install/.venv/bin/python -m tools.run_cli --task daily_task_reward_claim_daily
install/.venv/bin/python -m tools.run_cli --task battle_pass_reward_daily
```

Expected: each task returns `completed`, `already_complete`, or the weekly policy's planned `not_eligible`; any `blocked_safety` or `failed` stops this gate before the next task. Battle pass runs last. Diagnostics are created by `RunDiagnostics`, not shell setup.

- [ ] **Step 4: Rerun every safely rerunnable task and audit boundaries**

Repeat each eligible command after its postcondition is visible. Require `already_complete`, no protected claims, an independent postcondition image, and restored foreground/window state. Then run:

```bash
git status --short
if git ls-files | rg -q '^(diagnostics|install|\.venv)/'; then exit 1; fi
rg -n 'live_pending|live_verified' diagnostics || true
```

Expected: diagnostics/install/venv output is untracked; no runtime result contains a verification state; `AGENTS.md` remains unstaged and unchanged by this plan.

- [ ] **Step 5: Write the human verification report**

Create `docs/verification/2026-07-28-mja-daily-workflows-batch-1.md` with the exact commands above, tested commit, task/result table, diagnostic relative paths, independent postconditions, no-op outcomes, and any unavailable Monday branch described in prose. Do not add `verification_state`, `live_pending`, or `live_verified` fields; the aggregate admission plan later owns those machine records exclusively under `verification/tasks/`.

- [ ] **Step 6: Commit only the quality-gate report**

```bash
git add -- docs/verification/2026-07-28-mja-daily-workflows-batch-1.md
git commit -m "docs: record Batch 1 workflow verification"
```
