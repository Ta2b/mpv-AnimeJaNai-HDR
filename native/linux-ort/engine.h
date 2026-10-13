// Shared by the engine core and its executors.
//
// The core (aji_ort.cpp) reads the profile, resizes, cuts the model input in tiles, decides which
// tiles changed since they were last computed, and hands the others to executors. An executor is
// one device running one model on windows of one fixed size: ONNX Runtime with a provider
// (exec_ort.cpp), Core ML or Metal on Apple Silicon (native/apple), or the plain C++ reference
// used by the tests (exec_ref.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include "pixel_workers.h"

namespace aji {

inline void require(bool value, const std::string &message) { if (!value) throw std::runtime_error(message); }

inline std::string lower(std::string s)
{
    for (auto &ch : s) ch = (char)((ch >= 'A' && ch <= 'Z') ? ch - 'A' + 'a' : ch);
    return s;
}

// Runs body(first, last) over [0, count) on several threads. The host-side work of a frame is
// a few passes over millions of pixels. Helper threads persist across calls. AJI_PIXEL_POOL=0
// retains the former per-call threads for comparison. Nested helper calls run locally so
// several occupied helpers cannot deadlock waiting for one another.
template <typename Body> void parallel(size_t count, size_t grain, Body body)
{
    const unsigned cores = detail::pixel_cores();
    const size_t parts = std::min<size_t>(cores, std::max<size_t>(1, count / std::max<size_t>(1, grain)));
    if (parts <= 1) { body((size_t)0, count); return; }
    if (detail::pixel_pool_enabled()) {
        if (detail::on_pixel_worker()) { body((size_t)0, count); return; }
        std::vector<std::function<void()>> jobs;
        jobs.reserve(parts - 1);
        for (size_t k = 1; k < parts; k++)
            jobs.emplace_back([=] { body(count * k / parts, count * (k + 1) / parts); });
        detail::run_pixel_jobs(std::move(jobs), [=] { body((size_t)0, count / parts); });
        return;
    }
    std::vector<std::thread> workers;
    workers.reserve(parts - 1);
    for (size_t k = 1; k < parts; k++)
        workers.emplace_back([=] { body(count * k / parts, count * (k + 1) / parts); });
    body((size_t)0, count / parts);
    for (auto &w : workers) w.join();
}

// One window to compute. `in` is the top-left pixel of a width x height RGB24 window (the size the
// executor was made for); the model doubles it. The executor writes the crop_w x crop_h region
// that starts at (crop_x, crop_y) of that doubled window to `out`, RGB24.
struct Job {
    const uint8_t *in = nullptr;
    ptrdiff_t in_stride = 0;
    uint8_t *out = nullptr;
    ptrdiff_t out_stride = 0;
    int crop_x = 0, crop_y = 0, crop_w = 0, crop_h = 0;
    // The executor is the only one working: it may use the helper threads for its conversions.
    bool spread = false;
};

class Executor {
public:
    virtual ~Executor() = default;
    virtual void run(const Job &job) = 0;
    std::string label;   // "CoreML GPU", "Metal", "CPU"...
    std::string note;    // where the model really runs, when the device can tell
};

struct ExecutorRequest {
    std::string provider;     // cpu, openvino, migraphx, coreml, coremlnative, metal, reference
    std::string device;       // one device name; its meaning depends on the provider
    std::string models_dir;   // folder of NAME.onnx (and NAME.ajm, NAME.mlpackage on macOS)
    std::string model;        // NAME
    std::string cache_dir;    // writable folder for compiled models; may be empty
    int width = 0, height = 0;
};

std::unique_ptr<Executor> make_ort_executor(const ExecutorRequest &request);

// Frame interpolation: RIFE 4.x as exported for this project (one input of eleven planes: the
// two pictures, the instant, and four planes that describe the sampling grid; any size that is
// a multiple of 64, the pictures being padded to it).
struct InterpolatorRequest {
    std::string provider, device;   // as for an executor
    std::string models_dir;         // folder of rife_v4.NN.onnx
    std::string model;              // rife_v4.26, rife_v4.22_lite...
    std::string cache_dir;
    int width = 0, height = 0;      // of the pictures
    bool profile = false;         // separate CPU preparation / ORT run / output timings
};

class Interpolator {
public:
    virtual ~Interpolator() = default;
    // The picture at instant t (0 < t < 1) between a and b, three RGB24 pictures of the size the
    // interpolator was made for. The two pictures are kept in the model's input from one call
    // to the next: a pair is converted once whatever the number of instants, and the second
    // picture of a pair is not converted again when it becomes the first of the next one.
    virtual void run(const uint8_t *a, ptrdiff_t a_stride, const uint8_t *b, ptrdiff_t b_stride, double t,
                     uint8_t *out, ptrdiff_t out_stride) = 0;
    struct Timing {
        uint64_t runs = 0, source_preparations = 0, source_hits = 0, source_promotions = 0, timestep_updates = 0;
        double preparation_ms = 0, inference_ms = 0, output_ms = 0;
    } timing;
    std::string label;
};

std::unique_ptr<Interpolator> make_ort_interpolator(const InterpolatorRequest &request);
std::unique_ptr<Executor> make_reference_executor(const ExecutorRequest &request);
#if defined(__APPLE__)
std::unique_ptr<Executor> make_coreml_executor(const ExecutorRequest &request);
std::unique_ptr<Executor> make_metal_executor(const ExecutorRequest &request);
#endif

} // namespace aji
