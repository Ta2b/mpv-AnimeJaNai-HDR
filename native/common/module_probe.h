/* Optional, on-demand module diagnostic. Does not execute a model. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct aji_ort_probe_result_v1 {
    uint32_t struct_size, version, bridge_abi, required_cpu_features, checked_conversion;
    char ort_version[32], message[128];
} aji_ort_probe_result_v1;
/* Resolve by name on libaji_ort. Old modules have no such symbol.
 * x86-64 builds require OS-enabled AVX and CPU F16C (feature bits1/2).
 * Check these before calling any code from that module. An x86 load/version
 * lookup alone does not establish that its pixel conversion can execute.
 * Short/null outputs are untouched. Zero means the built conversion produced
 * the expected HALF value; this does not qualify provider/model kernels. */
int aji_ort_probe_v1(aji_ort_probe_result_v1 *,size_t);
#ifdef __cplusplus
}
#endif
