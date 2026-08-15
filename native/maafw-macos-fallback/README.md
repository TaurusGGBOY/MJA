# MaaFramework macOS capture fallback bundle

This directory owns MJA's minimal, reproducible patch for the MaaFramework macOS control
unit. The patch is based only on the official MaaFramework `v5.12.2` source at commit
`f625a60edeccd4549f9a71c0f74628d827ade8fb` and targets Apple Silicon (`macos-arm64`).
The existing checkout at `/Users/gaoguobin/project/MaaFramework` is reference material only;
the build process must use a separate clean clone or archive and must never modify or fetch
into that checkout.

## Fixed paths

- Patch: `native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch`
- Build entry point: `native/maafw-macos-fallback/build.sh`
- Attested bundle: `vendor/maafw/v5.12.2/macos-arm64/`
- Patched library: `libMaaMacOSControlUnit.dylib`
- Manifest: `manifest.json`
- Source notice: `SOURCE.md`
- Upstream license copy: `LICENSE.md`

The patch is applied only inside a temporary clone of the clean tagged source. The build
script checks the source tag, commit, and clean status; initializes only the MaaFramework
submodules needed by the native target; downloads the pinned `arm64-osx` MaaDeps target;
configures the official Ninja Multi-Config preset for arm64; builds only
`MaaMacOSControlUnit`; verifies the Mach-O slice; applies an ad-hoc signature; and writes the
library and manifest through a staging directory. It never modifies the reference checkout.

The manifest and dylib are committed only after the build has been performed and verified.

## MFW runtime bundle (v5.12.3)

MFW candidates use the separately attested bundle at
`vendor/maafw/v5.12.3/macos-arm64/`. It contains the patched
`libMaaMacOSControlUnit.dylib` and `libMaaToolkit.dylib`; the installer validates
the four official-base digests and replaces both the `maafw/` and
`runtimes/osx-arm64/` copies. Build it with
`native/maafw-macos-fallback/build-v5123.sh`, which applies all four patches in
lexical order to MaaFramework v5.12.3.

## Manifest contract

`manifest.json` is a UTF-8 JSON object with exactly these fields:

| Field | Required value |
| --- | --- |
| `schema_version` | Integer `1`; Boolean values are invalid |
| `upstream_repository` | `https://github.com/MaaXYZ/MaaFramework` |
| `upstream_tag` | `v5.12.2` |
| `target` | `macos-arm64` |
| `base_library_sha256` | Exactly 64 lowercase hexadecimal characters |
| `patch_sha256` | Exactly 64 lowercase hexadecimal characters |
| `patched_library_sha256` | Exactly 64 lowercase hexadecimal characters |
| `patched_library_size` | A positive integer; Boolean values are invalid |

No path is read from the manifest. Bundle filenames are fixed by the loader, which prevents
manifest-controlled traversal. Unknown and missing fields, duplicate JSON keys, non-standard
JSON constants, symlinked roots or files, non-regular files, altered notices, and digest or
size mismatches are rejected.

`tools.native_bundle.load_patched_bundle(root, require_library=...)` validates the manifest
and both notices on every call. With `require_library=False`, the dylib may be absent before
the build task runs; if it exists, its size and digest are still checked. With
`require_library=True`, absence of the dylib is an error.

## Reproducible build invocation

After `build.sh` is introduced, set the two source paths to absolute paths and run from the
MJA repository root:

```bash
native/maafw-macos-fallback/build.sh \
  --source "$MJA_MAAFW_V5122_SOURCE" \
  --official-bin "$MJA_MAAFW_V5122_OFFICIAL_BIN" \
  --output "$PWD/vendor/maafw/v5.12.2/macos-arm64"
```

The source must be a clean checkout exactly at tag `v5.12.2`. The official-bin directory
must come from the official runtime archive pinned by `runtime-manifest.json`.
