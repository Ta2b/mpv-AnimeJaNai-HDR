#pragma once
#include <hip/hip_runtime_api.h>
#include <memory>
#include <string>
#include <vector>

namespace aji::amd {
struct DeviceTensor {
    void *data=nullptr;
    int channels=0,width=0,height=0;
    bool half=false;
};
// Native graph execution usable by a video backend without the RGB24 bridge.
// Buffers belong to the graph and remain alive until the next enqueue. A
// caller-provided stream permits external D3D/Vulkan semaphore ordering.
class DeviceModel {
public:
    virtual ~DeviceModel()=default;
    virtual DeviceTensor input() const=0;
    virtual std::vector<DeviceTensor> output_shapes() const=0;
    virtual std::vector<DeviceTensor> enqueue(const void *input,void *output=nullptr)=0;
};
std::unique_ptr<DeviceModel> make_device_model(const std::string &path,int width,
    int height,int channels,int device,hipStream_t stream,bool motion_only=false);
}
