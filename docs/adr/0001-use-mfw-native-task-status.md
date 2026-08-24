# Use MFW native task status as the sole task status model

MJA reports task lifecycle only through MFW's native `Invalid`, `Pending`, `Running`, `Succeeded`, and `Failed` states. `Invalid` identifies an unknown task; `Pending` and `Running` describe progress; `Succeeded` and `Failed` are the only terminal states. Work completed during the run and work already complete both end as `Succeeded`; every other final business outcome ends as `Failed`.

Native terminal events are the sole acceptance result. Screenshots, node history, logs, and postconditions remain diagnostic only. MJA does not persist or read a parallel result file or additional status enumeration.

Ordinary business-task failure does not stop the remaining MFW queue, matching Maa_bbb. A failed `GAME_START` global prerequisite may stop the queue.

## Consequences

Legacy workflow and aggregate runners are retired after any still-used stateless recognition, input, or safety utilities are moved out. `on_error` is absent by default and is reserved for Maa_bbb-style, bounded, task-local recovery; it never routes to a custom outcome node, another business task, or `external`.
Returning to the game home page after business success is best-effort cleanup; if that cleanup fails, the task uses `StopTask` and remains native `Succeeded`.
Explicit business failure uses stateless `FailTask`, which returns false without accepting a status parameter or writing evidence. Manual or external stopping keeps MaaFramework's default semantics and is not reclassified from the last executed node.

Every acceptance run declares its expected native terminal before launch. `WEEKLY_FREE_GIFT_DAILY` remains runnable every day, and an already-claimed gift is a native success.
