# MJA MFW MaaFramework v5.12.3 native bundle provenance

This bundle is built from the official MaaFramework source repository
https://github.com/MaaXYZ/MaaFramework at tag v5.12.3 and commit
0c3f6454902b8ff9f7697cc6b09a7a935a41cdbb for target macos-arm64.

The clean source checkout is patched, in lexical order, with:

- native/maafw-macos-fallback/patches/0001-macos-coregraphics-region-fallback.patch
- native/maafw-macos-fallback/patches/0002-macos-coregraphics-window-finder.patch
- native/maafw-macos-fallback/patches/0003-macos-coregraphics-preflight.patch
- native/maafw-macos-fallback/patches/0004-macos-coregraphics-capture-guard.patch

The reproducible build entry point is native/maafw-macos-fallback/build-v5123.sh.
It verifies the clean tag and commit, initializes only the required submodules,
builds MaaMacOSControlUnit and MaaToolkit for arm64, and records official-base,
patch, and patched-library SHA-256 values in the attested manifest.
