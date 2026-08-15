#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_TAG="v5.12.2"
UPSTREAM_COMMIT="f625a60edeccd4549f9a71c0f74628d827ade8fb"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_PATH="$SCRIPT_DIR/patches/0001-plain-adb-defaults.patch"
REFERENCE_SOURCE="${MJA_MAAFRAME_REFERENCE:-$SCRIPT_DIR/../../../MaaFramework}"

usage() {
    cat <<'EOF'
Usage: native/maafw-android-cli/build.sh \
  --source /absolute/clean/MaaFramework-v5.12.2 \
  --official-bin /absolute/official-bin \
  --output /absolute/MJA/install
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
[[ -f "$PATCH_PATH" ]] || { echo "missing Android MaaPiCli patch: $PATCH_PATH" >&2; exit 1; }
[[ -d "$OFFICIAL_BIN" ]] || { echo "official bin directory is missing: $OFFICIAL_BIN" >&2; exit 1; }
[[ -f "$OFFICIAL_BIN/MaaPiCli" ]] || {
    echo "official MaaPiCli is missing: $OFFICIAL_BIN/MaaPiCli" >&2
    exit 1
}

REFERENCE_SOURCE_CANDIDATES=(
    "$REFERENCE_SOURCE"
    "/Users/gaoguobin/project/MaaFramework"
    "/Volumes/my_disk/project/MaaFramework"
)
for reference_candidate in "${REFERENCE_SOURCE_CANDIDATES[@]}"; do
    if [[ -d "$reference_candidate/.git" ]]; then
        reference_candidate="$(cd "$reference_candidate" && pwd)"
        [[ "$SOURCE" != "$reference_candidate" ]] || {
            echo "source must not be the reference MaaFramework checkout" >&2
            exit 1
        }
    fi
done

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

WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mja-maapi-build.XXXXXX")"
TEMP_BINARY=""
cleanup() {
    if [[ -n "$TEMP_BINARY" && -e "$TEMP_BINARY" ]]; then
        rm -f "$TEMP_BINARY"
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
    cmake --build build --config Release --target MaaPiCli
)

BUILT_BINARY=""
while IFS= read -r -d '' candidate; do
    BUILT_BINARY="$candidate"
    break
done < <(find "$BUILD_SOURCE/build" -type f -name MaaPiCli -print0)
[[ -n "$BUILT_BINARY" ]] || { echo "MaaPiCli build output was not produced" >&2; exit 1; }

BUILT_ADB_LIBRARY=""
while IFS= read -r -d '' candidate; do
    BUILT_ADB_LIBRARY="$candidate"
    break
done < <(find "$BUILD_SOURCE/build" -type f -name libMaaAdbControlUnit.dylib -print0)
[[ -n "$BUILT_ADB_LIBRARY" ]] || {
    echo "libMaaAdbControlUnit.dylib build output was not produced" >&2
    exit 1
}

/usr/bin/file "$BUILT_BINARY" | grep -q "Mach-O" || {
    echo "built MaaPiCli is not a Mach-O executable" >&2
    exit 1
}
ARCHES="$(/usr/bin/lipo -archs "$BUILT_BINARY")"
[[ "$ARCHES" == "arm64" ]] || { echo "built MaaPiCli architectures: $ARCHES" >&2; exit 1; }

PATCH_SHA256="$(/usr/bin/shasum -a 256 "$PATCH_PATH" | awk '{print $1}')"
BUILT_SHA256="$(/usr/bin/shasum -a 256 "$BUILT_BINARY" | awk '{print $1}')"
BUILT_SIZE="$(/usr/bin/stat -f %z "$BUILT_BINARY")"
BUILT_ADB_SHA256="$(/usr/bin/shasum -a 256 "$BUILT_ADB_LIBRARY" | awk '{print $1}')"
BUILT_ADB_SIZE="$(/usr/bin/stat -f %z "$BUILT_ADB_LIBRARY")"
[[ "$BUILT_SIZE" -gt 0 ]] || { echo "built MaaPiCli is empty" >&2; exit 1; }
[[ "$BUILT_ADB_SIZE" -gt 0 ]] || {
    echo "built libMaaAdbControlUnit.dylib is empty" >&2
    exit 1
}

TEMP_BINARY="$OUTPUT/.MaaPiCli.tmp"
cp "$BUILT_BINARY" "$TEMP_BINARY"
chmod 755 "$TEMP_BINARY"
/usr/bin/shasum -a 256 "$TEMP_BINARY" | grep -q "$BUILT_SHA256" || {
    echo "staged MaaPiCli digest mismatch" >&2
    exit 1
}
mv -f "$TEMP_BINARY" "$OUTPUT/MaaPiCli"
TEMP_BINARY=""

TEMP_ADB_LIBRARY="$OUTPUT/.libMaaAdbControlUnit.dylib.tmp"
cp "$BUILT_ADB_LIBRARY" "$TEMP_ADB_LIBRARY"
chmod 644 "$TEMP_ADB_LIBRARY"
for destination in \
    "$OUTPUT/libMaaAdbControlUnit.dylib" \
    "$OUTPUT/runtime/maafw/bin/libMaaAdbControlUnit.dylib"; do
    if [[ -d "$(dirname "$destination")" ]]; then
        cp "$TEMP_ADB_LIBRARY" "$destination"
    fi
done
rm -f "$TEMP_ADB_LIBRARY"

python3 - "$OUTPUT/MaaPiCli.android.manifest.json" "$PATCH_SHA256" "$BUILT_SHA256" "$BUILT_SIZE" "$BUILT_ADB_SHA256" "$BUILT_ADB_SIZE" <<'PY'
import json
import os
import sys

(
    manifest_path,
    patch_sha256,
    binary_sha256,
    binary_size,
    adb_library_sha256,
    adb_library_size,
) = sys.argv[1:]
temporary = manifest_path + ".tmp"
payload = {
    "schema_version": 1,
    "upstream_repository": "https://github.com/MaaXYZ/MaaFramework",
    "upstream_tag": "v5.12.2",
    "upstream_commit": "f625a60edeccd4549f9a71c0f74628d827ade8fb",
    "target": "macos-arm64",
    "patch_sha256": patch_sha256,
    "maapi_cli_sha256": binary_sha256,
    "maapi_cli_size": int(binary_size),
    "adb_control_unit_sha256": adb_library_sha256,
    "adb_control_unit_size": int(adb_library_size),
}
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, manifest_path)
PY

echo "built and attested $OUTPUT/MaaPiCli"
