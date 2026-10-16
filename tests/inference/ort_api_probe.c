// Test-only LD_PRELOAD shim: application C API calls, not ORT internal heap allocations.
#define _GNU_SOURCE
#include <onnxruntime_c_api.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const OrtApiBase *base;
static const OrtApi *real_api;
static OrtApi wrapped;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static _Atomic uint64_t counters[6];

static OrtStatus *ORT_API_CALL cpu_memory(enum OrtAllocatorType type, enum OrtMemType mem, OrtMemoryInfo **out)
{
    OrtStatus *s = real_api->CreateCpuMemoryInfo(type, mem, out);
    if (!s) atomic_fetch_add(&counters[0], 1);
    return s;
}
static OrtStatus *ORT_API_CALL tensor(const OrtMemoryInfo *info, void *data, size_t bytes,
    const int64_t *shape, size_t rank, ONNXTensorElementDataType type, OrtValue **out)
{
    OrtStatus *s = real_api->CreateTensorWithDataAsOrtValue(info, data, bytes, shape, rank, type, out);
    if (!s) atomic_fetch_add(&counters[1], 1);
    return s;
}
static OrtStatus *ORT_API_CALL shape(const OrtValue *value, OrtTensorTypeAndShapeInfo **out)
{
    OrtStatus *s = real_api->GetTensorTypeAndShape(value, out);
    if (!s) atomic_fetch_add(&counters[2], 1);
    return s;
}
static OrtStatus *ORT_API_CALL run(OrtSession *session, const OrtRunOptions *options,
    const char *const *names, const OrtValue *const *inputs, size_t input_count,
    const char *const *output_names, size_t output_count, OrtValue **outputs)
{
    for (size_t i = 0; i < output_count; ++i)
        if (!outputs[i]) atomic_fetch_add(&counters[3], 1);
    atomic_fetch_add(&counters[4], 1);
    return real_api->Run(session, options, names, inputs, input_count, output_names, output_count, outputs);
}
static OrtStatus *ORT_API_CALL borrowed_shape(const OrtValue *value, ONNXTensorElementDataType *type,
    const int64_t **dims, size_t *rank)
{
    OrtStatus *s = real_api->GetTensorElementTypeAndShapeDataReference(value, type, dims, rank);
    if (!s) atomic_fetch_add(&counters[5], 1);
    return s;
}
static const OrtApi *ORT_API_CALL get_api(uint32_t version)
{
    return version == ORT_API_VERSION ? &wrapped : base->GetApi(version);
}
static const char *ORT_API_CALL version_string(void) { return base->GetVersionString(); }
static OrtApiBase probe_base = {get_api, version_string};
static void initialize(void)
{
    const char *path = getenv("AJI_TEST_ORT_LIBRARY");
    void *handle = path ? dlopen(path, RTLD_NOW | RTLD_NOLOAD) : NULL;
    const OrtApiBase *(*entry)(void) = handle ? dlsym(handle, "OrtGetApiBase") : NULL;
    if (!entry || entry == OrtGetApiBase) {
        fputs("ORT probe requires AJI_TEST_ORT_LIBRARY pointing to the loaded runtime\n", stderr);
        abort();
    }
    base = entry(); real_api = base->GetApi(ORT_API_VERSION);
    if (!real_api) abort();
    memcpy(&wrapped, real_api, sizeof(wrapped));
    wrapped.CreateCpuMemoryInfo = cpu_memory;
    wrapped.CreateTensorWithDataAsOrtValue = tensor;
    wrapped.GetTensorTypeAndShape = shape;
    wrapped.Run = run;
    wrapped.GetTensorElementTypeAndShapeDataReference = borrowed_shape;
}
const OrtApiBase *ORT_API_CALL OrtGetApiBase(void)
{
    pthread_once(&once, initialize);
    return &probe_base;
}
void aji_test_ort_counters(uint64_t out[6])
{
    for (size_t i = 0; i < 6; ++i) out[i] = atomic_load(&counters[i]);
}
