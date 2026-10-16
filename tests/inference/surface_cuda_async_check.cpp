// Real native C ABI consumer: controlled producer/output events establish GPU
// dependency and lifetime rules without timing thresholds or neural repetitions.
#include "surface_async.h"
#include "aji.h"
#include <cuda_runtime_api.h>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <dlfcn.h>
#include <future>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
using Clock=std::chrono::steady_clock;
struct Gate {
    std::mutex mutex;std::condition_variable changed;bool entered=false,open=false;
    void block() {std::unique_lock<std::mutex> l(mutex);entered=true;changed.notify_all();
        assert(changed.wait_for(l,std::chrono::seconds(10),[&]{return open;}));}
    void wait() {std::unique_lock<std::mutex> l(mutex);
        assert(changed.wait_for(l,std::chrono::seconds(10),[&]{return entered;}));}
    void release() {std::lock_guard<std::mutex> l(mutex);open=true;changed.notify_all();}
    static void callback(void *p) {((Gate *)p)->block();} // no CUDA calls from callback
};
struct Owner {
    std::atomic<int> held{0},retains{0},releases{0};Gate *gate=nullptr;
    static void retain(void *p) {auto &o=*(Owner *)p;++o.held;++o.retains;}
    static void release(void *p) {auto &o=*(Owner *)p;if(o.gate)o.gate->block();++o.releases;--o.held;}
    void balanced() const {assert(held==0 && retains==releases);}
};
struct Cuda {
    void *library=dlopen("libcudart.so.13",RTLD_NOW|RTLD_LOCAL);
    int (*malloc_)(void **,size_t),(*free_)(void *),(*copy)(void *,const void *,size_t,int);
    int (*stream_create)(void **,unsigned),(*stream_destroy)(void *),(*stream_sync)(void *);
    int (*event_create)(void **,unsigned),(*event_record)(void *,void *),(*event_query)(void *),(*event_destroy)(void *);
    int (*wait_event)(void *,void *,unsigned),(*host_func)(void *,void (*)(void *),void *);
    int (*fill_2d)(void *,size_t,int,size_t,size_t,void *);
    int (*copy_2d)(void *,size_t,const void *,size_t,size_t,size_t,int,void *);
    template<class T>T get(const char *s) {auto f=(T)dlsym(library,s);assert(f);return f;}
    Cuda() {assert(library);
#define FN(field,symbol) field=get<decltype(field)>(symbol)
        FN(malloc_,"cudaMalloc");FN(free_,"cudaFree");FN(copy,"cudaMemcpy");
        FN(stream_create,"cudaStreamCreateWithFlags");FN(stream_destroy,"cudaStreamDestroy");FN(stream_sync,"cudaStreamSynchronize");
        FN(event_create,"cudaEventCreateWithFlags");FN(event_record,"cudaEventRecord");FN(event_query,"cudaEventQuery");FN(event_destroy,"cudaEventDestroy");
        FN(wait_event,"cudaStreamWaitEvent");FN(host_func,"cudaLaunchHostFunc");FN(fill_2d,"cudaMemset2DAsync");FN(copy_2d,"cudaMemcpy2DAsync");
#undef FN
    }
    static void ck(int code) {if(code)std::cerr<<"CUDA status "<<code<<'\n';assert(!code);}
};
struct Frame {
    Cuda &cuda;int w=128,h=72,stride=192;std::array<void *,2> data{};
    std::array<std::vector<unsigned char>,2> initial;Owner owner;aji_surface_v1 view{};
    Frame(Cuda &c,uint64_t sequence,int value,bool output=false):cuda(c) {
        view.struct_size=sizeof(view);view.version=1;view.resource_kind=view.device_kind=AJI_RESOURCE_CUDA;
        view.format=AJI_SURFACE_NV12;view.width=w;view.height=h;view.plane_count=2;
        view.color={AJI_SURFACE_MATRIX_709,AJI_SURFACE_PRIM_709,AJI_SURFACE_TRC_SRGB,
            AJI_SURFACE_RANGE_LIMITED,AJI_SURFACE_SITING_LEFT,8,AJI_SURFACE_QUANT_REFERENCE_NATIVE_YUV,AJI_SURFACE_DITHER_NONE};
        view.sequence=sequence;view.generation=1;view.pts=sequence;view.duration=1;view.timebase_num=1;view.timebase_den=24;view.time_flags=3;
        view.owner=&owner;view.retain=Owner::retain;view.release=Owner::release;
        for(int i=0;i<2;++i) {const int rows=i?h/2:h;initial[i].assign(stride*rows,0xa5);
            if(!output)for(int y=0;y<rows;++y)std::fill_n(initial[i].data()+y*stride,w,(unsigned char)(value+i*37));
            Cuda::ck(cuda.malloc_(&data[i],initial[i].size()));Cuda::ck(cuda.copy(data[i],initial[i].data(),initial[i].size(),1));
            view.planes[i]={data[i],initial[i].size(),0,stride};}
        Cuda::ck(cuda.stream_sync(nullptr));
    }
    ~Frame() {owner.balanced();for(auto p:data)Cuda::ck(cuda.free_(p));}
    void fill_on(void *stream,int value) {for(int i=0;i<2;++i)Cuda::ck(cuda.fill_2d(data[i],stride,value+i*37,w,i?h/2:h,stream));}
    void verify(int value,bool untouched=false) const {
        for(int i=0;i<2;++i) {auto pixels=initial[i];Cuda::ck(cuda.copy(pixels.data(),data[i],pixels.size(),2));
            for(int y=0;y<(i?h/2:h);++y)for(int x=0;x<stride;++x)
                assert(pixels[y*stride+x]==(x<w && !untouched?(unsigned char)(value+i*37):0xa5));}
    }
    void copy_on(const Frame &from,void *stream) {for(int i=0;i<2;++i)
        Cuda::ck(cuda.copy_2d(data[i],stride,from.data[i],from.stride,w,i?h/2:h,3,stream));}
};
struct Api {
    void *library;
    decltype(&aji_create) create;decltype(&aji_configure) configure;decltype(&aji_destroy) destroy;
    decltype(&aji_infer) legacy;decltype(&aji_last_error) error;decltype(&aji_surface_process_v1) sync;
    decltype(&aji_surface_async_query_v1) query;decltype(&aji_surface_async_enable_v1) enable;decltype(&aji_surface_async_disable_v1) disable;
    decltype(&aji_surface_submit_v1) submit;decltype(&aji_surface_complete_v1) complete;decltype(&aji_surface_drain_v1) drain;
    decltype(&aji_surface_output_fence_v1) fence;
    template<class T>T get(const char *s) {auto f=(T)dlsym(library,s);assert(f);return f;}
    Api(const char *path):library(dlopen(path,RTLD_NOW|RTLD_LOCAL)) {if(!library)std::cerr<<dlerror()<<'\n';assert(library);
#define FN(field,symbol) field=get<decltype(field)>(symbol)
        FN(create,"aji_create");FN(configure,"aji_configure");FN(destroy,"aji_destroy");FN(legacy,"aji_infer");FN(error,"aji_last_error");
        FN(sync,"aji_surface_process_v1");FN(query,"aji_surface_async_query_v1");FN(enable,"aji_surface_async_enable_v1");FN(disable,"aji_surface_async_disable_v1");
        FN(submit,"aji_surface_submit_v1");FN(complete,"aji_surface_complete_v1");FN(drain,"aji_surface_drain_v1");FN(fence,"aji_surface_output_fence_v1");
#undef FN
    }
    aji_ctx *context(const char *conf,const char *models,const char *rife) {
        aji_create_params p{};p.api_version=9;p.conf_path=conf;p.model_dir=models;p.rife_model_dir=rife;p.trtexec="/bin/false";p.slot=1;
        auto *c=create(&p);assert(c);assert(configure(c,128,72,24,nullptr,nullptr)==0);return c;
    }
    aji_surface_submit_v1_request request(Frame &source,Frame &out,void *event=nullptr) {
        aji_surface_submit_v1_request r{};r.struct_size=sizeof(r);r.version=1;r.current=&source.view;r.output=&out.view;r.timestep=1;
        if(event) {r.dependency_count=1;r.dependencies[0].kind=AJI_SURFACE_DEP_CUDA_EVENT;r.dependencies[0].event=event;}return r;
    }
    uint64_t send(aji_ctx *c,const aji_surface_submit_v1_request &r) {uint64_t t=0;int s=submit(c,&r,&t);if(s)std::cerr<<"submit "<<s<<'\n';assert(s==0 && t);return t;}
    aji_surface_completion_v1 poll(aji_ctx *c,uint64_t ticket,uint32_t flags=0) {
        aji_surface_completion_v1 out{};assert(complete(c,ticket,flags,&out,sizeof(out))==0);assert(out.ticket==ticket && out.version==1);return out;
    }
    aji_surface_fence_v1_result native_fence(aji_ctx *c,uint64_t ticket) {
        auto deadline=Clock::now()+std::chrono::seconds(5);aji_surface_fence_v1_result out{};int status;
        while((status=fence(c,ticket,&out,sizeof(out)))==AJI_SURFACE_ASYNC_BUSY) {assert(Clock::now()<deadline);std::this_thread::yield();}
        assert(!status && out.kind==AJI_SURFACE_DEP_CUDA_EVENT && out.event && !out.value);return out;
    }
};
int main(int argc,char **argv) {
    assert(argc==5 || argc==6);Cuda cuda;Api api(argv[1]);auto *ctx=api.context(argv[2],argv[3],argv[4]);
    aji_surface_async_caps_v1 caps{};assert(api.query(ctx,1,&caps,sizeof(caps))==0);
    assert(caps.max_capacity==64 && caps.dependency_mask==3 && caps.device_kind==AJI_RESOURCE_CUDA);
    const auto saved_caps=caps;assert(api.query(ctx,2,&caps,sizeof(caps))==-2 && !std::memcmp(&caps,&saved_caps,sizeof(caps)));
    assert(api.enable(ctx,0)==-1 && api.enable(ctx,65)==-1 && api.enable(ctx,2)==0 && api.enable(ctx,2)==-4);
    Frame source(cuda,1,23),other(cuda,2,41),out1(cuda,11,0,true),out2(cuda,12,0,true),out3(cuda,13,0,true),sink(cuda,14,0,true);
    if(argc==6) {
        assert(!std::strcmp(argv[5],"--snapshot"));Gate held_worker;out1.owner.gate=&held_worker;
        auto first=api.request(source,out1);api.send(ctx,first);held_worker.wait();
        void *ready=nullptr;Cuda::ck(cuda.event_create(&ready,2));Cuda::ck(cuda.event_record(ready,nullptr));
        auto next=api.request(other,out2,ready);const auto ticket=api.send(ctx,next);
        assert(api.poll(ctx,ticket).state==AJI_SURFACE_PENDING);
        const auto original=other.view;other.view.width=0;next.timestep=-1;next.dependencies[0].kind=AJI_SURFACE_DEP_HIP_EVENT;
        held_worker.release();assert(api.drain(ctx,0)==0);other.view=original;
        assert(api.poll(ctx,ticket,1).state==AJI_SURFACE_FINISHED);out2.verify(41);
        source.owner.balanced();other.owner.balanced();out1.owner.balanced();out2.owner.balanced();
        assert(other.owner.retains==1 && out2.owner.retains==1);api.destroy(&ctx);Cuda::ck(cuda.event_destroy(ready));
        std::cout<<"{\"passed\":true,\"queued_snapshot_controlled\":true,\"descriptors_and_dependencies_copied\":true,\"owners_once\":true,\"models_executed\":false}\n";
        return 0;
    }
    void *producer=nullptr,*consumer=nullptr,*ready=nullptr;
    Cuda::ck(cuda.stream_create(&producer,1));Cuda::ck(cuda.stream_create(&consumer,1));Cuda::ck(cuda.event_create(&ready,2));
    Gate input,releasing;out1.owner.gate=&releasing;
    Cuda::ck(cuda.host_func(producer,Gate::callback,&input));source.fill_on(producer,73);Cuda::ck(cuda.event_record(ready,producer));input.wait();
    auto r1=api.request(source,out1,ready),r2=api.request(source,out2,ready),r3=api.request(other,out3);
    const auto t1=api.send(ctx,r1),t2=api.send(ctx,r2);assert(t2>t1 && !input.open);
    const auto f=api.native_fence(ctx,t1);assert(cuda.event_query(f.event)==cudaErrorNotReady); // still behind producer gate
    assert(api.poll(ctx,t1,1).state==AJI_SURFACE_PENDING && api.poll(ctx,t2).state==AJI_SURFACE_PENDING);
    Cuda::ck(cuda.wait_event(consumer,f.event,0));sink.copy_on(out1,consumer);
    uint64_t refused=999;assert(api.submit(ctx,&r3,&refused)==-4 && !refused);
    assert(other.owner.retains==0 && out3.owner.retains==0 && source.owner.held==2);
    assert(api.configure(ctx,128,72,24,nullptr,nullptr)<0);
    assert(api.legacy(ctx,nullptr,nullptr,nullptr)<0 && api.sync(ctx,nullptr,&source.view,1,&out3.view)==-4);
    assert(std::strstr(api.error(ctx),"Async CUDA surface queue"));
    const auto original=source.view;source.view.width=0;r2.timestep=-1;r2.dependencies[0].kind=AJI_SURFACE_DEP_HIP_EVENT;
    input.release();releasing.wait();assert(api.poll(ctx,t1,1).state==AJI_SURFACE_PENDING && out1.owner.held==1);
    // A GPU consumer is ordered by the exported fence, independent of CPU release callbacks.
    Cuda::ck(cuda.stream_sync(consumer));sink.verify(73);releasing.release();assert(api.drain(ctx,0)==0);source.view=original;
    assert(api.poll(ctx,t1).state==AJI_SURFACE_FINISHED && api.poll(ctx,t2).state==AJI_SURFACE_FINISHED);
    out1.verify(73);out2.verify(73);source.owner.balanced();out1.owner.balanced();out2.owner.balanced();
    assert(source.owner.retains==2 && out1.owner.retains==1 && out2.owner.retains==1);
    assert(api.submit(ctx,&r3,&refused)==-4 && !refused);api.poll(ctx,t1,1);const auto t3=api.send(ctx,r3);assert(t3>t2);
    assert(api.drain(ctx,AJI_SURFACE_DROP_RESULTS)==0);out3.verify(41);aji_surface_completion_v1 gone{};
    assert(api.complete(ctx,t2,0,&gone,sizeof(gone))==-1);
    Frame active(cuda,3,51),queued(cuda,4,61),out4(cuda,15,0,true),out5(cuda,16,0,true);
    Gate worker,cancel;out4.owner.gate=&worker;out5.owner.gate=&cancel;
    auto r4=api.request(active,out4),r5=api.request(queued,out5);
    const auto t4=api.send(ctx,r4);worker.wait();const auto t5=api.send(ctx,r5);
    auto draining=std::async(std::launch::async,[&]{return api.drain(ctx,AJI_SURFACE_CANCEL_QUEUED);});
    cancel.wait();assert(out4.owner.held==1 && out5.owner.held==1);cancel.release();worker.release();assert(draining.get()==0);
    assert(api.poll(ctx,t4,1).state==AJI_SURFACE_FINISHED && api.poll(ctx,t5,1).state==AJI_SURFACE_CANCELLED);
    out5.verify(0,true);active.owner.balanced();queued.owner.balanced();out4.owner.balanced();out5.owner.balanced();
    auto bad=r3;bad.dependency_count=1;bad.dependencies[0].kind=AJI_SURFACE_DEP_HIP_EVENT;bad.dependencies[0].event=ready;
    assert(api.submit(ctx,&bad,&refused)==-2 && !refused);bad=r3;bad.execution_queue=producer;assert(api.submit(ctx,&bad,&refused)==-2);
    bad=r3;bad.dependencies[0].reserved=1;bad.dependency_count=1;assert(api.submit(ctx,&bad,&refused)==-1);
    assert(api.disable(ctx)==0 && api.enable(ctx,1)==0);
    other.view.retain=nullptr;other.view.release=nullptr;out3.view.retain=nullptr;out3.view.release=nullptr;r3.flags=AJI_SURFACE_BORROW_UNTIL_COMPLETE;
    const auto t6=api.send(ctx,r3);assert(t6>t5 && api.drain(ctx,0)==0 && api.poll(ctx,t6,1).state==AJI_SURFACE_FINISHED);
    assert(api.disable(ctx)==0 && api.enable(ctx,2)==0);
    Frame last(cuda,5,83),skip(cuda,6,93),out6(cuda,17,0,true),out7(cuda,18,0,true);Gate dying,discard;
    out6.owner.gate=&dying;out7.owner.gate=&discard;auto r6=api.request(last,out6),r7=api.request(skip,out7);
    api.send(ctx,r6);dying.wait();api.send(ctx,r7);
    auto destroying=std::async(std::launch::async,[&]{api.destroy(&ctx);});discard.wait();assert(out6.owner.held==1);
    discard.release();dying.release();destroying.get();assert(!ctx);out7.verify(0,true);
    auto inject=(void (*)())dlsym(RTLD_DEFAULT,"aji_test_cuda_fail_next_completed_event");assert(inject);
    ctx=api.context(argv[2],argv[3],argv[4]);assert(api.enable(ctx,1)==0);Frame errsrc(cuda,7,103),errout(cuda,19,0,true);
    auto er=api.request(errsrc,errout);inject();auto te=api.send(ctx,er);assert(api.drain(ctx,0)==0);
    auto error=api.poll(ctx,te,1);assert(error.state==AJI_SURFACE_FAILED && error.status==AJI_SURFACE_ENGINE_ERROR);
    assert(std::strstr(error.message,"CUDA completion event"));errsrc.owner.balanced();errout.owner.balanced();
    refused=999;assert(api.submit(ctx,&er,&refused)==AJI_SURFACE_ENGINE_ERROR && !refused);
    assert(errsrc.owner.retains==1 && errout.owner.retains==1);assert(api.disable(ctx)==0);api.destroy(&ctx);
    Cuda::ck(cuda.event_destroy(ready));Cuda::ck(cuda.stream_destroy(consumer));Cuda::ck(cuda.stream_destroy(producer));
    std::cout<<"{\"passed\":true,\"gpu_input_dependency\":true,\"native_output_fence\":true,\"pending_until_release\":true,\"bounded_results\":true,\"snapshot_descriptors_and_dependencies\":true,\"tickets_monotone\":true,\"cancel_destroy_drained\":true,\"deferred_event_error\":true,\"owners_once\":true,\"models_executed\":false}\n";
}
