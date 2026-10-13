#include "aji_vulkan.h"
#include "aji_conf.h"
#include "rife.h"
#include "gpu.h"
#include "tiles.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace {
std::mutex gpu_mutex;
int contexts = 0;
thread_local std::string create_error;
struct Step { std::unique_ptr<ncnn::Net> net; AjiModelConf conf; };
// The bridge has no frame IDs: decoder buffers can be reused. Only the active RGB bytes,
// compared according to the reuse policy (exact by default, including chroma), identify a
// source. Approximate hits retain their original anchor to avoid accumulating drift.
// Derived pictures are immutable:
// upscale() normalizes its argument in place, so a cached input must be cloned before use.
struct CachedFrame {
    std::vector<unsigned char> source, output, rife_pixels;
    ncnn::Mat prepared, endpoint;
    bool endpoint_served=false;
    uint64_t identity=0, used=0;
};
struct CachedPair {
    uint64_t a=0, b=0;
    bool scene=false;
};
struct Context {
    std::string conf, models, rife_dir, device, stats, error;
    int slot, gpu=-1, width=0, height=0, work_w=0, work_h=0;
    AjiChainConf chain;
    aji_vk_plan plan{};
    std::vector<Step> steps;
    std::unique_ptr<RIFE> rife;
    uint64_t count=0;
    double total_ms=0;
    bool cache=true, rife_gpu_cache=true;
    // Exact content remains the default. Similarity is opt-in: a numerical noise threshold
    // cannot distinguish every low-contrast movement from compression noise.
    aji::Sameness same{0,0};
    uint64_t held_outputs=0;
    CachedFrame frames[2];
    CachedPair pair;
    uint64_t clock=0, identity=0, cache_hits=0, source_preparations=0;
    uint64_t span_inferences=0, rife_inferences=0, pair_preparations=0;
    uint64_t rife_uploads=0, rife_gpu_hits=0;
    uint64_t rife_rgb_preparations=0, rife_packed_outputs=0;
    Context() { std::lock_guard<std::mutex> lock(gpu_mutex); if (!contexts++) ncnn::create_gpu_instance(); }
    ~Context() {
        rife.reset(); steps.clear();
        std::lock_guard<std::mutex> lock(gpu_mutex); if (!--contexts) ncnn::destroy_gpu_instance();
    }
};
void require(bool value, const std::string &message) { if (!value) throw std::runtime_error(message); }
int choose_gpu(const std::string &device) {
    for (int i=0; i<ncnn::get_gpu_count(); ++i) {
        const auto &info=ncnn::get_gpu_info(i);
        if (device.empty() || device==info.device_name()) return i;
    }
    throw std::runtime_error("Requested Vulkan inference device unavailable: " + device);
}
ncnn::Mat rgb(const unsigned char *data, ptrdiff_t stride, int w, int h) {
    return ncnn::Mat::from_pixels(data,ncnn::Mat::PIXEL_RGB,w,h,(int)stride);
}
std::vector<unsigned char> pixels(const ncnn::Mat &m) {
    std::vector<unsigned char> p((size_t)m.w*m.h*3);
    m.to_pixels(p.data(),ncnn::Mat::PIXEL_RGB);
    return p;
}
void resize(ncnn::Mat &m, int w, int h) {
    if (m.w==w && m.h==h) return;
    ncnn::Mat out; ncnn::resize_bilinear(m,out,w,h); m=out;
}
void resize_step(ncnn::Mat &m, const AjiModelConf &conf) {
    double factor=conf.resize_height_before_upscale>0 ? conf.resize_height_before_upscale/m.h
        : conf.resize_factor_before_upscale/100.0;
    if (factor!=1.0) {
        int w=std::max(2,(int)std::lround(m.w*factor)/2*2);
        int h=std::max(2,(int)std::lround(m.h*factor)/2*2);
        resize(m,w,h);
    }
}
ncnn::Mat upscale(Context &c, ncnn::Mat m, bool already_resized=false) {
    for (size_t i=0; i<c.steps.size(); ++i) {
        auto &step=c.steps[i];
        if (!(i==0 && already_resized)) resize_step(m,step.conf);
        require(m.w%2==0 && m.h%2==0,"AnimeJaNai unshuffle requires even dimensions");
        const float norm[3]={1.f/255,1.f/255,1.f/255};
        m.substract_mean_normalize(nullptr,norm);
        auto ex=step.net->create_extractor();
        require(ex.input("in0",m)==0,"NCNN model input failed");
        ncnn::Mat out;
        require(ex.extract("out0",out)==0 && !out.empty() && out.c==3,"NCNN model inference failed");
        ++c.span_inferences;
        const float denorm[3]={255,255,255};
        out.substract_mean_normalize(nullptr,denorm);
        // Keep independent storage for endpoints and the next chain step.
        m=out;
    }
    return m;
}
bool scene_changed(Context &c, const ncnn::Mat &a, const ncnn::Mat &b) {
    // The disabled detector cannot reject a pair. Identical immutable tensors have zero
    // difference. Neither case needs a full-resolution CPU traversal (RIFE still runs).
    if (!(c.chain.rife_scd_threshold>0) || a.data==b.data) return false;
    double difference=0;
    for (int channel=0; channel<3; ++channel) {
        const float *x=a.channel(channel), *y=b.channel(channel);
        for (int k=0; k<a.w*a.h; ++k) difference+=std::abs(x[k]-y[k]);
    }
    difference/=255.0*a.w*a.h*3;
    return c.chain.rife_scd_threshold>0 && difference>c.chain.rife_scd_threshold;
}
ncnn::Mat interpolate_pixels(Context &c, const ncnn::Mat &a,
    const std::vector<unsigned char> &pa, const std::vector<unsigned char> &pb, float t,
    uint64_t aid=0, uint64_t bid=0, bool packed_output=false) {
    // ncnn's external-storage constructor predates const input views; RIFE::process takes
    // const Mat references and only reads these packed input bytes.
    ncnn::Mat ia(a.w,a.h,const_cast<unsigned char *>(pa.data()),(size_t)3,3);
    ncnn::Mat ib(a.w,a.h,const_cast<unsigned char *>(pb.data()),(size_t)3,3);
    ncnn::Mat out(a.w,a.h,(size_t)3,3);
    if (c.rife_gpu_cache && aid && bid) {
        uint64_t uploads_before, hits_before, uploads_after, hits_after; size_t bytes;
        c.rife->cache_stats(uploads_before,hits_before,bytes);
        require(c.rife->process_cached(ia,ib,t,out,aid,bid)==0,"RIFE Vulkan inference failed");
        c.rife->cache_stats(uploads_after,hits_after,bytes);
        c.rife_uploads+=uploads_after-uploads_before;
        c.rife_gpu_hits+=hits_after-hits_before;
    } else require(c.rife->process(ia,ib,t,out)==0,"RIFE Vulkan inference failed");
    ++c.rife_inferences;
    // RIFE's postprocessing already produced RGB24. If it ends the chain, these
    // exact integer pixels can be copied straight to the caller. The cached
    // sources also own the endpoint views returned by RIFE at timestep 0 or 1.
    if (packed_output) { ++c.rife_packed_outputs; return out; }
    return rgb((unsigned char *)out.data,a.w*3,a.w,a.h);
}
ncnn::Mat interpolate(Context &c, const ncnn::Mat &a, const ncnn::Mat &b, float t) {
    if (scene_changed(c,a,b)) return a.clone();
    auto pa=pixels(a), pb=pixels(b);
    return interpolate_pixels(c,a,pa,pb,t);
}
bool same_source(const CachedFrame &frame, const unsigned char *data, ptrdiff_t stride, int w, int h, const aji::Sameness &same) {
    const size_t row=(size_t)w*3;
    if (!frame.identity || frame.source.size()!=row*(size_t)h) return false;
    return aji::picture_unchanged(data,stride,frame.source.data(),(ptrdiff_t)row,w,h,same);
}
CachedFrame &prepare_frame(Context &c, const unsigned char *data, ptrdiff_t stride) {
    for (auto &frame:c.frames) {
        if (same_source(frame,data,stride,c.width,c.height,c.same)) {
            frame.used=++c.clock;
            ++c.cache_hits;
            return frame;
        }
    }
    auto &frame=c.frames[c.frames[0].used<=c.frames[1].used?0:1];
    // Mark invalid until both the source and its derived picture have been prepared.
    frame.identity=0; frame.prepared=ncnn::Mat(); frame.endpoint=ncnn::Mat();
    frame.output.clear(); frame.endpoint_served=false;
    frame.rife_pixels.clear();
    const size_t row=(size_t)c.width*3;
    frame.source.resize(row*(size_t)c.height);
    for (int y=0;y<c.height;++y)
        std::memcpy(frame.source.data()+(size_t)y*row,data+(ptrdiff_t)y*stride,row);
    auto image=rgb(frame.source.data(),(ptrdiff_t)row,c.width,c.height);
    if (c.rife && c.chain.rife_before_upscale) resize(image,c.work_w,c.work_h);
    else image=upscale(c,image);
    frame.prepared=image;
    frame.identity=++c.identity; frame.used=++c.clock;
    ++c.source_preparations;
    return frame;
}
ncnn::Mat endpoint(Context &c, CachedFrame &frame) {
    if (!(c.rife && c.chain.rife_before_upscale)) return frame.prepared;
    if (frame.endpoint.empty()) frame.endpoint=upscale(c,frame.prepared.clone(),true);
    return frame.endpoint;
}
const std::vector<unsigned char> &rife_pixels(Context &c, CachedFrame &frame) {
    if (frame.rife_pixels.empty()) {
        frame.rife_pixels.resize((size_t)frame.prepared.w*frame.prepared.h*3);
        frame.prepared.to_pixels(frame.rife_pixels.data(),ncnn::Mat::PIXEL_RGB);
        ++c.rife_rgb_preparations;
    }
    return frame.rife_pixels;
}
ncnn::Mat interpolate_pair(Context &c, CachedFrame &a, CachedFrame &b, float t, bool &packed_output) {
    if (c.pair.a!=a.identity || c.pair.b!=b.identity) {
        c.pair.a=c.pair.b=0;
        c.pair.scene=scene_changed(c,a.prepared,b.prepared);
        c.pair.a=a.identity; c.pair.b=b.identity;
        ++c.pair_preparations;
    }
    // The caller handles a scene cut as the previous endpoint. It never normalizes this view.
    if (c.pair.scene) return a.prepared;
    const auto &pa=rife_pixels(c,a), &pb=rife_pixels(c,b);
    packed_output=!c.chain.rife_before_upscale;
    return interpolate_pixels(c,a.prepared,pa,pb,t,a.identity,b.identity,packed_output);
}
void write_endpoint(CachedFrame &frame, const ncnn::Mat &result, unsigned char *output, ptrdiff_t stride) {
    const size_t row=(size_t)result.w*3;
    // After-upscale RIFE already packed this endpoint using the same conversion.
    // Before-upscale endpoints use independent tensors and keep the path below.
    if (!frame.rife_pixels.empty() && result.data==frame.prepared.data) {
        for (int y=0;y<result.h;++y)
            std::memcpy(output+(ptrdiff_t)y*stride,frame.rife_pixels.data()+(size_t)y*row,row);
        frame.endpoint_served=true;
        return;
    }
    // Only retain packed pixels after an endpoint is requested again: changing-only playback
    // pays no extra full-output copy. Later held frames avoid float-to-byte conversion as well.
    if (frame.output.empty() && frame.endpoint_served) {
        frame.output.resize(row*(size_t)result.h);
        result.to_pixels(frame.output.data(),ncnn::Mat::PIXEL_RGB,(int)row);
    }
    if (frame.output.empty()) result.to_pixels(output,ncnn::Mat::PIXEL_RGB,(int)stride);
    else for (int y=0;y<result.h;++y)
        std::memcpy(output+(ptrdiff_t)y*stride,frame.output.data()+(size_t)y*row,row);
    frame.endpoint_served=true;
}
void load_steps(Context &c) {
    c.steps.clear();
    for (const auto &model:c.chain.models) {
        if (model.name.empty()) continue;
        require(model.frames<=1,"Temporal AnimeJaNai models are not supported by the Vulkan backend");
        std::string base=c.models+"/"+model.name+".ncnn";
        require(std::filesystem::is_regular_file(base+".param") && std::filesystem::is_regular_file(base+".bin"),
            "Model not converted for Vulkan: " + model.name);
        Step step; step.conf=model; step.net=std::make_unique<ncnn::Net>();
        step.net->opt.use_vulkan_compute=true;
        step.net->opt.use_fp16_storage=true;
        // Shipped FP16 SPAN weights; validate GPU output against ONNX Runtime.
        step.net->opt.use_fp16_arithmetic=true;
        step.net->opt.num_threads=2;
        // NCNN computes 3x3 convolutions through Winograd transforms by default. On a GPU whose
        // matrix units it can use (cooperative matrices), the direct product is faster and its
        // FP16 result closer to ONNX Runtime: measured on an RTX 4070 Ti, 720p, 42.7 -> 35.7 ms
        // (Performance) and 61.9 -> 44.1 ms (Balanced), largest difference with the reference
        // 5 instead of 10 levels. Without matrix units Winograd is the faster one (43 against
        // 53 ms). Only NVIDIA was measured: other GPUs keep NCNN's choice.
        const ncnn::GpuInfo &gpu=ncnn::get_gpu_info(c.gpu);
        if (gpu.vendor_id()==0x10de && gpu.support_cooperative_matrix()) step.net->opt.use_winograd_convolution=false;
        // To measure another GPU (1 = on, 0 = off): AJI_VK_WINOGRAD, AJI_VK_WINOGRAD43,
        // AJI_VK_COOPMAT (matrix units), AJI_VK_SGEMM.
        auto kernel=[](const char *name,bool &option) { if (const char *v=std::getenv(name); v && *v) option=std::atoi(v)!=0; };
        kernel("AJI_VK_WINOGRAD",step.net->opt.use_winograd_convolution);
        kernel("AJI_VK_WINOGRAD43",step.net->opt.use_winograd43_convolution);
        kernel("AJI_VK_COOPMAT",step.net->opt.use_cooperative_matrix);
        kernel("AJI_VK_SGEMM",step.net->opt.use_sgemm_convolution);
        step.net->set_vulkan_device(c.gpu);
        require(step.net->load_param((base+".param").c_str())==0 && step.net->load_model((base+".bin").c_str())==0,
            "Cannot load NCNN model " + model.name);
        c.steps.push_back(std::move(step));
    }
}
}
extern "C" uint32_t aji_vk_version(void) { return AJI_VK_ABI; }
extern "C" aji_vk_context *aji_vk_create(const char *conf, const char *models,
    const char *rife, const char *device, const char *stats, int slot) {
    try {
        auto c=std::make_unique<Context>();
        c->conf=conf?conf:"";c->models=models?models:"";c->rife_dir=rife?rife:"";
        c->device=device?device:"";c->stats=stats?stats:"";c->slot=slot;
        const char *cache=std::getenv("AJI_VK_CACHE");
        c->cache=!(cache && std::strcmp(cache,"0")==0);
        const char *rife_cache=std::getenv("AJI_VK_RIFE_GPU_CACHE");
        c->rife_gpu_cache=!(rife_cache && std::strcmp(rife_cache,"0")==0);
        // AJI_VK_SAME=similar opts in to the shared drawing detector. Explicit thresholds
        // also opt in. AJI_VK_SAME=exact takes precedence over both threshold variables.
        const char *same=std::getenv("AJI_VK_SAME");
        require(!same || !*same || std::strcmp(same,"exact")==0 || std::strcmp(same,"similar")==0,
            "AJI_VK_SAME must be exact or similar");
        if (!(same && std::strcmp(same,"exact")==0)) {
            if (same && std::strcmp(same,"similar")==0) c->same=aji::Sameness{};
            if (const char *v=std::getenv("AJI_REUSE_THRESHOLD"); v && *v) {
                c->same=aji::Sameness{};
                c->same.threshold=std::min(8.0,std::max(0.0,std::atof(v)));
            }
            if (const char *v=std::getenv("AJI_REUSE_PEAK"); v && *v) c->same.peak=std::min(255,std::max(0,std::atoi(v)));
        }
        c->gpu=choose_gpu(c->device); return c.release();
    } catch (const std::exception &e) { create_error=e.what();return nullptr; }
}
extern "C" int aji_vk_configure(aji_vk_context *context,int width,int height,double fps,aji_vk_plan *plan) {
    auto &c=*(Context *)context;
    try {
        require(width>0 && height>0 && width<=16384 && height<=16384,"Invalid source dimensions");
        require(width%2==0 && height%2==0,"Vulkan spatial profiles require even source dimensions");
        c.rife.reset();c.steps.clear();c.width=width;c.height=height;
        for (auto &frame:c.frames) frame=CachedFrame();
        c.pair=CachedPair();
        c.plan={width,height,1,1,0};
        if (c.slot==0) { *plan=c.plan;return 0; }
        AjiConf conf;std::string error;
        require(aji_conf_load(c.conf.c_str(),&conf,&error),error);
        auto found=conf.slots.find(c.slot);
        require(found!=conf.slots.end(),"Requested Vulkan profile missing");
        bool matched=false;
        for (auto &chain:found->second.chains) {
            double px=(double)width*height;
            if (px>=chain.min_px && px<=chain.max_px && fps>=chain.min_fps && fps<=chain.max_fps) {
                c.chain=chain;matched=true;break;
            }
        }
        if (!matched) { *plan=c.plan;return 0; }
        load_steps(c);
        ncnn::Mat shape(width,height,3);
        if (!c.steps.empty()) resize_step(shape,c.steps[0].conf);
        c.work_w=shape.w;c.work_h=shape.h;
        int w=width,h=height;
        for (auto &step:c.steps) {
            ncnn::Mat size(w,h,3);resize_step(size,step.conf);
            w=size.w*2;h=size.h*2; // Supported AnimeJaNai spatial models are 2x.
        }
        require(!c.steps.empty() || c.chain.rife,"Vulkan profile has neither upscale nor RIFE");
        int num=c.chain.rife_factor_num,den=c.chain.rife_factor_den;
        require(den>0 && num>=den && num<=8*den,"RIFE factor must be between 1 and 8");
        if (c.chain.rife && num>den) {
            require(c.chain.rife_model==46,"Vulkan currently supports converted RIFE 4.6 (model code 46)");
            std::string dir=c.rife_dir+"/rife-v4.6";
            require(std::filesystem::is_regular_file(dir+"/flownet.param") && std::filesystem::is_regular_file(dir+"/flownet.bin"),"RIFE 4.6 Vulkan model missing");
            require(dir.size()<220,"RIFE model path too long");
            c.rife=std::make_unique<RIFE>(c.gpu,false,c.chain.rife_ensemble,false,2,false,true);
            require(c.rife->load(dir)==0,"Cannot load RIFE 4.6");
        }
        int gcd=std::gcd(num,den);
        c.plan={w,h,c.rife?num/gcd:1,c.rife?den/gcd:1,1};*plan=c.plan;
        return 0;
    } catch(const std::exception &e) { c.error=e.what();return -1; }
}
extern "C" int aji_vk_process(aji_vk_context *context,const unsigned char *previous,ptrdiff_t previous_stride,
    const unsigned char *current,ptrdiff_t current_stride,double timestep,unsigned char *output,ptrdiff_t output_stride) {
    auto &c=*(Context *)context;
    try {
        auto start=std::chrono::steady_clock::now();
        require(current && output && timestep>=0 && timestep<=1,"Invalid frame arguments");
        ncnn::Mat result;
        bool packed_output=false;
        CachedFrame *output_frame=nullptr;
        if (!c.plan.active) result=rgb(current,current_stride,c.width,c.height);
        else if (c.cache) {
            if (!previous || timestep>=1 || !c.rife) {
                output_frame=&prepare_frame(c,current,current_stride);
                result=endpoint(c,*output_frame);
            }
            else {
                auto &a=prepare_frame(c,previous,previous_stride);
                auto &b=prepare_frame(c,current,current_stride);
                if (&a==&b && c.same.threshold>0) {
                    // The two frames are the same drawing: the picture between them is that drawing.
                    // (With identical bytes only, the interpolation runs as it always did.)
                    result=endpoint(c,a); output_frame=&a; ++c.held_outputs;
                } else {
                    result=interpolate_pair(c,a,b,(float)timestep,packed_output);
                    if (c.pair.scene) { result=endpoint(c,a); output_frame=&a; }
                    else if (c.chain.rife_before_upscale) result=upscale(c,result,true);
                }
            }
        } else {
            auto b=rgb(current,current_stride,c.width,c.height);
            if (!previous || timestep>=1 || !c.rife) result=upscale(c,b);
            else {
                auto a=rgb(previous,previous_stride,c.width,c.height);
                if (c.chain.rife_before_upscale) {
                    if (!c.steps.empty()) { resize(a,c.work_w,c.work_h);resize(b,c.work_w,c.work_h); }
                    result=upscale(c,interpolate(c,a,b,(float)timestep),true);
                } else { a=upscale(c,a);b=upscale(c,b);result=interpolate(c,a,b,(float)timestep); }
            }
        }
        require(result.w==c.plan.width && result.h==c.plan.height,"Model output dimensions differ from the configured 2x profile");
        if (packed_output) {
            const size_t row=(size_t)result.w*3;
            for (int y=0;y<result.h;++y)
                std::memcpy(output+(ptrdiff_t)y*output_stride,(unsigned char *)result.data+(size_t)y*row,row);
        }
        else if (output_frame) write_endpoint(*output_frame,result,output,output_stride);
        else result.to_pixels(output,ncnn::Mat::PIXEL_RGB,(int)output_stride);
        double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        c.total_ms+=ms;++c.count;
        if (!c.stats.empty()) {
            uint64_t uploads=0,hits=0; size_t bytes=0;
            if (c.rife) c.rife->cache_stats(uploads,hits,bytes);
            std::ofstream f(c.stats);
            f<<"Backend: NCNN/Vulkan\nGPU: "<<ncnn::get_gpu_info(c.gpu).device_name()
             <<"\nAnimeJaNai models: "<<c.steps.size()<<"\nRIFE: "<<(c.rife?"4.6":"off")
             <<"\nOutput: "<<result.w<<"x"<<result.h<<"\nFrames: "<<c.count
             <<"\nInference ms: "<<ms<<"\nAverage inference ms: "<<c.total_ms/c.count<<"\n";
            f<<"Source cache: "<<(c.cache?"on":"off");
            if (c.cache && c.same.threshold>0) f<<", same drawing within "<<c.same.threshold<<" level a block and "<<c.same.peak<<" a byte";
            else if (c.cache) f<<", identical bytes only";
            f<<"\nHeld RIFE outputs reused: "<<c.held_outputs
             <<"\nSource preparations: "<<c.source_preparations<<"\nSource cache hits: "<<c.cache_hits
             <<"\nSPAN inferences: "<<c.span_inferences<<"\nRIFE inferences: "<<c.rife_inferences
             <<"\nPair preparations: "<<c.pair_preparations
             <<"\nRIFE GPU input cache: "<<(c.cache && c.rife_gpu_cache?"on":"off")
             <<"\nRIFE cached uploads: "<<c.rife_uploads<<"\nRIFE GPU input hits: "<<c.rife_gpu_hits
             <<"\nRIFE cached tensor bytes: "<<bytes<<"\n";
            f<<"RIFE RGB preparations: "<<c.rife_rgb_preparations
             <<"\nRIFE direct RGB outputs: "<<c.rife_packed_outputs<<"\n";
        }
        return 0;
    }catch(const std::exception &e){c.error=e.what();return -1;}
}
extern "C" const char *aji_vk_error(aji_vk_context *c) { return c?((Context *)c)->error.c_str():create_error.c_str(); }
extern "C" void aji_vk_destroy(aji_vk_context *c) { delete (Context *)c; }
