// Minimal Android preload shim used only for diagnosing the game's native
// startup guard inside the hidden test emulator.  It intentionally does not
// alter input, game state, or network calls.

typedef int pid_t;
typedef unsigned long size_t;

extern int unsetenv(const char *name);

// Keep the shim resident in the wrapped game process, but do not leak the
// preload marker into framework helpers (for example idmap2) launched later.
// Those helpers have their own seccomp policy and must start without this
// diagnostic library in their environment.
__attribute__((constructor)) static void mja_clear_preload_environment(void)
{
    (void)unsetenv("LD_PRELOAD");
}

static long raw_syscall4(long number, long arg0, long arg1, long arg2, long arg3)
{
    register long x0 __asm__("x0") = arg0;
    register long x1 __asm__("x1") = arg1;
    register long x2 __asm__("x2") = arg2;
    register long x3 __asm__("x3") = arg3;
    register long x8 __asm__("x8") = number;
    __asm__ volatile("svc 0"
                     : "+r"(x0)
                     : "r"(x1), "r"(x2), "r"(x3), "r"(x8)
                     : "memory");
    return x0;
}

static size_t append_text(char *buffer, size_t offset, const char *text)
{
    while (*text != '\0') {
        buffer[offset++] = *text++;
    }
    return offset;
}

static size_t append_unsigned(char *buffer, size_t offset, unsigned long value)
{
    char digits[24];
    size_t count = 0;
    do {
        digits[count++] = (char)('0' + (value % 10));
        value /= 10;
    } while (value != 0);
    while (count != 0) {
        buffer[offset++] = digits[--count];
    }
    return offset;
}

static void record_signal(const char *name, unsigned long target, int signal_number)
{
    // openat/write/close syscall numbers for arm64 Linux.
    const long at_fdcwd = -100;
    const long openat = 56;
    const long write = 64;
    const long close = 57;
    const long flags = 1 | 64 | 1024; // O_WRONLY | O_CREAT | O_APPEND
    const char path[] = "/data/data/com.hanjiasongshu.dr22/files/mja_signal_shim.log";
    char line[160];
    size_t length = 0;
    long fd;

    line[length++] = '[';
    length = append_text(line, length, name);
    line[length++] = ' ';
    length = append_unsigned(line, length, (unsigned long)raw_syscall4(172, 0, 0, 0, 0));
    line[length++] = ' ';
    length = append_unsigned(line, length, target);
    line[length++] = ' ';
    length = append_unsigned(line, length, (unsigned long)signal_number);
    line[length++] = ']';
    line[length++] = '\n';

    fd = raw_syscall4(openat, at_fdcwd, (long)path, flags, 0666);
    if (fd >= 0) {
        (void)raw_syscall4(write, fd, (long)line, (long)length, 0);
        (void)raw_syscall4(close, fd, 0, 0, 0);
    }
}

__attribute__((visibility("default"))) int kill(pid_t pid, int signal_number)
{
    record_signal("kill", (unsigned long)pid, signal_number);
    if (signal_number == 9) {
        return 0;
    }
    return (int)raw_syscall4(129, (long)pid, signal_number, 0, 0);
}

__attribute__((visibility("default"))) int tgkill(pid_t tgid, pid_t tid, int signal_number)
{
    record_signal("tgkill", (unsigned long)tid, signal_number);
    if (signal_number == 9) {
        return 0;
    }
    return (int)raw_syscall4(131, (long)tgid, (long)tid, signal_number, 0);
}
