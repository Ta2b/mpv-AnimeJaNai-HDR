// Test-only Linux interposer: stop after writing 64 bytes of the selected
// staging file. The controller kills this owned process; production has no
// test hook and never loads this library.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/uio.h>
#include <unistd.h>

static ssize_t (*real_write)(int, const void *, size_t);
static ssize_t (*real_writev)(int, const struct iovec *, int);
static int paused;
static int fault_fd = -1, fault_errno;
static int target(int fd, char *path)
{
    const char *root = getenv("AJI_INTERRUPT_ROOT"), *name = getenv("AJI_INTERRUPT_FILE");
    if (paused || !root || !name) return 0;
    char link[64]; snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
    ssize_t n = readlink(link, path, PATH_MAX - 1);
    if (n < 0) return 0;
    path[n] = 0;
    const char *base = strrchr(path, '/');
    return base && !strcmp(base + 1, name) && !strncmp(path, root, strlen(root)) &&
        (strstr(path, "/.part-") || strstr(path, "/.aji-build-"));
}
static ssize_t stop_write(int fd, const void *data, size_t size, const char *path)
{
    paused = 1;
    ssize_t n = real_write(fd, data, size < 64 ? size : 64);
    const char *injected = getenv("AJI_INJECT_ERRNO");
    if (injected) {
        fault_fd = fd; fault_errno = atoi(injected);
        return n; // the next write reports the injected error after a real partial write
    }
    const char *marker = getenv("AJI_INTERRUPT_READY");
    int signal_fd = open(marker, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (signal_fd >= 0) {
        char record[PATH_MAX + 64];
        int bytes = snprintf(record, sizeof(record), "%d\n%s\n", getpid(), path);
        real_write(signal_fd, record, (size_t)bytes); close(signal_fd);
    }
    if (n >= 0) raise(SIGSTOP);
    errno = EINTR;
    return -1;
}
ssize_t write(int fd, const void *data, size_t size)
{
    if (fd == fault_fd) { errno = fault_errno; return -1; }
    if (!real_write) real_write = dlsym(RTLD_NEXT, "write");
    char path[PATH_MAX];
    if (size && target(fd, path)) return stop_write(fd, data, size, path);
    return real_write(fd, data, size);
}
ssize_t writev(int fd, const struct iovec *iov, int count)
{
    if (fd == fault_fd) { errno = fault_errno; return -1; }
    if (!real_write) real_write = dlsym(RTLD_NEXT, "write");
    if (!real_writev) real_writev = dlsym(RTLD_NEXT, "writev");
    char path[PATH_MAX];
    if (target(fd, path))
        for (int i = 0; i < count; ++i)
            if (iov[i].iov_len) return stop_write(fd, iov[i].iov_base, iov[i].iov_len, path);
    return real_writev(fd, iov, count);
}
