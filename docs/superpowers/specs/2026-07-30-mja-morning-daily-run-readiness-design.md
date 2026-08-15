# MJA Morning Daily Run Readiness Design

**Date:** 2026-07-30

## Goal

Provide one reliable way to launch all eligible Jianzhichuan daily workflows from MFAAvalonia or the command line, retain truthful per-task results, continue after ordinary task failures, and stop only when the Android runtime can no longer execute tasks.

This work hardens orchestration and reporting. It does not claim that an individual workflow is live-verified unless its verification record contains real device evidence.

## Current State

- `workflow_sequence_for_date()` is the canonical date-aware task ordering and already filters weekday-gated workflows.
- `AggregateScheduler` already expresses the desired broad policy: ordinary child failures are recorded and later tasks continue; Android, ADB, Controller, and window/runtime failures stop the run.
- Individual MFA tasks enter their daily pipeline and normally invoke `DailyWorkflowAction`.
- `assets/interface.json` advertises `MJA_Daily_All`, but the Android resource has no matching pipeline entry, so the GUI aggregate task is not executable.
- `tools/android_daily_run.py` independently loops over tasks through `AndroidRun`; it returns success when only some tasks fail and does not persist a useful aggregate report or interruption state.
- The installed resource can lag behind source assets unless synchronization is performed before launch.

## Chosen Architecture

### One orchestration model

The project will have one date-aware aggregate domain model, centered on `AggregateScheduler` and `AggregateResult`. Both frontends use the same task ordering and the same status rules:

1. Resolve the eligible task sequence once at aggregate start.
2. Run each task in canonical business order.
3. Preserve the real `TaskResult` returned by every attempted workflow.
4. Continue for task-level outcomes, including `failed`, `blocked_safety`, and `not_eligible`.
5. Stop for device/runtime failures that make later input impossible, including Android emulator, ADB transport, Maa Controller, and login/runtime connectivity failures.
6. Persist a checkpoint and aggregate report after each attempted task, so interruption never erases prior results.

`not_eligible` remains a truthful no-op result. It is not rewritten as `completed`, even though it does not stop the aggregate run.

### MFAAvalonia entry

Add a real `MJA_Daily_All` Android pipeline entry backed by a dedicated aggregate custom action. The custom action will:

- create one Maa Android workflow driver for the connected Controller;
- invoke the shared aggregate scheduler rather than enqueueing unrelated GUI tasks;
- expose aggregate success only when no task has a failure-class result;
- write the same aggregate report used by the CLI;
- leave the emulator open and preserve the failure screen when the run stops.

The existing individual task entries remain available for targeted retry and debugging.

### CLI entry

`python -m tools.android_daily_run` becomes the canonical command-line aggregate entry. Its launcher will perform these phases in order:

1. Synchronize source agent/resources/config into `install/` using the project's existing setup path.
2. Run non-mutating install/runtime preflight checks.
3. Execute the date-aware aggregate task set.
4. Print a concise Chinese summary and point to the machine-readable report.

The CLI adapter may retain process/session setup specific to `AndroidRun`, but it must consume the same task sequence, result classification, report schema, and exit-code policy as the GUI aggregate action. It must not maintain a second definition of business ordering.

## Result and Checkpoint Contract

Each aggregate run writes a JSON document beneath the configured debug/run directory. The document contains:

- run ID, start time, finish time, and selected date;
- aggregate status;
- ordered selected task IDs;
- one serialized `TaskResult` for each attempted task;
- `completed_task_ids` and `remaining_task_ids`;
- `last_task_id`;
- stop reason and error code when execution stops early;
- evidence and diagnostic paths already emitted by child workflows.

The report is rewritten atomically after every attempted task. A normal Ctrl-C records status `interrupted`, retains completed results, and lists the first unattempted task. The report is resumable information for a human or later command; this change does not silently resume a stale run by default.

The Chinese terminal summary lists each task and its true outcome, followed by counts for completed/already-complete, skipped/not-eligible, task failures, and remaining tasks.

## Status and Exit Codes

Aggregate statuses are:

- `completed`: every attempted task completed, was already complete, or was not eligible.
- `completed_with_task_failures`: all eligible tasks were attempted, with at least one ordinary task failure-class result.
- `failed_runtime`: execution stopped because the emulator, ADB transport, Controller, login/runtime connection, or equivalent device-level prerequisite failed.
- `interrupted`: execution received user/process interruption before all selected tasks were attempted.

CLI exit codes are:

- `0` for `completed`.
- `1` for `completed_with_task_failures`.
- `2` for invalid arguments or an empty/unknown selection.
- `3` for `failed_runtime`.
- `130` for interruption.

MFA reports aggregate success only for `completed`. Task-level details remain in the JSON report and diagnostics rather than being hidden by the single Boolean custom-action result.

## Failure Classification

Failure classification is centralized and uses stable exception/error codes where available. Runtime-stop failures include:

- emulator unavailable, boot failure, or emulator process loss;
- ADB unavailable, disconnected, unauthorized, offline, or transport failure;
- Maa Controller connection/capture/input failure that prevents further work;
- game/login state that requires user authentication before automation can continue.

Recognition misses, workflow timeouts, exhausted retries, safety blocks, ineligible tasks, and ordinary workflow exceptions are task-level results and do not stop later tasks.

No aggregate cleanup closes the emulator. No failure path sends host-side UI input or direct `adb shell input`; game input remains routed through MaaFramework's ADB Controller.

## Source and Installed Resource Consistency

The implementation will add the aggregate pipeline to source assets and extend project contract checks so generated `assets/interface.json`, Android pipeline resources, registered custom actions, and `install/` synchronization agree. The morning launcher performs synchronization once before preflight, not before each child task.

## Testing

Offline tests will cover:

- `MJA_Daily_All` exists in the interface and resolves to a real Android pipeline entry;
- the aggregate custom action is registered and invokes the scheduler;
- canonical order and Monday-only filtering;
- explicit selection validation;
- ordinary task failure, safety block, and not-eligible continuation;
- device/runtime failure stopping before later tasks;
- preservation of exact child `TaskResult` values;
- checkpoint updates after every task and correct remaining-task calculation;
- Ctrl-C interruption reporting;
- Chinese summary rendering and JSON schema;
- CLI exit codes, especially partial failure returning nonzero;
- source/install synchronization and install verification;
- no regression in individual MFA task execution.

Verification consists of the focused tests above, the full test suite, Ruff, `git diff --check`, and `tools.verify_install install`. Game execution is deliberately excluded tonight; live verification remains a separate evidence-producing step.

## Files Expected to Change

- `agent/workflows/aggregate.py`: aggregate statuses, failure classification, checkpoint/report hooks.
- `agent/actions/daily_workflow.py` or a focused adjacent action module: registered aggregate custom action.
- `assets/resource_android/pipeline/`: real `MJA_Daily_All` entry.
- `tools/android_daily_run.py`: canonical CLI behavior, summary, and exit codes.
- `tools/android_run.sh` or a dedicated all-dailies launcher: single morning command with sync/preflight.
- `tools/project_interface.py` and generated `assets/interface.json`: enforce the aggregate contract.
- focused tests under `tests/`.

## Non-Goals

- Running or interacting with the game during this implementation pass.
- Marking any `verification/tasks/*.json` record as live-verified without real evidence.
- Automatically retrying or resuming stale task checkpoints without an explicit future design.
- Closing or restarting the emulator after workflow failure.
- Replacing MaaFramework ADB Controller input with host automation or direct shell input.
