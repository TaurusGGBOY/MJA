# 2026-08-12 MFW native control-plane verification

## Root cause

The first-failure probe produced a real native `Tasker.Task.Failed`, but the
MFW-PyQt6 v4.8.23 batch wrapper treated a failed `run_task` as an abort and
continued to the next checked task.  The cause was the wrapper's failure branch
returning `None` instead of `False`; `post_stop()` alone only stops the current
Maa task chain and cannot change the outer Python queue decision.

## Fix

- Keep the native `Tasker.Task.Failed` sink and its one-shot `post_stop()`.
- Patch the packaged MFW-PyQt6 `TaskFlowRunner.run_task` failure return from
  `return` to `return False` during candidate construction.
- Apply and verify the Python 3.12 PyInstaller bytecode patch through
  `tools/mfw_install.py`; preserve the original ad hoc signing identifier.
- Keep the external watchdog, PID polling, log inference, and synthetic task
  result paths removed.

## Evidence

Candidate: `install/mfw-native-control-plane-20260812-r6`

- `tools/mfw_install.py --verify-candidate`: passed.
- Python 3.12 bytecode verifier: passed.
- macOS code signature: ad hoc, original identifier preserved.
- Android preflight: passed with `-gpu host`, `hw.gpu.enabled=yes`, and
  `hw.gpu.mode=host`.
- Real probe candidate:
  `install/mfw-native-control-plane-20260812-r6-probe`
- `debug/maafw.log`: native `Tasker.Task.Failed` followed by the sink's
  `MaaTaskerPostStop`.
- `debug/gui.log`: `PROBE_BUSINESS_FAILURE` failed and the outer flow logged
  `返回 False，终止流程`.
- No `执行任务: MJA_PROBE_SENTINEL` entry occurred after the failure.

The probe process was stopped manually after the GUI task flow had terminated;
no watchdog was used.

## Staged repair evidence (2026-08-12 to 2026-08-13)

The staged rounds followed the required first-failure boundary. Each round used
one candidate and one live MFW runner; after a failure, the next candidate was
rebuilt before rerunning the failed task and the later unrun tasks.

- r13: `HERO_DISPATCH_DAILY` failed with `HERO_POSTCONDITION_MISSING` after
  earlier selected tasks succeeded; the process stopped and the stale game
  surface was not restarted by an external watchdog.
- r14: the hero claim loop hit the old cumulative `max_hit=1` limit. The fresh
  result remained non-success, so the round was not reported as complete.
- r15-r18: startup/page-entry and cumulative-loop defects were fixed one at a
  time. r18 reached the empty dispatch page but still exhausted the claim loop.
- r19: the live screenshot and OCR showed the real no-task state:
  `任务:0/9` + `已完成:0` + `尚未选择派遣任务`. This became an explicit,
  task-local no-dispatch postcondition rather than an inferred click result.
- r20-r23: cleanup and world-home recognition were repaired. r23 proved the
  hero business path, but its profile accidentally had later tasks checked, so
  it was retained as diagnostic evidence and not used as strict acceptance.
- r24: the profile was restricted to `GAME_START` and
  `HERO_DISPATCH_DAILY` only. The strict acceptance ticket passed with fresh
  business and native evidence.
- r25: after the final source/test cleanup, a fresh candidate was rebuilt and
  the same strict acceptance was repeated. Its live task evidence passed, but
  the post-run candidate verifier exposed one deterministic MFW loader rewrite
  that still needed to be canonicalized.
- r26: the verifier now canonicalizes that sink-decorator rewrite. A fresh
  candidate was rebuilt, verified before and after the live run, and the strict
  acceptance was repeated. This is the final live evidence recorded below.

## Strict r26 acceptance

Candidate metadata:

- Candidate: `install/mfw-native-control-plane-20260813-r26`
- Payload SHA-256: `ba56ce6c061056b029aa853607e8b0a47cc2dc259f5f7466bd4a7fd82a33a8d0`
- Immutable tree SHA-256: `34fbc8abb14e7611c4c7be00df390cd634cd9fb78096f254835976b78880ea79`
- Acceptance ticket: `debug/acceptance/HERO_DISPATCH_DAILY/20260812T173749173437Z/ticket.json`
- Acceptance record: `debug/acceptance/HERO_DISPATCH_DAILY/20260812T173749173437Z/acceptance.json`

The acceptance record is `passed`. The fresh task result is:

```json
{
  "task_id": "HERO_DISPATCH_DAILY",
  "status": "success",
  "postcondition": "hero.no_dispatch_tasks",
  "native_terminal": "Tasker.Task.Succeeded"
}
```

The current MAA log shows `MJA_HERO_INITIAL_NO_TASKS` recognizing all four
empty-state signals, `RecordTaskOutcome` persisting the result, the painting
page closing successfully, the shared world-home boundary being recognized,
and `MJA_COMMON_STOP` ending the task. The same run logged only
`GAME_START` followed by `HERO_DISPATCH_DAILY`; no later business task started.

The MFW GUI process was exited after the native task flow had completed. No
external watchdog, PID polling scheduler, or synthetic result writer was used.

The candidate verifier passed both before and after this live run. MFW's
embedded-agent loader deterministically removes the `Tasker.tasker_sink()`
decorator and its import while loading the candidate; the verifier now
canonicalizes that rewrite, so the post-run payload remains verifiable.

## Remaining coverage

r26 proves the repaired native control plane and the hero task under the strict
scope. It is not a claim that all date-eligible daily tasks have passed live
acceptance. The remaining high-risk tasks still require their own strict
`GAME_START + selected task` tickets before the final all-task coverage gate
can be marked complete.
