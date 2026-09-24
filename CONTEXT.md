# MJA Task Execution

This context defines how one MJA business task is reported through MFW. MFW owns the lifecycle; MJA does not expose a parallel outcome taxonomy.

## Native state model

The only raw task states are:

| State | Meaning | Acceptance role |
| --- | --- | --- |
| `Invalid` | Unknown task or invalid handle | Not a business outcome |
| `Pending` | Accepted and waiting in the MFW queue | In progress |
| `Running` | Currently executing | In progress |
| `Succeeded` | Reached a native success leaf or `StopTask` | Successful terminal |
| `Failed` | Native execution or explicit `FailTask` failure | Failed terminal |

`Pending` and `Running` must remain raw values even if a UI groups them as “进行中”. A run is accepted only after its expected terminal state was declared before launch and the fresh native terminal event matches it.

## Language

**Successful task**:
A task whose native MFW terminal status is `Succeeded`; this includes both work completed during the run and work found already complete.
_Avoid_: separate labels for work completed during the run versus work already complete

**Failed task**:
A task whose native MFW terminal status is `Failed`; every final circumstance other than a successful task belongs here.
_Avoid_: eligibility, resource, runtime, or other parallel terminal labels

**Task evidence**:
The native MFW terminal status is the sole accepted task result. UI recognition conditions may be used inside a pipeline as business completion predicates that select the success or failure path, but they are not a second status system and never override the fresh native terminal event. Executed-node history, logs, screenshots, and postconditions remain diagnostic material outside the pipeline.
_Avoid_: result files, terminal-node allowlists, or postcondition checks as parallel acceptance gates

**Business completion predicate**:
A task-local, UI-observable condition that tells the pipeline whether the requested work is complete, already complete, or still needs action—for example, a visible “完成派遣” marker, a recognized elapsed-time field, or a counter reaching zero. It controls the pipeline branch; the resulting MFW native `Succeeded` or `Failed` remains the only task verdict.
_Avoid_: treating the predicate as a new task status or accepting a click merely because it was issued

**Hero dispatch rule**:
Process dispatch rows individually: a visible completion marker leads to selecting that row and claiming it; a visible elapsed-time marker leads to smart configuration and dispatching. Waiting completion requires the dispatch page, a positive running/countdown marker, and no actionable completion or duration marker in the current row. An unknown page or unrecognized state must not become native `Succeeded`.
_Avoid_: treating the first completed row as completion of the whole dispatch task

**Free appraisal rule**:
The home-page entry is the visible “鉴宝” label. Inside the appraisal page, click the recognized “免费鉴宝” target using its OCR/template result box rather than a hard-coded coordinate, then claim the result. If “免费鉴宝” is not recognized but “鉴宝一次” is recognized, treat the task as already complete, exit the page, and end with native `Succeeded`.
_Avoid_: using “免费一次” as the current label or clicking a fixed coordinate without fresh recognition evidence

**Free appraisal remaining-count rule**:
If the free-appraisal control region instead recognizes the complete marker `80`, treat that scoped marker as already complete and use the same native-success cleanup. It must remain guarded by the appraisal page and the original free-control ROI.
_Avoid_: accepting an unrelated page-wide number or OCR failure as completion

**Collection completion rule**:
The collection task is not complete merely because the collection page was opened. It must click the visible “一键部署” control and then click “收获全部/领取全部”; both actions must succeed before the task takes its native success path.
_Avoid_: treating entry into the collection page or closing the page as successful collection

**Shadow start flow**:
On the shadow-ruins page, both “探索中” and “可探索” are actionable cards, not completion states. The task must click the card, click “前往” in the resulting dialog, wait for automatic pathfinding to reach the destination, then inspect the battle-preparation page. If the “跳过战前准备” checkbox is unchecked, click it before starting the battle.
_Avoid_: treating “探索中” or “可探索” as already started/completed, or checking the preparation box before the card-to-“前往” pathfinding flow

**Condensate purchase rule**:
Process the two regions in order. In each region, click the upper-right silver currency entry, enter the purchase page, set the maximum quantity, and confirm the purchase. If a region is sold out or has nothing available, treat that region as processed and continue to the next region. If the final region does not produce a successful purchase, the whole task ends as native `Failed`.
_Avoid_: treating entry into the region or opening the shop as a successful purchase

**Martial study completion rule**:
Keep the existing martial-study entry path. On the study page, inspect only the first slot on the left for a visible “成功”, “成”, or “功” marker. If the marker is absent, treat the martial-study task as already complete and exit with native `Succeeded`; do not click the plus sign or enter an item-selection page. The “道具” entry belongs to the stamina-food task, not martial study.
_Avoid_: using the stamina-food navigation path for martial study or treating absence of the success marker as a failure

**Stamina-food completion rule**:
Read the same item and quantity before each use, then require an exact decrease of one before another use. Six verified decreases or the scoped “吃得太撑” notice permit native success cleanup; six clicks alone do not. Quantity mismatch, missing confirmation, or an unknown page follows native failure cleanup.

**Stamina-food entry rule**:
The food task enters through the bottom “道具” label, then keeps the existing food-category → “龙井虾仁” → “使用” flow. The old home-page ColorMatch resource-entry probe is not the entry contract.
_Avoid_: using the old fixed ColorMatch home ROI as the food entry

**Guild-affairs processing rule**:
The affairs page exposes about four and a half rows, not six. Before each scan, swipe upward from the upper half of the fifth visible row to the top, for at most five swipes, so the fifth row becomes the first row. Process the four visible rows: “领取奖励” is clicked to claim, and “开始/开始事务” is clicked to start the affair.
_Avoid_: hard-coding six visible rows or treating “开始事务” as a passive status

**Guild-activity completion rule**:
Open the guild activity, click the lower-right “挑战”, click the lower-right “开始”, and wait for the battle to finish. Re-read the lower-right “今日剩余征讨数” counter; a recognized `0` means the task is complete and may exit. The old `1/2` or `2/2` availability check is not the completion predicate.
_Avoid_: declaring success merely because the challenge/start buttons were clicked or because the old availability counter matched

**Guild-donation status**:
The current donation flow is provisionally retained; it requires a fresh run to confirm the existing click and reward-close sequence still produces the intended donation.

**Daily-reward completion rule**:
Enter daily rewards through the right-side function panel by recognizing and clicking “日常”. Claim visible “领取” rows and unlocked chests; close each reward popup. If the page has neither a claimable row nor an unlocked chest, exit with native `Succeeded`.
_Avoid_: treating failure to recognize the old home entry as proof that the daily page has no work

**Trial-sword rule**:
Update the home-page “试剑” entry recognition to the current icon/text location. Do not use “敬请期待” as a completion predicate; it is removed from the task’s success logic. The remaining no-reward/no-free-claim behavior must be explicitly defined rather than inferred from that text.
_Avoid_: treating an obsolete “敬请期待” label as proof of completion

**Trial-sword free-claim result**:
After recognizing and clicking “免费” and confirming, a reward popup is accepted through the existing cleanup path. The remaining no-reward/no-free-claim state is not inferred from the obsolete “敬请期待” label.
_Avoid_: requiring the obsolete “敬请期待” marker as proof of completion

**Trial-sword unknown-state rule**:
The post-free-claim UI must be explored at runtime before wiring the final predicate. Do not equate OCR failure to proof that the UI has no “10”. After the actual state is observed, define an explicit bounded failure branch for a page that remains in the trial screen without any recognized success state; until then, do not hard-code an unverified “no 10” condition.

**Break-array support boundary**:
The break-array martial task is not part of the current supported repair scope. Its declared task entry may remain visible to the task catalog, but the missing execution pipeline is not to be reconstructed as part of this fix session.
_Avoid_: treating a missing execution pipeline as an OCR issue or inventing a replacement flow without a separately confirmed design.

**Ring-ticket conversion rule**:
After the ring challenge reaches the post-sweep confirmation dialog, confirming the conversion of the remaining ring tickets into ring currency is an intended part of the task. The task must not leave this confirmation dialog unresolved.
_Avoid_: treating the conversion dialog as an unrelated warning or stopping before the confirmed business action.

**Ring cleanup rule**:
After confirming the ticket conversion, close the conversion result surface and return the game to the home page before the ring task ends successfully. A conversion click alone is not sufficient task cleanup evidence.
_Avoid_: ending the task on the ring page or on an unresolved result dialog.

**Condensate budget decision**:
The resource budget for the condensate-spending task is `9999999` units of 凝晶. This changes only the configured resource quantity cap; action-count limits and page/recognition guards remain in force.
_Avoid_: interpreting the large quantity cap as permission to bypass action bounds or visual page checks.

**Guild-activity completion counter**:
The guild-activity task completes only when the lower-right 今日剩余征讨数 counter is recognized as `0` on the guild-activity page, after the challenge/start battle flow. A zero elsewhere on the screen is not sufficient evidence.
_Avoid_: treating the start click or an unrelated OCR digit as completion.

**Startup recovery timeout**:
The startup attempt may wait 120 seconds at node 1356. If the game-ready/home predicate is still absent, the bounded recovery closes the game once and returns to 1356 for a fresh launch.
_Avoid_: allowing a stale login/loading surface to consume an unbounded startup wait.

**Break-array execution scope**:
Because the break-array pipeline will not be restored in this session, the break-array task is removed from the current executable task catalog. Historical notes may remain for reference, but normal task selection must not offer it as runnable work.
_Avoid_: exposing a task whose declared entry has no supported execution pipeline.

**Task queue**:
The MFW-managed sequence of selected tasks. An ordinary business task that reaches `Failed` does not stop later tasks; only a failed global prerequisite such as `GAME_START` may stop the queue.
_Avoid_: fail-fast batch or aggregate workflow status

**Recovery path**:
A small, task-local route for a known and reproducible UI recovery, following the Maa_bbb pipeline style. An absent or exhausted recovery ends the current task through MFW rather than routing to a custom outcome.
_Avoid_: result routing, cross-task recovery, `external` error targets

**Failure node**:
A node that identifies a definitive non-success outcome and immediately returns native MFW `Failed` through the stateless `FailTask` action. It has no result-writing or cross-file terminal route.
_Avoid_: outcome recorder, shared failure sink, status parameter

**Success node**:
A leaf node that ends naturally as native MFW `Succeeded`, whether work was performed or was already complete. A success node inside a jump-back branch uses `StopTask` locally when it must prevent returning to the parent flow.
_Avoid_: outcome recorder, shared success sink, separate already-complete terminal

**Task cleanup**:
After business completion is established, return to the home page through bounded native recovery. Refactored paths reach the native success leaf only after the home-page predicate; failed cleanup must not masquerade as a successful handoff to the next daily task.
_Avoid_: a parallel home-boundary status or converting an unverified business action into success during cleanup

## Run contract

- Select exactly `GAME_START + one business task` for pairwise acceptance.
- Declare `TASK_ID=Succeeded` or `TASK_ID=Failed` before launching MFW.
- Treat only the fresh native terminal event as the verdict. Keep all other artifacts for diagnosis.
- `WEEKLY_FREE_GIFT_DAILY` is runnable every day. If the game already shows the gift as claimed, the task still ends in native `Succeeded`.

## Startup recovery observations

- ADB `device` does not mean Android's framework is ready. The launcher checks both `sys.boot_completed` and the activity service for new and existing emulators, waits for a configurable elapsed-time window, and fails promptly if the emulator exits.
- Startup preflight retries only ADB transport failures in idempotent checks, at most three times. Each retry must obtain and verify actual device state; persistent failures and emulator contract mismatches still block MFW startup.
- A reproduced Pixel Launcher ANR can cover the game. The native startup pipeline matches the specific launcher title and the close-app button in the same frame, handles it at most once, then still requires the game-home predicate. Closing the Android dialog is not game-start success.

## Native startup-block regression

MaaFramework 5.12.3 can emit `Succeeded` when `post_stop` interrupts a newly submitted task before its first node. A real GUI run reproduced this for all queued daily tasks after failed `GAME_START`. The startup sink therefore temporarily routes subsequent entries through native `FailTask`, restores each original entry at its terminal event, and resets the block on an explicit new `GAME_START`. Ordinary business failures still allow later tasks. A real native no-input sentinel test checks Failed/zero business actions and recovery on a new run. Acceptance preserves raw native terminals but rejects `Succeeded` with no successful node action; this check does not replace task-specific business postconditions.

## 2026-09-11 user corrections

- Hero dispatch must never depend on task names before/after scrolling. List review uses countdowns and actionable status markers; names may be missing or arbitrarily misrecognized without changing the result.
- Dungeon history investigation: the user explicitly specified 风雪神道, 大师80级, two plus clicks and then 开始扫荡 on 2026-08-16. Commit ed71f10 (2026-08-23) replaced 风雪神道 with 燕王秘陵 while repairing false success, following an older workflow. That historical replacement contradicts the newer user instruction; do not treat the old 燕王秘陵 observations as current authorization. The dungeon pipeline is restored to 风雪神道 with exactly two master-row plus actions. Fresh native acceptance passed on 2026-09-11 at 09:53:58: two plus actions, recognized assigned count 2, start/confirm/reward-close, then home. Candidate: install/mfw-dungeon-fengxue-20260911-r2.

## Tea shop category and monthly-card inventory

Tea belongs to the **材料** category. A monthly card expands the inventory, so
tea can be at the bottom of that list. Select 材料, search for the exact 茶叶
label, and scroll inside the item grid with a bounded loop. Require the tea
name again in the detail panel before opening its purchase control; generic
当前拥有 text does not establish item identity. Keep the existing 500文 budget.

## Appraisal and ring preparation cleanup

After dismissing an appraisal reward, check the used/free-control state before
trying another reward-close action: the regular page also displays 鉴宝一次.
Closing the appraisal page may return to the 秘宝 catalog, which must also be
closed before accepting the home boundary.

A ring challenge can enter 战前准备. Recognize that page and 准备就绪 together,
click readiness once per encounter, then resume the existing battle/result
polling without issuing a second opponent challenge.

The free-appraisal button must match `^免费鉴宝$` within its lower control
region. The explanatory line 每日赠送一次免费鉴宝 is not a clickable free
control. The used-state OCR accepts the observed 宝一次 missing-first-character
variant only in that same button region, while retaining appraisal-page evidence.

The ring battle's 跳过 control is at the upper right. The parent battle loop
must wait through the visible two-minute combat timer (bounded at 180 seconds),
rather than timing out after 30 seconds before the result can appear.

Match the ring skip target with exact OCR 跳过. The skip dialog uses 确认,
not 确定. After confirming, wait for the result page before returning to
battle polling; otherwise the transition can queue another delayed skip
click that lands on a different screen.
