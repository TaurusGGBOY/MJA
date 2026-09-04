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
Process dispatch rows individually: a visible completion marker leads to selecting that row and claiming it; a visible elapsed-time marker leads to smart configuration and dispatching. If neither marker is recognized, wait for the node timeout and let the task-local `on_error` path end the task as native `Succeeded`, even when the dispatch entry page itself was not recognized.
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
A best-effort return to the game home page after business success is already established. Cleanup failure ends with `StopTask` and does not downgrade the task from native `Succeeded`.
_Avoid_: home-boundary status, cleanup failure as task failure

## Run contract

- Select exactly `GAME_START + one business task` for pairwise acceptance.
- Declare `TASK_ID=Succeeded` or `TASK_ID=Failed` before launching MFW.
- Treat only the fresh native terminal event as the verdict. Keep all other artifacts for diagnosis.
- `WEEKLY_FREE_GIFT_DAILY` is runnable every day. If the game already shows the gift as claimed, the task still ends in native `Succeeded`.
