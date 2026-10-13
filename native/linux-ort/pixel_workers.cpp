#include "pixel_workers.h"
#include <algorithm>
#include <condition_variable>
#include <cstdlib>
#include <deque>
#include <exception>
#include <memory>
#include <mutex>
#include <thread>

namespace aji {
namespace detail {
namespace {
thread_local bool pixel_worker = false;

struct Batch {
    explicit Batch(std::vector<std::function<void()>> work)
        : jobs(std::move(work)), remaining(jobs.size()) {}
    std::vector<std::function<void()>> jobs;
    size_t next = 0; // protected by the pool's queue lock
    std::mutex lock;
    std::condition_variable done;
    size_t remaining;
    std::exception_ptr failure;

    void finish(std::exception_ptr error) {
        std::lock_guard<std::mutex> guard(lock);
        if (error && !failure) failure = error;
        if (--remaining == 0) done.notify_one();
    }
};

class PixelWorkers {
public:
    PixelWorkers() {
        threads_.reserve(pixel_cores() - 1);
        try {
            for (unsigned i = 1; i < pixel_cores(); ++i)
                threads_.emplace_back([this] { worker(); });
        } catch (...) {
            stop();
            throw;
        }
    }
    ~PixelWorkers() { stop(); }
    void run(std::vector<std::function<void()>> jobs, const std::function<void()> &caller) {
        if (jobs.empty()) { caller(); return; }
        auto batch = std::make_shared<Batch>(std::move(jobs));
        {
            std::lock_guard<std::mutex> guard(lock_);
            // A batch is admitted in one operation: allocation failure cannot leave jobs
            // referencing the caller's buffers without a matching wait.
            queue_.push_back(batch);
        }
        available_.notify_all();
        std::exception_ptr caller_error;
        try { caller(); } catch (...) { caller_error = std::current_exception(); }
        {
            std::unique_lock<std::mutex> guard(batch->lock);
            batch->done.wait(guard, [&] { return batch->remaining == 0; });
        }
        if (caller_error) std::rethrow_exception(caller_error);
        if (batch->failure) std::rethrow_exception(batch->failure);
    }
private:
    void worker() {
        pixel_worker = true;
        for (;;) {
            std::shared_ptr<Batch> batch;
            size_t index;
            {
                std::unique_lock<std::mutex> guard(lock_);
                available_.wait(guard, [&] { return stopping_ || !queue_.empty(); });
                if (queue_.empty()) break;
                batch = queue_.front();
                index = batch->next++;
                if (batch->next == batch->jobs.size()) queue_.pop_front();
            }
            std::exception_ptr error;
            try { batch->jobs[index](); } catch (...) { error = std::current_exception(); }
            batch->finish(error);
        }
        pixel_worker = false;
    }
    void stop() {
        {
            std::lock_guard<std::mutex> guard(lock_);
            stopping_ = true;
        }
        available_.notify_all();
        for (auto &thread : threads_) if (thread.joinable()) thread.join();
    }
    std::mutex lock_;
    std::condition_variable available_;
    std::deque<std::shared_ptr<Batch>> queue_;
    std::vector<std::thread> threads_;
    bool stopping_ = false;
};
} // namespace

unsigned pixel_cores() {
    static const unsigned count = std::max(1u, std::min(8u, std::thread::hardware_concurrency()));
    return count;
}
bool pixel_pool_enabled() {
    static const bool enabled = [] {
        const char *value = std::getenv("AJI_PIXEL_POOL");
        return !(value && *value == '0');
    }();
    return enabled;
}
bool on_pixel_worker() { return pixel_worker; }
void run_pixel_jobs(std::vector<std::function<void()>> jobs, std::function<void()> caller) {
    static PixelWorkers workers;
    workers.run(std::move(jobs), caller);
}
} // namespace detail
} // namespace aji
