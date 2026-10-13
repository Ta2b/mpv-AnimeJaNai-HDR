/* Host RGB24 bridge, ABI 1. Independent of CUDA/D3D11 aji ABI 9. */
/* Sources are compared byte for byte before reuse; row padding is ignored. Configure clears
 * every derived picture. AJI_VK_CACHE=0 keeps the uncached path for comparison/diagnosis.
 * AJI_VK_RIFE_GPU_CACHE=0 disables only resident RIFE inputs, retaining source reuse. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define AJI_VK_ABI 1
struct aji_vk_plan { int width, height, numerator, denominator, active; };
typedef void aji_vk_context;
uint32_t aji_vk_version(void);
aji_vk_context *aji_vk_create(const char *conf, const char *models,
    const char *rife, const char *device, const char *stats, int slot);
int aji_vk_configure(aji_vk_context *, int width, int height, double fps,
    struct aji_vk_plan *plan);
int aji_vk_process(aji_vk_context *, const unsigned char *previous, ptrdiff_t previous_stride,
    const unsigned char *current, ptrdiff_t current_stride, double timestep,
    unsigned char *output, ptrdiff_t output_stride);
/* Optional (an engine may not have it; the bridge looks it up by name). Before a call to
 * aji_vk_process: the source frames that follow the one of that call, in display order, valid
 * until that call returns. Returns how many following frames the engine would like to be given
 * from now on (0: none; the bridge then starts each frame as soon as it has it). */
int aji_vk_upcoming(aji_vk_context *, const unsigned char *const *frames, const ptrdiff_t *strides, int count);
const char *aji_vk_error(aji_vk_context *);
void aji_vk_destroy(aji_vk_context *);
#ifdef __cplusplus
}
#endif
