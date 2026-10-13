// Executor: ONNX Runtime with the provider of the GPU vendor. AMD (MIGraphX, on ROCm), Intel
// (OpenVINO), Apple (Core ML) or the CPU. The original ONNX models are used as they are.
#include "engine.h"
#include <onnxruntime_cxx_api.h>
#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define AJI_F16C 1
#endif
#include <cstdlib>
#include <filesystem>
#include <unordered_map>

namespace aji {
namespace {

#if !defined(AJI_F16C)
// Half-float conversion through the compiler's 16-bit float type (ARM: vectorised by clang).
void floats_to_halves(const float *src, uint16_t *dst, size_t count)
{
    _Float16 *out = (_Float16 *)dst;
    for (size_t i = 0; i < count; i++) out[i] = (_Float16)src[i];
}

void halves_to_floats(const uint16_t *src, float *dst, size_t count)
{
    const _Float16 *in = (const _Float16 *)src;
    for (size_t i = 0; i < count; i++) dst[i] = (float)in[i];
}
#else
// Half-float conversion, 8 values at a time (F16C).
void floats_to_halves(const float *src, uint16_t *dst, size_t count)
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

void halves_to_floats(const uint16_t *src, float *dst, size_t count)
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

// 256 possible byte values as half floats: converted once, then looked up.
const uint16_t *byte_halves()
{
    static uint16_t table[256];
    static bool ready = false;
    if (!ready) {
        float values[256];
        for (int i = 0; i < 256; i++) values[i] = i * (1.0f / 255.0f);
        floats_to_halves(values, table, 256);
        ready = true;
    }
    return table;
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

Ort::Env &environment()
{
    static Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "aji_ort"};
    return env;
}

class OrtExecutor : public Executor {
public:
    explicit OrtExecutor(const ExecutorRequest &r) : w_(r.width), h_(r.height)
    {
        std::filesystem::path path = std::filesystem::path(r.models_dir) / (r.model + ".onnx");
        require(std::filesystem::is_regular_file(path), "Model not found: " + r.model + ".onnx");
        // Core ML: the variant whose pixel-unshuffle is one convolution (fuse_unshuffle.py), so
        // that the whole graph stays in Core ML. AJI_ORT_ORIGINAL=1 keeps the original model.
        if (r.provider == "coreml" && !std::getenv("AJI_ORT_ORIGINAL")) {
            std::filesystem::path fused = std::filesystem::path(r.models_dir) / (r.model + ".coreml.onnx");
            if (std::filesystem::is_regular_file(fused)) path = fused;
        }
        // Before anything else: a provider that logs while its options are read (OpenVINO) needs
        // the environment and its logger to exist.
        environment();
        Ort::SessionOptions options = session_options(r);
        // Every model gets its exact input size: the OpenVINO provider rejects the dynamic-shape
        // graph ("the graph is not acyclic"), and a static shape lets every provider compile once.
        options.AddFreeDimensionOverrideByName("height", h_);
        options.AddFreeDimensionOverrideByName("width", w_);
        session_ = std::make_unique<Ort::Session>(environment(), path.c_str(), options);
        Ort::AllocatorWithDefaultOptions allocator;
        require(session_->GetInputCount() == 1 && session_->GetOutputCount() >= 1, "Unexpected model signature: " + r.model);
        input_ = session_->GetInputNameAllocated(0, allocator).get();
        output_ = session_->GetOutputNameAllocated(0, allocator).get();
        auto kind = [](const Ort::TypeInfo &info) { return info.GetTensorTypeAndShapeInfo().GetElementType(); };
        auto in = kind(session_->GetInputTypeInfo(0)), out = kind(session_->GetOutputTypeInfo(0));
        auto supported = [](ONNXTensorElementDataType t) {
            return t == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || t == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16; };
        require(supported(in) && supported(out), "Model tensors must be float or half float: " + r.model);
        half_in_ = in == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
        half_out_ = out == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
    }

    void run(const Job &job) override
    {
        const int w = w_, h = h_;
        const int64_t shape[4] = {1, 3, h, w};
        const size_t plane = (size_t)w * h, count = 3 * plane;
        Ort::MemoryInfo memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        Ort::Value input{nullptr};
        const uint8_t *pixels = job.in;
        const ptrdiff_t stride = job.in_stride;
        if (half_in_) {
            halves_.resize(count);
            uint16_t *r = halves_.data(), *g = r + plane, *b = g + plane;
            const uint16_t *table = byte_halves();
            auto body = [=](size_t first, size_t last) {
                for (size_t y = first; y < last; y++) {
                    const uint8_t *row = pixels + (ptrdiff_t)y * stride;
                    const size_t o = y * w;
                    for (int x = 0; x < w; x++) {
                        r[o + x] = table[row[3 * x]];
                        g[o + x] = table[row[3 * x + 1]];
                        b[o + x] = table[row[3 * x + 2]];
                    }
                }
            };
            if (job.spread) parallel((size_t)h, 64, body); else body((size_t)0, (size_t)h);
            input = Ort::Value::CreateTensor(memory, halves_.data(), count * sizeof(uint16_t), shape, 4,
                                             ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16);
        } else {
            floats_.resize(count);
            float *r = floats_.data(), *g = r + plane, *b = g + plane;
            auto body = [=](size_t first, size_t last) {
                for (size_t y = first; y < last; y++) {
                    const uint8_t *row = pixels + (ptrdiff_t)y * stride;
                    const size_t o = y * w;
                    for (int x = 0; x < w; x++) {
                        r[o + x] = row[3 * x] * (1.0f / 255.0f);
                        g[o + x] = row[3 * x + 1] * (1.0f / 255.0f);
                        b[o + x] = row[3 * x + 2] * (1.0f / 255.0f);
                    }
                }
            };
            if (job.spread) parallel((size_t)h, 64, body); else body((size_t)0, (size_t)h);
            input = Ort::Value::CreateTensor<float>(memory, floats_.data(), count, shape, 4);
        }
        const char *input_names[1] = {input_.c_str()}, *output_names[1] = {output_.c_str()};
        auto outputs = session_->Run(Ort::RunOptions{nullptr}, input_names, &input, 1, output_names, 1);
        auto dims = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
        require(dims.size() == 4 && dims[1] == 3 && dims[2] == 2 * (int64_t)h && dims[3] == 2 * (int64_t)w,
                "Model inference returned an unexpected shape");

        // The wanted region of the doubled window, planar half or single floats, to RGB24.
        const int ow = 2 * w;
        const size_t out_plane = (size_t)ow * 2 * h;
        const bool half = half_out_;
        const uint16_t *hs = half ? outputs[0].GetTensorData<uint16_t>() : nullptr;
        const float *fs = half ? nullptr : outputs[0].GetTensorData<float>();
        const int cx = job.crop_x, cy = job.crop_y, cw = job.crop_w;
        uint8_t *out = job.out;
        const ptrdiff_t out_stride = job.out_stride;
        auto write = [=](size_t begin, size_t end) {
            std::vector<float> line((size_t)3 * cw);
            for (size_t y = begin; y < end; y++) {
                const size_t source = (y + cy) * ow + cx;
                const float *r, *g, *b;
                if (half) {
                    for (int k = 0; k < 3; k++)
                        halves_to_floats(hs + k * out_plane + source, line.data() + (size_t)k * cw, (size_t)cw);
                    r = line.data(); g = r + cw; b = g + cw;
                } else {
                    r = fs + source; g = r + out_plane; b = g + out_plane;
                }
                uint8_t *row = out + (ptrdiff_t)y * out_stride;
                for (int x = 0; x < cw; x++) {
                    row[3 * x] = (uint8_t)(std::min(std::max(r[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                    row[3 * x + 1] = (uint8_t)(std::min(std::max(g[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                    row[3 * x + 2] = (uint8_t)(std::min(std::max(b[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                }
            }
        };
        if (job.spread) parallel((size_t)job.crop_h, 32, write); else write((size_t)0, (size_t)job.crop_h);
    }

private:
    Ort::SessionOptions session_options(const ExecutorRequest &r)
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
        if (r.provider == "migraphx") {
            // AMD GPUs through ROCm. FP16 as shipped; the compiled program is cached by MIGraphX.
            OrtMIGraphXProviderOptions migraphx{};
            migraphx.device_id = r.device.empty() ? 0 : std::atoi(r.device.c_str());
            migraphx.migraphx_fp16_enable = 1;
            options.AppendExecutionProvider_MIGraphX(migraphx);
            label = "ONNX Runtime/MIGraphX";
        } else if (r.provider == "openvino") {
            // Intel GPUs. device: GPU, GPU.0, GPU.1 or CPU; empty = GPU.
            std::unordered_map<std::string, std::string> openvino{
                {"device_type", r.device.empty() ? "GPU" : r.device}, {"precision", "FP16"}};
            if (lower(openvino["device_type"]) == "cpu") openvino["precision"] = "FP32";
            merge_env(openvino, "AJI_ORT_OPENVINO");
            options.AppendExecutionProvider_OpenVINO_V2(openvino);
            label = "ONNX Runtime/OpenVINO " + openvino["device_type"];
        } else if (r.provider == "coreml") {
            // Apple Silicon. device: ALL (default), GPU, ANE (Neural Engine) or CPU. ML Program keeps
            // the models in half floats; the compiled model is cached.
            const std::string device = lower(r.device);
            const std::string units = device == "gpu" ? "CPUAndGPU" : device == "ane" || device == "npu" ? "CPUAndNeuralEngine"
                : device == "cpu" ? "CPUOnly" : "ALL";
            // FastPrediction: Core ML spends longer preparing the model to make each prediction
            // faster. Low-precision accumulation: half-float sums in the GPU convolutions, the
            // precision the models already use. Both can be turned off for a comparison:
            // AJI_ORT_COREML="SpecializationStrategy=Default;AllowLowPrecisionAccumulationOnGPU=0".
            std::unordered_map<std::string, std::string> coreml{
                {"ModelFormat", "MLProgram"}, {"MLComputeUnits", units}, {"RequireStaticInputShapes", "1"},
                {"SpecializationStrategy", "FastPrediction"}, {"AllowLowPrecisionAccumulationOnGPU", "1"}};
            merge_env(coreml, "AJI_ORT_COREML");
            const bool fast = coreml["SpecializationStrategy"] == "FastPrediction";
            const bool low = coreml["AllowLowPrecisionAccumulationOnGPU"] == "1";
            if (!r.cache_dir.empty() && !coreml.count("ModelCacheDirectory")) {
                // One folder per input size and compute units: Core ML keys its cache on the model
                // alone, and a model compiled for another size fails at the first frame.
                std::error_code ignored;
                std::filesystem::path cache = std::filesystem::path(r.cache_dir)
                    / (std::to_string(w_) + "x" + std::to_string(h_) + "-" + coreml["MLComputeUnits"] + (fast ? "-fast" : "") + (low ? "-low" : ""));
                std::filesystem::create_directories(cache, ignored);
                if (std::filesystem::is_directory(cache, ignored)) coreml["ModelCacheDirectory"] = cache.string();
            }
            options.AppendExecutionProvider("CoreML", coreml);
            label = "ONNX Runtime/CoreML " + coreml["MLComputeUnits"] + (fast ? " fast" : "") + (low ? " half-sums" : "");
        } else {
            label = "ONNX Runtime/CPU";
        }
        return options;
    }

    int w_, h_;
    std::unique_ptr<Ort::Session> session_;
    std::string input_, output_;
    bool half_in_ = false, half_out_ = false;
    std::vector<uint16_t> halves_;
    std::vector<float> floats_;
};

} // namespace

std::unique_ptr<Executor> make_ort_executor(const ExecutorRequest &request)
{
    return std::make_unique<OrtExecutor>(request);
}

} // namespace aji
