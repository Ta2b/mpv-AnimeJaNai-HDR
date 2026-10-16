// Executor: ONNX Runtime with the provider of the GPU vendor. AMD (MIGraphX, on ROCm), Intel
// (OpenVINO), Apple (Core ML) or the CPU. The original ONNX models are used as they are.
#include "engine.h"
#include "onnx_flow.h"
#include "cpu_activations.h"
#include <onnxruntime_cxx_api.h>
#include <onnxruntime_session_options_config_keys.h>
#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define AJI_F16C 1
#endif
#include <cstdlib>
#include <cstring>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <unordered_map>

namespace aji {
namespace {

bool reuse_ort_bindings(const std::string &provider)
{
    const char *value = std::getenv("AJI_ORT_REUSE_BINDINGS");
    // CPU is qualified here. Other providers keep their existing path until
    // native qualification; an explicit 1 permits a targeted provider trial.
    if (value && *value == '0') return false;
    return provider == "cpu" || (value && *value == '1');
}

// ORT 1.24 can lend a tensor's shape without creating an owned metadata handle
// or a shape vector. The view is used only while that OrtValue remains alive.
struct TensorView {
    ONNXTensorElementDataType type{};
    const int64_t *dims = nullptr;
    size_t rank = 0;
    std::vector<int64_t> owned;
    TensorView(const Ort::Value &value, bool reuse)
    {
#if ORT_API_VERSION >= 24
        if (reuse) {
            Ort::ThrowOnError(Ort::GetApi().GetTensorElementTypeAndShapeDataReference(value, &type, &dims, &rank));
            return;
        }
#endif
        auto info = value.GetTensorTypeAndShapeInfo();
        owned = info.GetShape(); type = info.GetElementType();
        dims = owned.data(); rank = owned.size();
    }
    TensorView(const TensorView &) = delete;
    TensorView &operator=(const TensorView &) = delete;
};

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
    static const std::array<uint16_t, 256> table = [] {
        std::array<float, 256> values;
        std::array<uint16_t, 256> result;
        for (int i = 0; i < 256; i++) values[i] = i * (1.0f / 255.0f);
        floats_to_halves(values.data(), result.data(), values.size());
        return result;
    }();
    return table.data();
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

GraphOptimizationLevel optimization_level(bool precise)
{
    const char *forced=std::getenv(precise ? "AJI_ORT_RIFE_OPT" : "AJI_ORT_SPAN_OPT");
    if (!forced || !*forced) forced=std::getenv("AJI_ORT_OPT");
    if (!forced || !*forced) return GraphOptimizationLevel::ORT_ENABLE_ALL;
    const int n=std::atoi(forced);
    return n<=0 ? GraphOptimizationLevel::ORT_DISABLE_ALL : n==1 ? GraphOptimizationLevel::ORT_ENABLE_BASIC
        : n==2 ? GraphOptimizationLevel::ORT_ENABLE_EXTENDED : GraphOptimizationLevel::ORT_ENABLE_ALL;
}

std::unique_ptr<Ort::Session> fixed_session(const std::filesystem::path &path,
    Ort::SessionOptions &options, const std::string &provider, int channels, int height, int width,
    bool request_motion=false, bool *motion_only=nullptr)
{
    if(motion_only)*motion_only=false;
    const char *flag=std::getenv("AJI_ORT_SPECIALIZE_SHAPES");
    const bool enabled=!(flag && *flag=='0') && (provider=="cpu" || (flag && *flag=='1'));
    bool native_cpu=false,native_motion=false;
#if ORT_API_VERSION >= 24 && defined(__linux__) && defined(__x86_64__)
    const char *activation_flag=std::getenv("AJI_ORT_CPU_ACTIVATIONS");
    const bool qualified=channels==11 && provider=="cpu"
        && optimization_level(true)==GraphOptimizationLevel::ORT_ENABLE_ALL
        && std::strcmp(OrtGetApiBase()->GetVersionString(),"1.24.1")==0;
    native_cpu=qualified && !(activation_flag && *activation_flag=='0');
    const char *motion_flag=std::getenv("AJI_ORT_CPU_MOTION_ONLY");
    native_motion=qualified && request_motion && !(motion_flag && *motion_flag=='0');
#endif
#if ORT_API_VERSION >= 24
    if (enabled || native_cpu || native_motion) {
        std::ifstream in(path,std::ios::binary);
        require(in.good(), "Cannot read ONNX model for input specialization: " + path.string());
        std::vector<char> original((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>()), activated;
        require(!in.bad(), "Incomplete ONNX model for input specialization: " + path.string());
        size_t activation_count=0;
        bool prepared_motion=false;std::string preparation_why;
        bool changed=aji_onnx_prepare_cpu_rife(original,native_cpu,native_motion,&activated,
            &activation_count,&prepared_motion,&preparation_why);
        if (changed && activation_count) {
            try { register_cpu_activations(options); }
            catch (const std::exception &e) {
                std::cerr<<"[aji] CPU activations unavailable; keeping reference graph: "<<e.what()<<'\n';changed=false;
            }
        }
        auto compile=[&](const std::vector<char> &graph,bool transformed) {
            auto attempt=options.Clone();
            std::vector<char> fixed;std::string why;
            const auto result=enabled ? aji_onnx_fixed_rank4_input(graph,{1,channels,height,width},&fixed,&why)
                                      : AjiFixedShape::Unchanged;
            require(result!=AjiFixedShape::Invalid,why);
            if (result==AjiFixedShape::Unsupported)
                std::cerr<<"[aji] ORT dynamic input route: "<<why<<'\n';
            if (result!=AjiFixedShape::Specialized) {
                attempt.AddFreeDimensionOverrideByName("height",height);
                attempt.AddFreeDimensionOverrideByName("width",width);
            }
            if (result==AjiFixedShape::Specialized || transformed) {
                const auto folder=std::filesystem::absolute(path).parent_path().string();
                attempt.AddConfigEntry(kOrtSessionOptionsModelExternalInitializersFileFolderPath,folder.c_str());
                const auto &bytes=result==AjiFixedShape::Specialized ? fixed : graph;
                return std::make_unique<Ort::Session>(environment(),bytes.data(),bytes.size(),attempt);
            }
            return std::make_unique<Ort::Session>(environment(),path.c_str(),attempt);
        };
        if (changed) {
            try {
                auto session=compile(activated,true);
                require(!prepared_motion || session->GetOutputCount()==2,"Unexpected motion-only output signature");
                if(motion_only)*motion_only=prepared_motion;
                if(activation_count)std::cerr<<"[aji] ORT CPU native activations: "<<activation_count<<" qualified RIFE nodes\n";
                if(prepared_motion)std::cerr<<"[aji] ORT CPU RIFE motion-only: flow/mask outputs, no RGB binding\n";
                return session;
            }catch(const std::exception &e) {
                std::cerr<<(prepared_motion ? "[aji] CPU motion compile failed; keeping reference graph: "
                                           : "[aji] CPU activation compile failed; keeping reference graph: ")<<e.what()<<'\n';
            }
        }
        return compile(original,false);
    }
#else
    (void)enabled; (void)native_cpu; (void)native_motion; (void)request_motion;
#endif
    options.AddFreeDimensionOverrideByName("height",height);
    options.AddFreeDimensionOverrideByName("width",width);
    return std::make_unique<Ort::Session>(environment(),path.c_str(),options);
}

// Session options for a provider and a device. `cache_tag` names the folder of the models Core ML
// compiles; `label` receives what the statistics show. `precise` disables the
// permission for reduced-precision GPU accumulation, not a proof of actual
// accumulator precision. RIFE coordinates and sampling need separate qualification.
Ort::SessionOptions provider_options(const std::string &provider, const std::string &device_name,
                                     const std::string &cache_dir, const std::string &cache_tag, std::string *label_out,
                                     bool precise = false)
{
    std::string label;
    Ort::SessionOptions options;
    // ONNX Runtime's optimisation must stay on: it folds the shape arithmetic of the models once
    // the input size is fixed. AJI_ORT_OPT=0..3 (none, basic, extended, all) is for trials.
    options.SetGraphOptimizationLevel(optimization_level(precise));
    // AJI_ORT_LOG=0..4 (verbose .. fatal): ONNX Runtime's own messages, e.g. which nodes a provider takes.
    if (const char *log = std::getenv("AJI_ORT_LOG"); log && *log) options.SetLogSeverityLevel(std::atoi(log));
    if (provider == "migraphx") {
        // AMD GPUs through ROCm. FP16 as shipped; the compiled program is cached by MIGraphX.
        OrtMIGraphXProviderOptions migraphx{};
        migraphx.device_id = device_name.empty() ? 0 : std::atoi(device_name.c_str());
        migraphx.migraphx_fp16_enable = 1;
        options.AppendExecutionProvider_MIGraphX(migraphx);
        label = "ONNX Runtime/MIGraphX";
    } else if (provider == "openvino") {
        // Intel GPUs. device: GPU, GPU.0, GPU.1 or CPU; empty = GPU.
        std::unordered_map<std::string, std::string> openvino{
            {"device_type", device_name.empty() ? "GPU" : device_name}, {"precision", "FP16"}};
        if (lower(openvino["device_type"]) == "cpu") openvino["precision"] = "FP32";
        merge_env(openvino, "AJI_ORT_OPENVINO");
        options.AppendExecutionProvider_OpenVINO_V2(openvino);
        label = "ONNX Runtime/OpenVINO " + openvino["device_type"];
    } else if (provider == "coreml") {
        // Apple Silicon. device: ALL (default), GPU, ANE (Neural Engine) or CPU. ML Program keeps
        // the models in half floats; the compiled model is cached.
        const std::string device = lower(device_name);
        const std::string units = device == "gpu" ? "CPUAndGPU" : device == "ane" || device == "npu" ? "CPUAndNeuralEngine"
            : device == "cpu" ? "CPUOnly" : "ALL";
        // FastPrediction: Core ML spends longer preparing the model to make each prediction
        // faster. Low-precision GPU accumulation is permitted for SPAN and
        // disallowed for RIFE unless explicitly overridden. FP16 model tensors
        // do not prove FP16 accumulator suitability. Compare with:
        // AJI_ORT_COREML="SpecializationStrategy=Default;AllowLowPrecisionAccumulationOnGPU=0".
        std::unordered_map<std::string, std::string> coreml{
            {"ModelFormat", "MLProgram"}, {"MLComputeUnits", units}, {"RequireStaticInputShapes", "1"},
            {"SpecializationStrategy", "FastPrediction"}, {"AllowLowPrecisionAccumulationOnGPU", precise ? "0" : "1"}};
        merge_env(coreml, "AJI_ORT_COREML");
        const bool fast = coreml["SpecializationStrategy"] == "FastPrediction";
        const bool low = coreml["AllowLowPrecisionAccumulationOnGPU"] == "1";
        if (!cache_dir.empty() && !coreml.count("ModelCacheDirectory")) {
            // One folder per input size and compute units: Core ML keys its cache on the model
            // alone, and a model compiled for another size fails at the first frame.
            std::error_code ignored;
            std::filesystem::path cache = std::filesystem::path(cache_dir)
                / (cache_tag + "-" + coreml["MLComputeUnits"] + (fast ? "-fast" : "") + (low ? "-low" : ""));
            std::filesystem::create_directories(cache, ignored);
            if (std::filesystem::is_directory(cache, ignored)) coreml["ModelCacheDirectory"] = cache.string();
        }
        options.AppendExecutionProvider("CoreML", coreml);
        label = "ONNX Runtime/CoreML " + coreml["MLComputeUnits"] + (fast ? " fast" : "") + (low ? " half-sums" : "");
    } else {
        label = "ONNX Runtime/CPU";
    }
    if (label_out) *label_out = label;
    return options;
}

class OrtExecutor : public Executor {
public:
    explicit OrtExecutor(const ExecutorRequest &r) : w_(r.width), h_(r.height)
    {
        reuse_bindings_ = reuse_ort_bindings(r.provider);
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
        Ort::SessionOptions options = provider_options(r.provider, r.device, r.cache_dir,
                                                       std::to_string(w_) + "x" + std::to_string(h_), &label);
        // Every model gets its exact input size: the OpenVINO provider rejects the dynamic-shape
        // graph ("the graph is not acyclic"), and a static shape lets every provider compile once.
        session_ = fixed_session(path, options, r.provider, 3, h_, w_);
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
        if (reuse_bindings_) {
            const size_t count = (size_t)3 * w_ * h_;
            const int64_t shape[4] = {1, 3, h_, w_}, output_shape[4] = {1, 3, 2 * (int64_t)h_, 2 * (int64_t)w_};
            if (half_in_) {
                halves_.resize(count);
                input_tensor_ = Ort::Value::CreateTensor(memory_, halves_.data(), count * sizeof(uint16_t), shape, 4, in);
            } else {
                floats_.resize(count);
                input_tensor_ = Ort::Value::CreateTensor<float>(memory_, floats_.data(), count, shape, 4);
            }
            if (half_out_) {
                output_halves_.resize(4 * count);
                output_tensor_ = Ort::Value::CreateTensor(memory_, output_halves_.data(), 4 * count * sizeof(uint16_t), output_shape, 4, out);
            } else {
                output_floats_.resize(4 * count);
                output_tensor_ = Ort::Value::CreateTensor<float>(memory_, output_floats_.data(), 4 * count, output_shape, 4);
            }
        }
    }

    void run(const Job &job) override
    {
        const int w = w_, h = h_;
        const int64_t shape[4] = {1, 3, h, w};
        const size_t plane = (size_t)w * h, count = 3 * plane;
        Ort::MemoryInfo memory{nullptr};
        if (!reuse_bindings_) memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
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
            if (!reuse_bindings_) input = Ort::Value::CreateTensor(memory, halves_.data(), count * sizeof(uint16_t), shape, 4,
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
            if (!reuse_bindings_) input = Ort::Value::CreateTensor<float>(memory, floats_.data(), count, shape, 4);
        }
        const char *input_names[1] = {input_.c_str()}, *output_names[1] = {output_.c_str()};
        std::vector<Ort::Value> allocated;
        if (reuse_bindings_)
            session_->Run(Ort::RunOptions{nullptr}, input_names, &input_tensor_, 1, output_names, &output_tensor_, 1);
        else allocated = session_->Run(Ort::RunOptions{nullptr}, input_names, &input, 1, output_names, 1);
        const Ort::Value &result = reuse_bindings_ ? output_tensor_ : allocated[0];
        const TensorView view(result, reuse_bindings_);
        require(view.rank == 4 && view.dims[1] == 3 && view.dims[2] == 2 * (int64_t)h && view.dims[3] == 2 * (int64_t)w,
                "Model inference returned an unexpected shape");

        // The wanted region of the doubled window, planar half or single floats, to RGB24.
        const int ow = 2 * w;
        const size_t out_plane = (size_t)ow * 2 * h;
        const bool half = half_out_;
        const uint16_t *hs = half ? result.GetTensorData<uint16_t>() : nullptr;
        const float *fs = half ? nullptr : result.GetTensorData<float>();
        const int cx = job.crop_x, cy = job.crop_y, cw = job.crop_w;
        uint8_t *out = job.out;
        const ptrdiff_t out_stride = job.out_stride;
        const bool reuse = reuse_bindings_;
        auto write = [=](size_t begin, size_t end) {
            thread_local std::vector<float> kept_line;
            std::vector<float> temporary_line;
            auto &line = reuse ? kept_line : temporary_line;
            if (!reuse || half) line.resize((size_t)3 * cw);
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
    int w_, h_;
    std::unique_ptr<Ort::Session> session_;
    std::string input_, output_;
    bool half_in_ = false, half_out_ = false;
    std::vector<uint16_t> halves_;
    std::vector<float> floats_;
    bool reuse_bindings_ = false;
    Ort::MemoryInfo memory_{Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault)};
    std::vector<uint16_t> output_halves_;
    std::vector<float> output_floats_;
    Ort::Value input_tensor_{nullptr}, output_tensor_{nullptr};
};


// RIFE through ONNX Runtime. The model's input is kept from one call to the next: planes 0-2 the
// first picture, 3-5 the second, 6 the instant, 7-10 the sampling grid (x and y from -1 to 1,
// then the steps 2 / (w - 1) and 2 / (h - 1)), all at the padded size.
class OrtInterpolator : public Interpolator {
public:
    explicit OrtInterpolator(const InterpolatorRequest &r) : w_(r.width), h_(r.height), profile_(r.profile)
    {
        reuse_bindings_ = reuse_ort_bindings(r.provider);
        const std::filesystem::path path = std::filesystem::path(r.models_dir) / (r.model + ".onnx");
        require(std::filesystem::is_regular_file(path), "RIFE model not found: " + r.model + ".onnx");
        // The models take sizes that are multiples of 64. The picture is centred in the padded
        // one, on even offsets, as the other engines of the project do.
        pw_ = (w_ + 63) / 64 * 64; ph_ = (h_ + 63) / 64 * 64;
        left_ = ((pw_ - w_) / 2) & ~1; top_ = ((ph_ - h_) / 2) & ~1;
        environment();
        Ort::SessionOptions options = provider_options(r.provider, r.device, r.cache_dir,
            r.model + "-" + std::to_string(pw_) + "x" + std::to_string(ph_), &label, true);
        // Models whose two free dimensions are named (the macOS package names them) get their
        // exact size, which Core ML needs; the others keep their dynamic shape.
        session_ = fixed_session(path, options, r.provider, 11, ph_, pw_, r.motion_only, &motion_only_);
        Ort::AllocatorWithDefaultOptions allocator;
        require(session_->GetInputCount() == 1 && session_->GetOutputCount() >= 1, "Unexpected RIFE model signature: " + r.model);
        input_ = session_->GetInputNameAllocated(0, allocator).get();
        output_ = session_->GetOutputNameAllocated(0, allocator).get();
        auto info = session_->GetInputTypeInfo(0);
        auto tensor = info.GetTensorTypeAndShapeInfo();
        auto shape = tensor.GetShape();
        require(shape.size() == 4 && shape[1] == 11, "This engine handles the RIFE 4.x models with an input of 11 planes: " + r.model);
        const auto in = tensor.GetElementType();
        const auto out = session_->GetOutputTypeInfo(0).GetTensorTypeAndShapeInfo().GetElementType();
        auto supported = [](ONNXTensorElementDataType t) {
            return t == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || t == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16; };
        require(supported(in) && supported(out), "RIFE tensors must be float or half float: " + r.model);
        half_in_ = in == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
        half_out_ = out == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
        // A model with its motion field and mask as outputs 2 and 3 (onnx_flow.h).
        if (motion_only_ || session_->GetOutputCount() >= 3) {
            const size_t offset=motion_only_ ? 0 : 1;
            flow_name_ = session_->GetOutputNameAllocated(offset, allocator).get();
            mask_name_ = session_->GetOutputNameAllocated(offset+1, allocator).get();
        }

        const size_t plane = (size_t)pw_ * ph_;
        floats_.assign(11 * plane, 0.0f);
        for (int y = 0; y < ph_; y++) for (int x = 0; x < pw_; x++) {
            const size_t at = (size_t)y * pw_ + x;
            floats_[7 * plane + at] = 2.0f * x / (pw_ - 1) - 1.0f;
            floats_[8 * plane + at] = 2.0f * y / (ph_ - 1) - 1.0f;
            floats_[9 * plane + at] = 2.0f / (pw_ - 1);
            floats_[10 * plane + at] = 2.0f / (ph_ - 1);
        }
        if (half_in_) {
            halves_.resize(11 * plane);
            floats_to_halves(floats_.data(), halves_.data(), 11 * plane);
            floats_.clear(); floats_.shrink_to_fit();
        }
        for (auto &kept : kept_) kept.assign((size_t)w_ * h_ * 3, 0);
        // The shape and storage stay fixed until this interpolator is destroyed. Reusing the
        // descriptor changes no input bytes and avoids creating it at every instant.
        const int64_t input_shape[4] = {1, 11, ph_, pw_};
        input_tensor_ = half_in_
            ? Ort::Value::CreateTensor(memory_, halves_.data(), halves_.size() * sizeof(uint16_t), input_shape, 4, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16)
            : Ort::Value::CreateTensor<float>(memory_, floats_.data(), floats_.size(), input_shape, 4);
        // A fixed output shape also allows ORT to write into persistent storage.
        // Only allocation changes: type, padded geometry and output conversion stay identical.
        const char *buffer = std::getenv("AJI_RIFE_OUTPUT_BUFFER");
        buffered_output_ = !motion_only_ && !(buffer && *buffer == '0');
        if (buffered_output_) {
            const int64_t output_shape[4] = {1, 3, ph_, pw_};
            if (half_out_) {
                output_halves_.resize(3 * plane);
                output_tensor_ = Ort::Value::CreateTensor(memory_, output_halves_.data(),
                    output_halves_.size() * sizeof(uint16_t), output_shape, 4, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16);
            } else {
                output_floats_.resize(3 * plane);
                output_tensor_ = Ort::Value::CreateTensor<float>(memory_, output_floats_.data(),
                    output_floats_.size(), output_shape, 4);
            }
        }
        if (reuse_bindings_ && has_motion()) {
            for (size_t k = 0; k < motion_tensors_.size(); ++k) {
                const auto type = session_->GetOutputTypeInfo(k + (motion_only_ ? 0 : 1)).GetTensorTypeAndShapeInfo().GetElementType();
                require(supported(type), "RIFE motion tensors must be float or half float: " + r.model);
                const size_t count = (k == 0 ? 4 : 1) * plane;
                const int64_t dims[4] = {1, k == 0 ? 4 : 1, ph_, pw_};
                if (type == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16) {
                    motion_halves_[k].resize(count);
                    motion_tensors_[k] = Ort::Value::CreateTensor(memory_, motion_halves_[k].data(),
                        count * sizeof(uint16_t), dims, 4, type);
                } else {
                    motion_floats_[k].resize(count);
                    motion_tensors_[k] = Ort::Value::CreateTensor<float>(memory_, motion_floats_[k].data(), count, dims, 4);
                }
            }
        }
    }

    bool has_motion() const override { return !flow_name_.empty(); }

    void motion(const uint8_t *a, ptrdiff_t a_stride, const uint8_t *b, ptrdiff_t b_stride, double t,
                std::vector<float> &flow, std::vector<float> &mask) override
    {
        require(has_motion(), "this RIFE model gives no motion field");
        double began = profile_ ? now_ms() : 0;
        prepare(a, a_stride, b, b_stride, t, began);
        const char *input_names[1] = {input_.c_str()}, *output_names[2] = {flow_name_.c_str(), mask_name_.c_str()};
        std::vector<Ort::Value> got;
        if (reuse_bindings_)
            session_->Run(Ort::RunOptions{nullptr}, input_names, &input_tensor_, 1, output_names, motion_tensors_.data(), 2);
        else got = session_->Run(Ort::RunOptions{nullptr}, input_names, &input_tensor_, 1, output_names, 2);
        if (profile_) { const double inferred = now_ms(); timing.inference_ms += inferred - began; began = inferred; }
        const size_t plane = (size_t)pw_ * ph_, area = (size_t)w_ * h_;
        flow.resize(4 * area);
        mask.resize(area);
        auto take = [&](const Ort::Value &v, int planes, float *dst) {
            const TensorView view(v, reuse_bindings_);
            require(view.rank == 4 && view.dims[1] == planes && view.dims[2] == ph_ && view.dims[3] == pw_, "RIFE motion of an unexpected shape");
            const bool half = view.type == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
            const uint16_t *hs = half ? v.GetTensorData<uint16_t>() : nullptr;
            const float *fs = half ? nullptr : v.GetTensorData<float>();
            const size_t rows = (size_t)h_;
            const int w = w_, pw = pw_, left = left_, top = top_;
            parallel((size_t)planes * rows, 64, [=](size_t first, size_t end) {
                for (size_t r = first; r < end; r++) {
                    const size_t k = r / rows, y = r % rows;
                    const size_t from = k * plane + (y + top) * pw + left;
                    float *to = dst + k * area + y * w;
                    if (half) halves_to_floats(hs + from, to, (size_t)w);
                    else std::memcpy(to, fs + from, (size_t)w * sizeof(float));
                }
            });
        };
        take(reuse_bindings_ ? motion_tensors_[0] : got[0], 4, flow.data());
        take(reuse_bindings_ ? motion_tensors_[1] : got[1], 1, mask.data());
        if (profile_) { timing.output_ms += now_ms() - began; ++timing.runs; }
    }

    void run(const uint8_t *a, ptrdiff_t a_stride, const uint8_t *b, ptrdiff_t b_stride, double t,
             uint8_t *out, ptrdiff_t out_stride) override
    {
        require(!motion_only_,"This interpolator exposes only flow/mask, not an RGB output");
        const size_t plane = (size_t)pw_ * ph_;
        double began = profile_ ? now_ms() : 0;
        prepare(a, a_stride, b, b_stride, t, began);
        run_model(out, out_stride, plane, began);
    }

private:
    // The input planes for the pair (a, b) at instant t; what is already there is kept.
    void prepare(const uint8_t *a, ptrdiff_t a_stride, const uint8_t *b, ptrdiff_t b_stride, double t, double &began)
    {
        const size_t plane = (size_t)pw_ * ph_;
        // The second picture of the last pair is the first of this one: its planes move, no
        // conversion.
        bool have_a = have_[0] && same(a, a_stride, kept_[0]);
        if (!have_a && have_[1] && same(a, a_stride, kept_[1])) {
            if (half_in_) std::memcpy(halves_.data(), halves_.data() + 3 * plane, 3 * plane * sizeof(uint16_t));
            else std::memcpy(floats_.data(), floats_.data() + 3 * plane, 3 * plane * sizeof(float));
            kept_[0].swap(kept_[1]);
            have_[0] = true; have_[1] = false;
            have_a = true;
            ++timing.source_promotions;
        }
        if (!have_a) load(0, a, a_stride); else ++timing.source_hits;
        if (!(have_[1] && same(b, b_stride, kept_[1]))) load(1, b, b_stride); else ++timing.source_hits;
        const float instant = (float)t;
        uint32_t instant_bits;
        std::memcpy(&instant_bits, &instant, sizeof(instant_bits));
        if (!have_time_ || instant_bits != time_bits_) {
            if (half_in_) {
                uint16_t value[8]; float values[8] = {instant};
                floats_to_halves(values, value, 8);
                std::fill_n(halves_.data() + 6 * plane, plane, value[0]);
            } else std::fill_n(floats_.data() + 6 * plane, plane, instant);
            have_time_ = true; time_bits_ = instant_bits;
            ++timing.timestep_updates;
        }
        if (profile_) {
            const double ready = now_ms();
            timing.preparation_ms += ready - began; began = ready;
        }
    }

    // The picture for the prepared input, to RGB24.
    void run_model(uint8_t *out, ptrdiff_t out_stride, size_t plane, double began)
    {
        const char *input_names[1] = {input_.c_str()}, *output_names[1] = {output_.c_str()};
        std::vector<Ort::Value> allocated;
        if (buffered_output_)
            session_->Run(Ort::RunOptions{nullptr}, input_names, &input_tensor_, 1, output_names, &output_tensor_, 1);
        else allocated = session_->Run(Ort::RunOptions{nullptr}, input_names, &input_tensor_, 1, output_names, 1);
        if (profile_) {
            const double inferred = now_ms();
            timing.inference_ms += inferred - began; began = inferred;
        }
        const Ort::Value &result = buffered_output_ ? output_tensor_ : allocated[0];
        const TensorView view(result, reuse_bindings_);
        require(view.rank == 4 && view.dims[1] == 3 && view.dims[2] == ph_ && view.dims[3] == pw_, "RIFE returned an unexpected shape");

        // The picture inside the padded result, planar half or single floats, to RGB24.
        const bool half = half_out_;
        const uint16_t *hs = half ? result.GetTensorData<uint16_t>() : nullptr;
        const float *fs = half ? nullptr : result.GetTensorData<float>();
        const int w = w_, pw = pw_, left = left_, top = top_;
        parallel((size_t)h_, 32, [=](size_t begin, size_t end) {
            // FP32 outputs need no scratch line. With FP16, each persistent pixel worker keeps
            // its scratch storage; concurrent callers use distinct thread-local buffers.
            thread_local std::vector<float> line;
            if (half) line.resize((size_t)3 * w);
            for (size_t y = begin; y < end; y++) {
                const size_t source = (y + top) * pw + left;
                const float *r, *g, *bl;
                if (half) {
                    for (int k = 0; k < 3; k++) halves_to_floats(hs + k * plane + source, line.data() + (size_t)k * w, (size_t)w);
                    r = line.data(); g = r + w; bl = g + w;
                } else { r = fs + source; g = r + plane; bl = g + plane; }
                uint8_t *row = out + (ptrdiff_t)y * out_stride;
                for (int x = 0; x < w; x++) {
                    row[3 * x] = (uint8_t)(std::min(std::max(r[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                    row[3 * x + 1] = (uint8_t)(std::min(std::max(g[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                    row[3 * x + 2] = (uint8_t)(std::min(std::max(bl[x], 0.0f), 1.0f) * 255.0f + 0.5f);
                }
            }
        });
        if (profile_) { timing.output_ms += now_ms() - began; ++timing.runs; }
    }

private:
    static double now_ms() {
        return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    bool same(const uint8_t *pixels, ptrdiff_t stride, const std::vector<uint8_t> &kept) const
    {
        for (int y = 0; y < h_; y++)
            if (std::memcmp(pixels + (ptrdiff_t)y * stride, kept.data() + (size_t)y * w_ * 3, (size_t)w_ * 3) != 0) return false;
        return true;
    }

    // Picture `slot` (0 or 1) into its three planes; the padding around it stays black.
    void load(int slot, const uint8_t *pixels, ptrdiff_t stride)
    {
        const size_t plane = (size_t)pw_ * ph_;
        const int w = w_, pw = pw_, left = left_, top = top_;
        uint8_t *kept = kept_[slot].data();
        if (half_in_) {
            uint16_t *r = halves_.data() + (size_t)slot * 3 * plane, *g = r + plane, *b = g + plane;
            const uint16_t *table = byte_halves();
            parallel((size_t)h_, 64, [=](size_t first, size_t last) {
                for (size_t y = first; y < last; y++) {
                    const uint8_t *row = pixels + (ptrdiff_t)y * stride;
                    std::memcpy(kept + y * (size_t)w * 3, row, (size_t)w * 3);
                    const size_t o = (y + top) * pw + left;
                    for (int x = 0; x < w; x++) { r[o + x] = table[row[3 * x]]; g[o + x] = table[row[3 * x + 1]]; b[o + x] = table[row[3 * x + 2]]; }
                }
            });
        } else {
            float *r = floats_.data() + (size_t)slot * 3 * plane, *g = r + plane, *b = g + plane;
            parallel((size_t)h_, 64, [=](size_t first, size_t last) {
                for (size_t y = first; y < last; y++) {
                    const uint8_t *row = pixels + (ptrdiff_t)y * stride;
                    std::memcpy(kept + y * (size_t)w * 3, row, (size_t)w * 3);
                    const size_t o = (y + top) * pw + left;
                    for (int x = 0; x < w; x++) {
                        r[o + x] = row[3 * x] * (1.0f / 255.0f); g[o + x] = row[3 * x + 1] * (1.0f / 255.0f); b[o + x] = row[3 * x + 2] * (1.0f / 255.0f);
                    }
                }
            });
        }
        have_[slot] = true;
        ++timing.source_preparations;
    }

    int w_, h_, pw_ = 0, ph_ = 0, left_ = 0, top_ = 0;
    std::unique_ptr<Ort::Session> session_;
    std::string input_, output_;
    bool half_in_ = false, half_out_ = false;
    std::vector<uint16_t> halves_;
    std::vector<float> floats_;
    std::vector<uint8_t> kept_[2];   // the two pictures as they were given, to recognise them
    bool have_[2] = {false, false};
    bool profile_ = false, have_time_ = false;
    uint32_t time_bits_ = 0;
    Ort::MemoryInfo memory_{Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault)};
    Ort::Value input_tensor_{nullptr};
    bool buffered_output_ = true;
    std::vector<uint16_t> output_halves_;
    std::vector<float> output_floats_;
    Ort::Value output_tensor_{nullptr};
    std::string flow_name_, mask_name_;
    bool reuse_bindings_ = false;
    bool motion_only_ = false;
    std::array<std::vector<uint16_t>, 2> motion_halves_;
    std::array<std::vector<float>, 2> motion_floats_;
    std::array<Ort::Value, 2> motion_tensors_{Ort::Value{nullptr}, Ort::Value{nullptr}};
};
} // namespace

std::unique_ptr<Executor> make_ort_executor(const ExecutorRequest &request)
{
    return std::make_unique<OrtExecutor>(request);
}

std::unique_ptr<Interpolator> make_ort_interpolator(const InterpolatorRequest &request)
{
    return std::make_unique<OrtInterpolator>(request);
}

} // namespace aji
