// One persistent model-submission lane. Pixel jobs use their own existing pool.
#pragma once
#include <condition_variable>
#include <functional>
#include <future>
#include <mutex>
#include <stdexcept>
#include <thread>

namespace aji {
class SubmissionWorker {
    std::mutex mutex;
    std::condition_variable changed;
    std::packaged_task<void()> queued;
    bool stopping = false;
    std::thread worker;
    void run()
    {
        for (;;) {
            std::packaged_task<void()> task;
            {
                std::unique_lock<std::mutex> lock(mutex);
                changed.wait(lock, [&] { return stopping || queued.valid(); });
                if (!queued.valid()) return;
                task = std::move(queued);
            }
            changed.notify_all(); // at most one running and one queued job
            task(); // transfers every exception to the caller
        }
    }
public:
    SubmissionWorker() : worker([this] { run(); }) { }
    SubmissionWorker(const SubmissionWorker &) = delete;
    SubmissionWorker &operator=(const SubmissionWorker &) = delete;
    ~SubmissionWorker()
    {
        { std::lock_guard<std::mutex> lock(mutex); stopping = true; }
        changed.notify_all(); worker.join(); // drain a queued job before destruction
    }
    std::future<void> submit(std::function<void()> work)
    {
        std::packaged_task<void()> task(std::move(work));
        auto completion = task.get_future();
        // Nested submission cannot wait on this lane's own queue.
        if (std::this_thread::get_id() == worker.get_id()) { task(); return completion; }
        {
            std::unique_lock<std::mutex> lock(mutex);
            changed.wait(lock, [&] { return stopping || !queued.valid(); });
            if (stopping) throw std::runtime_error("submission worker is stopping");
            queued = std::move(task);
        }
        changed.notify_all();
        return completion;
    }
};
} // namespace aji
