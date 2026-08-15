# MFW-PyQt6 runtime patch

MJA uses the offline MFW-PyQt6 `v4.8.23` runtime.  Its PyInstaller payload
contains the batch runner in `app/core/runner/task_flow.py`.  In that release,
the failure branch of `TaskFlowRunner.run_task` records the failure and then
returns `None`.  The outer batch loop interprets that value as an aborted task
and continues with the next checked task.

The patch changes only that return value to `False`.  The existing native
`Tasker.Task.Failed` event and `TaskFlowStopSink` then reach the MFW batch
runner's fatal branch, which stops the checked-task queue at the first failed
business task.

This is applied by `tools/mfw_install.py` while building a candidate.  The
installer invokes Python 3.12 because the packaged bytecode is Python 3.12
bytecode, rewrites the embedded PyInstaller `PYZ.pyz` archive in place, and
re-signs the macOS executable ad hoc.  The patcher is idempotent and verifies
the target bytecode after applying the change.  Fake runtimes used by offline
unit tests are not PyInstaller archives and are intentionally left unchanged.

There is deliberately no external watchdog, PID poller, log inference, or
synthetic task result in this integration.
