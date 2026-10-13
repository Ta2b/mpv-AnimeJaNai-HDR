// AnimeJaNai upscaling through ONNX Runtime, for the GPUs whose vendor provides an execution
// provider: AMD (MIGraphX, on ROCm), Intel (OpenVINO) and Apple (Core ML, macOS). Same host RGB24
// bridge ABI as the NCNN/Vulkan engine (aji_vulkan.h), so the player filter loads either library
// unchanged.
//
// The original ONNX models are used as they are: no conversion step. RIFE is not handled by this
// engine yet: a profile that asks for it is upscaled without interpolation, and the statistics
// file says so.
#include "aji_vulkan.h"
#include "aji_conf.h"
#include <onnxruntime_cxx_api.h>
#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define AJI_F16C 1
#endif
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#if defined(AJI_ORT_STATIC)
// Linked into a test program: the header's plain declarations apply.
#define AJI_ORT_EXPORT extern "C"
#elif defined(_WIN32)
#define AJI_ORT_EXPORT extern "C" __declspec(dllexport)
#else
#define AJI_ORT_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace {
thread_local std::string create_error;

void require(bool value, const std::string &message) { if (!value) throw std::runtime_error(message); }

std::string lower(std::string s) { for (auto &ch : s) ch = (char)std::tolower((unsigned char)ch); return s; }

// Planar float RGB image, values 0..1.
struct Image {
    int w = 0, h = 0;
    std::vector<float> data; // 3 planes of w*h
    Image() = default;
    Image(int width, int height) : w(width), h(height), data((size_t)3 * width * height) {}
    float *plane(int c) { return data.data() + (size_t)c * w * h; }
    const float *plane(int c) const { return data.data() + (size_t)c * w * h; }
};

// Runs body(first, last) over [0, count) on several threads. The host-side work of a frame is
// a few passes over millions of pixels: on one core it costs more than the model itself.
template <typename Body> void parallel(size_t count, size_t grain, Body body)
{
    static const unsigned cores = std::max(1u, std::min(8u, std::thread::hardware_concurrency()));
    const size_t parts = std::min<size_t>(cores, std::max<size_t>(1, count / std::max<size_t>(1, grain)));
    if (parts <= 1) { body((size_t)0, count); return; }
    std::vector<std::thread> workers;
    workers.reserve(parts - 1);
    for (size_t k = 1; k < parts; k++)
        workers.emplace_back([=] { body(count * k / parts, count * (k + 1) / parts); });
    body((size_t)0, count / parts);
    for (auto &w : workers) w.join();
}

Image from_rgb24(const unsigned char *pixels, ptrdiff_t stride, int w, int h)
{
    Image m(w, h);
    float *r = m.plane(0), *g = m.plane(1), *b = m.plane(2);
    parallel((size_t)h, 64, [=](size_t first, size_t last) {
        for (size_t y = first; y < last; y++) {
            const unsigned char *row = pixels + (ptrdiff_t)y * stride;
            const size_t o = y * w;
            for (int x = 0; x < w; x++) {
                r[o + x] = row[3 * x] * (1.0f / 255.0f);
                g[o + x] = row[3 * x + 1] * (1.0f / 255.0f);
                b[o + x] = row[3 * x + 2] * (1.0f / 255.0f);
            }
        }
    });
    return m;
}

void to_rgb24(const Image &m, unsigned char *pixels, ptrdiff_t stride)
{
    const float *r = m.plane(0), *g = m.plane(1), *b = m.plane(2);
    const int w = m.w;
    parallel((size_t)m.h, 64, [=](size_t first, size_t last) {
        for (size_t y = first; y < last; y++) {
            unsigned char *row = pixels + (ptrdiff_t)y * stride;
            const size_t o = y * w;
            for (int x = 0; x < w; x++) {
                row[3 * x] = (unsigned char)(std::min(std::max(r[o + x], 0.0f), 1.0f) * 255.0f + 0.5f);
                row[3 * x + 1] = (unsigned char)(std::min(std::max(g[o + x], 0.0f), 1.0f) * 255.0f + 0.5f);
                row[3 * x + 2] = (unsigned char)(std::min(std::max(b[o + x], 0.0f), 1.0f) * 255.0f + 0.5f);
            }
        }
    });
}

// Bilinear resize (half-pixel centres), as in the NCNN/Vulkan engine.
Image resize(const Image &src, int w, int h)
{
    if (src.w == w && src.h == h) return src;
    Image dst(w, h);
    const double sx = (double)src.w / w, sy = (double)src.h / h;
    // Column positions and weights are the same for every row.
    std::vector<int> x0s(w), x1s(w);
    std::vector<float> wxs(w);
    for (int x = 0; x < w; x++) {
        double fx = std::min(std::max((x + 0.5) * sx - 0.5, 0.0), (double)src.w - 1);
        x0s[x] = (int)fx; x1s[x] = std::min(x0s[x] + 1, src.w - 1); wxs[x] = (float)(fx - x0s[x]);
    }
    const int *x0 = x0s.data(), *x1 = x1s.data();
    const float *wx = wxs.data();
    const int sw = src.w, sh = src.h;
    for (int c = 0; c < 3; c++) {
        const float *s = src.plane(c);
        float *d = dst.plane(c);
        parallel((size_t)h, 64, [=](size_t first, size_t last) {
            for (size_t y = first; y < last; y++) {
                double fy = std::min(std::max((y + 0.5) * sy - 0.5, 0.0), (double)sh - 1);
                int y0 = (int)fy, y1 = std::min(y0 + 1, sh - 1);
                float wy = (float)(fy - y0);
                const float *top = s + (size_t)y0 * sw, *bottom = s + (size_t)y1 * sw;
                float *out = d + y * w;
                for (int x = 0; x < w; x++) {
                    float a = top[x0[x]] * (1 - wx[x]) + top[x1[x]] * wx[x];
                    float b = bottom[x0[x]] * (1 - wx[x]) + bottom[x1[x]] * wx[x];
                    out[x] = a * (1 - wy) + b * wy;
                }
            }
        });
    }
    return dst;
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

#if !defined(AJI_F16C)
// Half-float conversion through the compiler's 16-bit float type (ARM: vectorised by clang).
void floats_to_halves_part(const float *src, uint16_t *dst, size_t count)
{
    _Float16 *out = (_Float16 *)dst;
    for (size_t i = 0; i < count; i++) out[i] = (_Float16)src[i];
}

void halves_to_floats_part(const uint16_t *src, float *dst, size_t count)
{
    const _Float16 *in = (const _Float16 *)src;
    for (size_t i = 0; i < count; i++) dst[i] = (float)in[i];
}
#else
// Half-float conversion, 8 values at a time (F16C).
void floats_to_halves_part(const float *src, uint16_t *dst, size_t count)
{
    size_t i = 0;
    for (; i + 8 <= count; i += 8)
        _mm_storeu_si128((__m128i *)(dst + i), _mm256_cvtps_ph(_mm256_loadu_ps(src + i), _MM_FROUND_TO_NEAREST_INT));
    for (; i < count; i++) {
        float padded[8] = {src[i]};
        uint16_t out[8];
        _mm_storeu_si128((__m128i *)out, _mm256_cvtps_ph(_mm256_loadu_ps(padded), _MM_FROUND_TO_NEAREST_INT));
        dst[i] = out[0];
    }
}

void halves_to_floats_part(const uint16_t *src, float *dst, size_t count)
{
    size_t i = 0;
    for (; i + 8 <= count; i += 8)
        _mm256_storeu_ps(dst + i, _mm256_cvtph_ps(_mm_loadu_si128((const __m128i *)(src + i))));
    for (; i < count; i++) {
        uint16_t padded[8] = {src[i]};
        float out[8];
        _mm256_storeu_ps(out, _mm256_cvtph_ps(_mm_loadu_si128((const __m128i *)padded)));
        dst[i] = out[0];
    }
}
#endif

void floats_to_halves(const float *src, uint16_t *dst, size_t count)
{
    parallel(count, (size_t)1 << 16, [=](size_t first, size_t last) {
        floats_to_halves_part(src + first, dst + first, last - first); });
}

void halves_to_floats(const uint16_t *src, float *dst, size_t count)
{
    parallel(count, (size_t)1 << 16, [=](size_t first, size_t last) {
        halves_to_floats_part(src + first, dst + first, last - first); });
}

// NAME="key=value;key=value": extra or replaced provider options, for trials.
void merge_env(std::unordered_map<std::string, std::string> &options, const char *name)
{
    const char *extra = std::getenv(name);
    if (!extra || !*extra) return;
    const std::string all = extra;
    size_t at = 0;
    while (at < all.size()) {
        size_t end = all.find(';', at);
        if (end == std::string::npos) end = all.size();
        const std::string pair = all.substr(at, end - at);
        const size_t eq = pair.find('=');
        if (eq != std::string::npos && eq > 0) options[pair.substr(0, eq)] = pair.substr(eq + 1);
        at = end + 1;
    }
}

struct Step {
    AjiModelConf conf;
    std::unique_ptr<Ort::Session> session;
    std::string input, output;
    bool half_in = false, half_out = false;
};

struct Context {
    std::string conf, models, device, stats, error, provider, provider_label;
    int slot = 0, width = 0, height = 0;
    AjiChainConf chain;
    aji_vk_plan plan{};
    bool rife_skipped = false;
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "aji_ort"};
    std::vector<Step> steps;
    std::vector<uint16_t> halves;
    uint64_t count = 0;
    double total_ms = 0;
    // Where a frame's time goes: the model (ONNX Runtime, provider included) and the rest
    // (pixel conversions, resize, half floats). Sums since the profile was configured.
    double model_ms = 0, last_model_ms = 0;
};

// The bank's [global] backend names the provider; AJI_ORT_PROVIDER overrides it (tests).
std::string wanted_provider(const AjiConf &conf)
{
    const char *forced = std::getenv("AJI_ORT_PROVIDER");
    std::string name = lower(forced && *forced ? forced : conf.backend);
    if (name == "migraphx" || name == "openvino" || name == "coreml" || name == "cpu") return name;
    throw std::runtime_error("The ONNX Runtime engine handles backend=MIGraphX, OpenVINO, CoreML or CPU, not " + conf.backend);
}

// width x height: the input size of the model the session is for.
Ort::SessionOptions session_options(Context &c, int width, int height)
{
    Ort::SessionOptions options;
    // ONNX Runtime's optimisation must stay on: it folds the shape arithmetic of the models once
    // the input size is fixed. AJI_ORT_OPT=0..3 (none, basic, extended, all) is for trials.
    GraphOptimizationLevel level = GraphOptimizationLevel::ORT_ENABLE_ALL;
    if (const char *forced = std::getenv("AJI_ORT_OPT"); forced && *forced) {
        const int n = std::atoi(forced);
        level = n <= 0 ? GraphOptimizationLevel::ORT_DISABLE_ALL : n == 1 ? GraphOptimizationLevel::ORT_ENABLE_BASIC
              : n == 2 ? GraphOptimizationLevel::ORT_ENABLE_EXTENDED : GraphOptimizationLevel::ORT_ENABLE_ALL;
    }
    options.SetGraphOptimizationLevel(level);
    // AJI_ORT_LOG=0..4 (verbose .. fatal): ONNX Runtime's own messages, e.g. which nodes a provider takes.
    if (const char *log = std::getenv("AJI_ORT_LOG"); log && *log) options.SetLogSeverityLevel(std::atoi(log));
    if (c.provider == "migraphx") {
        // AMD GPUs through ROCm. FP16 as shipped; the compiled program is cached by MIGraphX.
        OrtMIGraphXProviderOptions migraphx{};
        migraphx.device_id = c.device.empty() ? 0 : std::atoi(c.device.c_str());
        migraphx.migraphx_fp16_enable = 1;
        options.AppendExecutionProvider_MIGraphX(migraphx);
        c.provider_label = "MIGraphX";
    } else if (c.provider == "openvino") {
        // Intel GPUs. device: GPU, GPU.0, GPU.1 or CPU; empty = GPU.
        std::unordered_map<std::string, std::string> openvino{
            {"device_type", c.device.empty() ? "GPU" : c.device}, {"precision", "FP16"}};
        if (lower(openvino["device_type"]) == "cpu") openvino["precision"] = "FP32";
        merge_env(openvino, "AJI_ORT_OPENVINO");
        options.AppendExecutionProvider_OpenVINO_V2(openvino);
        c.provider_label = "OpenVINO " + openvino["device_type"];
    } else if (c.provider == "coreml") {
        // Apple Silicon. device: ALL (default), GPU, ANE (Neural Engine) or CPU. ML Program keeps
        // the models in half floats; the compiled model is cached next to the ONNX files.
        const std::string device = lower(c.device);
        const std::string units = device == "gpu" ? "CPUAndGPU" : device == "ane" || device == "npu" ? "CPUAndNeuralEngine"
            : device == "cpu" ? "CPUOnly" : "ALL";
        std::unordered_map<std::string, std::string> coreml{
            {"ModelFormat", "MLProgram"}, {"MLComputeUnits", units}, {"RequireStaticInputShapes", "1"}};
        std::error_code ignored;
        // AJI_ORT_CACHE names another folder: an application bundle is read-only once installed.
        const char *chosen = std::getenv("AJI_ORT_CACHE");
        const char *home = std::getenv("HOME");
        std::filesystem::path cache = std::filesystem::path(c.models) / "coreml-cache";
        if (chosen && *chosen) cache = chosen;
        else if (c.models.find(".app/Contents/") != std::string::npos && home && *home)
            cache = std::filesystem::path(home) / "Library/Caches/AnimeJaNai/coreml";
        // One folder per input size and compute units: Core ML keys its cache on the model
        // alone, and a model compiled for another size fails at the first frame.
        cache /= std::to_string(width) + "x" + std::to_string(height) + "-" + units;
        std::filesystem::create_directories(cache, ignored);
        if (std::filesystem::is_directory(cache, ignored)) coreml["ModelCacheDirectory"] = cache.string();
        merge_env(coreml, "AJI_ORT_COREML");
        options.AppendExecutionProvider("CoreML", coreml);
        c.provider_label = "CoreML " + coreml["MLComputeUnits"];
    } else {
        c.provider_label = "CPU";
    }
    return options;
}

// width x height: the source frame. Every model gets its exact input size: the OpenVINO provider
// rejects the dynamic-shape graph ("the graph is not acyclic"), and a static shape lets every
// provider compile once.
void load_steps(Context &c, int width, int height)
{
    c.steps.clear();
    int w = width, h = height;
    for (const auto &model : c.chain.models) {
        if (model.name.empty()) continue;
        require(model.frames <= 1, "Temporal AnimeJaNai models are not supported by the ONNX Runtime engine");
        std::filesystem::path path = std::filesystem::path(c.models) / (model.name + ".onnx");
        require(std::filesystem::is_regular_file(path), "Model not found: " + model.name + ".onnx");
        // Core ML: the variant whose pixel-unshuffle is one convolution (fuse_unshuffle.py), so
        // that the whole graph stays in Core ML. AJI_ORT_ORIGINAL=1 keeps the original model.
        if (c.provider == "coreml" && !std::getenv("AJI_ORT_ORIGINAL")) {
            std::filesystem::path fused = std::filesystem::path(c.models) / (model.name + ".coreml.onnx");
            if (std::filesystem::is_regular_file(fused)) path = fused;
        }
        Step step;
        step.conf = model;
        resized_dims(w, h, model, &w, &h);
        Ort::SessionOptions options = session_options(c, w, h);
        options.AddFreeDimensionOverrideByName("height", h);
        options.AddFreeDimensionOverrideByName("width", w);
        w *= 2; h *= 2; // the supported AnimeJaNai spatial models are 2x
        step.session = std::make_unique<Ort::Session>(c.env, path.c_str(), options);
        Ort::AllocatorWithDefaultOptions allocator;
        require(step.session->GetInputCount() == 1 && step.session->GetOutputCount() >= 1,
                "Unexpected model signature: " + model.name);
        step.input = step.session->GetInputNameAllocated(0, allocator).get();
        step.output = step.session->GetOutputNameAllocated(0, allocator).get();
        auto kind = [](const Ort::TypeInfo &info) { return info.GetTensorTypeAndShapeInfo().GetElementType(); };
        auto in = kind(step.session->GetInputTypeInfo(0)), out = kind(step.session->GetOutputTypeInfo(0));
        auto supported = [](ONNXTensorElementDataType t) {
            return t == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || t == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16; };
        require(supported(in) && supported(out), "Model tensors must be float or half float: " + model.name);
        step.half_in = in == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
        step.half_out = out == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
        c.steps.push_back(std::move(step));
    }
}

// Runs one model. The input is either a float image or, for the first model of a chain that
// takes half floats at the source size, the frame's bytes directly.
std::vector<Ort::Value> infer(Context &c, Step &step, const Image *in, const unsigned char *pixels,
                              ptrdiff_t stride, int w, int h)
{
    require(w % 2 == 0 && h % 2 == 0, "AnimeJaNai unshuffle requires even dimensions");
    const int64_t shape[4] = {1, 3, h, w};
    const size_t plane = (size_t)w * h, count = 3 * plane;
    Ort::MemoryInfo memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value input{nullptr};
    if (step.half_in) {
        c.halves.resize(count);
        if (pixels) {
            // 256 possible values: converted once, then looked up.
            static uint16_t table[256];
            static bool ready = false;
            if (!ready) {
                float values[256];
                for (int i = 0; i < 256; i++) values[i] = i * (1.0f / 255.0f);
                floats_to_halves_part(values, table, 256);
                ready = true;
            }
            uint16_t *r = c.halves.data(), *g = r + plane, *b = g + plane;
            parallel((size_t)h, 64, [=](size_t first, size_t last) {
                for (size_t y = first; y < last; y++) {
                    const unsigned char *row = pixels + (ptrdiff_t)y * stride;
                    const size_t o = y * w;
                    for (int x = 0; x < w; x++) {
                        r[o + x] = table[row[3 * x]];
                        g[o + x] = table[row[3 * x + 1]];
                        b[o + x] = table[row[3 * x + 2]];
                    }
                }
            });
        } else {
            floats_to_halves(in->data.data(), c.halves.data(), count);
        }
        input = Ort::Value::CreateTensor(memory, c.halves.data(), count * sizeof(uint16_t), shape, 4,
                                         ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16);
    } else {
        input = Ort::Value::CreateTensor<float>(memory, const_cast<float *>(in->data.data()), count, shape, 4);
    }
    const char *input_names[1] = {step.input.c_str()}, *output_names[1] = {step.output.c_str()};
    const auto run_start = std::chrono::steady_clock::now();
    auto outputs = step.session->Run(Ort::RunOptions{nullptr}, input_names, &input, 1, output_names, 1);
    c.last_model_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - run_start).count();
    auto dims = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
    require(dims.size() == 4 && dims[1] == 3 && dims[2] > 0 && dims[3] > 0, "Model inference returned an unexpected shape");
    return outputs;
}

Image to_image(const Ort::Value &value, const Step &step)
{
    auto dims = value.GetTensorTypeAndShapeInfo().GetShape();
    Image out((int)dims[3], (int)dims[2]);
    if (step.half_out) halves_to_floats(value.GetTensorData<uint16_t>(), out.data.data(), out.data.size());
    else std::copy_n(value.GetTensorData<float>(), out.data.size(), out.data.data());
    return out;
}

// Model output (planar, half or single floats) straight to RGB24.
void to_rgb24(const Ort::Value &value, const Step &step, int w, int h, unsigned char *pixels, ptrdiff_t stride)
{
    const size_t plane = (size_t)w * h;
    const bool half = step.half_out;
    const uint16_t *hs = half ? value.GetTensorData<uint16_t>() : nullptr;
    const float *fs = half ? nullptr : value.GetTensorData<float>();
    parallel((size_t)h, 32, [=](size_t first, size_t last) {
        std::vector<float> line((size_t)3 * w);
        for (size_t y = first; y < last; y++) {
            const float *r, *g, *b;
            if (half) {
                for (int k = 0; k < 3; k++)
                    halves_to_floats_part(hs + k * plane + y * w, line.data() + (size_t)k * w, (size_t)w);
                r = line.data(); g = r + w; b = g + w;
            } else {
                r = fs + y * w; g = r + plane; b = g + plane;
            }
            unsigned char *row = pixels + (ptrdiff_t)y * stride;
            for (int x = 0; x < w; x++) {
                row[3 * x] = (unsigned char)(std::min(std::max(r[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                row[3 * x + 1] = (unsigned char)(std::min(std::max(g[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                row[3 * x + 2] = (unsigned char)(std::min(std::max(b[x], 0.0f), 1.0f) * 255.0f + 0.5f);
            }
        }
    });
}

// The whole chain, from the source frame's bytes to the output frame's bytes.
void upscale(Context &c, const unsigned char *pixels, ptrdiff_t stride, unsigned char *output, ptrdiff_t output_stride)
{
    Image m;
    int w = c.width, h = c.height;
    for (size_t i = 0; i < c.steps.size(); i++) {
        Step &step = c.steps[i];
        int mw, mh;
        resized_dims(w, h, step.conf, &mw, &mh);
        std::vector<Ort::Value> outputs;
        if (i == 0 && step.half_in && mw == w && mh == h) {
            outputs = infer(c, step, nullptr, pixels, stride, w, h);
        } else {
            if (i == 0) m = from_rgb24(pixels, stride, w, h);
            Image sized = resize(m, mw, mh);
            outputs = infer(c, step, &sized, nullptr, 0, mw, mh);
        }
        auto dims = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
        w = (int)dims[3]; h = (int)dims[2];
        if (i + 1 == c.steps.size()) {
            require(w == c.plan.width && h == c.plan.height,
                    "Model output dimensions differ from the configured 2x profile");
            to_rgb24(outputs[0], step, w, h, output, output_stride);
        } else {
            m = to_image(outputs[0], step);
        }
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
        c.count = 0; c.total_ms = 0; c.model_ms = 0;
        c.plan = {width, height, 1, 1, 0};
        if (c.slot == 0) { *plan = c.plan; return 0; }
        AjiConf conf; std::string error;
        require(aji_conf_load(c.conf.c_str(), &conf, &error), error);
        c.provider = wanted_provider(conf);
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
        require(!c.steps.empty(), "The ONNX Runtime engine needs at least one upscale model in the profile");
        int w = width, h = height;
        for (auto &step : c.steps) {
            resized_dims(w, h, step.conf, &w, &h);
            w *= 2; h *= 2; // the supported AnimeJaNai spatial models are 2x
        }
        c.rife_skipped = c.chain.rife && c.chain.rife_factor_num > c.chain.rife_factor_den;
        c.plan = {w, h, 1, 1, 1};
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
        auto start = std::chrono::steady_clock::now();
        require(current && output && timestep >= 0 && timestep <= 1, "Invalid frame arguments");
        c.last_model_ms = 0;
        if (c.plan.active) {
            upscale(c, current, current_stride, output, output_stride);
        } else {
            for (int y = 0; y < c.height; y++)
                std::copy_n(current + (ptrdiff_t)y * current_stride, (size_t)c.width * 3, output + (ptrdiff_t)y * output_stride);
        }
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
        c.total_ms += ms; ++c.count; c.model_ms += c.last_model_ms;
        if (!c.stats.empty()) {
            std::ofstream f(c.stats);
            f << "Backend: ONNX Runtime/" << c.provider_label << "\nAnimeJaNai models: " << c.steps.size()
              << "\nRIFE: " << (c.rife_skipped ? "requested, not available with this engine" : "off")
              << "\nOutput: " << c.plan.width << "x" << c.plan.height << "\nFrames: " << c.count
              << "\nInference ms: " << ms << "\nAverage inference ms: " << c.total_ms / c.count
              << "\nModel ms: " << c.last_model_ms << "\nAverage model ms: " << c.model_ms / c.count
              << "\nAverage conversion ms: " << (c.total_ms - c.model_ms) / c.count << "\n";
        }
        return 0;
    } catch (const std::exception &e) { c.error = e.what(); return -1; }
}

AJI_ORT_EXPORT const char *aji_vk_error(aji_vk_context *c) { return c ? ((Context *)c)->error.c_str() : create_error.c_str(); }
AJI_ORT_EXPORT void aji_vk_destroy(aji_vk_context *c) { delete (Context *)c; }
