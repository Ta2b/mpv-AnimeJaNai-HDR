/* Controlled adapter error-path test, never a real device fault. LD_PRELOAD
 * only in the dedicated test process. No production injection entry point. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdatomic.h>
#include <cuda.h>
static _Atomic unsigned countdown;
void aji_test_fruc_fail_kernel(unsigned n) { atomic_store(&countdown,n); }
CUresult CUDAAPI cuLaunchKernel(CUfunction f,unsigned x,unsigned y,unsigned z,
    unsigned bx,unsigned by,unsigned bz,unsigned bytes,CUstream s,void **p,void **e) {
    unsigned n=atomic_load(&countdown);
    if(n&&atomic_fetch_sub(&countdown,1)==1)return CUDA_ERROR_INVALID_VALUE;
    typedef CUresult (CUDAAPI *launch)(CUfunction,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,CUstream,void **,void **);
    launch real=(launch)dlsym(RTLD_NEXT,"cuLaunchKernel");
    return real?real(f,x,y,z,bx,by,bz,bytes,s,p,e):CUDA_ERROR_UNKNOWN;
}
