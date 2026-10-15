// Bounded, atomic text snapshots. The owning engine context is called serially.
#pragma once
#include <atomic>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <stdexcept>
#include <cstdint>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace aji {
class StatsPublisher {
    using Clock = std::chrono::steady_clock;
    Clock::time_point last_attempt_{};
    bool attempted_ = false;
    uint64_t publications_ = 0;
public:
    static constexpr int interval_ms = 250;
    uint64_t publications() const { return publications_; }

    // Rendering is lazy: a suppressed frame does no formatting or filesystem I/O.
    // Force is reserved for configure, first output, error and final state.
    template<class Render> bool publish(const std::string &name, Render render, bool force = false) noexcept
    {
        if (name.empty()) return false;
        const auto now = Clock::now();
        if (!force && attempted_ && now - last_attempt_ < std::chrono::milliseconds(interval_ms)) return false;
        attempted_ = true;
        last_attempt_ = now; // Also bound retries when the destination is unwritable.
        namespace fs = std::filesystem;
        fs::path temporary;
        bool owned = false;
        try {
            const fs::path target = fs::u8path(name);
            static std::atomic<uint64_t> serial{0};
            std::error_code ec;
            for (int attempt = 0; attempt < 32; ++attempt) {
                const auto token = std::to_string(now.time_since_epoch().count()) + "-" + std::to_string(++serial);
                temporary = target.parent_path() / (".aji-stats-" + token);
                if (fs::create_directory(temporary, ec)) { owned = true; break; }
                if (ec && ec != std::errc::file_exists) throw fs::filesystem_error("create stats temporary", temporary, ec);
                temporary.clear();
            }
            if (temporary.empty()) throw std::runtime_error("Cannot reserve stats temporary");
            const auto file = temporary / "snapshot";
            std::ofstream out(file, std::ios::binary | std::ios::trunc);
            out << render() << "Stats snapshot: v1\nStats sequence: " << publications_ + 1
                << "\nStats interval ms: " << interval_ms << "\n";
            out.close();
            if (!out) throw std::runtime_error("Cannot write complete stats snapshot");
#ifdef _WIN32
            if (!MoveFileExW(file.c_str(), target.c_str(), MOVEFILE_REPLACE_EXISTING))
                throw std::runtime_error("Cannot replace stats snapshot (Windows error " + std::to_string(GetLastError()) + ")");
#else
            fs::rename(file, target);
#endif
            ++publications_;
            fs::remove(temporary, ec);
            return true;
        } catch (const std::exception &e) {
            std::fprintf(stderr, "[aji] stats snapshot: %s\n", e.what());
            std::error_code ignored;
            if (owned) fs::remove_all(temporary, ignored);
            return false; // The previous complete snapshot remains readable.
        }
    }
};
} // namespace aji
