/* Test-only CUDA13 fence withholding/error injection; never use for performance claims. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static uint64_t deadline;
static int armed,failed;
static uint64_t now_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static void *resolve(const char *name){void *p=dlsym(RTLD_NEXT,name);if(!p){void *h=dlopen("libcudart.so.13",RTLD_LAZY|RTLD_LOCAL);p=h?dlsym(h,name):NULL;}if(!p)_exit(92);return p;}
static uint64_t gate(const char *operation){
 const char *path=getenv("AJI_TEST_GATE_FILE");if(!path || access(path,F_OK))return 0;
 pthread_mutex_lock(&mutex);
 if(!armed){armed=1;deadline=now_ns()+200000000;
  const char *marker=getenv("AJI_TEST_GATE_MARKER");FILE *f=marker?fopen(marker,"w"):NULL;
  if(f){fprintf(f,"%s %llu\n",operation,(unsigned long long)deadline);fclose(f);}}
 uint64_t result=deadline;pthread_mutex_unlock(&mutex);return result;
}
int cudaEventQuery(void *event){
 int (*real)(void *)=resolve("cudaEventQuery");int result=real(event);
 const char *error=getenv("AJI_TEST_GATE_ERROR");
 if(result==0 && error && !access(error,F_OK)){
  pthread_mutex_lock(&mutex);int inject=!failed;failed=1;pthread_mutex_unlock(&mutex);
  if(inject){const char *marker=getenv("AJI_TEST_GATE_MARKER");FILE *f=marker?fopen(marker,"w"):NULL;
   if(f){fputs("failure after real CUDA event success\n",f);fclose(f);}return 999;}
 }
 uint64_t until=gate("query");return until>now_ns()?600:result;
}
int cudaEventSynchronize(void *event){
 int (*real)(void *)=resolve("cudaEventSynchronize");uint64_t until=gate("synchronize");
 for(;;){uint64_t current=now_ns();if(current>=until)break;uint64_t left=until-current;struct timespec t={(time_t)(left/1000000000),(long)(left%1000000000)};nanosleep(&t,NULL);}
 return real(event);
}
