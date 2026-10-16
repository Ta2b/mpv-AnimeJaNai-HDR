// Independent evaluation client. Compile against the user's Optical Flow SDK.
// No NVIDIA SDK source or binaries are distributed with this client.
#include <algorithm>
#include <chrono>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <dlfcn.h>
#include <cuda.h>
#include <NvOFFRUC.h>

static void cuda_check(CUresult status) {
    if (status != CUDA_SUCCESS) {
        const char *message = nullptr;
        cuGetErrorString(status, &message);
        throw std::runtime_error(message ? message : "CUDA error");
    }
}
static void fruc_check(NvOFFRUC_STATUS status, const char *operation) {
    if (status != NvOFFRUC_SUCCESS)
        throw std::runtime_error(std::string(operation) + ": FRUC status " + std::to_string(status));
}
template<class T> static T symbol(void *library, const char *name) {
    auto fn = reinterpret_cast<T>(dlsym(library, name));
    if (!fn) throw std::runtime_error(std::string("Missing symbol ") + name);
    return fn;
}
struct Session {
    void *library = nullptr;
    CUcontext context = nullptr;
    CUdeviceptr buffers[3]{};
    NvOFFRUCHandle handle = nullptr;
    PtrToFuncNvOFFRUCUnregisterResource unregister = nullptr;
    PtrToFuncNvOFFRUCDestroy destroy = nullptr;
    bool registered = false;
    void close() {
        if (context) cuda_check(cuCtxSetCurrent(context));
        if (registered) {
            NvOFFRUC_UNREGISTER_RESOURCE_PARAM p{};
            p.uiCount = 3;
            for (int i = 0; i < 3; ++i) p.pArrResource[i] = &buffers[i];
            fruc_check(unregister(handle, &p), "unregister");
            registered = false;
        }
        if (handle) { fruc_check(destroy(handle), "destroy"); handle = nullptr; }
        for (auto &buffer : buffers) if (buffer) { cuda_check(cuMemFree(buffer)); buffer = 0; }
        if (context) { cuda_check(cuCtxDestroy(context)); context = nullptr; }
        if (library) { dlclose(library); library = nullptr; }
    }
    ~Session() { try { close(); } catch (const std::exception &e) { std::cerr << "Cleanup: " << e.what() << '\n'; } }
};
static double elapsed(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
}
int main(int argc, char **argv) {
    try {
        if (argc != 7) throw std::runtime_error("Usage: fruc_probe LIB INPUT.rgba WIDTH HEIGHT FPS OUTPUT_PREFIX");
        const int width = std::stoi(argv[3]), height = std::stoi(argv[4]);
        const double fps = std::stod(argv[5]);
        if (width < 32 || height < 32 || fps <= 0) throw std::runtime_error("Invalid dimensions/fps");
        const size_t bytes = size_t(width) * height * 4;
        std::ifstream input(argv[2], std::ios::binary | std::ios::ate);
        if (!input) throw std::runtime_error("Cannot read input");
        const auto length = input.tellg();
        if (length < std::streamoff(bytes * 2) || size_t(length) % bytes)
            throw std::runtime_error("Input must contain at least two complete RGBA frames");
        const size_t frames = size_t(length) / bytes;
        input.seekg(0);
        std::string prefix(argv[6]);
        if (std::ifstream(prefix + ".json")) throw std::runtime_error("Receipt already exists; inspect it instead of repeating");
        std::ofstream output(prefix + ".rgba", std::ios::binary);
        std::ofstream receipt(prefix + ".partial.json");
        if (!output || !receipt) throw std::runtime_error("Cannot open output");
        Session s;
        auto setup_start = std::chrono::steady_clock::now();
        cuda_check(cuInit(0));
        CUdevice device;
        cuda_check(cuDeviceGet(&device, 0));
        cuda_check(cuCtxCreate(&s.context, 0, device));
        size_t free_before = 0, total = 0;
        cuda_check(cuMemGetInfo(&free_before, &total));
        for (auto &buffer : s.buffers) cuda_check(cuMemAlloc(&buffer, bytes));
        s.library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
        if (!s.library) throw std::runtime_error(dlerror());
        auto create = symbol<PtrToFuncNvOFFRUCCreate>(s.library, CreateProcName);
        auto reg = symbol<PtrToFuncNvOFFRUCRegisterResource>(s.library, RegisterResourceProcName);
        auto process = symbol<PtrToFuncNvOFFRUCProcess>(s.library, ProcessProcName);
        s.unregister = symbol<PtrToFuncNvOFFRUCUnregisterResource>(s.library, UnregisterResourceProcName);
        s.destroy = symbol<PtrToFuncNvOFFRUCDestroy>(s.library, DestroyProcName);
        NvOFFRUC_CREATE_PARAM c{};
        c.uiWidth = width; c.uiHeight = height;
        c.eResourceType = CudaResource; c.eSurfaceFormat = ARGBSurface;
        c.eCUDAResourceType = CudaResourceCuDevicePtr;
        fruc_check(create(&c, &s.handle), "create");
        NvOFFRUC_REGISTER_RESOURCE_PARAM r{};
        r.uiCount = 3;
        for (int i = 0; i < 3; ++i) r.pArrResource[i] = &s.buffers[i];
        fruc_check(reg(s.handle, &r), "register"); s.registered = true;
        const double setup_ms = elapsed(setup_start);
        std::vector<unsigned char> host(bytes);
        size_t repetitions = 0;
        receipt << "{\"width\":" << width << ",\"height\":" << height << ",\"fps\":" << fps
                << ",\"format\":\"ARGBSurface (RGBA byte order)\",\"setup_ms\":" << setup_ms
                << ",\"client_allocated_bytes\":" << bytes * 3 << ",\"calls\":[";
        for (size_t i = 0; i < frames; ++i) {
            if (!input.read(reinterpret_cast<char *>(host.data()), bytes)) throw std::runtime_error("Short input");
            const int slot = i % 2;
            auto transfer_start = std::chrono::steady_clock::now();
            cuda_check(cuMemcpyHtoD(s.buffers[slot], host.data(), bytes));
            const double upload_ms = elapsed(transfer_start);
            NvOFFRUC_PROCESS_IN_PARAMS in{};
            NvOFFRUC_PROCESS_OUT_PARAMS out{};
            bool repeated = false;
            in.stFrameDataInput.pFrame = &s.buffers[slot];
            in.stFrameDataInput.nTimeStamp = (i + 1) * 1000.0 / fps;
            in.stFrameDataInput.nCuSurfacePitch = size_t(width) * 4;
            out.stFrameDataOutput.pFrame = &s.buffers[2];
            out.stFrameDataOutput.nTimeStamp = (i + 0.5) * 1000.0 / fps;
            out.stFrameDataOutput.nCuSurfacePitch = size_t(width) * 4;
            out.stFrameDataOutput.bHasFrameRepetitionOccurred = &repeated;
            auto start = std::chrono::steady_clock::now();
            fruc_check(process(s.handle, &in, &out), "process");
            const double call_ms = elapsed(start);
            cuda_check(cuCtxSynchronize());
            const double complete_ms = elapsed(start);
            transfer_start = std::chrono::steady_clock::now();
            cuda_check(cuMemcpyDtoH(host.data(), s.buffers[2], bytes));
            const double download_ms = elapsed(transfer_start);
            if (i) {
                output.write(reinterpret_cast<const char *>(host.data()), bytes);
                if (!output) throw std::runtime_error("Output write failed");
                repetitions += repeated;
            }
            if (i) receipt << ',';
            receipt << "{\"source\":" << i << ",\"prime\":" << (i ? "false" : "true")
                    << ",\"output_timestamp_ms\":" << out.stFrameDataOutput.nTimeStamp
                    << ",\"repeated\":" << (repeated ? "true" : "false")
                    << ",\"call_ms\":" << call_ms << ",\"complete_ms\":" << complete_ms
                    << ",\"upload_ms\":" << upload_ms << ",\"download_ms\":" << download_ms << '}';
            receipt.flush();
        }
        size_t free_after = 0;
        cuda_check(cuMemGetInfo(&free_after, &total));
        // This is a global device observation, not an allocation accounting API.
        const long long device_delta = static_cast<long long>(free_before) - static_cast<long long>(free_after);
        output.flush();
        if (!output) throw std::runtime_error("Output flush failed");
        output.close();
        s.close();
        receipt << "],\"outputs\":" << frames - 1 << ",\"repetitions\":" << repetitions
                << ",\"device_free_delta_bytes\":" << device_delta << ",\"cleanup_success\":true,\"passed\":true}\n";
        if (!receipt) throw std::runtime_error("Receipt write failed");
        receipt.close();
        std::filesystem::rename(prefix + ".partial.json", prefix + ".json");
        std::cout << "FRUC outputs=" << frames - 1 << " repetitions=" << repetitions << " cleanup=success\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
