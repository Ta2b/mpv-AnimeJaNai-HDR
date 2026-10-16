#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdatomic.h>
static _Atomic unsigned long long created;
int pthread_create(pthread_t *thread, const pthread_attr_t *attr, void *(*start)(void *), void *arg)
{
    int (*real_create)(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *) = dlsym(RTLD_NEXT, "pthread_create");
    int result = real_create(thread, attr, start, arg);
    if (!result) atomic_fetch_add(&created, 1);
    return result;
}
unsigned long long aji_test_thread_creations(void) { return atomic_load(&created); }
