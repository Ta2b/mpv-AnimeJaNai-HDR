/* mpv software-frame bridge for the host-frame engines (NCNN/Vulkan, ONNX Runtime, Core ML,
 * Metal). LGPL-2.1-or-later.
 *
 * The engine runs on a thread of its own, a few source frames ahead of the display ("ahead").
 * A frame then no longer has to be computed within the time between two frames: only the
 * average has to keep up. A pan that takes twice the budget is paid with the time saved on the
 * held drawings around it, which the engine reuses for almost nothing. The player's own thread
 * never waits for the engine, except for the frame in progress at a seek.
 *
 * An engine may ask to be shown the source frames that follow the one it is given
 * (aji_vk_upcoming, optional): it then knows how long a drawing stays on screen before it
 * computes it. A frame is started once that many following frames have been decoded. */
#include <dlfcn.h>
#include <stdlib.h>
#include <string.h>
#include "config.h"
#include "common/common.h"
#include "filters/f_autoconvert.h"
#include "filters/filter.h"
#include "filters/filter_internal.h"
#include "filters/user_filters.h"
#include "options/m_option.h"
#include "options/path.h"
#include "osdep/threads.h"
#include "video/mp_image.h"
#include "aji_vulkan.h"

#define MAX_JOBS 128
// Memory the computed pictures may hold while they wait for their turn on screen.
#define AHEAD_BYTES (640ll<<20)
enum { JOB_QUEUED, JOB_RUNNING, JOB_DONE };
#define MAX_PEEK 4
// One output picture. `last`: the last one made from its source frame, numbered `source`.
struct job { struct mp_image *previous, *in, *out; double t; int state; bool last; uint64_t source; };

struct opts { char *lib, *conf, *model_dir, *rife_model_dir, *device, *stats; int slot, ahead; };
struct priv {
    struct opts *opts;
    struct mp_autoconvert *conv;
    struct mp_pin *in;
    struct mp_image *previous, *pending;
    struct mp_image_params format;
    bool have_format, eof, reported;
    int acc, capacity;
    aji_vk_context *context;
    void *library;
    struct aji_vk_plan plan;
    aji_vk_context *(*create)(const char *,const char *,const char *,const char *,const char *,int);
    int (*configure)(aji_vk_context *,int,int,double,struct aji_vk_plan *);
    int (*process)(aji_vk_context *,const unsigned char *,ptrdiff_t,const unsigned char *,ptrdiff_t,double,unsigned char *,ptrdiff_t);
    const char *(*error)(aji_vk_context *);
    void (*destroy)(aji_vk_context *);
    int (*upcoming)(aji_vk_context *,const unsigned char *const *,const ptrdiff_t *,int);   // optional
    uint64_t source;
    // Pictures in display order, a ring that starts at `head`. Everything below is guarded by
    // `lock`. The engine keeps state from one call to the next (reuse, RIFE pairs): one thread
    // runs the jobs, in order.
    mp_mutex lock;
    mp_cond work, idle;
    mp_thread thread;
    bool locks, started, quit, failed;
    struct job jobs[MAX_JOBS];
    int head, count, sources;
    // Source frames the engine wants to see after the one it computes (what aji_vk_upcoming
    // last returned). `flush`: no further frame is coming for now (end of file, change of
    // format, memory allowance reached): the frames in hand are computed without waiting.
    int peek;
    bool flush;
};
static struct job *job_at(struct priv *p,int i) { return &p->jobs[(p->head+i)%MAX_JOBS]; }
static void job_free(struct job *j) {
    mp_image_unrefp(&j->previous);mp_image_unrefp(&j->in);mp_image_unrefp(&j->out);
    *j=(struct job){0};
}
static MP_THREAD_VOID worker(void *arg) {
    struct mp_filter *f=arg;struct priv *p=f->priv;
    mp_thread_set_name("animejanai");
    mp_mutex_lock(&p->lock);
    while(!p->quit) {
        struct job *j=NULL;int at=0;
        for(int i=0;i<p->count && !j && !p->failed;++i) if(job_at(p,i)->state==JOB_QUEUED) { j=job_at(p,i);at=i; }
        // The source frames that follow this one, as far as the engine asked to see them. They
        // stay alive during the call: a queued job is only freed once no job is running.
        const unsigned char *next[MAX_PEEK];ptrdiff_t strides[MAX_PEEK];int known=0;
        for(int i=at+1;j && i<p->count && known<p->peek;++i) {
            struct job *later=job_at(p,i);
            if(later->source==j->source || !later->last) continue;
            if(!later->in) break;
            next[known]=later->in->planes[0];strides[known++]=later->in->stride[0];
        }
        if(!j || (known<p->peek && !p->flush)) { mp_cond_wait(&p->work,&p->lock);continue; }
        // A running job keeps its place in the ring: nothing is removed before it ends.
        j->state=JOB_RUNNING;
        struct job run=*j;
        mp_mutex_unlock(&p->lock);
        int wanted=p->upcoming?p->upcoming(p->context,next,strides,known):0;
        int result=p->process(p->context,run.previous?run.previous->planes[0]:NULL,
            run.previous?run.previous->stride[0]:0,run.in->planes[0],run.in->stride[0],run.t,
            run.out->planes[0],run.out->stride[0]);
        mp_mutex_lock(&p->lock);
        j->state=JOB_DONE;
        p->peek=MPCLAMP(wanted,0,MAX_PEEK);
        if(result<0) p->failed=true;
        mp_cond_broadcast(&p->idle);
        mp_mutex_unlock(&p->lock);
        mp_filter_wakeup(f);
        mp_mutex_lock(&p->lock);
    }
    mp_mutex_unlock(&p->lock);
    MP_THREAD_RETURN();
}
// Forgets every picture. The one being computed is waited for: an engine call cannot be cut.
static void drain(struct priv *p) {
    if(!p->locks) return;
    mp_mutex_lock(&p->lock);
    for(int i=0;i<p->count;++i) if(job_at(p,i)->state==JOB_QUEUED) job_at(p,i)->state=JOB_DONE;
    for(;;) {
        bool running=false;
        for(int i=0;i<p->count;++i) running|=job_at(p,i)->state==JOB_RUNNING;
        if(!running) break;
        mp_cond_wait(&p->idle,&p->lock);
    }
    for(int i=0;i<p->count;++i) job_free(job_at(p,i));
    p->head=p->count=p->sources=0;p->failed=p->flush=false;
    mp_mutex_unlock(&p->lock);
}
// Nothing more is coming for now: the engine computes what it has.
static void flush(struct priv *p) {
    mp_mutex_lock(&p->lock);p->flush=true;mp_cond_signal(&p->work);mp_mutex_unlock(&p->lock);
}
static void reset(struct mp_filter *f) {
    struct priv *p=f->priv;
    drain(p);
    mp_image_unrefp(&p->previous);mp_image_unrefp(&p->pending);
    p->eof=p->reported=false;p->acc=p->plan.denominator;
}
static void destroy(struct mp_filter *f) {
    struct priv *p=f->priv;reset(f);
    if(p->started) {
        mp_mutex_lock(&p->lock);p->quit=true;mp_cond_signal(&p->work);mp_mutex_unlock(&p->lock);
        mp_thread_join(p->thread);
    }
    if(p->locks) { mp_cond_destroy(&p->work);mp_cond_destroy(&p->idle);mp_mutex_destroy(&p->lock); }
    if(p->context) p->destroy(p->context);
    if(p->library) dlclose(p->library);
}
// The picture a job writes to, with what it inherits from its source frame.
static struct mp_image *blank(struct mp_filter *f,struct mp_image *in) {
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
    if(in->nominal_fps>0) out->nominal_fps=in->nominal_fps*p->plan.numerator/p->plan.denominator;
    return out;
}
static bool drop_pre_seek(struct mp_filter *f,struct mp_image *image) {
    struct mp_stream_info *info=mp_filter_find_stream_info(f);double target;
    return image->pts!=MP_NOPTS_VALUE && info && info->get_hrseek && info->get_hrseek(info,&target) && image->pts<target-.005;
}
static void process(struct mp_filter *f) {
    struct priv *p=f->priv;
    // The oldest picture goes out as soon as it is finished and wanted.
    struct mp_image *ready=NULL;bool busy=false;
    mp_mutex_lock(&p->lock);
    bool failed=p->failed;
    if(!failed && p->count && job_at(p,0)->state==JOB_DONE && mp_pin_in_needs_data(f->ppins[1])) {
        struct job *j=job_at(p,0);
        ready=j->out;j->out=NULL;
        if(j->last) p->sources--;
        job_free(j);
        p->head=(p->head+1)%MAX_JOBS;p->count--;
    }
    for(int i=0;i<p->count;++i) busy|=job_at(p,i)->state!=JOB_DONE;
    int count=p->count,sources=p->sources,peek=p->peek;
    mp_mutex_unlock(&p->lock);
    if(failed) {
        if(!p->reported) MP_ERR(f,"AnimeJaNai inference: %s\n",p->error(p->context));
        p->reported=true;mp_filter_internal_mark_failed(f);return;
    }
    if(ready) {
        mp_pin_in_write(f->ppins[1],MAKE_FRAME(MP_FRAME_VIDEO,ready));
        mp_filter_internal_mark_progress(f);
    }
    // End of file: forwarded once every picture is out.
    if(p->eof) {
        if(!count && mp_pin_in_needs_data(f->ppins[1])) { mp_pin_in_write(f->ppins[1],MP_EOF_FRAME);p->eof=false; }
        return;
    }
    // A frame of another format: the profile is planned again once the engine is idle.
    if(p->pending && (!p->have_format || !mp_image_params_static_equal(&p->format,&p->pending->params))) {
        if(busy) { flush(p);return; }
        struct mp_image *format=p->pending;
        mp_image_unrefp(&p->previous);
        if(format->params.color.transfer==PL_COLOR_TRC_PQ || format->params.color.transfer==PL_COLOR_TRC_HLG) {
            MP_ERR(f,"Vulkan inference currently accepts SDR sources only; use normal playback for HDR.\n");
            mp_filter_internal_mark_failed(f);return;
        }
        if(p->configure(p->context,format->w,format->h,format->nominal_fps,&p->plan)<0) {
            MP_ERR(f,"Vulkan profile: %s\n",p->error(p->context));mp_filter_internal_mark_failed(f);return;
        }
        p->format=format->params;p->have_format=true;p->acc=p->plan.denominator;
        long long bytes=(long long)p->plan.width*p->plan.height*3;
        p->capacity=MPCLAMP(bytes>0?(int)(AHEAD_BYTES/bytes):MAX_JOBS,9,MAX_JOBS);
        MP_INFO(f,"NCNN/Vulkan %dx%d -> %dx%d, RIFE %d/%d, %d frame(s) ahead\n",format->w,format->h,
            p->plan.width,p->plan.height,p->plan.numerator,p->plan.denominator,p->plan.active?p->opts->ahead:1);
    }
    // Read ahead: up to `ahead` source frames computed or being computed, plus the ones the
    // engine wants to see before it starts a frame, within the memory allowed (a source frame
    // gives at most eight pictures).
    if(count+8>p->capacity) { flush(p);return; }
    if(sources>=(p->have_format && p->plan.active?p->opts->ahead+peek:1)) return;
    struct mp_image *in=p->pending;p->pending=NULL;
    if(!in) {
        if(!mp_pin_out_request_data(p->in)) return;
        struct mp_frame frame=mp_pin_out_read(p->in);
        if(frame.type==MP_FRAME_EOF) { p->eof=true;flush(p);mp_filter_internal_mark_progress(f);return; }
        if(frame.type!=MP_FRAME_VIDEO) {
            MP_ERR(f,"unsupported frame type\n");mp_frame_unref(&frame);mp_filter_internal_mark_failed(f);return;
        }
        in=frame.data;
        if(drop_pre_seek(f,in)) { talloc_free(in);mp_filter_internal_mark_progress(f);return; }
        if(!p->have_format || !mp_image_params_static_equal(&p->format,&in->params)) {
            p->pending=in;mp_filter_internal_mark_progress(f);return;
        }
    }
    struct job jobs[8]={0};int n=0;
    if(!p->plan.active) {
        mp_image_unrefp(&p->previous);
        jobs[n++]=(struct job){.out=in,.state=JOB_DONE};in=NULL;
    } else {
        bool pair=p->previous && p->previous->pts!=MP_NOPTS_VALUE && in->pts!=MP_NOPTS_VALUE && in->pts>p->previous->pts;
        if(pair && in->nominal_fps>0 && in->pts-p->previous->pts>3.0/in->nominal_fps)pair=false;
        if(pair && p->plan.numerator>p->plan.denominator) {
            while(p->acc<=p->plan.numerator && n<8) {
                double t=(double)p->acc/p->plan.numerator;
                struct mp_image *out=blank(f,in);if(!out)goto fail;
                out->pts=p->previous->pts+(in->pts-p->previous->pts)*t;
                jobs[n++]=(struct job){.out=out,.t=t};p->acc+=p->plan.denominator;
            }
            p->acc-=p->plan.numerator;
        }
        if(!n) {
            struct mp_image *out=blank(f,in);if(!out)goto fail;
            out->pts=in->pts;
            jobs[n++]=(struct job){.out=out,.t=1};p->acc=p->plan.denominator;
        }
        for(int i=0;i<n;++i) {
            jobs[i].in=mp_image_new_ref(in);MP_HANDLE_OOM(jobs[i].in);
            if(p->previous) { jobs[i].previous=mp_image_new_ref(p->previous);MP_HANDLE_OOM(jobs[i].previous); }
        }
        mp_image_unrefp(&p->previous);p->previous=in;
    }
    jobs[n-1].last=true;
    p->source++;
    mp_mutex_lock(&p->lock);
    for(int i=0;i<n;++i) { jobs[i].source=p->source;*job_at(p,p->count++)=jobs[i]; }
    p->sources++;p->flush=false;
    mp_cond_signal(&p->work);
    mp_mutex_unlock(&p->lock);
    mp_filter_internal_mark_progress(f);
    return;
fail:
    for(int i=0;i<n;++i) job_free(&jobs[i]);
    talloc_free(in);
    mp_filter_internal_mark_failed(f);
}
static const struct mp_filter_info info={.name="animejanai-vulkan",.process=process,.reset=reset,.destroy=destroy,.priv_size=sizeof(struct priv)};
static struct mp_filter *create(struct mp_filter *parent,void *options) {
    struct mp_filter *f=mp_filter_create(parent,&info);
    if(!f){talloc_free(options);return NULL;}
    struct priv *p=f->priv;p->opts=talloc_steal(p,options);
    mp_mutex_init(&p->lock);mp_cond_init(&p->work);mp_cond_init(&p->idle);p->locks=true;
    p->capacity=MAX_JOBS;
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
    *(void **)(&p->upcoming)=dlsym(p->library,"aji_vk_upcoming");
    p->context=p->create(paths[1],paths[2],paths[3],p->opts->device,paths[4],p->opts->slot);
    if(!p->context){MP_ERR(f,"Vulkan backend: %s\n",p->error(NULL));goto fail;}
    // Frames reach the engine as RGB24, whatever the decoder gives.
    p->conv=mp_autoconvert_create(f);
    if(!p->conv)goto fail;
    mp_autoconvert_add_imgfmt(p->conv,IMGFMT_RGB24,0);
    mp_pin_connect(p->conv->f->pins[0],f->ppins[0]);
    p->in=p->conv->f->pins[1];
    if(mp_thread_create(&p->thread,worker,f)){MP_ERR(f,"Vulkan backend: no thread for the engine\n");goto fail;}
    p->started=true;
    return f;
fail:
    talloc_free(f);return NULL;
}
#define OPT_BASE_STRUCT struct opts
static const m_option_t fields[]={
    {"lib",OPT_STRING(lib),.flags=M_OPT_FILE},{"conf",OPT_STRING(conf),.flags=M_OPT_FILE},
    {"model-dir",OPT_STRING(model_dir),.flags=M_OPT_FILE},{"rife-model-dir",OPT_STRING(rife_model_dir),.flags=M_OPT_FILE},
    {"stats",OPT_STRING(stats),.flags=M_OPT_FILE},{"device",OPT_STRING(device)},
    {"slot",OPT_INT(slot),M_RANGE(0,9999)},
    // Source frames computed in advance; 1 = each frame when it is asked for.
    {"ahead",OPT_INT(ahead),M_RANGE(1,16)},{0}
};
const struct mp_user_filter_entry vf_animejanai_vulkan={
    .desc={.description="AnimeJaNai/RIFE NCNN Vulkan (SDR host-frame bridge)",.name="animejanai-vulkan",
        .priv_size=sizeof(struct opts),.priv_defaults=&(const struct opts){.slot=1,.ahead=6},.options=fields},.create=create
};
