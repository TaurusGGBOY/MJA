# Daily Pipeline Home Return Implementation Plan

> **For agentic workers:** This plan is executed directly in the current workflow with independent sub-agent worktrees; no superpowers skill is required.

**Goal:** Make every daily pipeline return to the game home page after a normal, already-complete, or not-eligible outcome, while preserving failure semantics and the existing shared stop behavior.

**Architecture:** Each daily pipeline owns a small cleanup/return sequence that reverses the pages opened by that task, verifies the shared home-page predicate, and then enters `common/home_boundary.json` followed by `common/terminal.json`. Business outcome recording may defer the shared boundary until the task-specific cleanup has finished. Failure and abort paths remain native failures and continue to the shared abort path.

**Tech Stack:** MAA/MFW JSON pipelines, GuardedInput evidence, RecordTaskOutcome, Python JSON/resource validators, offline pytest.

## Global Constraints

- Do not modify `assets/resource/base/pipeline/common/terminal.json`, `common/home_boundary.json`, or `startup/game_start.json`.
- Do not run real MFW, an emulator, ADB, the game, or a real pipeline.
- Each task is handled in an independent sub-agent/worktree; at most five agents run at once.
- A sub-agent must read its full pipeline, edit only its assigned daily file plus an optional task-specific test, run JSON parsing and focused offline checks, and commit directly.
- Normal, `already_complete`, and `not_eligible` outcomes must use the task-owned cleanup and then reach `公共-主页边界` and `公共-通用停止`.
- Preserve `task_id`, status values, GuardedInput evidence, defensive guards, abort behavior, and bounded retries/loops.
- Do not add blind coordinates, global return logic, restart logic, or unbounded loops.
- Use the established `defer_home_boundary` convention when the outcome must be recorded before returning home.
- Required commit subject: `fix: return <task-file-name> to home`.

---

### Task 1: `break_array_martial_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/break_array_martial_daily.json`
- Test: existing focused break-array offline tests, or one task-specific contract test if the current tests do not cover the final boundary.

Read every entry, result, already-complete, not-eligible, failed, and loop-exhaustion branch. Reverse the actual route through the activity/detail/result pages using existing close/back nodes, add a bounded task-owned cleanup and home probe where needed, and make success/already-complete/not-eligible reach the shared home boundary then common stop. Keep battle failures, ambiguity, safety stops, and loop exhaustion as aborts. Parse JSON, run the focused offline tests, and commit with the required subject.

### Task 2: `daily_task_reward_claim_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json`
- Test: existing daily-task reward recovery/native pipeline tests, or a focused contract test if needed.

Trace both no-claimable and claimable result paths through the daily panel and any reward popup. Reuse existing panel close/home detection, ensure both `already_complete` and `success` are recorded before cleanup, and end at `公共-主页边界` then `公共-通用停止`; retain scan exhaustion and recovery failures as aborts. Parse JSON, run focused offline tests, and commit.

### Task 3: `dungeon_sweep_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/dungeon_sweep_daily.json`
- Test: relevant dungeon-sweep offline tests, or a focused task contract test.

Map the success, no-ticket, sweep-unavailable, and full-inventory branches back through result/detail/dungeon/function-panel layers. Ensure every normal outcome uses one task-owned cleanup before the home boundary and common stop; keep unexpected影页面, full-inventory safety failures, and missing postconditions as aborts. Parse JSON, run focused checks, and commit.

### Task 4: `eat_stamina_food_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/eat_stamina_food_daily.json`
- Test: a focused food-task home-boundary contract test if no suitable existing test exists.

Inspect full/partial stamina, safe-food unavailable, successful consumption, popup, bag, and recovery branches. Preserve the existing safety decision and evidence, close the opened bag or function layers through recognized nodes, verify home, and only then stop normally; recovery and failed postcondition paths remain aborts. Parse JSON, run offline checks, and commit.

### Task 5: `equipment_decompose_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/equipment_decompose_daily.json`
- Test: `tests/mfw/tasks/test_equipment_decompose.py` and any focused boundary test required by the branch graph.

Follow the route from home to resource/equipment decomposition and back. Convert successful completion from the direct common stop to task cleanup and a recognized home probe, while preserving failure recording and abort semantics. Parse JSON, run the focused test, and commit.

### Task 6: `free_appraisal_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/free_appraisal_daily.json`
- Test: existing free-appraisal home-direct, reward-popup, and shop-recovery tests.

Review the existing deferred outcome behavior and all reward/close branches. Ensure success and already-complete paths close the appraisal result/detail/shop/scroll layers actually opened, verify home, then finish the deferred boundary and common stop. Do not turn the failure node into success or weaken its evidence. Parse JSON, run all focused appraisal tests, and commit.

### Task 7: `guild_activity_challenge_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/guild_activity_challenge_daily.json`
- Test: `tests/mfw/tasks/test_guild_activity_challenge.py` plus a focused boundary test if required.

Trace success and already-complete paths through guild page, activity page, result popup, function panel, and home. Reuse the paired success/already-complete cleanup nodes or refactor only within this file so both outcomes reach home boundary and common stop. Keep failed/unknown battle and dangerous-stop branches aborting. Parse JSON, run focused tests, and commit.

### Task 8: `guild_affairs_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/guild_affairs_daily.json`
- Test: `tests/mfw/tasks/test_guild_affairs.py` and any focused boundary contract test.

Read the row-processing loop and its no-more-work/result paths. Preserve all row guards and payment ambiguity handling, then close the affairs page, guild page, and panel in the actual reverse order before verifying home. Both `success` and the existing completed result must defer/complete the boundary only after cleanup; cleanup failures abort. Parse JSON, run focused tests, and commit.

### Task 9: `guild_donation_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/guild_donation_daily.json`
- Test: `tests/mfw/tasks/test_guild_donation.py` and any focused boundary contract test.

Trace not-eligible, already-complete, and success through donation page, confirmation/result popup, guild page, and panel. Keep `defer_home_boundary` where required, route all three normal statuses through recognized close/back steps to home boundary and common stop, and retain payment/count/unknown-popup safety aborts. Parse JSON, run tests, and commit.

### Task 10: `hero_dispatch_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/hero_dispatch_daily.json`
- Test: existing hero-dispatch entry, traditional-entry, waiting-state, and loop-budget tests.

Cover every successful claim/progress/no-task and already-complete/waiting branch. Use the task's existing dispatch close and page/panel cleanup, add only bounded recognized steps needed to reach the home probe, and change normal termination to home boundary then common stop without changing dispatch loop budgets or failure behavior. Parse JSON, run focused tests, and commit.

### Task 11: `jianlin_resource_condensate_stamina_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`
- Test: `tests/mfw/tasks/test_jianlin_runtime_recovery.py` and relevant offline runtime tests.

Trace both low-stamina success variants through battle, reward/result, resource page, function panel, and home. Preserve the existing cleanup route and task-local stop behavior only where it is equivalent to the shared home boundary; otherwise add a home probe and route success there. Leave budget/safety failures as aborts. Parse JSON, run tests, and commit.

### Task 12: `mail_reward_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/mail_reward_daily.json`
- Test: a focused mail-reward boundary contract test if current tests do not cover both statuses.

Reverse the route from home to the mail panel and reward/result popup. Ensure already-complete and success both close the popup/mail panel, verify the home page, then enter the shared boundary and common stop; do not use startup recovery as a normal completion shortcut and keep missing-state failures aborted. Parse JSON, run offline checks, and commit.

### Task 13: `martial_study_breakthrough_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/martial_study_breakthrough_daily.json`
- Test: existing martial-study entry/material tests and any focused boundary contract test.

Inspect the breakthrough card/result/claim loop, including the no-success completion outcome. Close the martial-study panel and any result layers before home detection, make the normal success outcome reach shared boundary then common stop, and preserve claim-loop exhaustion and record-failure aborts. Parse JSON, run tests, and commit.

### Task 14: `ring_challenge_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/ring_challenge_daily.json`
- Test: `tests/mfw/tasks/test_ring_r20_start_siblings.py` and any focused home-boundary test.

Trace exhausted attempts, successful battle-loop termination, and unknown-result failure through opponent/detail/result cleanup. Ensure the normal already-complete and success statuses both return home before common stop, while unknown results and record failures remain aborts and attempt limits remain bounded. Parse JSON, run tests, and commit.

### Task 15: `shadow_ruins_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/shadow_ruins_daily.json`
- Test: all existing shadow-ruins offline tests, especially final-home-boundary and reward-popup cases.

Read mixed-state priority, battle wait, chest retry, reward popup, and final completion branches. Preserve the existing bounded recovery and evidence, route the final successful outcome through task cleanup and home boundary before common stop, and keep unknown/battle/loop failures aborted. Parse JSON, run focused tests, and commit.

### Task 16: `shop_free_gift_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/shop_free_gift_daily.json`
- Test: `tests/mfw/tasks/test_shop_free_gift_daily.py` and a focused boundary test if needed.

Trace already-complete and success through shop page, reward popup, and runtime recovery branches. Keep the existing deferred outcome semantics, close recognized shop/panel layers, verify home, then finish the boundary and common stop. Recovery exhaustion and missing postconditions remain aborts. Parse JSON, run focused tests, and commit.

### Task 17: `spend_condensate_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/spend_condensate_daily.json`
- Test: `tests/mfw/tasks/test_spend_condensate_shadow_failure.py` and any focused boundary test.

Cover already-complete and success for both spending routes, including sold-out recovery. Reverse the route through shop/detail/scroll/panel layers using existing recognized close nodes, then home boundary and common stop. Preserve currency/budget guards and all failure aborts; do not collapse distinct result states. Parse JSON, run tests, and commit.

### Task 18: `trial_sword_daily.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/trial_sword_daily.json`
- Test: existing trial-sword claimable/postcondition tests.

Review reward success, free-reward close, and existing home-close nodes. Ensure the success outcome is recorded with the correct deferred boundary semantics, the reward is closed before home verification, and only then does the pipeline enter shared home boundary and common stop. Preserve failure recording and evidence. Parse JSON, run tests, and commit.

### Task 19: `weekly_free_gift_monday.json`

**Files:**
- Modify: `assets/resource/base/pipeline/daily/weekly_free_gift_monday.json`
- Test: a focused weekly-gift boundary contract test if current tests do not cover all normal statuses.

Trace success, already-complete, and not-eligible through the weekly gift panel and reward popup. Make all three normal outcomes use recognized task cleanup, home verification, shared home boundary, and common stop; preserve the startup recovery entry only for recovery and keep failure records aborted. Parse JSON, run focused offline checks, and commit.

### Task 20: Review the three already-completed implementations

**Files:**
- Review only: `battle_pass_reward_daily.json`, `buy_tea_daily.json`, and `collection_deployment_daily.json`.
- Modify only if a concrete defect is found, in the affected daily file and optional focused test.

Check that the existing commits `324f119`, `5ac421f`, and `43bc7e8` satisfy the same status-to-cleanup-to-home-boundary contract, do not alter common/startup files, and retain abort semantics. Any corrective change must be made in an independent worktree, tested, and committed with the required task-specific subject.

### Task 21: Integration review and offline validation

**Files:**
- No production edits expected; only task commits may be integrated.

Review each returned commit and its diff before cherry-picking one at a time. Confirm every changed path is an assigned daily pipeline or its task-specific test, confirm no common/startup file changed, and inspect the graph from each normal outcome to the task cleanup, `公共-主页边界`, and `公共-通用停止`. Run `python3 tools/check_mfw_resources.py assets/resource/base` and the related offline pytest suite. Do not run a real pipeline, MFW, emulator, ADB, or game.

If a task's new cleanup `action_id` is rejected by the existing policy decoder or is not allowed after `defer_home_boundary`, add only the corresponding bounded action cap and cleanup-action declaration to `agent/custom/support/policy.py`, update its exact safety assertion, and rerun the policy/deferred-cleanup checks. This is required policy registration for already-defined GuardedInput actions, not a new runtime gate.
