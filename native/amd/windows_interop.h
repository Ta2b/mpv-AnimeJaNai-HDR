#pragma once
#ifdef _WIN32
#include "device_model.h"
#include <d3d12.h>
#include <wrl/client.h>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace aji::amd {
class DeviceBuffer {
public:
    DeviceBuffer()=default;
    DeviceBuffer(const DeviceBuffer&)=delete;
    DeviceBuffer(DeviceBuffer &&other) noexcept
        :pointer_(std::exchange(other.pointer_,nullptr)),size_(std::exchange(other.size_,0)) {}
    DeviceBuffer &operator=(DeviceBuffer &&other) noexcept {
        if(this!=&other) {
            if(pointer_) (void)hipFree(pointer_);
            pointer_=std::exchange(other.pointer_,nullptr);size_=std::exchange(other.size_,0);
        }
        return *this;
    }
    ~DeviceBuffer() { if(pointer_) (void)hipFree(pointer_); }
    void reserve(size_t bytes) {
        if(bytes<=size_) return;
        void *next=nullptr;
        const auto status=hipMalloc(&next,bytes);
        if(status!=hipSuccess) throw std::runtime_error(std::string("HIP video buffer: ")+hipGetErrorString(status));
        if(pointer_) (void)hipFree(pointer_);pointer_=next;size_=bytes;
    }
    void *data() const { return pointer_; }
    template<class T> T *as() const { return static_cast<T*>(pointer_); }
private:
    void *pointer_=nullptr;size_t size_=0;
};
inline void check_hip(hipError_t e,const char *operation) {
    if(e!=hipSuccess) throw std::runtime_error(std::string(operation)+": "+hipGetErrorString(e));
}
inline void check_dx(HRESULT e,const char *operation) {
    if(FAILED(e)) throw std::runtime_error(std::string(operation)+": HRESULT "+std::to_string((unsigned long)e));
}
class SharedAllocation {
public:
    SharedAllocation(ID3D12Device *device,ID3D12Resource *resource):resource_(resource) {
        try {
            check_dx(device->CreateSharedHandle(resource,nullptr,GENERIC_ALL,nullptr,&handle_),"D3D12 shared buffer handle");
            auto desc=resource->GetDesc();const auto allocation=device->GetResourceAllocationInfo(0,1,&desc);
            hipExternalMemoryHandleDesc memory{};memory.type=hipExternalMemoryHandleTypeD3D12Resource;
            memory.handle.win32.handle=handle_;memory.size=allocation.SizeInBytes;memory.flags=hipExternalMemoryDedicated;
            check_hip(hipImportExternalMemory(&memory_,&memory),"HIP import D3D12 buffer");
            hipExternalMemoryBufferDesc buffer{};buffer.size=desc.Width;
            check_hip(hipExternalMemoryGetMappedBuffer(&pointer_,memory_,&buffer),"HIP map D3D12 buffer");
        } catch(...) { release();throw; }
    }
    ~SharedAllocation() { release(); }
    SharedAllocation(const SharedAllocation&)=delete;
    void *pointer() const { return pointer_; }
private:
    void release() noexcept {
        if(pointer_) (void)hipFree(pointer_);
        if(memory_) (void)hipDestroyExternalMemory(memory_);
        if(handle_) CloseHandle(handle_);
        pointer_=nullptr;memory_=nullptr;handle_=nullptr;
    }
    Microsoft::WRL::ComPtr<ID3D12Resource> resource_;
    HANDLE handle_=nullptr;hipExternalMemory_t memory_=nullptr;void *pointer_=nullptr;
};
class WindowsInterop {
public:
    explicit WindowsInterop(ID3D12Device *dx) {
        try {
            const LUID luid=dx->GetAdapterLuid();int count=0;
            check_hip(hipGetDeviceCount(&count),"HIP device count");
            for(int i=0;i<count;++i) {
                hipDeviceProp_t p{};check_hip(hipGetDeviceProperties(&p,i),"HIP device properties");
                if(std::memcmp(p.luid,&luid,sizeof(luid))==0) { device_=i;break; }
            }
            if(device_<0) throw std::runtime_error("No HIP GPU matches the player's Direct3D adapter");
            activate();check_hip(hipStreamCreateWithFlags(&stream_,hipStreamNonBlocking),"HIP video stream");
            create_fence(dx,dx_to_hip_,handles_[0],semaphores_[0]);
            create_fence(dx,hip_to_dx_,handles_[1],semaphores_[1]);
        } catch(...) { release();throw; }
    }
    ~WindowsInterop() { release(); }
    void activate() { check_hip(hipSetDevice(device_),"HIP video adapter"); }
    int device() const { return device_; }
    hipStream_t stream() const { return stream_; }
    void begin(ID3D12CommandQueue *queue) {
        activate();++sequence_;
        check_dx(queue->Signal(dx_to_hip_.Get(),sequence_),"D3D12 signal to HIP");
        hipExternalSemaphoreWaitParams wait{};wait.params.fence.value=sequence_;
        check_hip(hipWaitExternalSemaphoresAsync(&semaphores_[0],&wait,1,stream_),"HIP wait for D3D12");
    }
    void end(ID3D12CommandQueue *queue) {
        hipExternalSemaphoreSignalParams signal{};signal.params.fence.value=sequence_;
        check_hip(hipSignalExternalSemaphoresAsync(&semaphores_[1],&signal,1,stream_),"HIP signal to D3D12");
        check_dx(queue->Wait(hip_to_dx_.Get(),sequence_),"D3D12 wait for HIP");
    }
    void drain() noexcept { if(stream_) { (void)hipSetDevice(device_);(void)hipStreamSynchronize(stream_); } }
private:
    void create_fence(ID3D12Device *dx,Microsoft::WRL::ComPtr<ID3D12Fence> &fence,
                      HANDLE &handle,hipExternalSemaphore_t &semaphore) {
        check_dx(dx->CreateFence(0,D3D12_FENCE_FLAG_SHARED,IID_PPV_ARGS(&fence)),"D3D12 HIP fence");
        check_dx(dx->CreateSharedHandle(fence.Get(),nullptr,GENERIC_ALL,nullptr,&handle),"D3D12 shared fence handle");
        hipExternalSemaphoreHandleDesc desc{};desc.type=hipExternalSemaphoreHandleTypeD3D12Fence;
        desc.handle.win32.handle=handle;
        check_hip(hipImportExternalSemaphore(&semaphore,&desc),"HIP import D3D12 fence");
    }
    void release() noexcept {
        drain();
        for(auto &s:semaphores_) if(s) { (void)hipDestroyExternalSemaphore(s);s=nullptr; }
        if(stream_) { (void)hipStreamDestroy(stream_);stream_=nullptr; }
        for(auto &h:handles_) if(h) { CloseHandle(h);h=nullptr; }
    }
    int device_=-1;hipStream_t stream_=nullptr;uint64_t sequence_=0;
    Microsoft::WRL::ComPtr<ID3D12Fence> dx_to_hip_,hip_to_dx_;
    HANDLE handles_[2]={nullptr,nullptr};hipExternalSemaphore_t semaphores_[2]={nullptr,nullptr};
};
}
#endif
