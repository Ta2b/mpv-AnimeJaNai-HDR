// Link the actual mpv misc/io_utils.c object. Allocation/randomness are fixtures;
// fopen/write/close/exclusive creation/rename/unlink are the real OS operations.
#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <dirent.h>
#include <assert.h>
typedef struct { uint64_t v[4]; } mp_rand_state;
mp_rand_state mp_rand_seed(uint64_t x) { return (mp_rand_state){{0xabc000,0,0,0}}; }
uint64_t mp_rand_next(mp_rand_state *s) { return ++s->v[0]; }
char *mp_tprintf_buf(char *b,size_t n,const char *fmt,...) { va_list a;va_start(a,fmt);vsnprintf(b,n,fmt,a);va_end(a);return b; }
char *ta_asprintf(void *p,const char *fmt,...) { char *b=NULL;va_list a;va_start(a,fmt);assert(vasprintf(&b,fmt,a)>=0);va_end(a);return b; }
void ta_free(void *p) { free(p); }
bool mp_save_to_file(const char *,const void *,size_t);
static const char *target;
static bool fail_rename;
static void read_into(const char *name,char *buf,size_t n) { FILE *f=fopen(name,"rb");assert(f);size_t k=fread(buf,1,n-1,f);buf[k]=0;fclose(f); }
int __real_rename(const char *,const char *);
int __wrap_rename(const char *a,const char *b) {
    char text[256];read_into(target,text,sizeof text);
    assert(strcmp(text,"old complete state\n")==0); // target never truncated before commit
    if(fail_rename) { errno=EACCES;return -1; }
    return __real_rename(a,b);
}
int main(int argc,char **argv) {
    assert(argc==3);const bool after=strcmp(argv[1],"after")==0;target=argv[2];char text[256];
    FILE *f=fopen(target,"wb");assert(f);fputs("old complete state\n",f);fclose(f);
    // Exact former filter pattern: an intervening reader observes the empty file.
    f=fopen(target,"w");assert(f);read_into(target,text,sizeof text);assert(text[0]==0);
    fputs("old complete state\n",f);fclose(f);
    FILE *reader=fopen(target,"rb");assert(reader);
    assert(mp_save_to_file(target,"new complete state\n",19));
    read_into(target,text,sizeof text);assert(strcmp(text,"new complete state\n")==0);
    memset(text,0,sizeof text);assert(fread(text,1,sizeof text-1,reader)==19);fclose(reader);
    assert(strcmp(text,"old complete state\n")==0);
    f=fopen(target,"wb");assert(f);fputs("old complete state\n",f);fclose(f);
    fail_rename=true;assert(!mp_save_to_file(target,"new complete state\n",19));
    read_into(target,text,sizeof text);assert(strcmp(text,"old complete state\n")==0);
    char temporary[4096];snprintf(temporary,sizeof temporary,"%sabc001",target);
    f=fopen(temporary,"rb");const bool leaked=f!=NULL;if(f)fclose(f);
    assert(leaked!=after);
    if(leaked)remove(temporary);
    printf("old_truncation_gap=1 atomic_reader_old_complete=1 new_complete=1 failed_replace_preserves_old=1 leaked_temporary=%d\n",leaked);
}
