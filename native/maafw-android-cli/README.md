# Reproducible Android MaaPiCli build

This bundle owns the small MaaFramework `v5.12.2` patch required by a plain ADB
emulator. MaaToolkit may return an empty config and no preferred screenshot/input
methods when the device is not registered in its desktop device list. The patch
supplies `{}`, `MaaAdbScreencapMethod_Default`, and `MaaAdbInputMethod_Default` before
creating the controller.

The build is isolated from `/Users/gaoguobin/project/MaaFramework`. It requires a clean
checkout exactly at tag `v5.12.2`, commit
`f625a60edeccd4549f9a71c0f74628d827ade8fb`, and applies the patch only inside a temporary
clone. It builds the `MaaPiCli` target for Apple Silicon, verifies the Mach-O architecture
and SHA-256 digest, then atomically replaces the destination `MaaPiCli` binary and writes
`MaaPiCli.android.manifest.json`.

```bash
native/maafw-android-cli/build.sh \
  --source /absolute/clean/MaaFramework-v5.12.2 \
  --official-bin /absolute/official-bin \
  --output /absolute/MJA/install
```

`--official-bin` is deliberately separate from the source checkout. It must contain the
existing runtime `MaaPiCli` binary and is used as the destination/runtime baseline; the
build never modifies it.
