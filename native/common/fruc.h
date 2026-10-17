#pragma once
#include "interpolator.h"
#ifdef __cplusplus
extern "C" {
#endif
enum aji_fruc_create_flags { AJI_FRUC_ALLOW_FAST=1, AJI_FRUC_PROTECT_ARTIFACTS=2 };
/* Static feature mask 1: synthesis artifact protection, no GPU initialization. */
uint64_t aji_fruc_features_v1(void);
typedef struct aji_fruc_protection_stats_v1 {
    uint32_t struct_size,version;
    uint64_t checked,protected_frames;
} aji_fruc_protection_stats_v1;
int aji_fruc_protection_stats_v1_get(void *,aji_fruc_protection_stats_v1 *,size_t);
typedef struct aji_fruc_create_v1_params {
    uint32_t struct_size,version,flags,width,height,device_index,capacity,reserved;
    uint64_t generation;
    void *cuda_context; /* Borrowed; NULL retains device primary context. */
    const char *sdk_library; /* Explicit absolute user-installed libNvOFFRUC.so. */
    const char *sdk_runtime; /* Optional absolute libcudart.so.11.0-compatible file. */
    const char *kernel_fatbin; /* This provider's portable conversion kernels. */
    aji_surface_wakeup_fn wakeup;
    void *wakeup_opaque;
} aji_fruc_create_v1_params;
/* Linux CUDA only, Fast opt-in, two inputs and a single scalar median per job.
 * RGB8/full RGB, NV12/left and YUV444P16 supported SDR, no rotation/flip/HDR.
 * Internal FRUC synthesis is 8 bit even with 16-bit YUV input/output. Separate
 * model/runtime/upscaler; no SDK redistribution, implicit load, CPU fallback,
 * or pretended Quality equivalence. PROTECT_ARTIFACTS rejects severe bright-edge
 * excess by repeating the exact previous source for matching surface formats;
 * local fluidity is reduced and defects outside this guard can remain. Error text buffer may be NULL/zero length.
 */
int aji_fruc_create_v1(const aji_fruc_create_v1_params *,void **,char *,size_t);
#ifdef __cplusplus
}
#endif
