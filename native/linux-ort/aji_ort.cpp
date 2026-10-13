// AnimeJaNai upscaling engine behind the host RGB24 bridge (aji_vulkan.h): the player filter
// loads this library like the NCNN/Vulkan one.
//
// The work on the pictures is done by executors (engine.h): ONNX Runtime with the provider of the
// GPU vendor (AMD MIGraphX, Intel OpenVINO, Apple Core ML, CPU) and, on Apple Silicon, Core ML
// and Metal without ONNX Runtime. This file is what they share:
//   - the profile: which models, at which size (animejanai.conf);
//   - tiles: the model input is cut in windows of one size, each seeing far enough past its
//     edges to compute what the whole frame would. Several devices then work on one frame at the
//     same time, each taking the next tile when it is free;
//   - reuse: anime holds a drawing for several frames and moves little of the picture. A tile
//     whose pixels did not change since it was computed keeps its result;
//   - the statistics the player shows.
// RIFE is not handled by this engine: a profile that asks for it is upscaled without
// interpolation, and the statistics file says so.
#include "aji_vulkan.h"
#include "aji_conf.h"
#include "ajm.h"
#include "engine.h"
#include "mlpatch.h"
#include "tiles.h"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <fstream>
#include <mutex>

#if defined(AJI_ORT_STATIC)
// Linked into a test program: the header's plain declarations apply.
#define AJI_ORT_EXPORT extern "C"
#elif defined(_WIN32)
#define AJI_ORT_EXPORT extern "C" __declspec(dllexport)
#else
#define AJI_ORT_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace {
using namespace aji;
thread_local std::string create_error;

double now_ms()
{
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// Engine settings of the bank's [global] section; the engines of the other platforms ignore them.
struct Settings {
    std::string reuse = "frame";   // off, frame (a whole unchanged frame), tiles (each unchanged tile)
    double threshold = 0.40;       // largest mean difference of a 32x32 block still "unchanged", in 8-bit levels
    std::string tiles = "auto";    // auto, 1, 2x2...
    int overlap = -1;              // pixels a tile sees past its edges; -1 = what the model reads
};

Settings read_settings(const std::string &conf)
{
    Settings s;
    std::ifstream file(conf);
    std::string line, section;
    auto trim = [](std::string v) {
        const size_t a = v.find_first_not_of(" \t\r"), b = v.find_last_not_of(" \t\r");
        return a == std::string::npos ? std::string() : v.substr(a, b - a + 1);
    };
    auto apply = [&](const std::string &key, const std::string &value) {
        if (value.empty()) return;
        if (key == "engine_reuse") {
            const std::string v = lower(value);
            s.reuse = v == "no" || v == "off" || v == "false" || v == "0" ? "off" : v == "tiles" || v == "areas" ? "tiles" : "frame";
        } else if (key == "engine_reuse_threshold") s.threshold = std::min(8.0, std::max(0.0, std::atof(value.c_str())));
        else if (key == "engine_tiles") s.tiles = lower(value);
        else if (key == "engine_overlap") s.overlap = std::atoi(value.c_str());
    };
    while (std::getline(file, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#' || line[0] == ';') continue;
        if (line[0] == '[') { section = lower(line); continue; }
        const size_t eq = line.find('=');
        if (section != "[global]" || eq == std::string::npos) continue;
        apply(lower(trim(line.substr(0, eq))), trim(line.substr(eq + 1)));
    }
    // Tests and trials.
    auto env = [&](const char *name, const char *key) { if (const char *v = std::getenv(name); v && *v) apply(key, v); };
    env("AJI_REUSE", "engine_reuse");
    env("AJI_REUSE_THRESHOLD", "engine_reuse_threshold");
    env("AJI_TILES", "engine_tiles");
    env("AJI_OVERLAP", "engine_overlap");
    return s;
}

struct Worker {
    std::unique_ptr<Executor> executor;
    double pace_ms = 0;        // recent time for one tile, 0 = not known yet
    double total_ms = 0;       // tiles after the first one (the first includes compilation)
    uint64_t tiles = 0;
    uint64_t idle = 0;         // frames in a row this device declined every tile
};

struct Step {
    AjiModelConf conf;
    int in_w = 0, in_h = 0;    // what the profile gives the model
    int w = 0, h = 0;          // the same, padded up to the smallest window an executor takes
    int reach = 0;
    TilePlan plan;
    std::vector<Worker> workers;
    std::vector<std::vector<uint8_t>> refs;   // per tile: its window when it was last computed
    std::vector<char> known;
    std::vector<uint8_t> resized, padded, canvas;
    uint64_t computed = 0, reused = 0;
    int last_computed = 0;
};

struct Context {
    std::string conf, models, device, stats, error, provider, backend_label, cache;
    int slot = 0, width = 0, height = 0;
    AjiChainConf chain;
    aji_vk_plan plan{};
    Settings settings;
    bool rife_skipped = false;
    std::vector<Step> steps;
    uint64_t count = 0, full_frames = 0;
    double total_ms = 0, model_ms = 0, last_model_ms = 0, full_ms = 0;
    std::deque<double> recent;
};

// The bank's [global] backend names the engine; AJI_ORT_PROVIDER overrides it (tests).
std::string wanted_provider(const AjiConf &conf)
{
    const char *forced = std::getenv("AJI_ORT_PROVIDER");
    std::string name = lower(forced && *forced ? forced : conf.backend);
    if (name == "coreml-native" || name == "coreml_native") name = "coremlnative";
    if (name == "migraphx" || name == "openvino" || name == "coreml" || name == "cpu" || name == "reference") return name;
#if defined(__APPLE__)
    if (name == "coremlnative" || name == "metal") return name;
#endif
    throw std::runtime_error("This engine handles backend=MIGraphX, OpenVINO, CoreML, CoreMLNative, Metal or CPU, not " + conf.backend);
}

// "GPU+ANE" -> {"GPU", "ANE"}; a plain device gives one entry.
std::vector<std::string> split_devices(const std::string &device)
{
    std::vector<std::string> list;
    size_t at = 0;
    while (true) {
        const size_t plus = device.find('+', at);
        list.push_back(device.substr(at, plus == std::string::npos ? std::string::npos : plus - at));
        if (plus == std::string::npos) break;
        at = plus + 1;
    }
    return list;
}

// Core ML models made from a template: Core ML itself, and the processors the Metal engine
// reaches through Core ML ("GPU+ANE" pairs Metal on the GPU with Core ML on the Neural Engine).
bool uses_template(const std::string &provider, const std::string &device)
{
    const std::string d = lower(device);
    return provider == "coremlnative" || (provider == "metal" && (d == "ane" || d == "npu" || d == "cpu"));
}

std::unique_ptr<Executor> make_executor(const ExecutorRequest &request)
{
    if (request.provider == "reference") return make_reference_executor(request);
#if defined(__APPLE__)
    if (uses_template(request.provider, request.device)) return make_coreml_executor(request);
    if (request.provider == "metal") return make_metal_executor(request);
#endif
    return make_ort_executor(request);
}

void resized_dims(int w, int h, const AjiModelConf &conf, int *ow, int *oh)
{
    double factor = conf.resize_height_before_upscale > 0 ? conf.resize_height_before_upscale / h
        : conf.resize_factor_before_upscale / 100.0;
    *ow = w; *oh = h;
    if (factor != 1.0) {
        *ow = std::max(2, (int)std::lround(w * factor) / 2 * 2);
        *oh = std::max(2, (int)std::lround(h * factor) / 2 * 2);
    }
}

// Bilinear resize of RGB24 (half-pixel centres), as in the NCNN/Vulkan engine.
void resize_rgb24(const uint8_t *src, ptrdiff_t stride, int sw, int sh, uint8_t *dst, int w, int h)
{
    const double sx = (double)sw / w, sy = (double)sh / h;
    // Column positions and weights are the same for every row.
    std::vector<int> x0s((size_t)w), x1s((size_t)w);
    std::vector<float> wxs((size_t)w);
    for (int x = 0; x < w; x++) {
        const double fx = std::min(std::max((x + 0.5) * sx - 0.5, 0.0), (double)sw - 1);
        x0s[(size_t)x] = (int)fx; x1s[(size_t)x] = std::min((int)fx + 1, sw - 1); wxs[(size_t)x] = (float)(fx - (int)fx);
    }
    const int *x0 = x0s.data(), *x1 = x1s.data();
    const float *wx = wxs.data();
    parallel((size_t)h, 32, [=](size_t first, size_t last) {
        for (size_t y = first; y < last; y++) {
            const double fy = std::min(std::max((y + 0.5) * sy - 0.5, 0.0), (double)sh - 1);
            const int y0 = (int)fy, y1 = std::min(y0 + 1, sh - 1);
            const float wy = (float)(fy - y0);
            const uint8_t *top = src + (ptrdiff_t)y0 * stride, *bottom = src + (ptrdiff_t)y1 * stride;
            uint8_t *out = dst + y * (size_t)w * 3;
            for (int x = 0; x < w; x++) {
                const uint8_t *a = top + 3 * x0[x], *b = top + 3 * x1[x], *c = bottom + 3 * x0[x], *d = bottom + 3 * x1[x];
                for (int k = 0; k < 3; k++) {
                    const float up = a[k] * (1 - wx[x]) + b[k] * wx[x], down = c[k] * (1 - wx[x]) + d[k] * wx[x];
                    out[3 * x + k] = (uint8_t)(up * (1 - wy) + down * wy + 0.5f);
                }
            }
        }
    });
}

// The input repeated past its right and bottom edges up to w x h.
void pad_rgb24(const uint8_t *src, ptrdiff_t stride, int sw, int sh, uint8_t *dst, int w, int h)
{
    for (int y = 0; y < h; y++) {
        const uint8_t *row = src + (ptrdiff_t)std::min(y, sh - 1) * stride;
        uint8_t *out = dst + (size_t)y * w * 3;
        std::memcpy(out, row, (size_t)sw * 3);
        for (int x = sw; x < w; x++) std::memcpy(out + 3 * x, row + 3 * (sw - 1), 3);
    }
}

// Where compiled models go. An application bundle is read-only once installed, and the cache
// must survive an update of the application.
std::string cache_dir(const std::string &models)
{
    const char *chosen = std::getenv("AJI_ORT_CACHE");
    const char *home = std::getenv("HOME");
    std::filesystem::path cache = std::filesystem::path(models) / "coreml-cache";
    if (chosen && *chosen) cache = chosen;
    else if (models.find(".app/Contents/") != std::string::npos && home && *home)
        cache = std::filesystem::path(home) / "Library/Caches/AnimeJaNai/coreml";
    return cache.string();
}

// width x height: the source frame.
void load_steps(Context &c, int width, int height)
{
    c.steps.clear();
    c.backend_label.clear();
    const std::vector<std::string> devices = split_devices(c.device);
    int w = width, h = height;
    for (const auto &model : c.chain.models) {
        if (model.name.empty()) continue;
        require(model.frames <= 1, "Temporal AnimeJaNai models are not supported by this engine");
        Step step;
        step.conf = model;
        resized_dims(w, h, model, &w, &h);
        require(w % 2 == 0 && h % 2 == 0, "AnimeJaNai unshuffle requires even dimensions");
        step.in_w = step.w = w; step.in_h = step.h = h;
        bool templated = false;
        for (const auto &device : devices) templated = templated || uses_template(c.provider, device);
        // A template cannot describe a window under 256 pixels a side: small pictures are padded.
        if (templated) { step.w = std::max(w, kCoreMLMinSide); step.h = std::max(h, kCoreMLMinSide); }
        // Core ML through ONNX Runtime returns a scrambled picture when a row of its half-float
        // output is not a multiple of 64 bytes (seen with windows 676 pixels wide): the widths it
        // is given are multiples of 32 pixels, the picture being padded on the right when needed.
        int align = c.provider == "coreml" ? 32 : 2;
        if (const char *forced = std::getenv("AJI_ALIGN"); forced && *forced) align = std::max(2, std::atoi(forced) / 2 * 2);
        step.w = (step.w + align - 1) / align * align;

        // What the model reads around a pixel: from its description when there is one.
        step.reach = 56;
        const std::string description = c.models + "/" + model.name + ".ajm";
        if (std::filesystem::is_regular_file(description)) step.reach = load_ajm(description).reach();
        if (c.settings.overlap >= 0) step.reach = std::min(512, c.settings.overlap) / 2 * 2;

        int nx = 1, ny = 1;
        grid_for(c.settings.tiles.c_str(), (int)devices.size(), c.settings.reuse == "tiles", step.w, step.h, &nx, &ny);
        step.plan = plan_tiles(step.w, step.h, nx, ny, step.reach, align, templated ? kCoreMLMinSide : 0);
        step.refs.assign(step.plan.tiles.size(), {});
        step.known.assign(step.plan.tiles.size(), 0);

        // One executor per device, never more than there are tiles to share.
        const size_t wanted = std::min(devices.size(), step.plan.tiles.size());
        for (size_t i = 0; i < wanted; i++) {
            ExecutorRequest request;
            request.provider = c.provider; request.device = devices[i];
            request.models_dir = c.models; request.model = model.name; request.cache_dir = c.cache;
            request.width = step.plan.width; request.height = step.plan.height;
            Worker worker;
            worker.executor = make_executor(request);
            if (!c.backend_label.empty()) c.backend_label += " + ";
            c.backend_label += worker.executor->label;
            step.workers.push_back(std::move(worker));
        }
        w *= 2; h *= 2; // the supported AnimeJaNai spatial models are 2x
        c.steps.push_back(std::move(step));
    }
}

// A slower device takes a tile only when that still finishes the frame sooner than leaving the
// tile to the others: without this, the frame would wait for the last tile of the slowest one.
bool worth_taking(const Step &step, size_t me, size_t queued)
{
    const double mine = step.workers[me].pace_ms;
    if (mine <= 0) return true;
    // A device that keeps declining would never be timed again: it takes one tile from time to
    // time, in case it got faster (another program left it) or was misjudged.
    if (step.workers[me].idle >= 96) return true;
    double rate = 0, fastest = 0;
    for (size_t i = 0; i < step.workers.size(); i++) {
        const double pace = step.workers[i].pace_ms;
        if (i == me) continue;
        if (pace <= 0) return true;                    // someone has not been timed yet
        rate += 1 / pace;
        fastest = fastest <= 0 ? pace : std::min(fastest, pace);
    }
    if (rate <= 0 || mine <= fastest) return true;     // alone, or the fastest: never declines
    const double others = queued / rate + fastest / 2; // they finish what they are on, then the queue
    return mine < 0.9 * others;
}

Job job_for(const Tile &t, const uint8_t *src, ptrdiff_t stride, uint8_t *dst, ptrdiff_t dst_stride, bool spread)
{
    Job job;
    job.in = src + (ptrdiff_t)t.wy * stride + 3 * t.wx;
    job.in_stride = stride;
    job.out = dst + (ptrdiff_t)(2 * t.y0) * dst_stride + 6 * t.x0;
    job.out_stride = dst_stride;
    job.crop_x = 2 * (t.x0 - t.wx); job.crop_y = 2 * (t.y0 - t.wy);
    job.crop_w = 2 * (t.x1 - t.x0); job.crop_h = 2 * (t.y1 - t.y0);
    job.spread = spread;
    return job;
}

// Computes the tiles of `todo`: every device takes the next one when it is free. Returns the
// time it took.
double run_tiles(Step &step, const std::vector<int> &todo, const uint8_t *src, ptrdiff_t stride, uint8_t *dst, ptrdiff_t dst_stride)
{
    const double start = now_ms();
    std::mutex lock;
    size_t next = 0;
    std::vector<std::string> errors(step.workers.size());
    const bool alone = step.workers.size() == 1;
    auto work = [&](size_t me) {
        Worker &worker = step.workers[me];
        bool took_one = false;
        try {
            while (true) {
                int index;
                {
                    std::lock_guard<std::mutex> guard(lock);
                    if (next >= todo.size() || !worth_taking(step, me, todo.size() - next)) break;
                    index = todo[next++];
                    worker.idle = 0;
                    took_one = true;
                }
                const double began = now_ms();
                worker.executor->run(job_for(step.plan.tiles[(size_t)index], src, stride, dst, dst_stride, alone));
                const double took = now_ms() - began;
                std::lock_guard<std::mutex> guard(lock);
                // The first tile of a device includes the compilation of its model: not a pace.
                if (worker.tiles > 0) {
                    worker.pace_ms = worker.pace_ms <= 0 ? took : 0.7 * worker.pace_ms + 0.3 * took;
                    worker.total_ms += took;
                }
                worker.tiles++;
            }
            if (!took_one) { std::lock_guard<std::mutex> guard(lock); worker.idle++; }
        } catch (const std::exception &e) { errors[me] = e.what(); }
    };
    std::vector<std::thread> threads;
    for (size_t i = 1; i < step.workers.size(); i++) threads.emplace_back(work, i);
    work(0);
    for (auto &t : threads) t.join();
    for (const auto &error : errors) require(error.empty(), error);
    // The fastest device never declines, so the queue is empty here; were the paces ever to tie
    // in a way that leaves tiles, the first device finishes them.
    for (; next < todo.size(); next++) {
        step.workers[0].executor->run(job_for(step.plan.tiles[(size_t)todo[next]], src, stride, dst, dst_stride, true));
        step.workers[0].tiles++;
    }
    return now_ms() - start;
}

// The whole chain, from the source frame's bytes to the output frame's bytes. Returns whether
// every tile of every model was computed (nothing reused).
bool upscale(Context &c, const uint8_t *pixels, ptrdiff_t stride, uint8_t *output, ptrdiff_t output_stride)
{
    const uint8_t *src = pixels;
    ptrdiff_t src_stride = stride;
    int w = c.width, h = c.height;
    bool whole = true;
    const bool reuse = c.settings.reuse != "off";
    for (size_t i = 0; i < c.steps.size(); i++) {
        Step &step = c.steps[i];
        if (step.in_w != w || step.in_h != h) {
            step.resized.resize((size_t)step.in_w * step.in_h * 3);
            resize_rgb24(src, src_stride, w, h, step.resized.data(), step.in_w, step.in_h);
            src = step.resized.data(); src_stride = (ptrdiff_t)step.in_w * 3;
        }
        const bool padded = step.w != step.in_w || step.h != step.in_h;
        if (padded) {
            step.padded.resize((size_t)step.w * step.h * 3);
            pad_rgb24(src, src_stride, step.in_w, step.in_h, step.padded.data(), step.w, step.h);
            src = step.padded.data(); src_stride = (ptrdiff_t)step.w * 3;
        }
        const bool last = i + 1 == c.steps.size();
        const int ow = 2 * step.in_w, oh = 2 * step.in_h;
        if (last) require(ow == c.plan.width && oh == c.plan.height, "Model output dimensions differ from the configured 2x profile");

        // Which tiles changed since they were computed.
        const size_t window_bytes = (size_t)step.plan.width * 3;
        std::vector<int> todo;
        for (size_t k = 0; k < step.plan.tiles.size(); k++) {
            const Tile &t = step.plan.tiles[k];
            const uint8_t *window = src + (ptrdiff_t)t.wy * src_stride + 3 * t.wx;
            if (!reuse || !step.known[k]
                || !window_unchanged(window, src_stride, step.refs[k].data(), step.plan.width, step.plan.height, c.settings.threshold))
                todo.push_back((int)k);
        }
        // "frame": a frame is reused whole or not at all.
        if (c.settings.reuse == "frame" && !todo.empty() && todo.size() < step.plan.tiles.size()) {
            todo.clear();
            for (size_t k = 0; k < step.plan.tiles.size(); k++) todo.push_back((int)k);
        }
        // Straight into the output frame when nothing has to be kept or cropped; otherwise into
        // the step's own picture, which keeps the result of the tiles that are not recomputed.
        const bool direct = last && !reuse && !padded;
        uint8_t *dst = output;
        ptrdiff_t dst_stride = output_stride;
        if (!direct) {
            step.canvas.resize((size_t)2 * step.w * 2 * step.h * 3);
            dst = step.canvas.data(); dst_stride = (ptrdiff_t)2 * step.w * 3;
        }
        if (!todo.empty()) c.last_model_ms += run_tiles(step, todo, src, src_stride, dst, dst_stride);
        if (reuse) {
            for (int k : todo) {
                const Tile &t = step.plan.tiles[(size_t)k];
                auto &ref = step.refs[(size_t)k];
                ref.resize(window_bytes * step.plan.height);
                for (int y = 0; y < step.plan.height; y++)
                    std::memcpy(ref.data() + (size_t)y * window_bytes, src + (ptrdiff_t)(t.wy + y) * src_stride + 3 * t.wx, window_bytes);
                step.known[(size_t)k] = 1;
            }
        }
        step.computed += todo.size();
        step.reused += step.plan.tiles.size() - todo.size();
        step.last_computed = (int)todo.size();
        whole = whole && todo.size() == step.plan.tiles.size();
        if (last && !direct) {
            const uint8_t *from = step.canvas.data();
            parallel((size_t)oh, 256, [=](size_t first, size_t end) {
                for (size_t y = first; y < end; y++)
                    std::memcpy(output + (ptrdiff_t)y * output_stride, from + y * (size_t)dst_stride, (size_t)ow * 3);
            });
        }
        // The next model reads this one's result (its top-left part when it was padded).
        src = step.canvas.data(); src_stride = (ptrdiff_t)2 * step.w * 3;
        w = ow; h = oh;
    }
    return whole;
}

void write_stats(const Context &c, double ms)
{
    std::ofstream f(c.stats);
    double recent = 0;
    for (double v : c.recent) recent += v;
    recent = c.recent.empty() ? 0 : recent / c.recent.size();
    f << "Backend: " << c.backend_label << "\nAnimeJaNai models: " << c.steps.size()
      << "\nRIFE: " << (c.rife_skipped ? "requested, not available with this engine" : "off")
      << "\nOutput: " << c.plan.width << "x" << c.plan.height << "\nFrames: " << c.count
      << "\nInference ms: " << ms << "\nAverage inference ms: " << c.total_ms / c.count
      << "\nModel ms: " << c.last_model_ms << "\nAverage model ms: " << c.model_ms / c.count
      << "\nAverage conversion ms: " << (c.total_ms - c.model_ms) / c.count
      // What the player's automatic profile choice reads: the last two seconds, and what a frame
      // costs when nothing can be reused (a pan, a cut).
      << "\nRecent ms: " << recent << "\nFull frame ms: " << (c.full_frames ? c.full_ms / c.full_frames : 0) << "\n";
    for (const auto &step : c.steps) {
        const uint64_t all = step.computed + step.reused;
        f << "Tiles: " << step.plan.nx << "x" << step.plan.ny << " of " << step.plan.width << "x" << step.plan.height
          << ", overlap " << step.reach << " | computed " << step.last_computed << " of " << step.plan.tiles.size()
          << " | reused since start: " << (all ? 100 * step.reused / all : 0) << " % (reuse=" << c.settings.reuse << ")\n";
        f << "Devices:";
        uint64_t tiles = 0;
        for (const auto &w : step.workers) tiles += w.tiles;
        for (const auto &w : step.workers)
            f << " [" << w.executor->label << ": " << (w.tiles > 1 ? w.total_ms / (w.tiles - 1) : 0) << " ms a tile, "
              << (tiles ? 100 * w.tiles / tiles : 0) << " % of the tiles]";
        f << "\n";
        for (const auto &w : step.workers)
            if (!w.executor->note.empty()) f << "Placement: " << w.executor->label << ": " << w.executor->note << "\n";
    }
}
} // namespace

AJI_ORT_EXPORT uint32_t aji_vk_version(void) { return AJI_VK_ABI; }

AJI_ORT_EXPORT aji_vk_context *aji_vk_create(const char *conf, const char *models, const char *rife,
                                             const char *device, const char *stats, int slot)
{
    (void)rife;
    try {
        auto c = std::make_unique<Context>();
        c->conf = conf ? conf : ""; c->models = models ? models : "";
        c->device = device ? device : ""; c->stats = stats ? stats : ""; c->slot = slot;
        return c.release();
    } catch (const std::exception &e) { create_error = e.what(); return nullptr; }
}

AJI_ORT_EXPORT int aji_vk_configure(aji_vk_context *context, int width, int height, double fps, aji_vk_plan *plan)
{
    auto &c = *(Context *)context;
    try {
        require(width > 0 && height > 0 && width <= 16384 && height <= 16384, "Invalid source dimensions");
        require(width % 2 == 0 && height % 2 == 0, "Spatial profiles require even source dimensions");
        c.steps.clear(); c.width = width; c.height = height; c.rife_skipped = false;
        c.count = 0; c.full_frames = 0; c.total_ms = 0; c.model_ms = 0; c.full_ms = 0; c.recent.clear();
        c.plan = {width, height, 1, 1, 0};
        if (c.slot == 0) { *plan = c.plan; return 0; }
        AjiConf conf; std::string error;
        require(aji_conf_load(c.conf.c_str(), &conf, &error), error);
        c.provider = wanted_provider(conf);
        c.settings = read_settings(c.conf);
        c.cache = cache_dir(c.models);
        auto found = conf.slots.find(c.slot);
        require(found != conf.slots.end(), "Requested profile missing");
        bool matched = false;
        for (auto &chain : found->second.chains) {
            double px = (double)width * height;
            if (px >= chain.min_px && px <= chain.max_px && fps >= chain.min_fps && fps <= chain.max_fps) {
                c.chain = chain; matched = true; break;
            }
        }
        if (!matched) { *plan = c.plan; return 0; }
        load_steps(c, width, height);
        require(!c.steps.empty(), "This engine needs at least one upscale model in the profile");
        c.rife_skipped = c.chain.rife && c.chain.rife_factor_num > c.chain.rife_factor_den;
        c.plan = {2 * c.steps.back().in_w, 2 * c.steps.back().in_h, 1, 1, 1};
        *plan = c.plan;
        return 0;
    } catch (const std::exception &e) { c.error = e.what(); return -1; }
}

AJI_ORT_EXPORT int aji_vk_process(aji_vk_context *context, const unsigned char *previous, ptrdiff_t previous_stride,
                                  const unsigned char *current, ptrdiff_t current_stride, double timestep,
                                  unsigned char *output, ptrdiff_t output_stride)
{
    (void)previous; (void)previous_stride;
    auto &c = *(Context *)context;
    try {
        const double start = now_ms();
        require(current && output && timestep >= 0 && timestep <= 1, "Invalid frame arguments");
        c.last_model_ms = 0;
        bool whole = false;
        if (c.plan.active) {
            whole = upscale(c, current, current_stride, output, output_stride);
        } else {
            for (int y = 0; y < c.height; y++)
                std::copy_n(current + (ptrdiff_t)y * current_stride, (size_t)c.width * 3, output + (ptrdiff_t)y * output_stride);
        }
        const double ms = now_ms() - start;
        c.total_ms += ms; ++c.count; c.model_ms += c.last_model_ms;
        if (whole) { c.full_ms += ms; c.full_frames++; }
        c.recent.push_back(ms);
        if (c.recent.size() > 48) c.recent.pop_front();
        if (!c.stats.empty()) write_stats(c, ms);
        return 0;
    } catch (const std::exception &e) { c.error = e.what(); return -1; }
}

AJI_ORT_EXPORT const char *aji_vk_error(aji_vk_context *c) { return c ? ((Context *)c)->error.c_str() : create_error.c_str(); }
AJI_ORT_EXPORT void aji_vk_destroy(aji_vk_context *c) { delete (Context *)c; }
