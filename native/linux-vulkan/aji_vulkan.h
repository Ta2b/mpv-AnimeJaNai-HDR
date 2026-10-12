/* Host RGB24 bridge, ABI 1. Independent of CUDA/D3D11 aji ABI 9. */
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
const char *aji_vk_error(aji_vk_context *);
void aji_vk_destroy(aji_vk_context *);
#ifdef __cplusplus
}
#endif
