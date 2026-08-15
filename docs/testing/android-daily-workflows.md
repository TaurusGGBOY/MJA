# Android daily workflow acceptance

The project now has a bounded implementation contract for all 17 canonical
daily tasks. Each task has a policy, registry definition, Android pipeline,
1280×720 fixture manifest, and a redacted verification record.

Offline acceptance:

```bash
./install/.venv/bin/python -m pytest -q tests/test_android_daily_acceptance.py
./install/.venv/bin/python -m tools.verify_live_tasks --root "$PWD" --all
```

The second command is expected to return nonzero until real emulator evidence
exists. This checkout deliberately does not treat black/scaffold fixtures as
live captures, and does not run consumptive, combat, stateful, or unknown
currency branches automatically during acceptance.

The safe live baseline is the read-only mail smoke test:

```bash
./tools/android_run.sh --task mail_smoke_test
```

It may open and close the mail panel, but must not claim mail, purchase, pay,
or enter account/security data.
