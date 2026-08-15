# MJA Aggregate Daily and Live Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit only genuinely live-verified Jianzhichuan tasks into one MFAAvalonia-visible daily preset, execute them in the approved order with safe skip and task-level continuation semantics, and produce a complete reproducible acceptance record from the current checkout.

**Architecture:** Each task owns a committed verification record pointing to local diagnostic evidence and declaring fixture/live branch status. A gate refuses to render or register the aggregate preset until all required live branches are verified. The aggregate runner schedules tasks by date, keeps explicit child results, optionally reuses a recognized parent page, continues after task-level `blocked_safety` or `failed` results, and stops only on device/runtime failures before delegating final window restoration to the existing idempotent lifecycle.

**Tech Stack:** Python 3.14, MaaFramework Agent API 5.12.2, ProjectInterface V2 JSON, MFAAvalonia 2.13.0-beta.5, pytest, Ruff, macOS Computer Use visual verification.

## Global Constraints

- This plan starts only after the capture fallback, workflow foundation, and all three batch plans pass their automated gates.
- Never stage or commit `AGENTS.md`; every commit command below names exact paths.
- Do not turn fixture-only or unavailable conditional branches into `live_verified`. Keep them `live_pending` until the real branch is exercised.
- The aggregate preset remains absent from `assets/interface.json` until the admission gate proves every required single task is live verified.
- Task statuses remain exactly `completed`, `already_complete`, `not_eligible`, `blocked_safety`, and `failed`. The aggregate report contains one child result for every scheduled task unless a device/runtime failure prevents the next task from starting.
- Continue after `completed`, `already_complete`, planned `not_eligible`, `blocked_safety`, or ordinary `failed`; stop only before the next task when the device/runtime itself fails.
- Real-money/payment/login/security/unknown-currency signals stop the current task, record `blocked_safety`, and allow the aggregate to continue with the next task.
- The weekly task is executed on Monday. On other weekdays the scheduler records a planned `not_eligible` result without opening the shop.
- Battle pass remains the final workflow. No task may be reordered after it.
- Live execution consumes only the previously authorized non-paid resources and never exceeds each task policy's committed counters.

---

### Task 1: Define machine-checkable live verification records

**Files:**

- Create: `agent/workflows/verification.py`
- Create: `verification/tasks/.gitkeep`
- Create: `tests/test_live_verification_records.py`
- Update: `.gitignore`

**Interfaces:**

```python
class VerificationState(StrEnum):
    FIXTURE_VERIFIED = "fixture_verified"
    LIVE_PENDING = "live_pending"
    LIVE_VERIFIED = "live_verified"
    BLOCKED = "blocked"

@dataclass(frozen=True, slots=True)
class EvidenceDigest:
    path: str
    sha256: str

@dataclass(frozen=True, slots=True)
class LiveVerificationRecord:
    task_id: str
    state: VerificationState
    implementation_commit: str
    verified_at: datetime
    controller_backend: Literal["ScreenCaptureKit", "CoreGraphicsRegion"]
    logical_window_size: tuple[int, int]
    maa_capture_size: tuple[int, int]
    normal_run_status: TaskStatus
    noop_run_status: TaskStatus | None
    evidence: tuple[EvidenceDigest, ...]
    postcondition_evidence: tuple[EvidenceDigest, ...]
    pending_branches: tuple[str, ...]

def load_verification_record(
    path: Path,
    *,
    repository_root: Path,
    require_local_evidence: bool = False,
) -> LiveVerificationRecord: ...
```

- [ ] **Step 1: Add failing schema and evidence tests**

Reject unknown fields, unknown task IDs, a non-40-hex implementation commit, a future timestamp, an unsupported backend, evidence paths outside `diagnostics/`, a `live_verified` record with pending branches, or missing `before.png`, `after.png`, `result.json`, `action-trace.jsonl`, `agent.log`, and `maafw.log` `EvidenceDigest` entries. With `require_local_evidence=True`, also reject nonexistent files and digest mismatches.

- [ ] **Step 2: Run the focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_live_verification_records.py -q`

Expected: FAIL because the record loader does not exist.

- [ ] **Step 3: Implement strict loading and path containment**

Resolve every evidence path against the repository root, reject path escapes, and verify task IDs against the canonical catalog. In local-evidence mode, also reject symlinks and require every file and digest to match. Require `normal_run_status` to be `completed` or `already_complete`; require `noop_run_status == already_complete` when the task can be safely rerun without additional resource consumption. Reject `live_pending`, `live_verified`, or any other verification state if it appears in either runtime-status field.

- [ ] **Step 4: Separate committed record metadata from ignored evidence bytes**

Keep one tracked JSON file in `verification/tasks/` for each canonical task ID. Continue ignoring `/diagnostics/`; verification records refer to local evidence and include SHA-256 digests for each evidence file so copied archives can be audited without committing account screenshots. Static checks validate record structure on clean clones; final live admission additionally requires local evidence.

- [ ] **Step 5: Run focused tests and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_live_verification_records.py -q
install/.venv/bin/python -m ruff check agent/workflows/verification.py tests/test_live_verification_records.py
```

Expected: all checks pass.

- [ ] **Step 6: Commit the verification-record contract**

```bash
git add -- agent/workflows/verification.py verification/tasks/.gitkeep \
  tests/test_live_verification_records.py .gitignore
git commit -m "feat: define live workflow verification records"
```

### Task 2: Admit all 17 single-task verification records

**Files:**

- Create or update: `verification/tasks/MAIL_REWARD_DAILY.json`
- Create or update: `verification/tasks/SHOP_FREE_GIFT_DAILY.json`
- Create or update: `verification/tasks/WEEKLY_FREE_GIFT_MONDAY.json`
- Create or update: `verification/tasks/TRIAL_SWORD_DAILY.json`
- Create or update: `verification/tasks/FREE_APPRAISAL_DAILY.json`
- Create or update: `verification/tasks/BUY_TEA_DAILY.json`
- Create or update: `verification/tasks/COLLECTION_DEPLOYMENT_DAILY.json`
- Create or update: `verification/tasks/HERO_DISPATCH_DAILY.json`
- Create or update: `verification/tasks/SHADOW_RUINS_DAILY.json`
- Create or update: `verification/tasks/SPEND_CONDENSATE_DAILY.json`
- Create or update: `verification/tasks/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json`
- Create or update: `verification/tasks/EAT_STAMINA_FOOD_DAILY.json`
- Create or update: `verification/tasks/DUNGEON_SWEEP_DAILY.json`
- Create or update: `verification/tasks/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json`
- Create or update: `verification/tasks/RING_CHALLENGE_DAILY.json`
- Create or update: `verification/tasks/DAILY_TASK_REWARD_CLAIM_DAILY.json`
- Create or update: `verification/tasks/BATTLE_PASS_REWARD_DAILY.json`
- Create: `tools/verify_live_tasks.py`
- Create: `tests/test_verify_live_tasks.py`

**Interfaces:**

```python
def verify_live_tasks(
    repository_root: Path,
    *,
    required_task_ids: Sequence[str],
    require_local_evidence: bool = False,
) -> list[str]: ...
```

- [ ] **Step 1: Add a failing complete-set test**

Require exactly one record per canonical task, catalog order, `live_verified` state, a recorded implementation commit that is an ancestor of the current commit, and zero pending branches. In local-evidence mode, also require evidence digests to match local files.

- [ ] **Step 2: Run the gate and observe outstanding tasks**

Run: `install/.venv/bin/python -m pytest tests/test_verify_live_tasks.py -q`

Expected: FAIL with a precise list of missing, pending, blocked, stale, or digest-mismatched task records.

- [ ] **Step 3: Implement a read-only gate CLI**

`python -m tools.verify_live_tasks --root "$PWD" --all` prints one line per task and returns nonzero when any task is not live verified. `--require-local-evidence` additionally checks every local file/digest for final admission. The command never modifies records or evidence.

- [ ] **Step 4: Re-run only the missing live branches**

For each reported task, use its batch plan's live command from the freshly assembled current checkout. Preserve before/after full-screen and MAA images, result, Maa/Agent logs, action trace, postcondition evidence, and safe no-op rerun where permitted. Stop immediately on a paid or unknown prompt.

- [ ] **Step 5: Keep conditional tasks pending until real**

If Monday-only or event/rank/state branches cannot occur, leave the record `live_pending` and leave this task failing. Do not edit test expectations or use fixture results to satisfy the gate.

- [ ] **Step 6: Write records from observed evidence**

Populate every field and digest from real files and the exact tested commit. Run:

```bash
install/.venv/bin/python -m tools.verify_live_tasks --root "$PWD" --all \
  --require-local-evidence
install/.venv/bin/python -m pytest tests/test_live_verification_records.py \
  tests/test_verify_live_tasks.py -q
```

Expected: all 17 records pass only after all required real branches have been observed.

- [ ] **Step 7: Commit the records and gate**

```bash
git add -- verification/tasks/MAIL_REWARD_DAILY.json \
  verification/tasks/SHOP_FREE_GIFT_DAILY.json \
  verification/tasks/WEEKLY_FREE_GIFT_MONDAY.json \
  verification/tasks/TRIAL_SWORD_DAILY.json \
  verification/tasks/FREE_APPRAISAL_DAILY.json \
  verification/tasks/BUY_TEA_DAILY.json \
  verification/tasks/COLLECTION_DEPLOYMENT_DAILY.json \
  verification/tasks/HERO_DISPATCH_DAILY.json \
  verification/tasks/SHADOW_RUINS_DAILY.json \
  verification/tasks/SPEND_CONDENSATE_DAILY.json \
  verification/tasks/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json \
  verification/tasks/EAT_STAMINA_FOOD_DAILY.json \
  verification/tasks/DUNGEON_SWEEP_DAILY.json \
  verification/tasks/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json \
  verification/tasks/RING_CHALLENGE_DAILY.json \
  verification/tasks/DAILY_TASK_REWARD_CLAIM_DAILY.json \
  verification/tasks/BATTLE_PASS_REWARD_DAILY.json \
  tools/verify_live_tasks.py tests/test_verify_live_tasks.py
git commit -m "test: admit live-verified daily workflows"
```

### Task 3: Implement date-aware aggregate scheduling and task-continuing results

**Files:**

- Create: `agent/workflows/aggregate.py`
- Create: `tests/test_aggregate_workflow.py`

**Interfaces:**

```python
AGGREGATE_ORDER: tuple[str, ...] = (
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

@dataclass(frozen=True, slots=True)
class NavigationSession:
    page_marker: str
    frame_id: str

@dataclass(frozen=True, slots=True)
class ScheduledTask:
    task_id: str
    eligible: bool
    ineligible_postcondition: str | None = None

class AggregateDriver(Protocol):
    def run_task(
        self,
        task_id: str,
        navigation: NavigationSession | None,
    ) -> tuple[TaskResult, NavigationSession | None]: ...

@dataclass(frozen=True, slots=True)
class AggregateResult:
    status: TaskStatus
    child_results: tuple[TaskResult, ...]
    stopped_before: tuple[str, ...]

def schedule_for(day: date) -> tuple[ScheduledTask, ...]: ...
def run_aggregate(driver: AggregateDriver, *, day: date) -> AggregateResult: ...
```

- [ ] **Step 1: Add failing schedule and stop-semantics tests**

Cover Monday execution of the weekly task; Tuesday planned `not_eligible` without opening the shop; exact order; battle pass last; continuation after completed/already-complete/not-eligible/blocked-safety/ordinary-failed; and immediate stop with untouched later drivers only after a device/runtime exception.

- [ ] **Step 2: Run focused tests**

Run: `install/.venv/bin/python -m pytest tests/test_aggregate_workflow.py -q`

Expected: FAIL because the aggregate runner does not exist.

- [ ] **Step 3: Implement explicit child execution**

Give every child its own diagnostics/result while also writing an aggregate index. Never share counters or unrecorded state. A recognized function-panel or painting-scroll page may be passed as an explicit `NavigationSession`; each child revalidates that page before using it.

```python
def run_aggregate(driver: AggregateDriver, *, day: date) -> AggregateResult:
    scheduled = schedule_for(day)
    results: list[TaskResult] = []
    navigation: NavigationSession | None = None

    for index, item in enumerate(scheduled):
        if not item.eligible:
            result = TaskResult(
                task_id=item.task_id,
                status=TaskStatus.NOT_ELIGIBLE,
                postcondition=item.ineligible_postcondition or "planned_not_eligible",
                action_counts={},
            )
        else:
            result, navigation = driver.run_task(item.task_id, navigation)
        results.append(result)

        if result.status in {TaskStatus.BLOCKED_SAFETY, TaskStatus.FAILED}:
            return AggregateResult(
                status=result.status,
                child_results=tuple(results),
                stopped_before=tuple(task.task_id for task in scheduled[index + 1:]),
            )

    return AggregateResult(
        status=TaskStatus.COMPLETED,
        child_results=tuple(results),
        stopped_before=(),
    )
```

`schedule_for(day)` always returns all 17 IDs in `AGGREGATE_ORDER`. It sets only `WEEKLY_FREE_GIFT_MONDAY.eligible` to `False` when `day.weekday() != 0`, with `ineligible_postcondition="weekday_not_monday"`; every other item is eligible.

- [ ] **Step 4: Implement task-continuing reporting**

After a task-level block or ordinary failure, preserve its result and continue with the next selected task. Stop before the next task only for a device/runtime exception, and restore the window once through the outer lifecycle.

- [ ] **Step 5: Run tests and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_aggregate_workflow.py -q
install/.venv/bin/python -m ruff check agent/workflows/aggregate.py tests/test_aggregate_workflow.py
```

Expected: all checks pass.

- [ ] **Step 6: Commit aggregate logic**

```bash
git add -- agent/workflows/aggregate.py tests/test_aggregate_workflow.py
git commit -m "feat: add task-continuing Jianzhichuan daily aggregate"
```

### Task 4: Register the aggregate pipeline and MFAAvalonia task

**Files:**

- Create: `agent/actions/jianzhichuan_daily.py`
- Update: `agent/actions/__init__.py`
- Update: `agent/main.py`
- Create: `assets/resource/pipeline/daily/jianzhichuan_daily.json`
- Update: `assets/interface.json`
- Update: `tools/project_interface.py`
- Update: `tools/verify_install.py`
- Update: `tools/run_cli.py`
- Update: `tests/test_project_interface_generation.py`
- Update: `tests/test_project_interface.py`
- Update: `tests/test_verify_install.py`
- Update: `tests/test_run_cli.py`
- Create: `tests/test_jianzhichuan_daily_action.py`

**Interfaces:**

```python
class MaaAggregateDriver(AggregateDriver):
    def __init__(self, context: Context, argv: Any) -> None: ...
    def run_task(
        self,
        task_id: str,
        navigation: NavigationSession | None,
    ) -> tuple[TaskResult, NavigationSession | None]: ...
    def close(self, result: AggregateResult | None) -> None: ...

class JianzhichuanDailyAggregate(CustomAction):
    def __init__(
        self,
        driver_factory: Callable[[Context, Any], MaaAggregateDriver] = MaaAggregateDriver,
        day_factory: Callable[[], date] = date.today,
    ) -> None: ...
    def run(self, context: Context, argv: Any) -> Any: ...
```

Register `JianzhichuanDailyAggregate` exactly once with `AgentServer.custom_action("JianzhichuanDailyAggregate")`. Its `run` method builds `MaaAggregateDriver(context, argv)`, calls `run_aggregate(..., day=date.today())`, closes aggregate diagnostics in `finally`, and returns `CustomAction.RunResult(success=result.status is TaskStatus.COMPLETED)`.

```json
{
  "MJA_JianzhichuanDaily": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "JianzhichuanDailyAggregate"
  }
}
```

The ProjectInterface task name is `jianzhichuan_daily`, label is `剑之川日常`, and `default_check` remains `false`.

- [ ] **Step 1: Add failing admission, custom-action, and interface tests**

Assert the renderer refuses to add the preset when any record is missing/pending, adds it exactly once after all records pass, points to the aggregate entry, uses `controller: ["macos"]` and `resource: ["mja"]`, and does not replace the 17 single tasks. In `tests/test_jianzhichuan_daily_action.py`, inject a fake aggregate driver and date; require one `run_aggregate` call, success only for canonical `completed`, and diagnostics finalization for completed, blocked, failed, and exception paths.

- [ ] **Step 2: Run focused tests**

Run:

```bash
install/.venv/bin/python -m pytest tests/test_project_interface_generation.py \
  tests/test_project_interface.py tests/test_verify_install.py tests/test_run_cli.py \
  tests/test_jianzhichuan_daily_action.py -q
```

Expected: FAIL because the aggregate is absent.

- [ ] **Step 3: Register the aggregate custom action and pipeline**

The custom action resolves today's date once, invokes `run_aggregate`, records the aggregate index, and returns success only when the aggregate status is `completed`.

```python
class JianzhichuanDailyAggregate(CustomAction):
    def __init__(
        self,
        driver_factory: Callable[[Context, Any], MaaAggregateDriver] = MaaAggregateDriver,
        day_factory: Callable[[], date] = date.today,
    ) -> None:
        self._driver_factory = driver_factory
        self._day_factory = day_factory

    def run(self, context: Context, argv: Any) -> Any:
        driver = self._driver_factory(context, argv)
        result: AggregateResult | None = None
        try:
            result = run_aggregate(driver, day=self._day_factory())
            return CustomAction.RunResult(success=result.status is TaskStatus.COMPLETED)
        finally:
            driver.close(result)
```

`MaaAggregateDriver.close` is idempotent. It writes the aggregate index when `result` exists, records the exception path when it is `None`, closes Maa and Agent logs, and never restores the window itself; the outer CLI lifecycle owns the single restoration.

- [ ] **Step 4: Add CLI task/preset selection**

Extend `tools.run_cli` with mutually exclusive `--task TASK_NAME` and `--preset jianzhichuan_daily`. `TASK_NAME` is the lowercase ProjectInterface name, while canonical uppercase IDs remain internal catalog keys. Keep the existing mail smoke default only when neither option is passed. Validate names against the singular ProjectInterface `task` array before spawning MaaPiCli.

- [ ] **Step 5: Extend install verification**

Require all 17 individual task entries, the aggregate entry, all statically valid verification records, and exact aggregate order. Reject any forbidden standard input action or a preset whose record admission gate no longer passes. Do not require ignored local diagnostics during ordinary install verification.

- [ ] **Step 6: Run setup and static validation**

```bash
install/.venv/bin/python -m pytest tests/test_project_interface_generation.py \
  tests/test_project_interface.py tests/test_verify_install.py tests/test_run_cli.py \
  tests/test_jianzhichuan_daily_action.py -q
install/.venv/bin/python -m tools.setup --root "$PWD"
install/.venv/bin/python -m tools.verify_install "$PWD/install"
```

Expected: all checks pass and the freshly assembled interface contains 17 single tasks plus the aggregate and mail smoke test.

- [ ] **Step 7: Commit aggregate registration**

```bash
git add -- agent/actions/jianzhichuan_daily.py agent/actions/__init__.py agent/main.py \
  assets/resource/pipeline/daily/jianzhichuan_daily.json \
  assets/interface.json tools/project_interface.py tools/verify_install.py tools/run_cli.py \
  tests/test_project_interface_generation.py tests/test_project_interface.py \
  tests/test_verify_install.py tests/test_run_cli.py tests/test_jianzhichuan_daily_action.py
git commit -m "feat: register Jianzhichuan daily preset"
```

### Task 5: Verify aggregate behavior against fakes and fixture replays

**Files:**

- Create: `tests/test_aggregate_fixture_replay.py`
- Create: `tests/fixtures/aggregate/manifest.json`
- Create: `docs/verification/aggregate-fixture-replay.md`

**Interfaces:**

```python
def replay_aggregate(
    fixture_root: Path,
    *,
    injected_terminal_result: tuple[str, TaskStatus] | None = None,
) -> AggregateResult: ...
```

- [ ] **Step 1: Add failing replay tests**

Replay all completed fixtures; all already-complete fixtures; Tuesday weekly ineligibility; a paid signal in each phase group; and one technical failure in each phase group. Require zero input after the injected blocking frame.

- [ ] **Step 2: Run the replay tests**

Run: `install/.venv/bin/python -m pytest tests/test_aggregate_fixture_replay.py -q`

Expected: FAIL because aggregate replay fixtures are absent.

- [ ] **Step 3: Implement aggregate fixture composition**

Reference existing per-task fixture PNGs by digest rather than duplicating them. The replay driver exposes screenshots and records proposed inputs without controlling the real game.

- [ ] **Step 4: Verify skip, reuse, and fail-fast traces**

Assert page reuse occurs only with an explicit recognized parent page, child counters never leak, already-complete tasks produce no side-effect input, and the first blocked/failed task is the final action-trace record.

- [ ] **Step 5: Run replay, full tests, and Ruff**

```bash
install/.venv/bin/python -m pytest tests/test_aggregate_fixture_replay.py -q
install/.venv/bin/python -m pytest -q
install/.venv/bin/python -m ruff check agent tools tests
```

Expected: all checks pass.

- [ ] **Step 6: Commit replay acceptance**

```bash
git add -- tests/test_aggregate_fixture_replay.py tests/fixtures/aggregate/manifest.json \
  docs/verification/aggregate-fixture-replay.md
git commit -m "test: verify aggregate daily fixture replay"
```

### Task 6: Run the complete daily preset live from the current checkout

**Files:**

- Create: `docs/verification/jianzhichuan-daily-live.md`
- Create: `verification/aggregate.json`

**Interfaces:** none.

- [ ] **Step 1: Prove the run uses the current checkout**

Record `git rev-parse HEAD`, `git status --short`, patched dylib digest, ProjectInterface digest, controller backend, game bundle ID, window ID, and logical screenshot size. Re-run setup and install verification immediately before execution.

- [ ] **Step 2: Capture before evidence**

With Computer Use, capture the full desktop showing the unobscured foreground game. Capture the same frame through Maa and save both under the aggregate diagnostic run.

- [ ] **Step 3: Run only the aggregate preset**

From an authorized Terminal:

```bash
install/.venv/bin/python -m tools.run_cli \
  --install-root "$PWD/install" \
  --preset jianzhichuan_daily
```

Do not operate the computer during execution except to stop on an unexpected real-money/system payment prompt that the automation has not already blocked.

- [ ] **Step 4: Audit every child result as it finishes**

Require approved order, planned weekly behavior for the current date, no cap excess, a verified independent postcondition, and evidence paths for every attempted task. Stop the acceptance run if a child record is missing even when MaaPiCli exits zero.

- [ ] **Step 5: Capture after evidence and restoration**

Capture full-screen and MAA images after the final battle-pass close. Confirm the game returns to a known page, the window ID/bounds remain prepared, the prior foreground application is restored after CLI exit, and aggregate/child logs are closed and readable.

- [ ] **Step 6: Perform safe aggregate no-op replay**

Run the preset again only if every task policy says a rerun cannot spend another resource. Otherwise run the non-consumptive subset and retain each consumptive task's single-task no-op evidence. Verify all eligible children return `already_complete` or planned `not_eligible` without side-effect input.

- [ ] **Step 7: Write the aggregate verification record**

Record commit, date, exact command, child results, stopped-before list, action counts, evidence digests, postconditions, restoration result, and whether no-op verification was full or policy-limited.

- [ ] **Step 8: Commit live acceptance metadata**

```bash
git add -- docs/verification/jianzhichuan-daily-live.md verification/aggregate.json
git commit -m "test: verify complete Jianzhichuan daily preset"
```

### Task 7: Verify the preset in MFAAvalonia

**Files:**

- Update: `docs/verification/jianzhichuan-daily-live.md`

**Interfaces:** none.

- [ ] **Step 1: Launch the freshly assembled MFAAvalonia**

Open only `install/MFAAvalonia.app` or the assembled `install/MFAAvalonia` host, select the current MJA `interface.json`, and confirm it uses the installed patched MaaFramework files.

- [ ] **Step 2: Visually verify task presentation**

With Computer Use, confirm all 17 individual labels and `剑之川日常` appear, no duplicate/stale mail-only project is selected, the macOS controller is available, and the aggregate is not default-selected.

- [ ] **Step 3: Run a safe UI-selected verification path**

Select an already-complete non-consumptive individual task first, verify it returns `already_complete`, then select the aggregate only when the policy-limited no-op condition from Task 6 holds. Do not re-consume resources merely to test GUI selection.

- [ ] **Step 4: Verify MFA evidence and restoration**

Save screenshots of project selection, task list, running status, child result summary, and final restored window. Record the MFA build version and evidence paths in the live verification document.

- [ ] **Step 5: Commit MFA verification notes**

```bash
git add -- docs/verification/jianzhichuan-daily-live.md
git commit -m "test: verify daily preset in MFAAvalonia"
```

### Task 8: Final repository, safety, and publication gate

**Files:**

- Update: `README.md`
- Update: `docs/verification/jianzhichuan-daily-live.md`

**Interfaces:** none.

- [ ] **Step 1: Document installation and foreground operation**

Document setup, native permission request command, authorized Terminal/MFA host requirement, single-task and aggregate launch commands, no-background limitation, resource-consumption warning, paid hard stops, evidence locations, and recovery behavior.

- [ ] **Step 2: Run the complete automated gate**

```bash
git diff --check
install/.venv/bin/python -m pytest -q
install/.venv/bin/python -m ruff check agent tools tests
install/.venv/bin/python -m tools.verify_live_tasks --root "$PWD" --all \
  --require-local-evidence
install/.venv/bin/python -m tools.verify_install "$PWD/install"
```

Expected: every command passes.

- [ ] **Step 3: Scan for forbidden implementation remnants**

Run searches for unbounded loops, standard Maa input actions, keyboard operations, paid-confirmation terms in action nodes, stale mail-only descriptions, fixture-only `live_verified` claims, and paths referencing a different checkout. Review every match rather than suppressing it.

- [ ] **Step 4: Confirm only intended working-tree state remains**

Run: `git status --short`

Expected: only the user's pre-existing `AGENTS.md` modification plus the intended `README.md` and `docs/verification/jianzhichuan-daily-live.md` edits are tracked; ignored diagnostics may exist but must not be staged.

- [ ] **Step 5: Commit final documentation**

```bash
git add -- README.md docs/verification/jianzhichuan-daily-live.md
git commit -m "docs: document verified Jianzhichuan daily automation"
```

Run `git status --short` again. Expected: only the user's pre-existing `AGENTS.md` modification remains among tracked files.

- [ ] **Step 6: Push the implementation branch to the existing private repository**

Run:

```bash
git push origin agent/macos-mail-smoke-test
git status --short --branch
```

Expected: the branch is synchronized with the private `TaurusGGBOY/MJA` remote, the existing pull request remains draft unless the user separately asks to change it, and `AGENTS.md` remains uncommitted.
