#include "../../native/common/quality_contract.h"
#include <assert.h>
#include <stdio.h>

int main(void)
{
    aji_rife_semantics_v1_result value={0};
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_QUALITY)==-1);
    value.struct_size=sizeof(value);value.version=1;value.policy=AJI_RIFE_POLICY_QUALITY;
    value.flags=AJI_RIFE_REFERENCE_RGB;strcpy(value.module_path,"/observed/inner-provider.so");
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_NONE)==0);
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_QUALITY)==0);
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_FAST)==-2);
    value.flags|=AJI_RIFE_FAST_MOTION_READY;
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_NONE)==-2);
    value.policy=AJI_RIFE_POLICY_FAST;value.flags=AJI_RIFE_FAST_MOTION_READY;
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_FAST)==0);
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_QUALITY)==-2);
    value.flags=16;assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_FAST)==-1);
    value.flags=0;memset(value.module_path,'x',sizeof(value.module_path));
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_FAST)==-1);
    strcpy(value.module_path,"/observed/inner-provider.so");value.flags=AJI_RIFE_SOURCE_DECLARED;
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_FAST)==-1);
    memset(value.source_revision,'b',40);value.source_revision[40]=0;
    assert(aji_rife_semantics_check_v1(&value,AJI_RIFE_POLICY_FAST)==0);
    puts("PASS: the legacy reader's C validator checks effective policy, RGB/shortcut flags and bounded metadata");
}
