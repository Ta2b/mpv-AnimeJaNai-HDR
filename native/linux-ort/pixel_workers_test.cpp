// Pixel worker coverage, simultaneous callers, nesting and failure recovery.
#include "engine.h"
#include <atomic>
#include <chrono>
#include <cmath>
#include <iostream>
#include <numeric>

int main(int argc, char **argv)
{
    using namespace aji;
    try {
        for (size_t count : {size_t(0), size_t(1), size_t(7), size_t(64), size_t(1025), size_t(16393)})
            for (size_t grain : {size_t(0), size_t(1), size_t(32), size_t(256), size_t(99999)}) {
                std::vector<std::atomic<int>> visits(count);
                for (auto &v : visits) v = 0;
                parallel(count, grain, [&](size_t first, size_t last) {
                    require(first <= last && last <= count, "invalid pixel range");
                    for (size_t i = first; i < last; ++i) ++visits[i];
                });
                for (auto &v : visits) require(v == 1, "missing or duplicated pixel");
            }
        std::cout << "PASS zero, uneven, small and large ranges, grain zero\n";

        std::atomic<int> failures{0};
        std::vector<std::thread> callers;
        for (int caller = 0; caller < 6; ++caller) callers.emplace_back([&, caller] {
            try {
                for (int iteration = 0; iteration < 100; ++iteration) {
                    std::vector<int> output(2049, -1);
                    parallel(output.size(), 32, [&](size_t first, size_t last) {
                        for (size_t i = first; i < last; ++i) output[i] = caller * 100 + iteration;
                    });
                    for (int v : output) require(v == caller * 100 + iteration, "concurrent call mixed buffers");
                }
            } catch (...) { ++failures; }
        });
        for (auto &t : callers) t.join();
        require(failures == 0, "simultaneous caller failed");
        std::cout << "PASS six simultaneous callers, 600 batches\n";

        std::vector<int> nested(1025, 0);
        parallel(nested.size(), 128, [&](size_t first, size_t last) {
            parallel(last - first, 16, [&](size_t begin, size_t end) {
                for (size_t i = begin; i < end; ++i) ++nested[first + i];
            });
        });
        for (int v : nested) require(v == 1, "nested call failed");
        std::cout << "PASS nested conversions complete without deadlock\n";

        if (detail::pixel_pool_enabled() && detail::pixel_cores() > 1) {
            std::atomic<int> reused{0};
            for (int batch = 1; batch <= 20; ++batch)
                parallel(size_t(4096), size_t(32), [&, batch](size_t first, size_t last) {
                    thread_local int previous_batch = 0;
                    if (detail::on_pixel_worker() && previous_batch && previous_batch != batch) ++reused;
                    previous_batch = batch;
                    for (size_t i = first; i < last; ++i) std::atomic_signal_fence(std::memory_order_seq_cst);
                });
            require(reused > 0, "helper threads did not persist across calls");
            std::cout << "PASS helpers persist across batches\n";

            for (bool caller_throws : {false, true}) {
                std::atomic<int> completed{0};
                bool caught = false;
                try {
                    parallel(size_t(4096), size_t(32), [&](size_t first, size_t) {
                        if ((first == 0) == caller_throws) throw std::runtime_error("conversion failed");
                        ++completed;
                    });
                } catch (const std::runtime_error &) { caught = true; }
                require(caught && completed > 0, "conversion failure not propagated after join");
                parallel(size_t(4096), size_t(32), [&](size_t, size_t) { ++completed; });
                require(completed > 1, "helpers did not recover after error");
            }
            std::cout << "PASS helper/caller errors are joined and propagated, pool recovers\n";
        }

        if (argc > 1 && std::string(argv[1]) == "--benchmark") {
            const int width = 1280, height = 720, iterations = 200;
            const size_t plane = (size_t)width * height;
            std::vector<uint8_t> pixels(3 * plane);
            std::iota(pixels.begin(), pixels.end(), uint8_t(0));
            std::vector<float> planar(3 * plane);
            std::vector<double> times;
            for (int run = 0; run < iterations + 10; ++run) {
                const auto start = std::chrono::steady_clock::now();
                parallel((size_t)height, 64, [&](size_t first, size_t last) {
                    for (size_t y = first; y < last; ++y) for (int x = 0; x < width; ++x) {
                        const size_t at = y * width + x;
                        for (int k = 0; k < 3; ++k) planar[k * plane + at] = pixels[3 * at + k] * (1.f / 255.f);
                    }
                });
                const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
                if (run >= 10) times.push_back(ms);
            }
            for (size_t i = 0; i < plane; ++i) for (int k = 0; k < 3; ++k)
                require(planar[k * plane + i] == pixels[3 * i + k] * (1.f / 255.f), "conversion changed values");
            std::sort(times.begin(), times.end());
            std::cout << "PIXEL_BENCH pool=" << detail::pixel_pool_enabled() << " 1280x720 RGB24 to FP32 planes, median="
                      << (times[99] + times[100]) / 2 << " ms p95=" << times[189]
                      << " ms (CPU helper only, no inference)\n";
        }
    } catch (const std::exception &e) { std::cerr << "FAIL " << e.what() << '\n'; return 1; }
    return 0;
}
