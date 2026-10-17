// Internal Apple-only probe ABI. The RGB24 engine ABI is unchanged.
// pixel_buffer is a borrowed CVPixelBufferRef, never an RGB byte pointer.
// Calls to consume/reset/destroy are serialized by the owning filter worker.
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define AJI_APPLE_NV12_PROBE_ABI 1
#define AJI_APPLE_NV12_SDR709 1u
struct aji_apple_nv12_view_v1 {
    uint32_t size,version,width,height;
    uint32_t crop_x0,crop_y0,crop_x1,crop_y1;
    uint32_t flags,rotation;
    uint64_t generation,source;
    double pts;
};
// Optional validation only, planar active bytes, no color conversion. A null
// readback makes the experimental consumer touch just one texel per plane.
struct aji_apple_nv12_readback_v1 {
    uint32_t size;
    uint8_t *y,*uv;
    uint64_t y_stride,uv_stride,y_bytes,uv_bytes;
};
struct aji_apple_nv12_stats_v1 {
    uint32_t size,version;
    uint64_t device,imports,live_images,peak_images,sampled_bytes,validation_bytes,resets;
};
struct aji_apple_nv12_probe_api {
    uint32_t size,version;
    void *(*create)(char *error,uint32_t capacity);
    // 0 supported; 1 unsupported (caller uses its software-frame fallback).
    int (*query)(void *,void *pixel_buffer,const struct aji_apple_nv12_view_v1 *,char *reason,uint32_t capacity);
    int (*consume)(void *,void *pixel_buffer,const struct aji_apple_nv12_view_v1 *,const struct aji_apple_nv12_readback_v1 *,char *error,uint32_t capacity);
    void (*reset)(void *);
    int (*stats)(void *,struct aji_apple_nv12_stats_v1 *);
    void (*destroy)(void *);
};
const struct aji_apple_nv12_probe_api *aji_apple_nv12_probe_api_v1(void);
#ifdef __cplusplus
}
#endif
