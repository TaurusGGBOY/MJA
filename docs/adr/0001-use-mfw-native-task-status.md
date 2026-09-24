# Use MFW native task status as the sole task status model

MJA reports task lifecycle only through MFW's native `Invalid`, `Pending`, `Running`, `Succeeded`, and `Failed` states. `Invalid` identifies an unknown task; `Pending` and `Running` describe progress; `Succeeded` and `Failed` are the only terminal states. Work completed during the run and work already complete both end as `Succeeded`; every other final business outcome ends as `Failed`.

Native terminal events are the sole authority for lifecycle state. Acceptance also verifies that a reported success actually executed native nodes and satisfied the task's business and home-page predicates. Evidence validation never rewrites the raw native terminal. MJA does not persist or read a parallel business-result file or additional status enumeration.

Ordinary business-task failure does not stop the remaining MFW queue, matching Maa_bbb. After a failed `GAME_START`, later GUI submissions must not execute business actions. They run native `FailTask` at the entry and preserve `Failed`; the original entry is restored afterward. Calling `post_stop` at Starting is unsuitable because Maa 5.12.3 can report an unexecuted task as `Succeeded`.

## Consequences

Legacy workflow and aggregate runners are retired after any still-used stateless recognition, input, or safety utilities are moved out. `on_error` is absent by default and is reserved for Maa_bbb-style, bounded, task-local recovery; it never routes to a custom outcome node, another business task, or `external`.
Business success requires a task-local completion predicate, not merely a successful click. Refactored cleanup paths verify the home page before entering the native success leaf; an error before completion or an unsuccessful required handoff remains native `Failed`. Cleanup helpers perform UI recovery only and never write an alternative business status.
Explicit business failure uses stateless `FailTask`, which returns false without accepting a status parameter or writing evidence. Manual or external stopping keeps MaaFramework's default semantics and is not reclassified from the last executed node.

Every acceptance run declares its expected native terminal before launch. `WEEKLY_FREE_GIFT_DAILY` remains runnable every day, and an already-claimed gift is a native success.
