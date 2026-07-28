# MaaFramework patched control-unit source notice

The future binary in this directory is a locally built, modified MaaFramework control unit.
Its reproducibility inputs are fixed as follows:

- Upstream repository: `https://github.com/MaaXYZ/MaaFramework`
- Upstream tag: `v5.12.2`
- Upstream commit: `f625a60edeccd4549f9a71c0f74628d827ade8fb`
- Target architecture: `macos-arm64`
- Patch: `native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch`
- License notice: `vendor/maafw/v5.12.2/macos-arm64/LICENSE.md`

The exact upstream `LICENSE.md` from that commit is copied beside this notice. The patched
library remains covered by the GNU Lesser General Public License, version 3.

## Local build command

Run from the MJA repository root after assigning both task-specific variables to absolute
paths for a clean source snapshot and the extracted official runtime `bin` directory:

```bash
native/maafw-macos-fallback/build.sh \
  --source "$MJA_MAAFW_V5122_SOURCE" \
  --official-bin "$MJA_MAAFW_V5122_OFFICIAL_BIN" \
  --output "$PWD/vendor/maafw/v5.12.2/macos-arm64"
```

The build entry point and patch are introduced by the subsequent native implementation
tasks. No binary or manifest is attested until that guarded build completes successfully.
