/* mpv software-frame bridge for the NCNN/Vulkan backend. LGPL-2.1-or-later. */
#include <dlfcn.h>
#include <stdlib.h>
#include <string.h>
#include "config.h"
#include "common/common.h"
#include "filters/filter.h"
#include "filters/filter_internal.h"
#include "filters/user_filters.h"
#include "options/m_option.h"
#include "options/path.h"
#include "video/mp_image.h"
#include "refqueue.h"
#include "aji_vulkan.h"

struct opts { char *lib, *conf, *model_dir, *rife_model_dir, *device, *stats; int slot; };
struct priv {
    struct opts *opts;
    struct mp_refqueue *queue;
    struct mp_image *previous, *outq[8];
    int outq_n, outq_pos, acc;
    aji_vk_context *context;
    void *library;
    struct aji_vk_plan plan;
    aji_vk_context *(*create)(const char *,const char *,const char *,const char *,const char *,int);
    int (*configure)(aji_vk_context *,int,int,double,struct aji_vk_plan *);
    int (*process)(aji_vk_context *,const unsigned char *,ptrdiff_t,const unsigned char *,ptrdiff_t,double,unsigned char *,ptrdiff_t);
    const char *(*error)(aji_vk_context *);
    void (*destroy)(aji_vk_context *);
};
static void reset(struct mp_filter *f) {
    struct priv *p=f->priv;
    mp_image_unrefp(&p->previous);
    for(int i=0;i<8;++i) mp_image_unrefp(&p->outq[i]);
    p->outq_n=p->outq_pos=0;p->acc=p->plan.denominator;
    if(p->queue) mp_refqueue_flush(p->queue);
}
static void destroy(struct mp_filter *f) {
    struct priv *p=f->priv;reset(f);
    // Destroy refqueue before mpv frees its autoconvert child filter.
    talloc_free(p->queue);p->queue=NULL;
    if(p->context) p->destroy(p->context);
    if(p->library) dlclose(p->library);
}
static struct mp_image *render(struct mp_filter *f,struct mp_image *in,double t) {
    struct priv *p=f->priv;
    struct mp_image *out=mp_image_alloc(IMGFMT_RGB24,p->plan.width,p->plan.height);
    if(!out) return NULL;
    mp_image_copy_attributes(out,in);
    out->params.w=p->plan.width;out->params.h=p->plan.height;
    if(mp_image_crop_valid(&in->params)) {
        out->params.crop=(struct mp_rect){
            in->params.crop.x0*p->plan.width/in->w,
            in->params.crop.y0*p->plan.height/in->h,
            in->params.crop.x1*p->plan.width/in->w,
            in->params.crop.y1*p->plan.height/in->h};
    }
    // Preserve display aspect ratio through uniform pre-resize/upscale.
    out->params.p_w=in->params.p_w;out->params.p_h=in->params.p_h;
    if(p->process(p->context,p->previous?p->previous->planes[0]:NULL,
        p->previous?p->previous->stride[0]:0,in->planes[0],in->stride[0],t,out->planes[0],out->stride[0])<0) {
        MP_ERR(f,"NCNN/Vulkan inference: %s\n",p->error(p->context));mp_image_unrefp(&out);return NULL;
    }
    if(in->nominal_fps>0) out->nominal_fps=in->nominal_fps*p->plan.numerator/p->plan.denominator;
    return out;
}
static void process(struct mp_filter *f) {
    struct priv *p=f->priv;
    // Drain interpolation frames before requesting more inputs or forwarding EOF.
    if(p->outq_n) {
        if(mp_pin_in_needs_data(f->ppins[1])) {
            struct mp_image *image=p->outq[p->outq_pos];p->outq[p->outq_pos++]=NULL;
            if(--p->outq_n==0)p->outq_pos=0;
            mp_pin_in_write(f->ppins[1],MAKE_FRAME(MP_FRAME_VIDEO,image));
            mp_filter_internal_mark_progress(f);
        }
        return;
    }
    struct mp_image *format=mp_refqueue_execute_reinit(p->queue);
    if(format) {
        mp_image_unrefp(&p->previous);
        if(format->params.color.transfer==PL_COLOR_TRC_PQ || format->params.color.transfer==PL_COLOR_TRC_HLG) {
            MP_ERR(f,"Vulkan inference currently accepts SDR sources only; use normal playback for HDR.\n");
            mp_filter_internal_mark_failed(f);return;
        }
        if(p->configure(p->context,format->w,format->h,format->nominal_fps,&p->plan)<0) {
            MP_ERR(f,"Vulkan profile: %s\n",p->error(p->context));mp_filter_internal_mark_failed(f);return;
        }
        p->acc=p->plan.denominator;
        MP_INFO(f,"NCNN/Vulkan %dx%d -> %dx%d, RIFE %d/%d\n",format->w,format->h,p->plan.width,p->plan.height,p->plan.numerator,p->plan.denominator);
    }
    if(!mp_refqueue_can_output(p->queue))return;
    struct mp_image *in=mp_refqueue_get(p->queue,0);
    if(!in)return;
    if(!p->plan.active) {
        mp_image_unrefp(&p->previous);
        mp_refqueue_write_out_pin(p->queue,mp_image_new_ref(in));return;
    }
    struct mp_image *frames[8]={0};int n=0;
    bool pair=p->previous && p->previous->pts!=MP_NOPTS_VALUE && in->pts!=MP_NOPTS_VALUE && in->pts>p->previous->pts;
    if(pair && in->nominal_fps>0 && in->pts-p->previous->pts>3.0/in->nominal_fps)pair=false;
    if(pair && p->plan.numerator>p->plan.denominator) {
        while(p->acc<=p->plan.numerator && n<8) {
            double t=(double)p->acc/p->plan.numerator;
            frames[n]=render(f,in,t);if(!frames[n])goto fail;
            frames[n]->pts=p->previous->pts+(in->pts-p->previous->pts)*t;
            ++n;p->acc+=p->plan.denominator;
        }
        p->acc-=p->plan.numerator;
    }
    if(!n) {
        frames[0]=render(f,in,1);if(!frames[0])goto fail;
        frames[0]->pts=in->pts;n=1;p->acc=p->plan.denominator;
    }
    mp_image_unrefp(&p->previous);p->previous=mp_image_new_ref(in);
    for(int i=1;i<n;++i)p->outq[p->outq_n++]=frames[i];
    p->outq_pos=0;
    mp_refqueue_write_out_pin(p->queue,frames[0]);return;
fail:
    for(int i=0;i<8;++i)mp_image_unrefp(&frames[i]);
    mp_filter_internal_mark_failed(f);
}
static bool drop_pre_seek(void *ctx,struct mp_image *image) {
    struct mp_stream_info *info=mp_filter_find_stream_info(ctx);double target;
    return image->pts!=MP_NOPTS_VALUE && info && info->get_hrseek && info->get_hrseek(info,&target) && image->pts<target-.005;
}
static const struct mp_filter_info info={.name="animejanai-vulkan",.process=process,.reset=reset,.destroy=destroy,.priv_size=sizeof(struct priv)};
static struct mp_filter *create(struct mp_filter *parent,void *options) {
    struct mp_filter *f=mp_filter_create(parent,&info);
    if(!f){talloc_free(options);return NULL;}
    struct priv *p=f->priv;p->opts=talloc_steal(p,options);
    mp_filter_add_pin(f,MP_PIN_IN,"in");mp_filter_add_pin(f,MP_PIN_OUT,"out");
    char *paths[5];char *sources[]={p->opts->lib,p->opts->conf,p->opts->model_dir,p->opts->rife_model_dir,p->opts->stats};
    for(int i=0;i<5;++i)paths[i]=sources[i]?mp_normalize_user_path(p,f->global,sources[i]):NULL;
    p->library=dlopen(paths[0]?paths[0]:"libaji_vulkan.so",RTLD_NOW|RTLD_LOCAL);
    if(!p->library){MP_ERR(f,"Vulkan backend: %s\n",dlerror());goto fail;}
    uint32_t (*version)(void)=dlsym(p->library,"aji_vk_version");
    if(!version || version()!=AJI_VK_ABI){MP_ERR(f,"Vulkan bridge ABI mismatch\n");goto fail;}
#define LOAD(field) do { *(void **)(&p->field)=dlsym(p->library,"aji_vk_" #field);if(!p->field)goto fail; } while(0)
    LOAD(create);LOAD(configure);LOAD(process);LOAD(error);LOAD(destroy);
#undef LOAD
    p->context=p->create(paths[1],paths[2],paths[3],p->opts->device,paths[4],p->opts->slot);
    if(!p->context){MP_ERR(f,"Vulkan backend: %s\n",p->error(NULL));goto fail;}
    p->queue=mp_refqueue_alloc(f);
    mp_refqueue_add_in_format(p->queue,IMGFMT_RGB24,0);
    mp_refqueue_set_refs(p->queue,0,0);mp_refqueue_set_mode(p->queue,0);
    mp_refqueue_set_drop_check(p->queue,drop_pre_seek,f);
    return f;
fail:
    talloc_free(f);return NULL;
}
#define OPT_BASE_STRUCT struct opts
static const m_option_t fields[]={
    {"lib",OPT_STRING(lib),.flags=M_OPT_FILE},{"conf",OPT_STRING(conf),.flags=M_OPT_FILE},
    {"model-dir",OPT_STRING(model_dir),.flags=M_OPT_FILE},{"rife-model-dir",OPT_STRING(rife_model_dir),.flags=M_OPT_FILE},
    {"stats",OPT_STRING(stats),.flags=M_OPT_FILE},{"device",OPT_STRING(device)},
    {"slot",OPT_INT(slot),M_RANGE(0,9999)},{0}
};
const struct mp_user_filter_entry vf_animejanai_vulkan={
    .desc={.description="AnimeJaNai/RIFE NCNN Vulkan (SDR host-frame bridge)",.name="animejanai-vulkan",
        .priv_size=sizeof(struct opts),.priv_defaults=&(const struct opts){.slot=1},.options=fields},.create=create
};
