/* Optional synchronous batch extension. ABI9 and Surfacev1 are unchanged.
 * Resolve on the selected engine and query after successful configuration. */
#pragma once
#include "surface.h"
#ifdef __cplusplus
extern "C" {
#endif
#define AJI_SURFACE_BATCH_MAX_JOBS 17

typedef struct aji_surface_batch_caps_v1 {
    uint32_t struct_size,version,max_jobs,flags;
} aji_surface_batch_caps_v1;
typedef struct aji_surface_batch_job_v1 {
    uint32_t struct_size,version;
    const aji_surface_v1 *previous,*current,*output;
    double timestep;
} aji_surface_batch_job_v1;

/* Calls remain serial on the context; an enabled async queue returns BUSY.
 * Jobs run in array order on the provider's same stream. All descriptors and
 * allocations remain valid until return. External writers must not modify
 * sources meanwhile. Owners are retained for the entire batch, including an
 * error drain, and released before return. An error invalidates the whole
 * batch: discard all its outputs. Synchronous completion is performed once
 * after the queued output work, preserving internal scene/stream dependencies.
 * No new formats, device imports or approximations are implied by support. */
AJI_OPTIONAL_EXPORT int aji_surface_batch_query_v1(void *context,uint32_t version,
    aji_surface_batch_caps_v1 *,size_t);
AJI_OPTIONAL_EXPORT int aji_surface_process_batch_v1(void *context,uint32_t version,
    const aji_surface_batch_job_v1 *,size_t count);
#ifdef __cplusplus
}
#endif
