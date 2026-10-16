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
static _Atomic uint64_t capture_index;

// Optional shape/graph evidence for specialization trials; configure-time only.
static void capture_path(char out[4096], const char *folder, const char *kind, uint64_t index, const char *extension)
{
    if (snprintf(out,4096,"%s/%s-%llu.%s",folder,kind,(unsigned long long)index,extension) >= 4096) abort();
}
static OrtSessionOptions *capture_options(const OrtSessionOptions *options, const char *folder, uint64_t index)
{
    OrtSessionOptions *copy = NULL;
    if (real_api->CloneSessionOptions(options,&copy)) abort();
    char path[4096]; capture_path(path,folder,"optimized",index,"onnx");
    if (real_api->SetOptimizedModelFilePath(copy,path)) abort();
    if (getenv("AJI_TEST_ORT_PROFILE_ALL")) {
        capture_path(path,folder,"profile",index,"trace");
        if (real_api->EnableProfiling(copy,path)) abort();
    }
    // The Quality probe creates SPAN then RIFE on each configure. This test
    // hook isolates newly exposed RIFE fusions, without changing production.
    const char *disabled = getenv("AJI_TEST_ORT_RIFE_DISABLE");
    if (disabled && *disabled && index % 2 == 1
        && real_api->AddSessionConfigEntry(copy,"optimization.disable_specified_optimizers",disabled)) abort();
    const char *custom = getenv("AJI_TEST_ORT_OP_LIBRARY");
    if (custom && *custom && index % 2 == 1 && real_api->RegisterCustomOpsLibrary_V2(copy,custom)) abort();
    return copy;
}
static void capture_shapes(OrtSession *session, const char *folder, uint64_t index)
{
    char path[4096]; capture_path(path,folder,"shapes",index,"txt");
    FILE *out = fopen(path,"w"); if (!out) abort();
    size_t count = 0; if (real_api->SessionGetInputCount(session,&count)) abort();
    for (size_t i = 0; i < count; ++i) {
        OrtTypeInfo *info = NULL; const OrtTensorTypeAndShapeInfo *tensor_info = NULL;
        size_t rank = 0; int64_t dims[8];
        if (real_api->SessionGetInputTypeInfo(session,i,&info)
            || real_api->CastTypeInfoToTensorInfo(info,&tensor_info)
            || real_api->GetDimensionsCount(tensor_info,&rank) || rank > 8
            || real_api->GetDimensions(tensor_info,dims,rank)) abort();
        for (size_t k = 0; k < rank; ++k) fprintf(out,"%lld%s",(long long)dims[k],k+1==rank?"\n":" ");
        real_api->ReleaseTypeInfo(info);
    }
    if (fclose(out)) abort();
}
static OrtStatus *ORT_API_CALL create_file(const OrtEnv *env, const ORTCHAR_T *path,
    const OrtSessionOptions *options, OrtSession **out)
{
    const char *folder = getenv("AJI_TEST_ORT_CAPTURE");
    if (!folder || !*folder) return real_api->CreateSession(env,path,options,out);
    const uint64_t index = atomic_fetch_add(&capture_index,1);
    char dest[4096]; capture_path(dest,folder,"input",index,"onnx");
    FILE *in = fopen(path,"rb"), *file = fopen(dest,"wb"); if (!in || !file) abort();
    char bytes[8192]; size_t n;
    while ((n=fread(bytes,1,sizeof(bytes),in)) != 0) if (fwrite(bytes,1,n,file) != n) abort();
    if (ferror(in) || fclose(in) || fclose(file)) abort();
    OrtSessionOptions *copy = capture_options(options,folder,index);
    OrtStatus *s = real_api->CreateSession(env,path,copy,out);
    real_api->ReleaseSessionOptions(copy);
    if (!s) capture_shapes(*out,folder,index);
    return s;
}

static void ORT_API_CALL release_session(OrtSession *session)
{
    if (session && getenv("AJI_TEST_ORT_PROFILE_ALL")) {
        OrtAllocator *allocator=NULL;char *file=NULL;
        if (real_api->GetAllocatorWithDefaultOptions(&allocator)
            || real_api->SessionEndProfiling(session,allocator,&file)) abort();
        allocator->Free(allocator,file);
    }
    real_api->ReleaseSession(session);
}
static OrtStatus *ORT_API_CALL create_array(const OrtEnv *env, const void *bytes, size_t size,
    const OrtSessionOptions *options, OrtSession **out)
{
    if (getenv("AJI_TEST_ORT_ACTIVATION_COMPILE_FAIL")
        && memmem(bytes,size,"AjiLeakyReluF32",strlen("AjiLeakyReluF32")))
        return real_api->CreateStatus(ORT_FAIL,"injected CPU activation compilation failure");
    const char *folder = getenv("AJI_TEST_ORT_CAPTURE");
    if (!folder || !*folder) return real_api->CreateSessionFromArray(env,bytes,size,options,out);
    const uint64_t index = atomic_fetch_add(&capture_index,1);
    char path[4096]; capture_path(path,folder,"input",index,"onnx");
    FILE *file = fopen(path,"wb"); if (!file || fwrite(bytes,1,size,file) != size || fclose(file)) abort();
    OrtSessionOptions *copy = capture_options(options,folder,index);
    OrtStatus *s = real_api->CreateSessionFromArray(env,bytes,size,copy,out);
    real_api->ReleaseSessionOptions(copy);
    if (!s) capture_shapes(*out,folder,index);
    return s;
}

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
    wrapped.CreateSession = create_file;
    wrapped.CreateSessionFromArray = create_array;
    wrapped.ReleaseSession = release_session;
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
