/* Negotiated interpolation API, independent of the legacy RIFE entry point.
 * Optional provider symbols; in-process ABI, descriptors from surface.h.
 * A capability is an implemented route, not qualification of every model/GPU.
 */
#pragma once
#include "surface_async.h"
#ifdef __cplusplus
extern "C" {
#endif
#define AJI_INTERPOLATOR_VERSION 1
#define AJI_INTERPOLATOR_MAX_IO 8
enum aji_interpolator_phase_kind { AJI_INTERPOLATOR_SCALAR=1, AJI_INTERPOLATOR_MAP=2 };
enum aji_interpolator_flags { AJI_INTERPOLATOR_FAST=1, AJI_INTERPOLATOR_FIXED_MEDIAN=2 };
enum aji_interpolator_completion_flags { AJI_INTERPOLATOR_REPEATED=1 };
typedef struct aji_interpolator_phase_v1 {
    uint32_t kind,reserved;
    double scalar;
    const aji_surface_v1 *map;
} aji_interpolator_phase_v1;
typedef struct aji_interpolator_caps_v1 {
    uint32_t struct_size,version,flags,min_inputs,max_inputs,lookahead,max_outputs,max_phases;
    uint64_t input_resource_mask,output_resource_mask,input_format_mask,output_format_mask;
    uint64_t dependency_mask;
    uint32_t phase_mask,queue_capacity,device_index,effective_bits;
    uint8_t device_uuid[16];
    char provider[64];
} aji_interpolator_caps_v1;
typedef struct aji_interpolator_submit_v1_request {
    uint32_t struct_size,version,flags,input_count,output_count,phase_count,dependency_count,reserved;
    uint64_t generation;
    const aji_surface_v1 *inputs[AJI_INTERPOLATOR_MAX_IO];
    const aji_surface_v1 *outputs[AJI_INTERPOLATOR_MAX_IO];
    aji_interpolator_phase_v1 phases[AJI_INTERPOLATOR_MAX_IO];
    aji_surface_dependency_v1 dependencies[AJI_INTERPOLATOR_MAX_IO];
} aji_interpolator_submit_v1_request;
typedef struct aji_interpolator_completion_v1 {
    uint32_t struct_size,version,state,flags;
    uint64_t ticket;
    int32_t status;
    uint32_t reserved;
    char message[256];
} aji_interpolator_completion_v1;
typedef struct aji_interpolator_stats_v1 {
    uint32_t struct_size,version;
    uint64_t submitted,finished,failed,cancelled,primes,resets,sdk_calls,input_conversions;
    uint64_t repeated,owned_pixel_bytes,cpu_pixel_copies;
} aji_interpolator_stats_v1;

/* Submit copies descriptors and retains each owner, or requires explicit
 * BORROW_UNTIL_COMPLETE. Sources remain immutable; outputs/dependencies remain
 * allocated until terminal Complete. Producer events must already be recorded.
 * No CPU pixel staging. Submit/Complete never wait for GPU execution/capacity.
 * FINISHED includes all GPU work and owner releases. REPEATED is a usable SDK
 * repetition, not a newly synthesized image. FAILED/CANCELLED outputs discarded.
 * CONSUME frees terminal slots only. Lifecycle calls (including stats) are serial
 * with Submit; Complete may poll during Drain. Drain waits explicitly, optionally
 * cancelling queued work/dropping results. Reset requires a new nonzero generation,
 * drains, invalidates SDK/preparation state, and keeps ticket IDs monotone.
 * Destroy joins the worker before releasing resources; no callback afterwards.
 * Wakeups/owner callbacks must be thread-safe, nonblocking, noexcept, no reentry.
 * Client owns all media PTS/durations; SDK timestamps never replace descriptors.
 * Exact nonzero sequence/generation identify immutable views, including color,
 * geometry and pointers. Providers may cache OWNED pixels, never client owners
 * beyond completion. Zero identity disables reuse. Query before submission.
 */
int aji_interpolator_query_v1(void *,uint32_t,aji_interpolator_caps_v1 *,size_t);
int aji_interpolator_submit_v1(void *,const aji_interpolator_submit_v1_request *,uint64_t *);
int aji_interpolator_complete_v1(void *,uint64_t,uint32_t,aji_interpolator_completion_v1 *,size_t);
int aji_interpolator_drain_v1(void *,uint32_t);
int aji_interpolator_reset_v1(void *,uint64_t generation);
int aji_interpolator_stats_v1_get(void *,aji_interpolator_stats_v1 *,size_t);
void aji_interpolator_destroy_v1(void *);
#ifdef __cplusplus
}
#endif
