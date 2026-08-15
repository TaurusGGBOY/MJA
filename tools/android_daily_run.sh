#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"
/opt/homebrew/bin/python3 -m tools.setup --root "$ROOT_DIR" --sync-only
if ! "$ROOT_DIR/install/.venv/bin/python" -m tools.verify_install "$ROOT_DIR/install"; then
    echo "WARNING: MJA install verification failed; continuing best-effort Android daily run" >&2
fi
exec "$ROOT_DIR/install/.venv/bin/python" -m tools.android_daily_run "$@"
