# Contributing to MJA

Please open an issue before substantial pipeline or native-runtime changes.
Pull requests should explain the behavior change, tests run, fixture updates,
and any third-party assets involved.

Before submitting:

```bash
python3 -m pytest -q
ruff check agent tools tests/mfw tests
```

Do not commit credentials, account identifiers, unredacted screenshots,
runtime logs, local absolute paths, or generated installation directories.
Changes to game interaction must remain bounded and must not automate login,
verification codes, payments, or purchases outside the task's documented
scope.
