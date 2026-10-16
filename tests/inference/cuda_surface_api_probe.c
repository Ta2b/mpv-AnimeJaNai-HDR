/* Test-only allocation error after surface owner acquisition, before inference. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stddef.h>
#include <stdatomic.h>
static _Atomic int fail_next;
void aji_test_cuda_fail_next_allocation(void) {atomic_store(&fail_next,1);}
int cudaMalloc(void **out,size_t size) {
    if(atomic_exchange(&fail_next,0)) {if(out)*out=NULL;return 2; /* cudaErrorMemoryAllocation */}
    int (*real)(void **,size_t)=dlsym(RTLD_NEXT,"cudaMalloc");
    /* ctypes loads cudart locally; RTLD_NEXT need not include that scope. */
    if(!real)real=dlsym(dlopen("libcudart.so.13",RTLD_NOW|RTLD_LOCAL),"cudaMalloc");
    return real?real(out,size):999;
}

static _Atomic int fail_completed_event;
void aji_test_cuda_fail_next_completed_event(void) {atomic_store(&fail_completed_event,1);}
int cudaEventQuery(void *event) {
    int (*real)(void *)=dlsym(RTLD_NEXT,"cudaEventQuery");
    if(!real)real=dlsym(dlopen("libcudart.so.13",RTLD_NOW|RTLD_LOCAL),"cudaEventQuery");
    int status=real?real(event):999;
    if(!status && atomic_exchange(&fail_completed_event,0))return 999;
    return status;
}
