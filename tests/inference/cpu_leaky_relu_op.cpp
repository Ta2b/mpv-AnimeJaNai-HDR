// Test-only registration wrapper; hidden C++ API state prevents ELF interposition.
#define ORT_API_MANUAL_INIT
#include "../../native/linux-ort/cpu_activations.cpp"
extern "C" __attribute__((visibility("default"))) OrtStatus *RegisterCustomOps(OrtSessionOptions *options,const OrtApiBase *base) noexcept {
    Ort::InitApi(base->GetApi(ORT_API_VERSION));
    try { aji::register_cpu_activations(options);return nullptr; }
    catch (const std::exception &e) { return base->GetApi(ORT_API_VERSION)->CreateStatus(ORT_FAIL,e.what()); }
}
