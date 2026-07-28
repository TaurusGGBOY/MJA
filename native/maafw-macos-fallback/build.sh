#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_TAG="v5.12.2"
UPSTREAM_COMMIT="f625a60edeccd4549f9a71c0f74628d827ade8fb"
OFFICIAL_BASE_SHA256="f9f341ca13db62ef6f8bd642862510d191efbfc55de896fdec523b5b507ffc9a"
LIBRARY_NAME="libMaaMacOSControlUnit.dylib"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_PATH="$SCRIPT_DIR/patches/0001-macos-coregraphics-region-fallback.patch"

usage() {
    cat <<'EOF'
Usage: native/maafw-macos-fallback/build.sh \
  --source /absolute/clean/MaaFramework-v5.12.2 \
  --official-bin /absolute/official-v5.12.2/bin \
  --output /absolute/MJA/vendor/maafw/v5.12.2/macos-arm64
EOF
}

SOURCE=""
OFFICIAL_BIN=""
OUTPUT=""
while (($#)); do
    case "$1" in
        --source)
            [[ $# -ge 2 ]] || { echo "--source requires a path" >&2; exit 2; }
            SOURCE="$2"
            shift 2
            ;;
        --official-bin)
            [[ $# -ge 2 ]] || { echo "--official-bin requires a path" >&2; exit 2; }
            OFFICIAL_BIN="$2"
            shift 2
            ;;
        --output)
            [[ $# -ge 2 ]] || { echo "--output requires a path" >&2; exit 2; }
            OUTPUT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[[ -n "$SOURCE" && -n "$OFFICIAL_BIN" && -n "$OUTPUT" ]] || {
    echo "--source, --official-bin, and --output are required" >&2
    usage >&2
    exit 2
}

SOURCE="$(cd "$SOURCE" && pwd)"
OFFICIAL_BIN="$(cd "$OFFICIAL_BIN" && pwd)"
mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"

[[ -d "$SOURCE/.git" ]] || { echo "source is not a Git checkout: $SOURCE" >&2; exit 1; }
[[ -f "$PATCH_PATH" ]] || { echo "missing fallback patch: $PATCH_PATH" >&2; exit 1; }
[[ -d "$OFFICIAL_BIN" ]] || { echo "official bin directory is missing: $OFFICIAL_BIN" >&2; exit 1; }

SOURCE_TAG="$(git -C "$SOURCE" describe --tags --exact-match 2>/dev/null || true)"
[[ "$SOURCE_TAG" == "$UPSTREAM_TAG" ]] || {
    echo "source must be exactly tagged $UPSTREAM_TAG (got ${SOURCE_TAG:-none})" >&2
    exit 1
}
SOURCE_HEAD="$(git -C "$SOURCE" rev-parse HEAD)"
[[ "$SOURCE_HEAD" == "$UPSTREAM_COMMIT" ]] || {
    echo "source commit mismatch: expected $UPSTREAM_COMMIT, got $SOURCE_HEAD" >&2
    exit 1
}
[[ -z "$(git -C "$SOURCE" status --porcelain)" ]] || {
    echo "source checkout is dirty: $SOURCE" >&2
    exit 1
}

OFFICIAL_LIBRARY="$OFFICIAL_BIN/$LIBRARY_NAME"
[[ -f "$OFFICIAL_LIBRARY" && ! -L "$OFFICIAL_LIBRARY" ]] || {
    echo "official base library is missing or is a symlink: $OFFICIAL_LIBRARY" >&2
    exit 1
}
BASE_SHA256="$(/usr/bin/shasum -a 256 "$OFFICIAL_LIBRARY" | awk '{print $1}')"
PATCH_SHA256="$(/usr/bin/shasum -a 256 "$PATCH_PATH" | awk '{print $1}')"
[[ "$BASE_SHA256" == "$OFFICIAL_BASE_SHA256" ]] || {
    echo "official base library digest mismatch: expected $OFFICIAL_BASE_SHA256, got $BASE_SHA256" >&2
    exit 1
}

WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mja-maafw-build.XXXXXX")"
STAGING=""
BACKUP=""
cleanup() {
    if [[ -n "$STAGING" && -d "$STAGING" ]]; then
        rm -rf "$STAGING"
    fi
    if [[ -n "$BACKUP" && -d "$BACKUP" && ! -e "$OUTPUT" ]]; then
        mv "$BACKUP" "$OUTPUT"
    fi
    rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

BUILD_SOURCE="$WORK_ROOT/source"
git clone --no-local --quiet "$SOURCE" "$BUILD_SOURCE"
git -C "$BUILD_SOURCE" submodule update --init --recursive \
    3rdparty/EmulatorExtras \
    3rdparty/MaaAgentBinary \
    3rdparty/quickjs \
    source/MaaUtils
git -C "$BUILD_SOURCE" apply --check "$PATCH_PATH"
git -C "$BUILD_SOURCE" apply "$PATCH_PATH"

(
    cd "$BUILD_SOURCE"
    python3 tools/maadeps-download.py arm64-osx
    cmake --preset NinjaMulti \
        -DCMAKE_OSX_ARCHITECTURES=arm64 \
        -DCMAKE_OSX_DEPLOYMENT_TARGET=13.3
    cmake --build build --config Release --target MaaMacOSControlUnit
)

BUILT_LIBRARY=""
while IFS= read -r -d '' candidate; do
    BUILT_LIBRARY="$candidate"
    break
done < <(find "$BUILD_SOURCE/build" -type f -name "$LIBRARY_NAME" -print0)
[[ -n "$BUILT_LIBRARY" ]] || { echo "built library was not produced" >&2; exit 1; }

/usr/bin/file "$BUILT_LIBRARY" | grep -q "Mach-O" || {
    echo "built output is not a Mach-O library" >&2
    exit 1
}
ARCHES="$(/usr/bin/lipo -archs "$BUILT_LIBRARY")"
[[ "$ARCHES" == "arm64" ]] || { echo "built output architectures: $ARCHES" >&2; exit 1; }
/usr/bin/codesign --force --sign - --timestamp=none "$BUILT_LIBRARY"
/usr/bin/codesign --verify --strict "$BUILT_LIBRARY"

PATCHED_SHA256="$(/usr/bin/shasum -a 256 "$BUILT_LIBRARY" | awk '{print $1}')"
PATCHED_SIZE="$(/usr/bin/stat -f %z "$BUILT_LIBRARY")"
[[ "$PATCHED_SIZE" -gt 0 ]] || { echo "built output is empty" >&2; exit 1; }

STAGING="$(mktemp -d "${OUTPUT}.staging.XXXXXX")"
cp -a "$OUTPUT/." "$STAGING/"
cp "$BUILT_LIBRARY" "$STAGING/$LIBRARY_NAME"
/usr/bin/codesign --verify --strict "$STAGING/$LIBRARY_NAME"
python3 - "$STAGING/manifest.json" "$BASE_SHA256" "$PATCH_SHA256" "$PATCHED_SHA256" "$PATCHED_SIZE" <<'PY'
import json
import os
import sys

manifest_path, base_sha256, patch_sha256, patched_sha256, patched_size = sys.argv[1:]
payload = {
    "schema_version": 1,
    "upstream_repository": "https://github.com/MaaXYZ/MaaFramework",
    "upstream_tag": "v5.12.2",
    "target": "macos-arm64",
    "base_library_sha256": base_sha256,
    "patch_sha256": patch_sha256,
    "patched_library_sha256": patched_sha256,
    "patched_library_size": int(patched_size),
}
with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
PY
BACKUP="$(mktemp -d "${OUTPUT}.previous.XXXXXX")"
rmdir "$BACKUP"
mv "$OUTPUT" "$BACKUP"
mv "$STAGING" "$OUTPUT"
STAGING=""
rm -rf "$BACKUP"
BACKUP=""
echo "built and attested $OUTPUT/$LIBRARY_NAME"
