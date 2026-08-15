# Android daily aggregate verification

## Current status

- Android runtime: verified on `mja-api35-apis`, serial `emulator-5556`, SDK 35,
  1280×720, non-Google-Play `google_apis` image.
- Game startup: verified in the Chinese UI after the existing login state was
  available.
- Safe baseline: `mail_smoke_test` completed successfully on the emulator.
- Daily aggregate: implemented and exposed as an opt-in UI task, but not
  admitted as `live_verified`; all 17 records remain `live_pending`.

## Why the aggregate is pending

The committed daily images and fixtures are contract scaffolding. They are not
evidence that every consumptive, combat, Monday-only, stateful, or conditional
branch was observed in the live game. A real record requires independent
before/after evidence, result and action logs, postcondition evidence, and no
paid or unknown-currency prompt.

Run the read-only admission gate:

```bash
./install/.venv/bin/python -m tools.verify_live_tasks --root "$PWD" --all
```

It must remain failing with a precise pending-task list until those branches
are genuinely exercised. No fixture replay may be used to turn a record into
`live_verified`.
