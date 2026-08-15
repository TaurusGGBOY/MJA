#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_TAG="v5.12.3"
UPSTREAM_COMMIT="0c3f6454902b8ff9f7697cc6b09a7a935a41cdbb"
# MFW v4.8.23 embeds the v5.12.2 MaaFramework ABI.  Keep the patched
# v5.12.3 sources binary-compatible with the framework that loads them.
MAA_RUNTIME_VERSION="v5.12.2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_DIR="$SCRIPT_DIR/patches"
LIBRARIES=(libMaaMacOSControlUnit.dylib libMaaToolkit.dylib)

usage() {
    cat <<'EOF'
Usage: native/maafw-macos-fallback/build-v5123.sh \
  --source /absolute/clean/MaaFramework-v5.12.3 \
  --official-maafw /absolute/official/mfw/maafw \
  --official-runtime /absolute/official/maa/runtimes/osx-arm64 \
  --output /absolute/MJA/vendor/maafw/v5.12.3/macos-arm64
EOF
}

SOURCE=""
OFFICIAL_MAAFW=""
OFFICIAL_RUNTIME=""
OUTPUT=""
while (($#)); do
    case "$1" in
        --source) SOURCE="$2"; shift 2 ;;
        --official-maafw) OFFICIAL_MAAFW="$2"; shift 2 ;;
        --official-runtime) OFFICIAL_RUNTIME="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done
[[ -n "$SOURCE" && -n "$OFFICIAL_MAAFW" && -n "$OFFICIAL_RUNTIME" && -n "$OUTPUT" ]] || {
    echo "all four path arguments are required" >&2
    usage >&2
    exit 2
}

SOURCE="$(cd "$SOURCE" && pwd)"
OFFICIAL_MAAFW="$(cd "$OFFICIAL_MAAFW" && pwd)"
OFFICIAL_RUNTIME="$(cd "$OFFICIAL_RUNTIME" && pwd)"
mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"

[[ -d "$SOURCE/.git" ]] || { echo "source is not a Git checkout: $SOURCE" >&2; exit 1; }
SOURCE_TAG="$(git -C "$SOURCE" describe --tags --exact-match 2>/dev/null || true)"
[[ "$SOURCE_TAG" == "$UPSTREAM_TAG" ]] || { echo "source tag mismatch" >&2; exit 1; }
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$UPSTREAM_COMMIT" ]] || {
    echo "source commit mismatch" >&2
    exit 1
}
[[ -z "$(git -C "$SOURCE" status --porcelain)" ]] || { echo "source checkout is dirty" >&2; exit 1; }

for library in "${LIBRARIES[@]}"; do
    [[ -f "$OFFICIAL_MAAFW/$library" && ! -L "$OFFICIAL_MAAFW/$library" ]] || exit 1
    [[ -f "$OFFICIAL_RUNTIME/$library" && ! -L "$OFFICIAL_RUNTIME/$library" ]] || exit 1
done

WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mja-maafw-v5123-build.XXXXXX")"
STAGING=""
BACKUP=""
cleanup() {
    [[ -z "$STAGING" || ! -d "$STAGING" ]] || rm -rf "$STAGING"
    [[ -z "$BACKUP" || ! -d "$BACKUP" || -e "$OUTPUT" ]] || mv "$BACKUP" "$OUTPUT"
    [[ -d "$WORK_ROOT" ]] && rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

BUILD_SOURCE="$WORK_ROOT/source"
git clone --no-local --quiet "$SOURCE" "$BUILD_SOURCE"
git -C "$BUILD_SOURCE" submodule update --init --recursive \
    3rdparty/EmulatorExtras 3rdparty/MaaAgentBinary 3rdparty/quickjs source/MaaUtils
for patch in "$PATCH_DIR"/*.patch; do
    git -C "$BUILD_SOURCE" apply --check "$patch"
    git -C "$BUILD_SOURCE" apply "$patch"
done

(
    cd "$BUILD_SOURCE"
    python3 tools/maadeps-download.py arm64-osx
    cmake --preset NinjaMulti \
      -DCMAKE_OSX_ARCHITECTURES=arm64 \
      -DCMAKE_OSX_DEPLOYMENT_TARGET=13.3 \
      -DENABLE_HASH_VERSION=ON \
      -DMAA_HASH_VERSION="$MAA_RUNTIME_VERSION"
    cmake --build build --config Release --target MaaMacOSControlUnit MaaToolkit -j 8
)

find_library() {
    local name="$1"
    local path
    path="$(find "$BUILD_SOURCE/build" -type f -name "$name" -print -quit)"
    [[ -n "$path" ]] || { echo "built library is missing: $name" >&2; exit 1; }
    printf '%s\n' "$path"
}
BUILT_CONTROL="$(find_library libMaaMacOSControlUnit.dylib)"
BUILT_TOOLKIT="$(find_library libMaaToolkit.dylib)"
/usr/bin/file "$BUILT_CONTROL" "$BUILT_TOOLKIT" | grep -q "Mach-O"
[[ "$(/usr/bin/lipo -archs "$BUILT_CONTROL")" == "arm64" ]]
[[ "$(/usr/bin/lipo -archs "$BUILT_TOOLKIT")" == "arm64" ]]

# CMake records build-tree search paths in the dylib RPATH.  They are useful
# while linking but must never escape into the attested bundle.
for built in "$BUILT_CONTROL" "$BUILT_TOOLKIT"; do
    for rpath in \
        "$BUILD_SOURCE/build/bin/Release" \
        "$BUILD_SOURCE/source/MaaUtils/MaaDeps/vcpkg/installed/maa-arm64-osx/lib"; do
        install_name_tool -delete_rpath "$rpath" "$built" 2>/dev/null || true
    done
    if otool -l "$built" | awk '/LC_RPATH/{getline; getline; print}' | grep -q 'path /'; then
        echo "absolute build RPATH remains in $built" >&2
        exit 1
    fi
done
/usr/bin/codesign --force --sign - --timestamp=none "$BUILT_CONTROL" "$BUILT_TOOLKIT"

STAGING="$(mktemp -d "$OUTPUT.staging.XXXXXX")"
cp "$BUILT_CONTROL" "$STAGING/libMaaMacOSControlUnit.dylib"
cp "$BUILT_TOOLKIT" "$STAGING/libMaaToolkit.dylib"
cp "$BUILD_SOURCE/LICENSE.md" "$STAGING/LICENSE.md"
cp "$SCRIPT_DIR/SOURCE-v5123.md" "$STAGING/SOURCE.md"
python3 - "$STAGING/manifest.json" "$OFFICIAL_MAAFW" "$OFFICIAL_RUNTIME" "$PATCH_DIR" "$BUILT_CONTROL" "$BUILT_TOOLKIT" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

manifest_path, official_maafw, official_runtime, patch_dir, built_control, built_toolkit = sys.argv[1:]
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
libraries = ("libMaaMacOSControlUnit.dylib", "libMaaToolkit.dylib")
destinations = {
    f"maafw/{name}": os.path.join(official_maafw, name) for name in libraries
}
destinations.update({
    f"runtimes/osx-arm64/{name}": os.path.join(official_runtime, name) for name in libraries
})
patches = {
    pathlib.Path(path).name: digest(path)
    for path in sorted(pathlib.Path(patch_dir).glob("*.patch"))
}
payload = {
    "schema_version": 1,
    "upstream_repository": "https://github.com/MaaXYZ/MaaFramework",
    "upstream_tag": "v5.12.3",
    "upstream_commit": "0c3f6454902b8ff9f7697cc6b09a7a935a41cdbb",
    "target": "macos-arm64",
    "base_libraries_sha256": {key: digest(path) for key, path in destinations.items()},
    "patches_sha256": patches,
    "patched_libraries_sha256": {
        "libMaaMacOSControlUnit.dylib": digest(built_control),
        "libMaaToolkit.dylib": digest(built_toolkit),
    },
    "patched_libraries_size": {
        "libMaaMacOSControlUnit.dylib": os.path.getsize(built_control),
        "libMaaToolkit.dylib": os.path.getsize(built_toolkit),
    },
}
with open(manifest_path, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY

BACKUP="$(mktemp -d "$OUTPUT.previous.XXXXXX")"
rmdir "$BACKUP"
mv "$OUTPUT" "$BACKUP"
mv "$STAGING" "$OUTPUT"
STAGING=""
rm -rf "$BACKUP"
BACKUP=""
echo "built and attested $OUTPUT"
