/* Standalone C consumer: optional surface negotiation, borrowed buffers and ABI1 fallback. */
#include "surface.h"
#include "aji_vulkan.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
    assert(argc==2 || argc==3);
    void *lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);assert(lib);
    aji_vk_context *(*create)(const char *,const char *,const char *,const char *,const char *,int)=dlsym(lib,"aji_vk_create");
    int (*configure)(aji_vk_context *,int,int,double,struct aji_vk_plan *)=dlsym(lib,"aji_vk_configure");
    int (*legacy)(aji_vk_context *,const unsigned char *,ptrdiff_t,const unsigned char *,ptrdiff_t,double,unsigned char *,ptrdiff_t)=dlsym(lib,"aji_vk_process");
    void (*destroy)(aji_vk_context *)=dlsym(lib,"aji_vk_destroy");
    int (*query)(void *,uint32_t,aji_surface_caps_v1 *,size_t)=dlsym(lib,"aji_surface_query_v1");
    int (*process)(void *,const aji_surface_v1 *,const aji_surface_v1 *,double,const aji_surface_v1 *)=dlsym(lib,"aji_surface_process_v1");
    assert(create && configure && legacy && destroy);
    aji_vk_context *ctx=create(NULL,NULL,NULL,"cpu",NULL,0);assert(ctx);
    struct aji_vk_plan plan;assert(configure(ctx,4,2,24,&plan)==0);
    unsigned char input[24],output[24];for(int i=0;i<24;++i)input[i]=(unsigned char)(i*7);
    memset(output,0xa5,sizeof(output));
    aji_surface_v1 a={0};a.struct_size=sizeof(a);a.version=1;
    a.resource_kind=a.device_kind=AJI_RESOURCE_HOST;a.format=AJI_SURFACE_RGB8;
    a.width=4;a.height=2;a.plane_count=1;
    a.color=(aji_surface_color_v1){AJI_SURFACE_MATRIX_RGB,AJI_SURFACE_PRIM_709,AJI_SURFACE_TRC_709,
        AJI_SURFACE_RANGE_FULL,AJI_SURFACE_SITING_UNKNOWN,8,AJI_SURFACE_QUANT_REFERENCE_RGB8,AJI_SURFACE_DITHER_NONE};
    a.planes[0]=(aji_surface_plane_v1){input,sizeof(input),0,12};
    aji_surface_v1 b=a;b.planes[0].data=output;
    aji_surface_caps_v1 caps={0};
    int modern=query && process && query(ctx,1,&caps,sizeof(caps))==0;
    if(argc==3) {
        assert(!strcmp(argv[2],"--failed-configure") && modern);
        assert(configure(ctx,0,2,24,&plan)<0);
        memset(&caps,0xa5,sizeof(caps));aji_surface_caps_v1 saved=caps;
        assert(query(ctx,1,&caps,sizeof(caps))==AJI_SURFACE_UNSUPPORTED && !memcmp(&caps,&saved,sizeof(caps)));
        assert(process(ctx,NULL,&a,1,&b)==AJI_SURFACE_UNSUPPORTED);
        for(int i=0;i<24;++i)assert(output[i]==0xa5);
        assert(configure(ctx,4,2,24,&plan)==0 && query(ctx,1,&caps,sizeof(caps))==0);
        destroy(ctx);dlclose(lib);
        puts("{\"passed\":true,\"failed_configure_disables_surfaces\":true,\"reconfigure_restores_capabilities\":true,\"models_executed\":false}");
        return 0;
    }
    if(modern) {
        assert(caps.format_mask==(1ull<<AJI_SURFACE_RGB8) && (caps.flags&AJI_SURFACE_BORROWED_CALL));
        aji_surface_v1 saved_a=a,saved_b=b;
        assert(process(ctx,NULL,&a,1,&b)==0);
        assert(!memcmp(&a,&saved_a,sizeof(a)) && !memcmp(&b,&saved_b,sizeof(b)));
    } else assert(legacy(ctx,NULL,0,input,12,1,output,12)==0);
    assert(!memcmp(input,output,sizeof(input)));
    destroy(ctx);dlclose(lib);
    printf("{\"passed\":true,\"route\":\"%s\",\"borrowed_buffers\":true,\"models_executed\":false}\n",modern?"surface-v1":"legacy-abi1");
}
