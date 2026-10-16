/* Optional native surface contract. In-process C ABI; all sizes are bytes.
 * Descriptors are immutable for the duration of a call. No storage/device is
 * implied by the format enum; query the selected module's capabilities first.
 * This interface does not change aji_vk ABI1 or aji ABI9. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define AJI_SURFACE_VERSION 1
enum aji_surface_status { AJI_SURFACE_OK=0, AJI_SURFACE_INVALID=-1,
    AJI_SURFACE_UNSUPPORTED=-2, AJI_SURFACE_ENGINE_ERROR=-3 };
enum aji_resource_kind { AJI_RESOURCE_HOST=1, AJI_RESOURCE_CUDA=2, AJI_RESOURCE_HIP=3,
    AJI_RESOURCE_D3D11=4, AJI_RESOURCE_D3D12=5, AJI_RESOURCE_METAL=6,
    AJI_RESOURCE_VULKAN=7, AJI_RESOURCE_DMABUF=8 };
enum aji_surface_format { AJI_SURFACE_RGB8=1, AJI_SURFACE_RGB16=2,
    AJI_SURFACE_RGB_F16_NCHW=3, AJI_SURFACE_RGB_F32_NCHW=4,
    AJI_SURFACE_NV12=5, AJI_SURFACE_P010=6, AJI_SURFACE_YUV444P16=7 };
enum aji_surface_matrix { AJI_SURFACE_MATRIX_UNKNOWN=0, AJI_SURFACE_MATRIX_RGB=1,
    AJI_SURFACE_MATRIX_601=2, AJI_SURFACE_MATRIX_709=3, AJI_SURFACE_MATRIX_2020_NC=4 };
enum aji_surface_primaries { AJI_SURFACE_PRIM_UNKNOWN=0, AJI_SURFACE_PRIM_709=1,
    AJI_SURFACE_PRIM_2020=2, AJI_SURFACE_PRIM_P3=3, AJI_SURFACE_PRIM_601=4 };
enum aji_surface_transfer { AJI_SURFACE_TRC_UNKNOWN=0, AJI_SURFACE_TRC_709=1,
    AJI_SURFACE_TRC_SRGB=2, AJI_SURFACE_TRC_1886=3, AJI_SURFACE_TRC_LINEAR=4,
    AJI_SURFACE_TRC_PQ=5, AJI_SURFACE_TRC_HLG=6 };
enum aji_surface_range { AJI_SURFACE_RANGE_UNKNOWN=0, AJI_SURFACE_RANGE_FULL=1,
    AJI_SURFACE_RANGE_LIMITED=2 };
enum aji_surface_siting { AJI_SURFACE_SITING_UNKNOWN=0, AJI_SURFACE_SITING_LEFT=1,
    AJI_SURFACE_SITING_CENTER=2, AJI_SURFACE_SITING_TOPLEFT=3 };
enum aji_surface_quantization { AJI_SURFACE_QUANT_UNKNOWN=0,
    AJI_SURFACE_QUANT_REFERENCE_RGB8=1, AJI_SURFACE_QUANT_HIGH_DEPTH=2,
    AJI_SURFACE_QUANT_REFERENCE_NATIVE_YUV=3 };
enum aji_surface_dither { AJI_SURFACE_DITHER_UNKNOWN=0, AJI_SURFACE_DITHER_NONE=1,
    AJI_SURFACE_DITHER_ORDERED=2, AJI_SURFACE_DITHER_BLUE_NOISE=3 };
enum aji_surface_cap_flags { AJI_SURFACE_SYNC=1, AJI_SURFACE_BORROWED_CALL=2,
    AJI_SURFACE_OWNER_CALLBACKS=4, AJI_SURFACE_HOST_ROI=8,
    AJI_SURFACE_PRESERVES_DESCRIPTORS=16, AJI_SURFACE_CUDA_ROI=32,
    AJI_SURFACE_SPATIAL=64, AJI_SURFACE_RIFE=128, AJI_SURFACE_EXACT_SOURCE_CACHE=256 };
enum aji_surface_time_flags { AJI_SURFACE_HAS_PTS=1, AJI_SURFACE_HAS_DURATION=2 };

typedef struct aji_surface_rect_v1 { int32_t x,y,width,height; } aji_surface_rect_v1;
typedef struct aji_surface_color_v1 {
    uint32_t matrix,primaries,transfer,range,siting,component_bits,quantization,dither;
} aji_surface_color_v1;
typedef struct aji_surface_plane_v1 {
    void *data;                 /* host allocation base; native resource may use NULL */
    uint64_t bytes,offset;      /* extent of allocation and first logical row offset */
    int64_t row_stride;         /* signed bytes; support is negotiated per provider */
} aji_surface_plane_v1;
typedef void (*aji_surface_owner_fn)(void *owner);
typedef struct aji_surface_v1 {
    uint32_t struct_size,version,resource_kind,format;
    uint32_t device_kind,device_index;
    void *device_context;       /* backend-specific, never silently imported */
    uint8_t device_uuid[16];
    uint64_t device_luid;
    void *resource;            /* opaque native resource, independent of plane data */
    uint64_t subresource;
    int32_t width,height;       /* logical allocation geometry */
    aji_surface_rect_v1 crop;   /* active view; all-zero rectangle means full image */
    uint32_t plane_count,rotation,vertical_flip,reserved;
    aji_surface_color_v1 color;
    int64_t pts,duration;
    int32_t timebase_num,timebase_den;
    uint32_t time_flags,reserved_time;
    uint64_t sequence,generation; /* immutable active-view identity, zero disables trust */
    aji_surface_plane_v1 planes[4];
    void *owner;
    aji_surface_owner_fn retain,release;
} aji_surface_v1;
typedef struct aji_surface_caps_v1 {
    uint32_t struct_size,version,flags,max_dimension;
    uint64_t resource_mask,format_mask; /* bit n corresponds to enum value n */
    uint32_t max_planes,negative_stride,device_kind,device_index;
} aji_surface_caps_v1;

/* Optional native counters. Read only while the context is idle and its async
 * queue disabled; otherwise BUSY. Counters are observational, never a cache key.
 * These values do not certify timing/quality or other hardware. */
typedef struct aji_surface_cache_stats_v1_result {
    uint32_t struct_size,version;
    uint64_t eligible_hits,eligible_misses,uncached_calls;
    uint64_t rife_preparations,rife_hits,promoted_inputs,fast_upscaled,fast_warped;
} aji_surface_cache_stats_v1_result;
int aji_surface_cache_stats_v1(void *context,uint32_t version,aji_surface_cache_stats_v1_result *,size_t);

/* CUDA Linux v1 accepts native NV12/P010/YUV444P16 SDR on the configured
 * context, positive strides and chroma-aligned crop, reference-native YUV
 * quantization with no added dither. SPATIAL/RIFE flags describe the configured
 * standard chain; temporal/pre-resize/RTX configurations are refused. Source
 * identities may protect owned GPU preparation across phases when
 * EXACT_SOURCE_CACHE is negotiated. Nonzero sequence/generation identify an
 * immutable active view; complete source/device/color/view keys must match.
 * Zero identities, changed views/policy, errors, reset/drain and legacy calls
 * invalidate reuse. No client owners/descriptors are retained after completion;
 * owned prepared pixels and numeric view addresses may remain as cache keys.
 * No host staging.
 *
 * Resolve these optional symbols on the selected engine module. Query after
 * successful configure; unsupported version/provider/format is never an implicit convert.
 * Short/null capability outputs are untouched. Capability success describes an
 * implemented route, not qualification of all models, colors or hardware.
 *
 * CPU v1 accepts host RGB8 SDR, positive strides and explicit reference RGB8
 * output quantization/no added dither. Crop selects the actual source/output
 * view; it does not resize, rotate or change colors. Descriptor color/orientation
 * must match across a pair/output. Timing is carried untouched; the client owns
 * its interpolated output PTS/duration. No timestamps are fabricated.
 *
 * When both callbacks are supplied, retain/release once per descriptor (including
 * output), balanced until all pixel work completes. Otherwise memory is borrowed
 * until return. Callbacks must not throw, fail or reenter this context. No pointer
 * or owner is kept after return. Calls/configure remain serial for each context.
 * Submit/Complete/fences and future-source descriptors are separate extensions.
 * Changing metadata/view invalidates derived source results even with repeated
 * IDs. Clients still advance generation on seek/content lifetime changes.
 */
int aji_surface_query_v1(void *context,uint32_t requested_version,aji_surface_caps_v1 *,size_t);
int aji_surface_process_v1(void *context,const aji_surface_v1 *previous,
    const aji_surface_v1 *current,double timestep,const aji_surface_v1 *output);
#ifdef __cplusplus
}
#endif
