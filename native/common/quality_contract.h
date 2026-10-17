/* Optional configured RIFE semantics, independent of ABI9 and Surfacev1.
 * Resolve/query on the same engine image as create/configure, once while idle.
 * A module path observes the loaded image, not the hash of its mapped pages.
 * source_revision is a build declaration only when SOURCE_DECLARED is set.
 * Quality retains full reference RGB predictions and the reference scene cut;
 * exact prepared-source caches are allowed. Fast may fall back to full RGB.
 * Linux CUDA is implemented; other platforms return UNSUPPORTED. No pixel work.
 * Errors leave the caller's output untouched. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#ifdef __cplusplus
extern "C" {
#endif
enum aji_rife_policy_v1 { AJI_RIFE_POLICY_NONE=0, AJI_RIFE_POLICY_QUALITY=1, AJI_RIFE_POLICY_FAST=2 };
enum aji_rife_semantics_flags_v1 {
    AJI_RIFE_REFERENCE_RGB=1, AJI_RIFE_FAST_MOTION_READY=2,
    AJI_RIFE_FAST_HELD_ENABLED=4, AJI_RIFE_SOURCE_DECLARED=8
};
typedef struct aji_rife_semantics_v1_result {
    uint32_t struct_size,version,policy,flags;
    char module_path[1024];
    char source_revision[41];
} aji_rife_semantics_v1_result;
int aji_rife_semantics_v1(void *context,uint32_t requested_version,
    aji_rife_semantics_v1_result *,size_t);
/* Consumer validation: expected=NONE means infer the known effective policy,
 * never label an unknown provider Quality. 0 valid, -1 malformed, -2 mismatch.
 * These checks are also used by the real legacy reader, before any pixels. */
static inline int aji_rife_semantics_check_v1(const aji_rife_semantics_v1_result *value,uint32_t expected)
{
    const uint32_t known=AJI_RIFE_REFERENCE_RGB|AJI_RIFE_FAST_MOTION_READY|AJI_RIFE_FAST_HELD_ENABLED|AJI_RIFE_SOURCE_DECLARED;
    if(!value||value->struct_size<sizeof(*value)||value->version!=1||
       (value->policy!=AJI_RIFE_POLICY_QUALITY&&value->policy!=AJI_RIFE_POLICY_FAST)||
       (value->flags&~known)||!value->module_path[0]||!memchr(value->module_path,0,sizeof(value->module_path)))return -1;
    if(value->flags&AJI_RIFE_SOURCE_DECLARED) {
        const char *end=(const char*)memchr(value->source_revision,0,sizeof(value->source_revision));
        if(end!=value->source_revision+40)return -1;
        for(int i=0;i<40;i++)if(!((value->source_revision[i]>='0'&&value->source_revision[i]<='9')||
            (value->source_revision[i]>='a'&&value->source_revision[i]<='f')))return -1;
    }
    if((expected!=AJI_RIFE_POLICY_NONE&&expected!=value->policy)||
       (value->policy==AJI_RIFE_POLICY_QUALITY&&(!(value->flags&AJI_RIFE_REFERENCE_RGB)||
        (value->flags&(AJI_RIFE_FAST_MOTION_READY|AJI_RIFE_FAST_HELD_ENABLED)))))return -2;
    return 0;
}
#ifdef __cplusplus
}
#endif
