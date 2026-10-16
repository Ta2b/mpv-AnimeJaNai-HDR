#include "submission_worker.h"
#include "pixel_workers.h"
#include <atomic>
#include <cassert>
#include <iostream>
#include <stdexcept>
#include <vector>
int main()
{
    aji::SubmissionWorker lane;
    std::vector<int> order;
    std::thread::id first, second;
    auto a = lane.submit([&] { first = std::this_thread::get_id(); order.push_back(1); });
    auto b = lane.submit([&] { second = std::this_thread::get_id(); order.push_back(2); });
    a.get(); b.get();
    assert(first == second && first != std::this_thread::get_id() && (order == std::vector<int>{1, 2}));
    bool nested = false;
    lane.submit([&] { lane.submit([&] { nested = true; }).get(); }).get();
    assert(nested);
    bool threw = false;
    try { lane.submit([] { throw std::runtime_error("fixture failure"); }).get(); }
    catch (const std::runtime_error &) { threw = true; }
    assert(threw);
    lane.submit([&] { order.push_back(3); }).get(); // lane survives a failed task
    std::atomic<int> total{0};
    aji::SubmissionWorker producer, tile;
    producer.submit([&] {
        tile.submit([&] {
            aji::detail::run_pixel_jobs({[&] { total.fetch_add(2); }}, [&] { total.fetch_add(3); });
        }).get();
    }).get();
    assert(total == 5); // production, model and pixel work have independent queues
    std::atomic<bool> drained{false};
    { aji::SubmissionWorker ending; ending.submit([&] { drained = true; }); }
    assert(drained);
    std::cout << "{\"passed\":true,\"persistent_thread\":true,\"fifo\":true,\"nested_inline\":true,"
        "\"failure_recovery\":true,\"independent_nested_queues\":true,\"destruction_drains\":true}\n";
}
