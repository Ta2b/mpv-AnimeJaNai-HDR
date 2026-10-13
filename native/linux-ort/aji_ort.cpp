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
// RIFE is run by the interpolator, with cached endpoints and optional overlap with upscaling.
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
#include <iomanip>
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
    std::string reuse = "frame";   // off, frame (a whole unchanged frame), tiles (each unchanged area)
    Sameness same;                 // when two pictures are the same drawing (tiles.h); engine_reuse_threshold, engine_reuse_peak
    std::string tiles = "auto";    // auto, 1, 2x2...: how a whole new frame is shared between devices
    std::string areas = "auto";    // auto, off, 4x3...: the finer grid of reuse=tiles
    bool boost = false;            // the heavier model for drawings that stay on screen (reuse=frame)
    std::string rife_device = "auto";   // the processor of the interpolation: auto, gpu, npu, cpu
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
        } else if (key == "engine_reuse_threshold") {
            s.same.threshold = std::min(8.0, std::max(0.0, std::atof(value.c_str())));
            // 0.40 was the value of the first versions, written in banks since: it only recognised
            // one held drawing in thirteen on compressed video. It now means the current default.
            if (s.same.threshold > 0.399 && s.same.threshold < 0.401) s.same.threshold = Sameness().threshold;
        } else if (key == "engine_reuse_peak") s.same.peak = std::min(255, std::max(0, std::atoi(value.c_str())));
        else if (key == "engine_tiles") s.tiles = lower(value);
        else if (key == "engine_areas") s.areas = lower(value);
        else if (key == "engine_rife_device") s.rife_device = lower(value);
        else if (key == "engine_boost") { const std::string v = lower(value); s.boost = v == "yes" || v == "true" || v == "1" || v == "on"; }
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
    env("AJI_REUSE_PEAK", "engine_reuse_peak");
    env("AJI_TILES", "engine_tiles");
    env("AJI_AREAS", "engine_areas");
    env("AJI_BOOST", "engine_boost");
    env("AJI_RIFE_DEVICE", "engine_rife_device");
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
    // A frame that is all new is cut by `plan` (one tile, or a few shared between devices).
    // With reuse=tiles, a frame of which a part changed is cut by `areas`, a finer grid with
    // executors of its own size: only the areas that changed are computed. Cutting every frame
    // finely would compute each overlap again on the frames where everything moves.
    TilePlan plan, areas;
    std::vector<Worker> workers, area_workers;
    bool fine = false;                        // `areas` exists and differs from `plan`
    std::vector<std::vector<uint8_t>> refs;   // per tile of the reuse grid: its window when last computed
    std::vector<char> known;
    std::vector<uint8_t> resized, padded, canvas;
    uint64_t computed = 0, reused = 0, by_areas = 0;
    int last_computed = 0, last_total = 0;
    double whole_ms = 0;                      // recent time of a frame computed with `plan`
    uint64_t whole_runs = 0;
    // engine_boost: the heavier model of the same family (Performance -> Balanced), with the
    // same input and output. A drawing that stays on screen for several frames is computed
    // once and reused: when the time it stays covers the heavier model, that one computes it.
    struct Boost {
        std::string model, label;
        TilePlan plan;
        std::vector<Worker> workers;
        double whole_ms = 0;                  // recent time of a frame, 0 until it has been timed
        uint64_t whole_runs = 0;
        double ratio = 2.7;                   // its cost against the profile's model, until timed
    };
    std::unique_ptr<Boost> boost;
    uint64_t drawings = 0, boosted = 0;
    const TilePlan &reuse_plan() const { return fine ? areas : plan; }
};

// A source frame of the pair being interpolated, recognised by its bytes (the player reuses its
// buffers: an address says nothing), with what was derived from it.
struct Endpoint {
    std::vector<uint8_t> source, work, up;   // as given; at the interpolation size; upscaled
    bool valid = false, has_work = false, has_up = false;
    uint64_t used = 0;
};

struct Context {
    std::string conf, models, rife_dir, device, stats, error, provider, backend_label, cache;
    // Interpolation. Before the upscale (the profile's default): the two source frames are
    // interpolated at the size the first model takes, and the result is upscaled like a frame.
    // After: the two upscaled frames are interpolated.
    std::unique_ptr<Interpolator> rife;
    bool rife_before = true;
    int rife_w = 0, rife_h = 0;
    std::string rife_model, rife_note;
    Endpoint ends[2];
    uint64_t tick = 0;
    std::vector<uint8_t> between;
    uint64_t interpolated = 0, held = 0, cuts = 0;
    double rife_ms = 0;
    double rife_wait_ms = 0;
    bool rife_profiled = false;
    int slot = 0, width = 0, height = 0;
    AjiChainConf chain;
    aji_vk_plan plan{};
    Settings settings;
    bool rife_skipped = false;
    // The source frames after the one being computed (aji_vk_upcoming), until that call returns.
    std::vector<const uint8_t *> upcoming;
    std::vector<ptrdiff_t> upcoming_stride;
    double interval_ms = 41.7;     // time between two source frames
    double boost_extra_ms = 0;     // this frame: what the heavier model cost beyond the profile's
    std::string boost_note;        // why engine_boost is not active
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

// The heavier model of the same family when the profile's model has one. Model file names are
// fixed by the model lineup (CLAUDE.md, "ONNX model filenames are load-bearing").
std::string heavier_model(const std::string &name)
{
    const std::string light = "_Performance_SPANF3_b5f48_", heavy = "_Balanced_SPANF3_b8f64_";
    const size_t at = name.find(light);
    return at == std::string::npos ? std::string() : name.substr(0, at) + heavy + name.substr(at + light.size());
}

// width x height: the source frame.
void load_steps(Context &c, int width, int height)
{
    c.steps.clear();
    c.backend_label.clear();
    const std::vector<std::string> devices = split_devices(c.device);
    int w = width, h = height;
    size_t models = 0;
    for (const auto &model : c.chain.models) models += !model.name.empty();
    c.boost_note.clear();
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
        const int min_window = templated ? kCoreMLMinSide : 0;
        grid_for(c.settings.tiles.c_str(), (int)devices.size(), step.w, step.h, &nx, &ny);
        step.plan = plan_tiles(step.w, step.h, nx, ny, step.reach, align, min_window);
        if (c.settings.reuse == "tiles") {
            areas_for(c.settings.areas.c_str(), step.w, step.h, &nx, &ny);
            step.areas = plan_tiles(step.w, step.h, nx, ny, step.reach, align, min_window);
            step.fine = step.areas.tiles.size() > step.plan.tiles.size();
        }
        step.refs.assign(step.reuse_plan().tiles.size(), {});
        step.known.assign(step.reuse_plan().tiles.size(), 0);

        // One executor per device and per window size, never more than there are tiles to share.
        auto executors = [&](const TilePlan &plan, std::vector<Worker> &workers, bool named, const std::string &name) {
            const size_t wanted = std::min(devices.size(), plan.tiles.size());
            for (size_t i = 0; i < wanted; i++) {
                ExecutorRequest request;
                request.provider = c.provider; request.device = devices[i];
                request.models_dir = c.models; request.model = name; request.cache_dir = c.cache;
                request.width = plan.width; request.height = plan.height;
                Worker worker;
                worker.executor = make_executor(request);
                if (named) {
                    if (!c.backend_label.empty()) c.backend_label += " + ";
                    c.backend_label += worker.executor->label;
                }
                workers.push_back(std::move(worker));
            }
        };
        executors(step.plan, step.workers, true, model.name);
        if (step.fine) executors(step.areas, step.area_workers, false, model.name);

        if (c.settings.boost) {
            const std::string heavy = heavier_model(model.name);
            if (c.settings.reuse != "frame") c.boost_note = "needs engine_reuse=frame";
            else if (models != 1) c.boost_note = "needs a profile with one model";
            else if (c.chain.rife && c.chain.rife_factor_num > c.chain.rife_factor_den) c.boost_note = "not with RIFE";
            else if (heavy.empty()) c.boost_note = "the profile's model has no heavier one";
            else try {
                auto boost = std::make_unique<Step::Boost>();
                boost->model = heavy;
                int reach = 56;
                const std::string heavy_description = c.models + "/" + heavy + ".ajm";
                if (std::filesystem::is_regular_file(heavy_description)) {
                    const AjmModel described = load_ajm(heavy_description);
                    reach = described.reach();
                    if (std::filesystem::is_regular_file(description)) {
                        const double light = load_ajm(description).cost();
                        if (light > 0) boost->ratio = described.cost() / light;
                    }
                }
                if (c.settings.overlap >= 0) reach = std::min(512, c.settings.overlap) / 2 * 2;
                grid_for(c.settings.tiles.c_str(), (int)devices.size(), step.w, step.h, &nx, &ny);
                boost->plan = plan_tiles(step.w, step.h, nx, ny, reach, align, min_window);
                executors(boost->plan, boost->workers, false, heavy);
                // Compiled now, on a grey picture: the first drawing it is used for must not wait
                // for a compilation in the middle of playback.
                std::vector<uint8_t> grey((size_t)boost->plan.width * boost->plan.height * 3, 128);
                std::vector<uint8_t> scratch((size_t)boost->plan.width * boost->plan.height * 12);
                for (auto &worker : boost->workers) {
                    Job job;
                    job.in = grey.data(); job.in_stride = (ptrdiff_t)boost->plan.width * 3;
                    job.out = scratch.data(); job.out_stride = (ptrdiff_t)boost->plan.width * 6;
                    job.crop_w = 2 * boost->plan.width; job.crop_h = 2 * boost->plan.height;
                    worker.executor->run(job);
                    worker.tiles = 1;
                    boost->label += (boost->label.empty() ? "" : " + ") + worker.executor->label;
                }
                boost->whole_runs = 1;
                step.boost = std::move(boost);
            } catch (const std::exception &e) { c.boost_note = e.what(); }
        }
        w *= 2; h *= 2; // the supported AnimeJaNai spatial models are 2x
        c.steps.push_back(std::move(step));
    }
}

// A slower device takes a tile only when that still finishes the frame sooner than leaving the
// tile to the others: without this, the frame would wait for the last tile of the slowest one.
bool worth_taking(const std::vector<Worker> &workers, size_t me, size_t queued)
{
    const double mine = workers[me].pace_ms;
    if (mine <= 0) return true;
    // A device that keeps declining would never be timed again: it takes one tile from time to
    // time, in case it got faster (another program left it) or was misjudged.
    if (workers[me].idle >= 96) return true;
    double rate = 0, fastest = 0;
    for (size_t i = 0; i < workers.size(); i++) {
        const double pace = workers[i].pace_ms;
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

// Computes the tiles of `todo` in `plan`: every device takes the next one when it is free.
// Returns the time it took.
double run_tiles(const TilePlan &plan, std::vector<Worker> &workers, const std::vector<int> &todo,
                 const uint8_t *src, ptrdiff_t stride, uint8_t *dst, ptrdiff_t dst_stride)
{
    const double start = now_ms();
    std::mutex lock;
    size_t next = 0;
    std::vector<std::string> errors(workers.size());
    const bool alone = workers.size() == 1;
    auto work = [&](size_t me) {
        Worker &worker = workers[me];
        bool took_one = false;
        try {
            while (true) {
                int index;
                {
                    std::lock_guard<std::mutex> guard(lock);
                    if (next >= todo.size() || !worth_taking(workers, me, todo.size() - next)) break;
                    index = todo[next++];
                    worker.idle = 0;
                    took_one = true;
                }
                const double began = now_ms();
                worker.executor->run(job_for(plan.tiles[(size_t)index], src, stride, dst, dst_stride, alone));
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
    for (size_t i = 1; i < workers.size(); i++) threads.emplace_back(work, i);
    work(0);
    for (auto &t : threads) t.join();
    for (const auto &error : errors) require(error.empty(), error);
    // The fastest device never declines, so the queue is empty here; were the paces ever to tie
    // in a way that leaves tiles, the first device finishes them.
    for (; next < todo.size(); next++) {
        workers[0].executor->run(job_for(plan.tiles[(size_t)todo[next]], src, stride, dst, dst_stride, true));
        workers[0].tiles++;
    }
    return now_ms() - start;
}

// Whether computing `changed` areas takes less time than the whole frame with the main plan:
// from the times measured so far, or from the number of pixels until both have been timed.
bool areas_cheaper(const Step &step, size_t changed)
{
    double rate = 0;
    bool timed = step.whole_ms > 0;
    for (const auto &w : step.area_workers) {
        if (w.pace_ms <= 0) timed = false; else rate += 1 / w.pace_ms;
    }
    if (timed) return changed / rate < 0.85 * step.whole_ms;
    const double areas = (double)changed * step.areas.width * step.areas.height;
    const double whole = (double)step.plan.tiles.size() * step.plan.width * step.plan.height;
    return areas < 0.85 * whole;
}

// The whole chain, from the source frame's bytes to the output frame's bytes. Returns whether
// every tile of every model was computed (nothing reused).
// width x height: the size of `pixels` (the source frame, or a frame already at the size the
// first model takes).
bool upscale(Context &c, const uint8_t *pixels, ptrdiff_t stride, int width, int height, uint8_t *output, ptrdiff_t output_stride)
{
    const uint8_t *src = pixels;
    ptrdiff_t src_stride = stride;
    int w = width, h = height;
    bool whole = true;
    int hold = 0;   // frames this drawing stays on screen, as far as the upcoming frames tell; 0 = not looked at
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

        // Which tiles of the reuse grid changed since they were computed.
        const TilePlan &grid = step.reuse_plan();
        const size_t window_bytes = (size_t)grid.width * 3;
        std::vector<int> todo;
        for (size_t k = 0; k < grid.tiles.size(); k++) {
            const Tile &t = grid.tiles[k];
            const uint8_t *window = src + (ptrdiff_t)t.wy * src_stride + 3 * t.wx;
            if (!reuse || !step.known[k]
                || !window_unchanged(window, src_stride, step.refs[k].data(), grid.width, grid.height, c.settings.same))
                todo.push_back((int)k);
        }
        auto everything = [](const TilePlan &plan) {
            std::vector<int> all(plan.tiles.size());
            for (size_t k = 0; k < all.size(); k++) all[k] = (int)k;
            return all;
        };
        // "frame": a frame is reused whole or not at all.
        if (c.settings.reuse == "frame" && !todo.empty() && todo.size() < grid.tiles.size()) todo = everything(grid);
        // engine_boost: a new drawing is computed with the heavier model when the time it stays
        // on screen covers it. The drawing pays for itself: the frames that follow it are reused.
        bool boosted = false;
        if (step.boost && !todo.empty()) {
            if (hold == 0) {
                hold = 1;
                for (size_t k = 0; k < c.upcoming.size(); k++) {
                    if (!picture_unchanged(c.upcoming[k], c.upcoming_stride[k], pixels, stride, c.width, c.height, c.settings.same)) break;
                    hold++;
                }
            }
            const Step::Boost &boost = *step.boost;
            const double heavy = boost.whole_ms > 0 ? boost.whole_ms : step.whole_ms * boost.ratio;
            boosted = step.whole_ms > 0 && heavy <= 0.8 * hold * c.interval_ms;
            step.drawings++;
        }
        // Areas only when a part of the frame changed and computing them is the shorter way.
        const bool by_areas = step.fine && !todo.empty() && todo.size() < grid.tiles.size() && areas_cheaper(step, todo.size());
        const bool by_plan = !todo.empty() && !by_areas;
        if (step.fine && by_plan) todo = everything(grid);   // the main plan computes all of it
        // Straight into the output frame when nothing has to be kept or cropped; otherwise into
        // the step's own picture, which keeps the result of the tiles that are not recomputed.
        const bool direct = last && !reuse && !padded;
        uint8_t *dst = output;
        ptrdiff_t dst_stride = output_stride;
        if (!direct) {
            step.canvas.resize((size_t)2 * step.w * 2 * step.h * 3);
            dst = step.canvas.data(); dst_stride = (ptrdiff_t)2 * step.w * 3;
        }
        if (by_areas) {
            c.last_model_ms += run_tiles(step.areas, step.area_workers, todo, src, src_stride, dst, dst_stride);
            step.by_areas++;
        } else if (boosted) {
            Step::Boost &boost = *step.boost;
            const double took = run_tiles(boost.plan, boost.workers, everything(boost.plan), src, src_stride, dst, dst_stride);
            c.last_model_ms += took;
            boost.whole_ms = boost.whole_runs++ > 1 ? 0.7 * boost.whole_ms + 0.3 * took : took;
            c.boost_extra_ms += std::max(0.0, took - step.whole_ms);
            step.boosted++;
        } else if (by_plan) {
            const std::vector<int> tiles = step.fine ? everything(step.plan) : todo;
            const double took = run_tiles(step.plan, step.workers, tiles, src, src_stride, dst, dst_stride);
            c.last_model_ms += took;
            // The first frame includes the compilation of the models: not a time to compare with.
            if (tiles.size() == step.plan.tiles.size() && step.whole_runs++ > 0)
                step.whole_ms = step.whole_ms <= 0 ? took : 0.7 * step.whole_ms + 0.3 * took;
        }
        if (reuse) {
            for (int k : todo) {
                const Tile &t = grid.tiles[(size_t)k];
                auto &ref = step.refs[(size_t)k];
                ref.resize(window_bytes * grid.height);
                for (int y = 0; y < grid.height; y++)
                    std::memcpy(ref.data() + (size_t)y * window_bytes, src + (ptrdiff_t)(t.wy + y) * src_stride + 3 * t.wx, window_bytes);
                step.known[(size_t)k] = 1;
            }
        }
        step.computed += todo.size();
        step.reused += grid.tiles.size() - todo.size();
        step.last_computed = (int)todo.size();
        step.last_total = (int)grid.tiles.size();
        whole = whole && todo.size() == grid.tiles.size();
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

// rife_v4.26, rife_v4.22_lite, rife_v4.18_ensemble...: the file of a profile's model code
// (426, 4221, 418), as the other engines of the project name them.
std::string rife_file(int code, bool ensemble)
{
    const std::string digits = std::to_string(code);
    if (digits.size() < 2) return "";
    std::string name = "rife_v" + digits.substr(0, 1) + "." + digits.substr(1, digits.size() == 2 ? 1 : 2);
    if (digits.size() == 4 && digits.back() == '1') name += "_lite";
    return ensemble ? name + "_ensemble" : name;
}

// The interpolator of the profile, when it asks for one and the model is there.
void load_rife(Context &c)
{
    c.rife.reset(); c.rife_note.clear(); c.rife_model.clear();
    for (auto &e : c.ends) e = Endpoint{};
    c.interpolated = c.held = c.cuts = 0; c.rife_ms = c.rife_wait_ms = 0;
    c.rife_profiled = false;
    if (!c.chain.rife || c.chain.rife_factor_num <= c.chain.rife_factor_den) return;
    try {
        require(!c.rife_dir.empty(), "no folder of RIFE models was given");
        require(c.chain.rife_factor_den > 0 && c.chain.rife_factor_num <= 8 * c.chain.rife_factor_den, "interpolation factor above 8");
        InterpolatorRequest request;
        // The native engines of macOS have no interpolator of their own: Core ML through ONNX
        // Runtime runs it, on the processor of engine_rife_device (auto: Core ML chooses).
        request.provider = c.provider == "coremlnative" || c.provider == "metal" ? "coreml" : c.provider;
        if (request.provider == "reference") request.provider = "cpu";
        const std::vector<std::string> devices = split_devices(c.device);
        request.device = c.settings.rife_device != "auto" ? c.settings.rife_device
            : request.provider == "coreml" ? "ALL" : devices.empty() ? "" : devices[0];
        request.models_dir = c.rife_dir;
        request.model = rife_file(c.chain.rife_model, c.chain.rife_ensemble);
        require(!request.model.empty(), "unknown RIFE model " + std::to_string(c.chain.rife_model));
        request.cache_dir = c.cache;
        c.rife_before = c.chain.rife_before_upscale;
        c.rife_w = c.rife_before ? c.steps.front().in_w : 2 * c.steps.back().in_w;
        c.rife_h = c.rife_before ? c.steps.front().in_h : 2 * c.steps.back().in_h;
        request.width = c.rife_w; request.height = c.rife_h;
        const char *profile = std::getenv("AJI_RIFE_PROFILE");
        request.profile = profile && *profile && *profile != '0';
        std::unique_ptr<Interpolator> rife = make_ort_interpolator(request);
        // Run once now, on two grey pictures: the model is compiled when the profile opens, and
        // a provider that cannot run it is found out here, not in the middle of playback.
        {
            const std::vector<uint8_t> dark((size_t)c.rife_w * c.rife_h * 3, 96), light((size_t)c.rife_w * c.rife_h * 3, 160);
            std::vector<uint8_t> scratch(dark.size());
            const ptrdiff_t stride = (ptrdiff_t)c.rife_w * 3;
            rife->run(dark.data(), stride, light.data(), stride, 0.5, scratch.data(), stride);
        }
        rife->timing = Interpolator::Timing{}; // exclude the compilation/warm-up run
        c.rife = std::move(rife);
        c.rife_profiled = request.profile;
        c.rife_model = request.model;
    } catch (const std::exception &e) { c.rife_note = e.what(); }
}

bool same_bytes(const std::vector<uint8_t> &kept, const uint8_t *pixels, ptrdiff_t stride, int width, int height)
{
    for (int y = 0; y < height; y++)
        if (std::memcmp(pixels + (ptrdiff_t)y * stride, kept.data() + (size_t)y * width * 3, (size_t)width * 3) != 0) return false;
    return true;
}

// The entry of a source frame: found by its bytes, or taking the place of the one used longest ago.
Endpoint &endpoint(Context &c, const uint8_t *pixels, ptrdiff_t stride)
{
    for (auto &e : c.ends)
        if (e.valid && same_bytes(e.source, pixels, stride, c.width, c.height)) { e.used = ++c.tick; return e; }
    Endpoint &e = c.ends[0].used <= c.ends[1].used ? c.ends[0] : c.ends[1];
    e.source.resize((size_t)c.width * c.height * 3);
    for (int y = 0; y < c.height; y++)
        std::memcpy(e.source.data() + (size_t)y * c.width * 3, pixels + (ptrdiff_t)y * stride, (size_t)c.width * 3);
    e.valid = true; e.has_work = e.has_up = false; e.used = ++c.tick;
    return e;
}

// The frame at the size the interpolation runs at (before the upscale).
const std::vector<uint8_t> &work_of(Context &c, Endpoint &e)
{
    if (c.rife_w == c.width && c.rife_h == c.height) return e.source;
    if (!e.has_work) {
        e.work.resize((size_t)c.rife_w * c.rife_h * 3);
        resize_rgb24(e.source.data(), (ptrdiff_t)c.width * 3, c.width, c.height, e.work.data(), c.rife_w, c.rife_h);
        e.has_work = true;
    }
    return e.work;
}

// The upscaled frame, computed once.
const std::vector<uint8_t> &up_of(Context &c, Endpoint &e, bool *whole)
{
    if (!e.has_up) {
        e.up.resize((size_t)c.plan.width * c.plan.height * 3);
        *whole = upscale(c, e.source.data(), (ptrdiff_t)c.width * 3, c.width, c.height, e.up.data(), (ptrdiff_t)c.plan.width * 3);
        e.has_up = true;
    }
    return e.up;
}

// The share of the full range by which two frames differ on average: the measure of a cut.
double difference(const uint8_t *a, ptrdiff_t a_stride, const uint8_t *b, ptrdiff_t b_stride, int width, int height)
{
    uint64_t sum = 0;
    for (int y = 0; y < height; y++) {
        const uint8_t *x = a + (ptrdiff_t)y * a_stride, *z = b + (ptrdiff_t)y * b_stride;
        uint32_t row = 0;
        for (int k = 0; k < width * 3; k++) row += (uint32_t)std::abs((int)x[k] - (int)z[k]);
        sum += row;
    }
    return (double)sum / (255.0 * width * height * 3);
}

// One output frame of a profile that interpolates. t = 1 (or no previous frame): the frame
// itself. Otherwise the picture between the two: nothing is computed when the two frames are
// the same drawing (it is that drawing) or belong to two scenes (the first one stays).
bool interpolate(Context &c, const uint8_t *previous, ptrdiff_t previous_stride, const uint8_t *current, ptrdiff_t current_stride,
                 double t, uint8_t *output, ptrdiff_t output_stride)
{
    bool whole = false;
    auto give = [&](const std::vector<uint8_t> &picture) {
        const size_t row = (size_t)c.plan.width * 3;
        parallel((size_t)c.plan.height, 256, [&, row](size_t first, size_t end) {
            for (size_t y = first; y < end; y++) std::memcpy(output + (ptrdiff_t)y * output_stride, picture.data() + y * row, row);
        });
    };
    Endpoint &b = endpoint(c, current, current_stride);
    if (!previous || t >= 1) { give(up_of(c, b, &whole)); return whole; }
    Endpoint &a = endpoint(c, previous, previous_stride);
    const bool same = &a == &b
        || picture_unchanged(current, current_stride, previous, previous_stride, c.width, c.height, c.settings.same);
    const bool cut = !same && c.chain.rife_scd_threshold > 0
        && difference(previous, previous_stride, current, current_stride, c.width, c.height) > c.chain.rife_scd_threshold;
    if (same || cut) {
        (same ? c.held : c.cuts)++;
        give(up_of(c, a, &whole));
        return whole;
    }
    const double start = now_ms();
    if (c.rife_before) {
        const std::vector<uint8_t> &wa = work_of(c, a), &wb = work_of(c, b);
        c.between.resize((size_t)c.rife_w * c.rife_h * 3);
        const ptrdiff_t stride = (ptrdiff_t)c.rife_w * 3;
        // The frame that follows this picture has to be upscaled anyway, and neither computation
        // needs the other: it is upscaled while the picture is interpolated. With the two on
        // different processors a source frame then costs the longer of the two plus one
        // upscale, instead of their sum plus one upscale. AJI_RIFE_PARALLEL=0 for a comparison.
        static const bool together = [] { const char *v = std::getenv("AJI_RIFE_PARALLEL"); return !(v && *v == '0'); }();
        std::thread following;
        std::string failure;
        bool following_whole = false;
        if (together && !b.has_up)
            following = std::thread([&] {
                try { up_of(c, b, &following_whole); } catch (const std::exception &e) { failure = e.what(); }
            });
        try {
            c.rife->run(wa.data(), stride, wb.data(), stride, t, c.between.data(), stride);
        } catch (...) { if (following.joinable()) following.join(); throw; }
        if (following.joinable()) {
            const double wait = c.rife_profiled ? now_ms() : 0;
            following.join();
            if (c.rife_profiled) c.rife_wait_ms += now_ms() - wait;
        }
        require(failure.empty(), failure);
        c.rife_ms += now_ms() - start;
        whole = upscale(c, c.between.data(), stride, c.rife_w, c.rife_h, output, output_stride);
    } else {
        // Both upscaled frames first: the second one is the frame that follows this picture.
        const std::vector<uint8_t> &ua = up_of(c, a, &whole), &ub = up_of(c, b, &whole);
        const ptrdiff_t stride = (ptrdiff_t)c.plan.width * 3;
        const double began = now_ms();
        c.rife->run(ua.data(), stride, ub.data(), stride, t, output, output_stride);
        c.rife_ms += now_ms() - began;
    }
    c.interpolated++;
    return whole;
}

void write_stats(const Context &c, double ms)
{
    std::ofstream f(c.stats);
    double recent = 0;
    for (double v : c.recent) recent += v;
    recent = c.recent.empty() ? 0 : recent / c.recent.size();
    // The player compares this with the time between two source frames: with interpolation a
    // source frame is several calls.
    if (c.rife) recent *= (double)c.plan.numerator / c.plan.denominator;
    f << "Backend: " << c.backend_label << "\nAnimeJaNai models: " << c.steps.size()
      << "\nRIFE: ";
    if (c.rife)
        f << c.rife_model << " (" << c.rife->label << "), " << (c.rife_before ? "before" : "after") << " the upscale at "
          << c.rife_w << "x" << c.rife_h << ", x" << (double)c.plan.numerator / c.plan.denominator
          << " | interpolated " << c.interpolated << ", held " << c.held << ", cuts " << c.cuts
          << " | " << (c.interpolated ? c.rife_ms / c.interpolated : 0) << " ms an interpolation";
    else f << (c.rife_skipped ? "requested, not available: " + c.rife_note : std::string("off"));
    f
      << "\nOutput: " << c.plan.width << "x" << c.plan.height << "\nFrames: " << c.count
      << "\nInference ms: " << ms << "\nAverage inference ms: " << c.total_ms / c.count
      << "\nModel ms: " << c.last_model_ms << "\nAverage model ms: " << c.model_ms / c.count
      << "\nAverage conversion ms: " << (c.total_ms - c.model_ms) / c.count
      << "\nModel total ms: " << std::setprecision(12) << c.model_ms << std::setprecision(6)
      // What the player's automatic profile choice reads: the last two seconds, and what a frame
      // costs when nothing can be reused (a pan, a cut).
      << "\nRecent ms: " << recent << "\nFull frame ms: " << (c.full_frames ? c.full_ms / c.full_frames : 0) << "\n";
    if (c.rife) {
        const auto &timing = c.rife->timing;
        f << "RIFE profiling: " << (c.rife_profiled ? "on" : "off")
          << "\nRIFE source preparations: " << timing.source_preparations
          << "\nRIFE source hits: " << timing.source_hits
          << "\nRIFE source promotions: " << timing.source_promotions
          << "\nRIFE timestep updates: " << timing.timestep_updates << "\n";
        if (c.rife_profiled)
            f << "RIFE measured runs: " << timing.runs
              << "\nRIFE preparation total ms: " << std::setprecision(12) << timing.preparation_ms
              << "\nRIFE inference total ms: " << timing.inference_ms
              << "\nRIFE output total ms: " << timing.output_ms
              << "\nRIFE overlap wait total ms: " << c.rife_wait_ms << std::setprecision(6) << "\n";
    }
    for (const auto &step : c.steps) {
        const uint64_t all = step.computed + step.reused;
        f << "Tiles: " << step.plan.nx << "x" << step.plan.ny << " of " << step.plan.width << "x" << step.plan.height
          << ", overlap " << step.reach << " | computed " << step.last_computed << " of " << step.last_total
          << " | reused since start: " << (all ? 100 * step.reused / all : 0) << " % (reuse=" << c.settings.reuse << ")\n";
        // The finer grid of reuse=tiles, and how many frames were computed through it.
        if (step.boost)
            f << "Boost: " << step.boost->model << " on " << (step.drawings ? 100 * step.boosted / step.drawings : 0)
              << " % of the computed frames (" << step.boost->label << ", "
              << (step.boost->whole_ms > 0 ? step.boost->whole_ms : step.whole_ms * step.boost->ratio) << " ms a frame"
              << (step.boost->whole_ms > 0 ? "" : ", estimated") << ")\n";
        if (step.fine)
            f << "Areas: " << step.areas.nx << "x" << step.areas.ny << " of " << step.areas.width << "x" << step.areas.height
              << " | frames computed by areas: " << (c.count ? 100 * step.by_areas / c.count : 0) << " %\n";
        f << "Devices:";
        uint64_t tiles = 0;
        for (const auto &w : step.workers) tiles += w.tiles;
        for (const auto &w : step.workers)
            f << " [" << w.executor->label << ": " << (w.tiles > 1 ? w.total_ms / (w.tiles - 1) : 0) << " ms a tile, "
              << (tiles ? 100 * w.tiles / tiles : 0) << " % of the tiles]";
        f << "\n";
        if (step.fine) {
            f << "Area devices:";
            for (const auto &w : step.area_workers)
                f << " [" << w.executor->label << ": " << (w.tiles > 1 ? w.total_ms / (w.tiles - 1) : 0) << " ms an area]";
            f << "\n";
        }
        for (const auto &w : step.workers)
            if (!w.executor->note.empty()) f << "Placement: " << w.executor->label << ": " << w.executor->note << "\n";
    }
    if (!c.boost_note.empty()) f << "Boost: not active (" << c.boost_note << ")\n";
}
} // namespace

AJI_ORT_EXPORT uint32_t aji_vk_version(void) { return AJI_VK_ABI; }

AJI_ORT_EXPORT aji_vk_context *aji_vk_create(const char *conf, const char *models, const char *rife,
                                             const char *device, const char *stats, int slot)
{
    try {
        auto c = std::make_unique<Context>();
        c->conf = conf ? conf : ""; c->models = models ? models : "";
        c->device = device ? device : ""; c->stats = stats ? stats : ""; c->slot = slot;
        c->rife_dir = rife ? rife : "";
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
        c.rife.reset();
        c.count = 0; c.full_frames = 0; c.total_ms = 0; c.model_ms = 0; c.full_ms = 0; c.recent.clear();
        c.upcoming.clear(); c.upcoming_stride.clear();
        c.interval_ms = fps > 1 ? 1000.0 / fps : 41.7;
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
        load_rife(c);
        c.rife_skipped = !c.rife && c.chain.rife && c.chain.rife_factor_num > c.chain.rife_factor_den;
        c.plan = {2 * c.steps.back().in_w, 2 * c.steps.back().in_h, 1, 1, 1};
        if (c.rife) { c.plan.numerator = c.chain.rife_factor_num; c.plan.denominator = c.chain.rife_factor_den; }
        *plan = c.plan;
        return 0;
    } catch (const std::exception &e) { c.error = e.what(); return -1; }
}

AJI_ORT_EXPORT int aji_vk_process(aji_vk_context *context, const unsigned char *previous, ptrdiff_t previous_stride,
                                  const unsigned char *current, ptrdiff_t current_stride, double timestep,
                                  unsigned char *output, ptrdiff_t output_stride)
{
    auto &c = *(Context *)context;
    try {
        const double start = now_ms();
        require(current && output && timestep >= 0 && timestep <= 1, "Invalid frame arguments");
        c.last_model_ms = 0;
        c.boost_extra_ms = 0;
        bool whole = false;
        if (c.plan.active && c.rife) {
            whole = interpolate(c, previous, previous_stride, current, current_stride, timestep, output, output_stride);
        } else if (c.plan.active) {
            whole = upscale(c, current, current_stride, c.width, c.height, output, output_stride);
        } else {
            for (int y = 0; y < c.height; y++)
                std::copy_n(current + (ptrdiff_t)y * current_stride, (size_t)c.width * 3, output + (ptrdiff_t)y * output_stride);
        }
        const double ms = now_ms() - start;
        c.total_ms += ms; ++c.count; c.model_ms += c.last_model_ms;
        if (whole) { c.full_ms += ms; c.full_frames++; }
        // What the player compares with the time between two frames to tell whether the profile
        // keeps up: the heavier model is extra work taken on spare time, not what the profile needs.
        c.recent.push_back(ms - c.boost_extra_ms);
        if (c.recent.size() > 48) c.recent.pop_front();
        c.upcoming.clear(); c.upcoming_stride.clear();
        if (!c.stats.empty()) write_stats(c, ms);
        return 0;
    } catch (const std::exception &e) { c.error = e.what(); return -1; }
}

// The frames that follow the next aji_vk_process call. Asked for (two of them) only when a
// model can be boosted: knowing them delays the start of a frame by as many decoded frames.
AJI_ORT_EXPORT int aji_vk_upcoming(aji_vk_context *context, const unsigned char *const *frames, const ptrdiff_t *strides, int count)
{
    auto &c = *(Context *)context;
    c.upcoming.clear(); c.upcoming_stride.clear();
    for (int k = 0; k < count && frames && strides; k++) {
        if (!frames[k]) break;
        c.upcoming.push_back(frames[k]); c.upcoming_stride.push_back(strides[k]);
    }
    for (const auto &step : c.steps) if (step.boost) return 2;
    return 0;
}

AJI_ORT_EXPORT const char *aji_vk_error(aji_vk_context *c) { return c ? ((Context *)c)->error.c_str() : create_error.c_str(); }
AJI_ORT_EXPORT void aji_vk_destroy(aji_vk_context *c) { delete (Context *)c; }
