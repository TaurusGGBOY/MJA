#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$ROOT_DIR/tools/android_daily_run.sh" "$@"
