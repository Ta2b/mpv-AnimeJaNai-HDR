#pragma once
#include "cache_io.h"
#include <atomic>
#include <chrono>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <thread>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace aji::cache {
struct KeyLockBusy : std::runtime_error {
    KeyLockBusy() : std::runtime_error("Cache key lock busy") {}
};
// Stable lock files are deliberately never unlinked: replacing the inode
// would let a third process lock a different file while a waiter owns the old
// one. Kernel ownership is released on close/process exit, not by a timestamp.
class KeyLock {
#ifdef _WIN32
    HANDLE handle_ = INVALID_HANDLE_VALUE;
#else
    int handle_ = -1;
#endif
    void close() noexcept
    {
#ifdef _WIN32
        if (handle_ != INVALID_HANDLE_VALUE) CloseHandle(handle_);
        handle_ = INVALID_HANDLE_VALUE;
#else
        if (handle_ >= 0) ::close(handle_);
        handle_ = -1;
#endif
    }
public:
    explicit KeyLock(const std::filesystem::path &path, const std::atomic<bool> *stop = nullptr,
                     bool wait = true)
    {
        try {
#ifdef _WIN32
            handle_ = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (handle_ == INVALID_HANDLE_VALUE) throw io_error("open cache key lock",path,{(int)GetLastError(),std::system_category()});
#else
            handle_ = ::open(path.c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0600);
            if (handle_ < 0) throw io_error("open cache key lock",path);
#endif
            for (;;) {
                if (stop && stop->load()) throw std::runtime_error("Cache build cancelled while waiting for key lock");
#ifdef _WIN32
                OVERLAPPED offset{};
                if (LockFileEx(handle_, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &offset)) break;
                if (GetLastError() != ERROR_LOCK_VIOLATION) throw io_error("acquire cache key lock",path,{(int)GetLastError(),std::system_category()});
#else
                if (flock(handle_, LOCK_EX | LOCK_NB) == 0) break;
                if (errno != EWOULDBLOCK && errno != EAGAIN && errno != EINTR)
                    throw io_error("acquire cache key lock",path);
#endif
                if (!wait) throw KeyLockBusy();
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
            }
        } catch (...) { close(); throw; }
    }
    ~KeyLock() { close(); }
    KeyLock(const KeyLock &) = delete;
    KeyLock &operator=(const KeyLock &) = delete;
};
}
