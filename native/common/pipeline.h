/* Optional ordered native pipeline, separate from ABI9/RIFE.
 * Explicit INI stage schema v1. Linux CUDA implementation; query after create.
 */
#pragma once
#include "interpolator.h"
#ifdef __cplusplus
extern "C" {
#endif
#define AJI_PIPELINE_MAX_OUTPUTS 16
enum aji_pipeline_status { AJI_PIPELINE_LEGACY=1 };
enum aji_pipeline_features { AJI_PIPELINE_FEATURE_AREA_DOWNSCALE=1, AJI_PIPELINE_FEATURE_TRUEHDR=2, AJI_PIPELINE_FEATURE_SPLINE36_DOWNSCALE=4, AJI_PIPELINE_FEATURE_RENDER_HDR=8 };
/* Static reader features, no CUDA initialization or pixel work. */
uint64_t aji_pipeline_features_v1(void);
enum aji_pipeline_create_flags { AJI_PIPELINE_ALLOW_FAST=1, AJI_PIPELINE_ALLOW_COLOR_CHANGE=2 };
enum aji_pipeline_cap_flags { AJI_PIPELINE_COLOR_CHANGE=4 };
enum aji_pipeline_request_flags { AJI_PIPELINE_EOF=2 };
enum aji_pipeline_output_flags { AJI_PIPELINE_ORIGINAL=1, AJI_PIPELINE_RIFE=2,
    /* Bit 4 is retired; other ABI v1 flag values remain stable. */
    AJI_PIPELINE_REPEATED=8, AJI_PIPELINE_UPSCALED=16,
    AJI_PIPELINE_RESIZED=32, AJI_PIPELINE_HDR=64, AJI_PIPELINE_PROTECTED=128 };
typedef struct aji_pipeline_create_v1_params {
    uint32_t struct_size,version,width,height,device_index,slot,capacity,flags;
    uint64_t generation;
    void *cuda_context;
    const char *conf,*model_dir,*rife_dir,*trtexec,*trtexec_env;
    const char *trt_library,*reserved_provider_library,*kernel_fatbin; /* Reserved pointer ignored; initialize to NULL. */
    int64_t fps_numerator,fps_denominator;
    uint64_t pixel_budget; /* Provider-owned pixel pool only; 0 = 512 MiB. */
    aji_surface_wakeup_fn wakeup;
    void *wakeup_opaque;
} aji_pipeline_create_v1_params;
typedef struct aji_pipeline_caps_v1 {
    uint32_t struct_size,version,width,height,factor,capacity,flags,device_index;
    uint32_t stage_count,lookahead,output_format,reserved;
    uint64_t generation;
} aji_pipeline_caps_v1;
typedef struct aji_pipeline_submit_v1_request {
    uint32_t struct_size,version,flags,output_count,dependency_count,reserved;
    uint64_t generation;
    const aji_surface_v1 *previous,*current;
    const aji_surface_v1 *outputs[AJI_PIPELINE_MAX_OUTPUTS];
    aji_surface_dependency_v1 dependencies[3];
} aji_pipeline_submit_v1_request;
typedef struct aji_pipeline_completion_v1 {
    aji_interpolator_completion_v1 result; /* flags: any provider or protection repetition in this burst */
    uint32_t output_count,output_flags[AJI_PIPELINE_MAX_OUTPUTS];
} aji_pipeline_completion_v1;
typedef struct aji_pipeline_stats_v1 {
    uint32_t struct_size,version;
    uint64_t submitted,finished,failed,cancelled,source_conversions,rife_predictions,reserved_provider_predictions,reserved_provider_repetitions,spatial_predictions;
    uint64_t pixel_bytes,peak_pixel_bytes,cpu_pixel_copies;
} aji_pipeline_stats_v1;
/* Create only copies/config-validates and starts one bounded worker. Query
 * BUSY while engines initialize on that worker; ENGINE_ERROR + last_error on
 * failure, no repeated builds or passthrough of a requested unsupported stage.
 * LEGACY with null context selects the unchanged ABI9 path when no ordered
 * schema, or when the schema exactly describes the existing legacy settings.
 *
 * Normal job: previous/current increasing media PTS, factor outputs representing
 * [previous,current), uniform rational phases j/factor. EOF job: previous=NULL,
 * current=last source, one output. It preserves the final source duration; no
 * imaginary future frames. Output PTS/duration is supplied and owned by caller,
 * checked against the grid within half an output tick, never overwritten.
 *
 * Input CUDA NV12/P010/YUV444P16 SDR, canonical owned YUV444P16 internally.
 * Output CUDA YUV444P16. Nonzero IDs are immutable full-view identities. No
 * owner is held after terminal Complete. Inputs/events must be ready or have
 * recorded producer events supplied; remain alive until terminal completion.
 * BORROW_UNTIL_COMPLETE and Complete/drain flag semantics match interpolator.h.
 * Writable output ranges must be distinct across outstanding requests; clients
 * must not recycle any source/target for external writes until completion.
 * Stats count API requests, not proven TensorRT kernel launches (cuts can copy).
 * Submit/Complete do not wait for GPU or capacity. Reset drains/drops old work,
 * invalidates stages/cache and requires a new generation; tickets monotone.
 * Destroy joins before freeing state. Lifecycle calls serial with Submit;
 * callbacks nonblocking, noexcept, thread-safe, no reentry. No CPU pixel copies.
 */
int aji_pipeline_create_v1(const aji_pipeline_create_v1_params *,void **,char *,size_t);
int aji_pipeline_query_v1(void *,aji_pipeline_caps_v1 *,size_t);
/* Optional color-aware client extension. Outputs untouched on failure; peak
 * is the SDK target, not measured content metadata. Peak0 means native HDR is
 * preserved by an HDR-only chain, so retain its existing HDR metadata.
 * Success advertises policy,
 * frames are released only after successful pixel processing. Older clients
 * without ALLOW_COLOR_CHANGE explicitly reject an HDR stage. */
int aji_pipeline_output_color_v1(void *,const aji_surface_color_v1 *,aji_surface_color_v1 *,size_t,double *peak);
int aji_pipeline_submit_v1(void *,const aji_pipeline_submit_v1_request *,uint64_t *);
int aji_pipeline_complete_v1(void *,uint64_t,uint32_t,aji_pipeline_completion_v1 *,size_t);
int aji_pipeline_drain_v1(void *,uint32_t);
int aji_pipeline_reset_v1(void *,uint64_t);
int aji_pipeline_stats_v1_get(void *,aji_pipeline_stats_v1 *,size_t);
int aji_pipeline_last_error_v1(void *,char *,size_t);
void aji_pipeline_destroy_v1(void *);
#ifdef __cplusplus
}
#endif
