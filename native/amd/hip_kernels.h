#pragma once
#include <hip/hip_runtime_api.h>
#include <cstddef>
#include <cstdint>

namespace aji::amd {
// All launches use the inference stream. FP16 is the model's declared type,
// never a request to quantize additional operations or weights.
hipError_t pack_rgb(const uint8_t *, void *, bool half, int w, int h,
                    int pw, int ph, int left, int top, hipStream_t);
hipError_t rife_grid(void *, bool half, int pw, int ph, hipStream_t);
hipError_t timestep(void *, bool half, int pw, int ph, float t, hipStream_t);
hipError_t unpack_rgb(const void *, bool half, uint8_t *, int pw, int ph,
                      int x, int y, int w, int h, hipStream_t);
hipError_t crop_planes(const void *, bool half, float *, int planes, int pw,
                       int ph, int left, int top, int w, int h, hipStream_t);
hipError_t flow_max(const float *, size_t count, unsigned int *, hipStream_t);
hipError_t warp_rgb(const uint8_t *, const uint8_t *, uint8_t *, int w, int h,
                    const float *, const float *, int fw, int fh, float t,
                    bool derived, hipStream_t);
hipError_t warp_tensor(const void *, const void *, void *, bool half, int w, int h,
                       const float *, const float *, int fw, int fh, float t,
                       bool derived, hipStream_t);
}
