// Real C ABI consumer. Controlled callbacks establish queue/lifetime behavior
// without timing guesses; neural mode compares one new worker result externally.
#include "surface_async.h"
#include "aji_vulkan.h"
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <future>
#include <iostream>
#include <mutex>
#include <vector>

struct Gate {
    std::mutex mutex;std::condition_variable changed;
    bool entered=false,open=false;
    void block() {std::unique_lock<std::mutex> l(mutex);entered=true;changed.notify_all();
        assert(changed.wait_for(l,std::chrono::seconds(10),[&]{return open;}));}
    void wait() {std::unique_lock<std::mutex> l(mutex);
        assert(changed.wait_for(l,std::chrono::seconds(10),[&]{return entered;}));}
    void release() {std::lock_guard<std::mutex> l(mutex);open=true;changed.notify_all();}
};
struct Owner {
    std::atomic<int> held{0},retains{0},releases{0};
    Gate *gate=nullptr;
    static void retain(void *p) {auto &o=*(Owner *)p;++o.retains;++o.held;}
    static void release(void *p) {auto &o=*(Owner *)p;if(o.gate)o.gate->block();++o.releases;--o.held;}
    void balanced() const {assert(held==0 && retains==releases);}
};
struct Frame {
    int w,h,stride;std::vector<unsigned char> pixels;Owner owner;aji_surface_v1 view{};
    Frame(int width,int height,uint64_t sequence,int value,bool destination=false):w(width),h(height),stride(3*w+(destination?19:17)),pixels((size_t)stride*h,0xa5) {
        if(!destination)for(int y=0;y<h;++y)for(int x=0;x<w;++x)for(int c=0;c<3;++c)
            pixels[(size_t)y*stride+3*x+c]=(unsigned char)(x*3+y*7+c*13+value*37);
        view.struct_size=sizeof(view);view.version=1;view.resource_kind=view.device_kind=AJI_RESOURCE_HOST;
        view.format=AJI_SURFACE_RGB8;view.width=w;view.height=h;view.plane_count=1;
        view.color={AJI_SURFACE_MATRIX_RGB,AJI_SURFACE_PRIM_709,AJI_SURFACE_TRC_SRGB,
            AJI_SURFACE_RANGE_FULL,AJI_SURFACE_SITING_UNKNOWN,8,AJI_SURFACE_QUANT_REFERENCE_RGB8,AJI_SURFACE_DITHER_NONE};
        view.planes[0]={pixels.data(),pixels.size(),0,stride};view.sequence=sequence;view.generation=1;
        view.time_flags=AJI_SURFACE_HAS_PTS|AJI_SURFACE_HAS_DURATION;
        view.pts=(int64_t)sequence;view.duration=1;view.timebase_num=1;view.timebase_den=24;
        view.owner=&owner;view.retain=Owner::retain;view.release=Owner::release;
    }
    void equals(const Frame &other) const {assert(w==other.w && h==other.h);
        for(int y=0;y<h;++y)assert(!std::memcmp(pixels.data()+(size_t)y*stride,other.pixels.data()+(size_t)y*other.stride,3*w));}
    void sentinel() const {for(auto v:pixels)assert(v==0xa5);}
};
struct Api {
    void *library;
    decltype(&aji_vk_create) create;decltype(&aji_vk_configure) configure;decltype(&aji_vk_destroy) destroy;
    decltype(&aji_vk_process) legacy;decltype(&aji_vk_error) error;
    decltype(&aji_surface_process_v1) sync;
    decltype(&aji_surface_async_query_v1) query;decltype(&aji_surface_async_enable_v1) enable;
    decltype(&aji_surface_submit_v1) submit;decltype(&aji_surface_complete_v1) complete;
    decltype(&aji_surface_drain_v1) drain;decltype(&aji_surface_async_disable_v1) disable;
    template<class T>T get(const char *name) {auto fn=(T)dlsym(library,name);assert(fn);return fn;}
    explicit Api(const char *path):library(dlopen(path,RTLD_NOW|RTLD_LOCAL)) {assert(library);
        create=get<decltype(create)>("aji_vk_create");configure=get<decltype(configure)>("aji_vk_configure");
        destroy=get<decltype(destroy)>("aji_vk_destroy");legacy=get<decltype(legacy)>("aji_vk_process");error=get<decltype(error)>("aji_vk_error");
        sync=get<decltype(sync)>("aji_surface_process_v1");query=get<decltype(query)>("aji_surface_async_query_v1");
        enable=get<decltype(enable)>("aji_surface_async_enable_v1");submit=get<decltype(submit)>("aji_surface_submit_v1");
        complete=get<decltype(complete)>("aji_surface_complete_v1");drain=get<decltype(drain)>("aji_surface_drain_v1");
        disable=get<decltype(disable)>("aji_surface_async_disable_v1");}
    ~Api() {dlclose(library);}
    aji_surface_submit_v1_request request(Frame *a,Frame &b,Frame &out,double t=1) {
        aji_surface_submit_v1_request r{};r.struct_size=sizeof(r);r.version=1;
        r.previous=a?&a->view:nullptr;r.current=&b.view;r.output=&out.view;r.timestep=t;return r;
    }
    uint64_t send(void *ctx,aji_surface_submit_v1_request &r) {uint64_t t=0;assert(submit(ctx,&r,&t)==0 && t);return t;}
    aji_surface_completion_v1 poll(void *ctx,uint64_t ticket,uint32_t flags=0) {
        aji_surface_completion_v1 r{};assert(complete(ctx,ticket,flags,&r,sizeof(r))==0);
        assert(r.version==1 && r.struct_size==sizeof(r) && r.ticket==ticket);return r;
    }
};

int main(int argc,char **argv) {
    assert(argc==2 || argc==8);Api api(argv[1]);
    if(argc==8) {
        const int w=std::stoi(argv[5]),h=72;void *ctx=api.create(argv[2],argv[3],argv[4],argv[6],nullptr,1);assert(ctx);
        aji_vk_plan plan{};assert(api.configure(ctx,w,h,24,&plan)==0);
        assert(plan.width==2*w && plan.height==2*h && plan.numerator==2 && plan.denominator==1);
        assert(api.enable(ctx,2)==0);
        Frame a(w,h,1,0),b(w,h,2,1),out(2*w,2*h,3,0,true);
        auto request=api.request(&a,b,out,.5);const auto saved_a=a.view,saved_b=b.view,saved_out=out.view;
        const auto ticket=api.send(ctx,request);assert(api.drain(ctx,0)==0);
        auto result=api.poll(ctx,ticket,AJI_SURFACE_CONSUME_RESULT);
        if(result.state!=AJI_SURFACE_FINISHED)std::cerr<<result.message<<'\n';
        assert(result.state==AJI_SURFACE_FINISHED && result.status==0);
        a.owner.balanced();b.owner.balanced();out.owner.balanced();
        assert(a.owner.retains==1 && b.owner.retains==1 && out.owner.retains==1);
        assert(!std::memcmp(&saved_a,&a.view,sizeof(a.view)) && !std::memcmp(&saved_b,&b.view,sizeof(b.view))
            && !std::memcmp(&saved_out,&out.view,sizeof(out.view)));
        std::ofstream pixels(argv[7],std::ios::binary);
        for(int y=0;y<out.h;++y) {
            pixels.write((const char *)out.pixels.data()+(size_t)y*out.stride,out.w*3);
            for(int x=out.w*3;x<out.stride;++x)assert(out.pixels[(size_t)y*out.stride+x]==0xa5);
        }
        pixels.close();assert(pixels);
        auto fail=(void (*)())dlsym(RTLD_DEFAULT,"aji_test_ort_fail_next_run");assert(fail);
        Frame c(w,h,4,2),bad(2*w,2*h,5,0,true);request=api.request(nullptr,c,bad);
        fail();const auto error_ticket=api.send(ctx,request);assert(api.drain(ctx,0)==0);
        result=api.poll(ctx,error_ticket,AJI_SURFACE_CONSUME_RESULT);
        assert(result.state==AJI_SURFACE_FAILED && result.status==AJI_SURFACE_ENGINE_ERROR);
        assert(std::strstr(result.message,"injected surface execution failure"));
        c.owner.balanced();bad.owner.balanced();assert(c.owner.retains==1 && bad.owner.retains==1);
        assert(api.disable(ctx)==0);api.destroy(ctx);
        std::cout<<"{\"passed\":true,\"neural_output\":1,\"owners_acquired_once\":true,\"deferred_error\":true,\"descriptors_unchanged\":true}\n";
        return 0;
    }
    void *ctx=api.create(nullptr,nullptr,nullptr,"cpu",nullptr,0);assert(ctx);aji_vk_plan plan{};
    aji_surface_async_caps_v1 caps{};assert(api.query(ctx,1,&caps,sizeof(caps))==AJI_SURFACE_UNSUPPORTED);
    assert(api.configure(ctx,4,2,24,&plan)==0 && api.query(ctx,1,&caps,sizeof(caps))==0);
    assert(caps.max_capacity==64 && caps.dependency_mask==1 && caps.owner_callbacks_required==1);
    auto saved=caps;assert(api.query(ctx,2,&caps,sizeof(caps))<0 && !std::memcmp(&saved,&caps,sizeof(caps)));
    assert(api.query(ctx,1,&caps,1)<0 && !std::memcmp(&saved,&caps,sizeof(caps)));
    assert(api.enable(ctx,0)<0 && api.enable(ctx,65)<0 && api.enable(ctx,2)==0);
    assert(api.enable(ctx,2)==AJI_SURFACE_ASYNC_BUSY);
    Frame a(4,2,1,0),b(4,2,2,1),c(4,2,3,2),out1(4,2,11,0,true),out2(4,2,12,0,true),out3(4,2,13,0,true);
    Gate running;out1.owner.gate=&running;
    auto r1=api.request(nullptr,a,out1);auto r2=api.request(&a,b,out2,.5);auto r3=api.request(nullptr,c,out3);
    const auto t1=api.send(ctx,r1);running.wait();const auto t2=api.send(ctx,r2);assert(t2>t1);
    assert(api.poll(ctx,t1,AJI_SURFACE_CONSUME_RESULT).state==AJI_SURFACE_PENDING);
    assert(api.poll(ctx,t2).state==AJI_SURFACE_PENDING);
    uint64_t refused=999;assert(api.submit(ctx,&r3,&refused)==AJI_SURFACE_ASYNC_BUSY && !refused);
    assert(c.owner.retains==0 && out3.owner.retains==0);
    assert(api.configure(ctx,4,2,24,&plan)<0);
    assert(api.sync(ctx,nullptr,&a.view,1,&out3.view)==AJI_SURFACE_ASYNC_BUSY);
    assert(api.legacy(ctx,nullptr,0,a.pixels.data(),a.stride,1,out3.pixels.data(),out3.stride)<0);
    assert(std::strstr(api.error(ctx),"Async surface queue"));
    // Originals can be reused after submission; snapshots still refer to b.
    auto original_b=b.view;b.view.width=0;r2.timestep=-1;
    running.release();assert(api.drain(ctx,0)==0);b.view=original_b;
    assert(api.poll(ctx,t1).state==AJI_SURFACE_FINISHED && api.poll(ctx,t2).state==AJI_SURFACE_FINISHED);
    out1.equals(a);out2.equals(b);a.owner.balanced();b.owner.balanced();out1.owner.balanced();out2.owner.balanced();
    assert(a.owner.retains==2 && b.owner.retains==1 && out1.owner.retains==1 && out2.owner.retains==1);
    refused=999;assert(api.submit(ctx,&r3,&refused)==AJI_SURFACE_ASYNC_BUSY && !refused); // done slots still bounded
    api.poll(ctx,t1,AJI_SURFACE_CONSUME_RESULT);const auto t3=api.send(ctx,r3);assert(t3>t2);
    assert(api.drain(ctx,AJI_SURFACE_DROP_RESULTS)==0);out3.equals(c);
    aji_surface_completion_v1 completion{};assert(api.complete(ctx,t2,0,&completion,sizeof(completion))<0);
    c.owner.balanced();out3.owner.balanced();
    // Running work is retained; queued work is cancelled and released first.
    Frame d(4,2,4,3),e(4,2,5,4),out4(4,2,14,0,true),out5(4,2,15,0,true);
    Gate active,cancelled;out4.owner.gate=&active;out5.owner.gate=&cancelled;
    auto r4=api.request(nullptr,d,out4),r5=api.request(nullptr,e,out5);
    const auto t4=api.send(ctx,r4);active.wait();const auto t5=api.send(ctx,r5);
    auto draining=std::async(std::launch::async,[&]{return api.drain(ctx,AJI_SURFACE_CANCEL_QUEUED);});
    cancelled.wait();assert(out4.owner.held==1 && out5.owner.held==1);
    cancelled.release();active.release();assert(draining.get()==0);
    assert(api.poll(ctx,t4,1).state==AJI_SURFACE_FINISHED && api.poll(ctx,t5,1).state==AJI_SURFACE_CANCELLED);
    out5.sentinel();d.owner.balanced();e.owner.balanced();out4.owner.balanced();out5.owner.balanced();
    r3.dependency_count=1;refused=999;assert(api.submit(ctx,&r3,&refused)==AJI_SURFACE_UNSUPPORTED && !refused);r3.dependency_count=0;
    r3.execution_queue=(void *)1;assert(api.submit(ctx,&r3,&refused)==AJI_SURFACE_UNSUPPORTED);r3.execution_queue=nullptr;
    r3.struct_size=1;assert(api.submit(ctx,&r3,&refused)==AJI_SURFACE_INVALID);r3.struct_size=sizeof(r3);
    auto owned=c.view;c.view.retain=nullptr;c.view.release=nullptr;
    assert(api.submit(ctx,&r3,&refused)==AJI_SURFACE_INVALID && !refused);c.view=owned;
    assert(api.disable(ctx)==0 && api.configure(ctx,4,2,24,&plan)==0 && api.enable(ctx,1)==0);
    // Explicit borrowed-until-complete lifetime, ticket counter survives enable.
    c.view.retain=nullptr;c.view.release=nullptr;out3.view.retain=nullptr;out3.view.release=nullptr;r3.flags=1;
    const auto t6=api.send(ctx,r3);assert(t6>t5 && api.drain(ctx,0)==0 && api.poll(ctx,t6,1).state==AJI_SURFACE_FINISHED);
    out3.equals(c);assert(api.disable(ctx)==0 && api.enable(ctx,2)==0);
    Frame f(4,2,6,5),g(4,2,7,6),out7(4,2,17,0,true),out8(4,2,18,0,true);
    Gate dying,discard;out7.owner.gate=&dying;out8.owner.gate=&discard;
    auto r7=api.request(nullptr,f,out7),r8=api.request(nullptr,g,out8);
    api.send(ctx,r7);dying.wait();api.send(ctx,r8);
    auto destroying=std::async(std::launch::async,[&]{api.destroy(ctx);});
    discard.wait();assert(out7.owner.held==1);discard.release();dying.release();destroying.get();
    out8.sentinel();f.owner.balanced();g.owner.balanced();out7.owner.balanced();out8.owner.balanced();
    std::cout<<"{\"passed\":true,\"pending_until_release\":true,\"nonblocking_full_queue\":true,\"snapshot_descriptors\":true,\"bounded_results\":true,\"cancel_and_destroy_drained\":true,\"tickets_monotone\":true,\"owners_once\":true,\"models_executed\":false}\n";
}
