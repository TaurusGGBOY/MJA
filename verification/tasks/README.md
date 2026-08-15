# Daily workflow verification records

Each canonical task has one JSON admission record in this directory. Records
must be generated from real emulator evidence; fixture replay is never enough
to mark a task `live_verified`.

The current records are intentionally `live_pending`: the committed Android
daily images and fixtures are scaffolding, not captures from a live logged-in
game. Run the read-only gate with:

```bash
./install/.venv/bin/python -m tools.verify_live_tasks --root "$PWD" --all
```

Only after a real run produces the required redacted diagnostics may a record
be changed to `live_verified`.
