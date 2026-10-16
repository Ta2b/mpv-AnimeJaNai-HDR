// Native CPU activation, registered only for content-qualified RIFE graphs.
#include "cpu_activations.h"
#include <onnxruntime_cxx_api.h>
#include <limits>
#include <memory>
#include <mutex>
#if ORT_API_VERSION >= 24
namespace aji {
namespace {
OrtStatus *failure(const std::exception &e) { return Ort::GetApi().CreateStatus(ORT_FAIL,e.what()); }
struct Kernel {
    float alpha;
    explicit Kernel(const OrtKernelInfo *info) : alpha(Ort::ConstKernelInfo(info).GetAttribute<float>("alpha")) {}
    OrtStatus *ComputeV2(OrtKernelContext *raw) noexcept {
        try {
            Ort::KernelContext context(raw);
            auto input=context.GetInput(0);
            ONNXTensorElementDataType type; const int64_t *dims=nullptr; size_t rank=0;
            Ort::ThrowOnError(Ort::GetApi().GetTensorElementTypeAndShapeDataReference(input,&type,&dims,&rank));
            if (type!=ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) return Ort::GetApi().CreateStatus(ORT_INVALID_ARGUMENT,"Expected FLOAT input");
            size_t count=1;
            for (size_t k=0;k<rank;++k) {
                if (dims[k]<0 || (dims[k] && count>std::numeric_limits<size_t>::max()/(size_t)dims[k]))
                    return Ort::GetApi().CreateStatus(ORT_INVALID_ARGUMENT,"Invalid tensor dimensions");
                count*=(size_t)dims[k];
            }
            auto output=context.GetOutput(0,dims,rank);
            const float *src=input.GetTensorData<float>(); float *dst=output.GetTensorMutableData<float>();
            // Matches reference Less(x,0), Mul(alpha,x), Where(negative,mul,x).
            // No Conv/activation fusion and no intermediate half conversion.
            for (size_t i=0;i<count;++i) {
                if (src[i]<0.0f) {
                    const float scaled=alpha*src[i];
                    // ORT's reference Mul canonicalizes a nonzero negative
                    // underflow to +0; an input -0 itself takes the other branch.
                    dst[i]=scaled==0.0f && alpha>0.0f ? 0.0f : scaled;
                } else dst[i]=src[i];
            }
            return nullptr;
        } catch (const std::exception &e) { return failure(e); }
    }
};
struct Op : Ort::CustomOpBase<Op,Kernel,true> {
    static OrtStatusPtr InferOutputShape(Ort::ShapeInferContext &context) {
        return context.SetOutputShape(0,context.GetInputShape(0),ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT).release();
    }
    const char *GetName() const { return "AjiLeakyReluF32"; }
    const char *GetExecutionProviderType() const { return "CPUExecutionProvider"; }
    size_t GetInputTypeCount() const { return 1; }
    size_t GetOutputTypeCount() const { return 1; }
    ONNXTensorElementDataType GetInputType(size_t) const { return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT; }
    ONNXTensorElementDataType GetOutputType(size_t) const { return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT; }
    OrtStatus *CreateKernelV2(const OrtApi &,const OrtKernelInfo *info,void **out) const noexcept {
        *out=nullptr;
        try { *out=new Kernel(info);return nullptr; }
        catch (const std::exception &e) { return failure(e); }
    }
};
}
void register_cpu_activations(OrtSessionOptions *options)
{
    static std::once_flag once;
    static std::unique_ptr<Ort::CustomOpDomain> domain;
    static Op op;
    std::call_once(once,[&] {
        domain=std::make_unique<Ort::CustomOpDomain>("aji.cpu");domain->Add(&op);
    });
    Ort::UnownedSessionOptions(options).Add(*domain);
}
} // namespace aji
#else
#include <stdexcept>
namespace aji { void register_cpu_activations(OrtSessionOptions *) { throw std::runtime_error("ORT API24 required for CPU activations"); } }
#endif
