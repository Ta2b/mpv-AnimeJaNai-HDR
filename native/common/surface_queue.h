#pragma once
#include "surface_async.h"
#include <algorithm>
#include <array>
#include <condition_variable>
#include <cstdio>
#include <functional>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

namespace aji::surface {
struct QueuedSurfaces {
    bool has_previous=false;
    aji_surface_v1 previous{},current{},output{};
    double timestep=1;
    const aji_surface_v1 *descriptor(size_t i) const {
        return i==0 ? (has_previous?&previous:nullptr) : i==1?&current:&output;
    }
};
struct QueueResult {
    int status=AJI_SURFACE_OK;
    std::array<char,256> message{};
};

// One inference owner, fixed result slots. No per-submit task/future allocation.
// Lifecycle operations exclude concurrent public queue calls; submit/poll are
// concurrent while enabled. Owner callbacks follow the public no-reentry rule.
class SurfaceQueue {
    static uint32_t checked_capacity(uint32_t value) {
        if(!value || value>64)throw std::invalid_argument("Surface queue capacity must be 1..64");
        return value;
    }
    enum State { Free,Reserved,Queued,Running,Releasing,Done };
    struct Slot {
        State state=Free;
        uint64_t ticket=0;
        QueuedSurfaces work;
        QueueResult result;
        std::array<const aji_surface_v1 *,3> retained{};
        size_t retained_count=0;
    };
    std::vector<Slot> slots;
    uint64_t &next_ticket;
    std::function<QueueResult(const QueuedSurfaces &)> process;
    std::mutex mutex;
    std::condition_variable changed;
    bool accepting=true,stopping=false;
    std::thread worker;
    static void release(Slot &s) noexcept {
        while(s.retained_count) {
            const auto *d=s.retained[--s.retained_count];d->release(d->owner);
        }
    }
    bool inflight() const {
        for(const auto &s:slots)if(s.state!=Free && s.state!=Done)return true;
        return false;
    }
    Slot *first_queued() {
        Slot *found=nullptr;
        for(auto &s:slots)if(s.state==Queued && (!found || s.ticket<found->ticket))found=&s;
        return found;
    }
    void run() {
        for(;;) {
            Slot *s;
            {
                std::unique_lock<std::mutex> lock(mutex);
                changed.wait(lock,[&]{return stopping || first_queued();});
                s=first_queued();
                if(!s) {if(stopping)return;continue;}
                s->state=Running;
            }
            QueueResult result;
            try {result=process(s->work);}
            catch(const std::exception &e) {
                result.status=AJI_SURFACE_ENGINE_ERROR;
                std::snprintf(result.message.data(),result.message.size(),"%s",e.what());
            } catch(...) {
                result.status=AJI_SURFACE_ENGINE_ERROR;
                std::snprintf(result.message.data(),result.message.size(),"Unexpected surface execution failure");
            }
            // Pending includes release callbacks. No reader may reuse buffers
            // until this has finished; result slots are still reserved then.
            release(*s);
            {
                std::lock_guard<std::mutex> lock(mutex);
                s->result=result;s->state=Done;
            }
            changed.notify_all();
        }
    }
public:
    SurfaceQueue(uint32_t capacity,uint64_t &counter,std::function<QueueResult(const QueuedSurfaces &)> fn)
        :slots(checked_capacity(capacity)),next_ticket(counter),process(std::move(fn)),worker([this]{run();}) {}
    SurfaceQueue(const SurfaceQueue &)=delete;
    SurfaceQueue &operator=(const SurfaceQueue &)=delete;
    bool on_worker() const {return std::this_thread::get_id()==worker.get_id();}
    int submit(const QueuedSurfaces &work,uint64_t *ticket) {
        std::lock_guard<std::mutex> lock(mutex);
        if(!accepting || stopping)return AJI_SURFACE_ASYNC_BUSY;
        Slot *s=nullptr;for(auto &v:slots)if(v.state==Free){s=&v;break;}
        if(!s)return AJI_SURFACE_ASYNC_BUSY;
        if(next_ticket==std::numeric_limits<uint64_t>::max())return AJI_SURFACE_INVALID;
        s->state=Reserved;s->work=work;s->result={};s->retained_count=0;
        try {
            for(size_t i=0;i<3;++i) {
                const auto *d=s->work.descriptor(i);
                if(d && d->retain) {d->retain(d->owner);s->retained[s->retained_count++]=d;}
            }
        }catch(...) {release(*s);s->state=Free;throw;}
        s->ticket=next_ticket++;*ticket=s->ticket;s->state=Queued;
        changed.notify_all();return AJI_SURFACE_OK;
    }
    int complete(uint64_t ticket,uint32_t flags,aji_surface_completion_v1 *out) {
        std::lock_guard<std::mutex> lock(mutex);
        Slot *s=nullptr;for(auto &v:slots)if(v.state!=Free && v.ticket==ticket){s=&v;break;}
        if(!s || !ticket)return AJI_SURFACE_INVALID;
        *out={};out->struct_size=sizeof(*out);out->version=1;out->ticket=ticket;
        if(s->state!=Done)out->state=AJI_SURFACE_PENDING;
        else {
            out->status=s->result.status;
            out->state=out->status==AJI_SURFACE_OK ? AJI_SURFACE_FINISHED
                :out->status==AJI_SURFACE_ASYNC_CANCELLED ? AJI_SURFACE_CANCELLED:AJI_SURFACE_FAILED;
            std::copy(s->result.message.begin(),s->result.message.end(),out->message);
            if(flags&AJI_SURFACE_CONSUME_RESULT)s->state=Free;
        }
        return AJI_SURFACE_OK;
    }
    void drain(uint32_t flags) {
        // Stop acceptance until the caller has reset any derived context state.
        std::array<Slot *,64> cancelled{};size_t count=0;
        {
            std::lock_guard<std::mutex> lock(mutex);accepting=false;
            if(flags&AJI_SURFACE_CANCEL_QUEUED)for(auto &s:slots)if(s.state==Queued) {
                s.state=Releasing;cancelled[count++]=&s;
            }
        }
        for(size_t i=0;i<count;++i) {
            auto &s=*cancelled[i];release(s);
            std::lock_guard<std::mutex> lock(mutex);
            s.result={};s.result.status=AJI_SURFACE_ASYNC_CANCELLED;
            std::snprintf(s.result.message.data(),s.result.message.size(),"Surface work cancelled before execution");
            s.state=Done;
        }
        changed.notify_all();
        std::unique_lock<std::mutex> lock(mutex);
        changed.wait(lock,[&]{return !inflight();});
        if(flags&AJI_SURFACE_DROP_RESULTS)for(auto &s:slots)s.state=Free;
    }
    void resume() {std::lock_guard<std::mutex> lock(mutex);accepting=true;}
    void shutdown() {
        if(!worker.joinable())return;
        drain(AJI_SURFACE_CANCEL_QUEUED|AJI_SURFACE_DROP_RESULTS);
        {std::lock_guard<std::mutex> lock(mutex);stopping=true;}
        changed.notify_all();worker.join();
    }
    ~SurfaceQueue() {shutdown();}
};
}
