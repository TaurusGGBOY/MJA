# macOS controller mail regression

## Status

Task 8 has an automated, conservative calibration contract. Live regression is
pending because no authorized live screenshot capture was available during this
change. No screenshot assets were generated, recropped, or replaced.

The observed window contract is:

- logical window: `1051x820`
- Maa output after short-side scaling: `923x720`
- display short side: `720`

The existing seven templates and their ROIs remain in the separate
`true_1280_legacy_assets` contract (`1280x720`). They must not be used with a
`923x720` frame. A future authorized capture must recapture home, function
panel, and mail frames before switching that contract.

## Automated evidence

Run from the repository root:

```bash
install/.venv/bin/python -m pytest tests/test_capture_templates.py -q
install/.venv/bin/python -m ruff check tools/capture_templates.py tests/test_capture_templates.py
```

The tests cover both `1051x820 -> 923x720` and true `1280x720` captures,
calibrated crop bounds, stale-size rejection, aspect-ratio drift, and the
read-only capture path. The fake controller exposes an input counter and the
capture helper never invokes it.

## Live verification procedure

When an authorized Terminal is available, capture only the home, function-panel,
and mail pages with `tools.capture_templates`. Do not select a message, click
`全部领取`, or interact with reward, payment, or claim controls. Record the
window ID, logical bounds, Maa frame size, and the patched-runtime fallback log.

Only after all seven crops are visually reviewed may the template contract be
changed to `observed_ios_window` and the pipeline ROIs be recropped to the
actual `923x720` frames. A fixture or synthetic image is not live evidence.
