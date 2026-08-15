#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static const char *const kSdkRoot = "/Volumes/my_disk/project/MJA/install/android-sdk";
static const char *const kEmulatorRoot = "/Volumes/my_disk/project/MJA/install/android-sdk/emulator";
static const char *const kBundledEmulator = "/Volumes/my_disk/project/MJA/runtime/MJAAndroidEmulator.app/Contents/MacOS/emulator";
static const char *const kQtLib = "/Volumes/my_disk/project/MJA/install/android-sdk/emulator/lib64/qt/lib";
static const char *const kQtPlugins = "/Volumes/my_disk/project/MJA/install/android-sdk/emulator/lib64/qt/plugins";
static const char *const kDyldPath = "/Volumes/my_disk/project/MJA/install/android-sdk/emulator/lib64:/Volumes/my_disk/project/MJA/install/android-sdk/emulator/lib64/qt/lib";

int main(int argc, char **argv) {
    if (setenv("ANDROID_SDK_ROOT", kSdkRoot, 1) != 0 ||
        setenv("ANDROID_HOME", kSdkRoot, 1) != 0 ||
        setenv("ANDROID_EMULATOR_LAUNCHER_DIR", kEmulatorRoot, 1) != 0 ||
        setenv("ANDROID_QT_LIB_PATH", kQtLib, 1) != 0 ||
        setenv("ANDROID_QT_QPA_PLATFORM_PLUGIN_PATH", kQtPlugins, 1) != 0 ||
        setenv("DYLD_LIBRARY_PATH", kDyldPath, 1) != 0 ||
        setenv("DYLD_FALLBACK_LIBRARY_PATH", kDyldPath, 1) != 0 ||
        chdir(kEmulatorRoot) != 0) {
        fprintf(stderr, "MJA emulator wrapper setup failed: %s\n", strerror(errno));
        return 1;
    }

    // LaunchServices adds this marker for the app wrapper. The Android
    // emulator uses its own SDK/process discovery and must not inherit it.
    unsetenv("__CFBundleIdentifier");

    char **bundled_argv = calloc((size_t)argc + 1, sizeof(*bundled_argv));
    if (bundled_argv == NULL) {
        fprintf(stderr, "MJA emulator wrapper argv allocation failed\n");
        return 1;
    }

    bundled_argv[0] = (char *)kBundledEmulator;
    for (int i = 1; i < argc; ++i) {
        bundled_argv[i] = argv[i];
    }

    execv(kBundledEmulator, bundled_argv);
    int exec_error = errno;
    free(bundled_argv);
    if (exec_error != 0) {
        fprintf(stderr, "MJA emulator wrapper could not exec bundled emulator: %s\n", strerror(exec_error));
        return 1;
    }
    return 1;
}
