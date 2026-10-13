// Persistent workers for independent CPU pixel ranges. No model work is queued here.
#pragma once
#include <functional>
#include <vector>

namespace aji {
namespace detail {
unsigned pixel_cores();
bool pixel_pool_enabled();
bool on_pixel_worker();
// Runs jobs on the helpers and caller on this thread. Waits for all jobs, including on error.
void run_pixel_jobs(std::vector<std::function<void()>> jobs, std::function<void()> caller);
} // namespace detail
} // namespace aji
