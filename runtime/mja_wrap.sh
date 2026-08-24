#!/system/bin/sh

# Android zygote wrap hook for the hidden emulator only.
#
# Keep this hook as a transparent launcher.  Injecting LD_PRELOAD here also
# affects Android's early app_process/idmap startup path; on API 35 that path
# is killed by the app seccomp policy while preparing overlays.  The signal
# shim remains available as a standalone diagnostic artifact, but must not be
# inherited by the game or its framework helpers.
unset LD_PRELOAD
exec "$@"
