#include "aji_vulkan.h"
#include "aji_conf.h"
#include "rife.h"
#include "gpu.h"
#include <algorithm>
#include <chrono>
#include <cmath>
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
struct Context {
    std::string conf, models, rife_dir, device, stats, error;
    int slot, gpu=-1, width=0, height=0, work_w=0, work_h=0;
    AjiChainConf chain;
    aji_vk_plan plan{};
    std::vector<Step> steps;
    std::unique_ptr<RIFE> rife;
    uint64_t count=0;
    double total_ms=0;
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
        const float denorm[3]={255,255,255};
        out.substract_mean_normalize(nullptr,denorm);
        // Keep independent storage for endpoints and the next chain step.
        m=out;
    }
    return m;
}
ncnn::Mat interpolate(Context &c, const ncnn::Mat &a, const ncnn::Mat &b, float t) {
    double difference=0;
    for (int channel=0; channel<3; ++channel) {
        const float *x=a.channel(channel), *y=b.channel(channel);
        for (int k=0; k<a.w*a.h; ++k) difference+=std::abs(x[k]-y[k]);
    }
    difference/=255.0*a.w*a.h*3;
    if (c.chain.rife_scd_threshold>0 && difference>c.chain.rife_scd_threshold) return a.clone();
    auto pa=pixels(a), pb=pixels(b);
    ncnn::Mat ia(a.w,a.h,pa.data(),(size_t)3,3), ib(b.w,b.h,pb.data(),(size_t)3,3);
    ncnn::Mat out(a.w,a.h,(size_t)3,3);
    require(c.rife->process(ia,ib,t,out)==0,"RIFE Vulkan inference failed");
    return rgb((unsigned char *)out.data,a.w*3,a.w,a.h);
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
        c->gpu=choose_gpu(c->device); return c.release();
    } catch (const std::exception &e) { create_error=e.what();return nullptr; }
}
extern "C" int aji_vk_configure(aji_vk_context *context,int width,int height,double fps,aji_vk_plan *plan) {
    auto &c=*(Context *)context;
    try {
        require(width>0 && height>0 && width<=16384 && height<=16384,"Invalid source dimensions");
        require(width%2==0 && height%2==0,"Vulkan spatial profiles require even source dimensions");
        c.rife.reset();c.steps.clear();c.width=width;c.height=height;
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
        ncnn::Mat b=rgb(current,current_stride,c.width,c.height),result;
        if (!c.plan.active) result=b;
        else if (!previous || timestep>=1 || !c.rife) result=upscale(c,b);
        else {
            auto a=rgb(previous,previous_stride,c.width,c.height);
            if (c.chain.rife_before_upscale) {
                if (!c.steps.empty()) { resize(a,c.work_w,c.work_h);resize(b,c.work_w,c.work_h); }
                result=upscale(c,interpolate(c,a,b,(float)timestep),true);
            } else { a=upscale(c,a);b=upscale(c,b);result=interpolate(c,a,b,(float)timestep); }
        }
        require(result.w==c.plan.width && result.h==c.plan.height,"Model output dimensions differ from the configured 2x profile");
        result.to_pixels(output,ncnn::Mat::PIXEL_RGB,(int)output_stride);
        double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        c.total_ms+=ms;++c.count;
        if (!c.stats.empty()) {
            std::ofstream f(c.stats);
            f<<"Backend: NCNN/Vulkan\nGPU: "<<ncnn::get_gpu_info(c.gpu).device_name()
             <<"\nAnimeJaNai models: "<<c.steps.size()<<"\nRIFE: "<<(c.rife?"4.6":"off")
             <<"\nOutput: "<<result.w<<"x"<<result.h<<"\nFrames: "<<c.count
             <<"\nInference ms: "<<ms<<"\nAverage inference ms: "<<c.total_ms/c.count<<"\n";
        }
        return 0;
    }catch(const std::exception &e){c.error=e.what();return -1;}
}
extern "C" const char *aji_vk_error(aji_vk_context *c) { return c?((Context *)c)->error.c_str():create_error.c_str(); }
extern "C" void aji_vk_destroy(aji_vk_context *c) { delete (Context *)c; }
