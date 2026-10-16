#!/usr/bin/env python3
"""Short Surface CUDA cache ablation. One warmup, then one phase burst.

Run off/on in separate processes with identical inputs/plans/options; receipts
prevent repetition. CUDA interval includes host enqueue gaps, not just kernels.
"""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from surface_cuda_check import Params,Surface,Color,Plane,Rect,Caps,Frame as LegacyFrame,ptr,ownerfn

class Dependency(C.Structure):
    _fields_=[('kind',C.c_uint32),('reserved',C.c_uint32),('event',ptr),('value',C.c_uint64)]
class Request(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','flags','dependency_count']]+[
        ('previous',ptr),('current',ptr),('output',ptr),('timestep',C.c_double),('execution_queue',ptr),('dependencies',Dependency*3)]
class Completion(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','state','reserved']]+[
        ('ticket',C.c_uint64),('status',C.c_int32),('reserved_status',C.c_uint32),('message',C.c_char*256)]
class Fence(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','kind','reserved']]+[('event',ptr),('value',C.c_uint64)]
class Stats(C.Structure):
    _fields_=[('struct_size',C.c_uint32),('version',C.c_uint32)]+[(n,C.c_uint64) for n in [
        'eligible_hits','eligible_misses','uncached_calls','rife_preparations','rife_hits','promoted_inputs','fast_upscaled','fast_warped']]

def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists():
        assert json.loads((out/'summary.json').read_text())['passed'];print('Conclusive receipt exists; no repeat.');return
    os.environ['AJI_SURFACE_PAIR_CACHE']=str(s['cache'])
    cuda=C.CDLL('libcudart.so.13');cuda.cudaGetErrorString.restype=C.c_char_p
    sig={'cudaMalloc':([C.POINTER(ptr),C.c_size_t],C.c_int),'cudaFree':([ptr],C.c_int),'cudaMemcpy':([ptr,ptr,C.c_size_t,C.c_int],C.c_int),
        'cudaStreamCreateWithFlags':([C.POINTER(ptr),C.c_uint],C.c_int),'cudaStreamDestroy':([ptr],C.c_int),'cudaStreamSynchronize':([ptr],C.c_int),
        'cudaEventCreateWithFlags':([C.POINTER(ptr),C.c_uint],C.c_int),'cudaEventRecord':([ptr,ptr],C.c_int),'cudaEventSynchronize':([ptr],C.c_int),
        'cudaEventElapsedTime':([C.POINTER(C.c_float),ptr,ptr],C.c_int),'cudaEventDestroy':([ptr],C.c_int),'cudaStreamWaitEvent':([ptr,ptr,C.c_uint],C.c_int)}
    for name,(args,ret) in sig.items():getattr(cuda,name).argtypes=args;getattr(cuda,name).restype=ret
    def ck(code):
        if code:raise RuntimeError(cuda.cudaGetErrorString(code).decode())
    lib=C.CDLL(s['library'],mode=os.RTLD_LOCAL)
    sig={'aji_create':([C.POINTER(Params)],ptr),'aji_configure':([ptr,C.c_int,C.c_int,C.c_double,ptr,ptr],C.c_int),
        'aji_infer':([ptr,ptr,ptr,ptr],C.c_int),'aji_infer_rife':([ptr,ptr,ptr,C.c_double,ptr,ptr],C.c_int),
        'aji_surface_process_v1':([ptr,ptr,ptr,C.c_double,ptr],C.c_int),
        'aji_last_error':([ptr],C.c_char_p),'aji_destroy':([C.POINTER(ptr)],None),'aji_current_log':([ptr],C.c_char_p),
        'aji_surface_query_v1':([ptr,C.c_uint32,ptr,C.c_size_t],C.c_int),'aji_surface_cache_stats_v1':([ptr,C.c_uint32,ptr,C.c_size_t],C.c_int),
        'aji_surface_async_enable_v1':([ptr,C.c_uint32],C.c_int),'aji_surface_async_disable_v1':([ptr],C.c_int),
        'aji_surface_submit_v1':([ptr,ptr,C.POINTER(C.c_uint64)],C.c_int),'aji_surface_complete_v1':([ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],C.c_int),
        'aji_surface_output_fence_v1':([ptr,C.c_uint64,ptr,C.c_size_t],C.c_int),'aji_surface_drain_v1':([ptr,C.c_uint32],C.c_int)}
    for name,(args,ret) in sig.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=ret
    held={};acquired={};released={};allocations=[];streams=[];events=[];ctx=ptr()
    @ownerfn
    def retain(owner):held[owner]=held.get(owner,0)+1;acquired[owner]=acquired.get(owner,0)+1
    @ownerfn
    def release(owner):held[owner]-=1;released[owner]=released.get(owner,0)+1
    def frame(w,h,sequence,value,destination=False):
        aw,ah=w+4,h+4;stride=aw+32;v=Surface();v.struct_size=C.sizeof(v);v.version=1
        v.resource_kind=v.device_kind=2;v.format=5;v.width=aw;v.height=ah;v.crop=Rect(2,2,w,h);v.plane_count=2
        v.color=Color(3,1,2,2,1,8,3,1);v.sequence=sequence;v.generation=1;v.owner=sequence+1000;v.retain=retain;v.release=release
        v.pts=sequence;v.duration=1;v.timebase_num=1;v.timebase_den=24;v.time_flags=3;backups=[]
        for i in range(2):
            sy=2 if i else 1;raw=np.full(16+stride*(ah//sy),0xa5,np.uint8);start=16+(2//sy)*stride+2
            if not destination:
                y,x=np.indices((h//sy,w));sample=((x*3+y*7+i*31+value*17)%220+16 if not i else (x+y+value*3)%31+112).astype(np.uint8)
                for row in range(h//sy):raw[start+row*stride:start+row*stride+w]=sample[row]
            p=ptr();ck(cuda.cudaMalloc(C.byref(p),raw.nbytes));allocations.append(p);ck(cuda.cudaMemcpy(p,raw.ctypes.data,raw.nbytes,1))
            v.planes[i]=Plane(p.value,raw.nbytes,16,stride);backups.append(raw)
        ck(cuda.cudaStreamSynchronize(None));return v,backups,w,h
    def pixels(f):
        v,backups,w,h=f;values=[]
        for i in range(2):
            p=v.planes[i];sy=2 if i else 1;raw=np.empty(p.bytes,np.uint8);ck(cuda.cudaMemcpy(raw.ctypes.data,p.data,raw.nbytes,2))
            start=p.offset+(v.crop.y//sy)*p.row_stride+v.crop.x;mask=np.ones(raw.size,bool)
            for row in range(h//sy):
                pos=start+row*p.row_stride;values.append(raw[pos:pos+w].copy());mask[pos:pos+w]=False
            assert np.array_equal(raw[mask],backups[i][mask]),'write outside native view'
        return np.concatenate(values)
    def submit(a,b,dst,t,dependency=None):
        r=Request();r.struct_size=C.sizeof(r);r.version=1;r.previous=C.addressof(a[0]);r.current=C.addressof(b[0]);r.output=C.addressof(dst[0]);r.timestep=t
        if dependency:r.dependency_count=1;r.dependencies[0]=Dependency(1,0,dependency.value,0)
        ticket=C.c_uint64();assert lib.aji_surface_submit_v1(ctx,C.byref(r),C.byref(ticket))==0 and ticket.value
        return ticket.value
    def consume(ticket):
        r=Completion();assert lib.aji_surface_complete_v1(ctx,ticket,1,C.byref(r),C.sizeof(r))==0
        assert r.state==2 and not r.status,(r.state,r.status,r.message)
    def fence(ticket):
        r=Fence();deadline=time.monotonic()+10
        while True:
            status=lib.aji_surface_output_fence_v1(ctx,ticket,C.byref(r),C.sizeof(r))
            if not status:assert r.kind==1 and r.event;return r.event
            assert status==-4 and time.monotonic()<deadline,(status,lib.aji_last_error(ctx))
            time.sleep(0)
    try:
        p=Params(api_version=9,conf_path=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),rife_model_dir=os.fsencode(s['rife']),trtexec=b'/bin/false',slot=1)
        ctx=ptr(lib.aji_create(C.byref(p)));assert ctx
        ow,oh=C.c_int(),C.c_int();assert lib.aji_configure(ctx,128,72,24,C.byref(ow),C.byref(oh))==1,lib.aji_last_error(ctx)
        assert (ow.value,oh.value)==(256,144);print(lib.aji_current_log(ctx).decode(),flush=True)
        caps=Caps();assert lib.aji_surface_query_v1(ctx,1,C.byref(caps),C.sizeof(caps))==0
        assert bool(caps.flags&256)==bool(s['cache'])
        a,b=frame(128,72,1,0),frame(128,72,2,1)
        warm=frame(256,144,100,0,True);outputs=[frame(256,144,101+i,0,True) for i in range(3)]
        for i,f in enumerate(outputs):f[0].pts=5+i;f[0].timebase_den=96
        for _ in range(2):
            stream=ptr();ck(cuda.cudaStreamCreateWithFlags(C.byref(stream),1));streams.append(stream)
        for _ in range(2):
            event=ptr();ck(cuda.cudaEventCreateWithFlags(C.byref(event),0));events.append(event)
        if s.get('phase') in ['guards-ref','guards-on']:
            results={};checks=[]
            def stats_now():
                v=Stats();assert lib.aji_surface_cache_stats_v1(ctx,1,C.byref(v),C.sizeof(v))==0
                return {n:getattr(v,n) for n,_ in Stats._fields_ if n not in ['struct_size','version']}
            def write(f,value):
                v,backups,w,h=f
                for i in range(2):
                    sy=2 if i else 1;p=v.planes[i];raw=np.full(p.bytes,0xa5,np.uint8)
                    y,x=np.indices((h//sy,w));sample=((x*3+y*7+i*31+value*17)%220+16 if not i else (x+y+value*3)%31+112).astype(np.uint8)
                    start=p.offset+(2//sy)*p.row_stride+2
                    for row in range(h//sy):raw[start+row*p.row_stride:start+row*p.row_stride+w]=sample[row]
                    ck(cuda.cudaMemcpy(p.data,raw.ctypes.data,raw.nbytes,1))
                ck(cuda.cudaStreamSynchronize(None))
            def color():
                for f in [a,b]+outputs:f[0].color.primaries=2;f[0].color.transfer=3
            def run(label,reference,expected='eligible_misses'):
                before=stats_now();snapshots=[bytes(f[0]) for f in [a,b,outputs[0]]]
                status=lib.aji_surface_process_v1(ctx,C.byref(a[0]),C.byref(b[0]),.5,C.byref(outputs[0][0]));assert not status,lib.aji_last_error(ctx)
                assert snapshots==[bytes(f[0]) for f in [a,b,outputs[0]]] and acquired==released and not any(held.values())
                actual=pixels(outputs[0]);after=stats_now()
                if reference is not None:assert np.array_equal(actual,reference),label
                if s['cache']:
                    assert after[expected]==before[expected]+1,(label,before,after)
                    assert after['rife_preparations']==before['rife_preparations']+1,(label,before,after)
                results[label]=actual;checks.append(label);return actual
            sentinel=Stats();C.memset(C.byref(sentinel),0xa5,C.sizeof(sentinel));original=bytes(sentinel)
            assert lib.aji_surface_cache_stats_v1(ctx,2,C.byref(sentinel),C.sizeof(sentinel))==-2 and bytes(sentinel)==original
            assert lib.aji_surface_cache_stats_v1(ctx,1,C.byref(sentinel),1)==-1 and bytes(sentinel)==original
            if s['phase']=='guards-ref':
                assert not s['cache'];write(a,2);write(b,3);a[0].generation=b[0].generation=2
                run('generation',None)
                if s['guards_full']:
                    color();a[0].crop.x=b[0].crop.x=4;run('roi',None)
                write(a,4);write(b,5);run('legacy',None)
            else:
                assert s['cache'];ref=np.load(s['guard_reference']);base=np.load(s['base_reference'])['phase-1']
                run('prime',base)
                write(a,2);write(b,3);a[0].generation=b[0].generation=2;run('generation',ref['generation'])
                if s['guards_full']:
                    color();run('color',ref['generation'])
                    a[0].crop.x=b[0].crop.x=4;run('roi',ref['roi'])
                # Same allocation/IDs/generation/views, rewritten through legacy
                # use: the bridge must invalidate native trust before ABI9 reads.
                write(a,4);write(b,5);middle=frame(128,72,200,0,True)
                def legacy(f):
                    v,_,w,h=f;result=LegacyFrame(width=w,height=h,format=1,matrix=v.color.matrix-1,
                        range=1 if v.color.range==2 else 2,siting=v.color.siting)
                    for i in range(2):
                        sy=2 if i else 1;p=v.planes[i]
                        result.plane[i]=p.data+p.offset+(v.crop.y//sy)*p.row_stride+v.crop.x;result.stride[i]=p.row_stride
                    return result
                la,lb,lm,lo=map(legacy,[a,b,middle,outputs[2]])
                assert lib.aji_infer_rife(ctx,C.byref(la),C.byref(lb),.5,C.byref(lm),streams[0])==0,lib.aji_last_error(ctx)
                assert lib.aji_infer(ctx,C.byref(lm),C.byref(lo),streams[0])==0,lib.aji_last_error(ctx)
                ck(cuda.cudaStreamSynchronize(streams[0]));assert np.array_equal(pixels(outputs[2]),ref['legacy'])
                checks.append('legacy-direct-reference');run('after-legacy',ref['legacy'])
                if s['guards_full']:
                    # Empty drain must invalidate the cached synchronous pair.
                    before=stats_now();assert lib.aji_surface_async_enable_v1(ctx,1)==0
                    assert lib.aji_surface_drain_v1(ctx,0)==0;ticket=submit(a,b,outputs[0],.5)
                    deadline=time.monotonic()+10
                    while True:
                        done=Completion();assert lib.aji_surface_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0
                        if done.state!=1:assert done.state==2 and not done.status,done.message;break
                        assert time.monotonic()<deadline;time.sleep(0)
                    assert lib.aji_surface_async_disable_v1(ctx)==0
                    after=stats_now();assert after['eligible_misses']==before['eligible_misses']+1
                    assert after['rife_preparations']==before['rife_preparations']+1
                    assert np.array_equal(pixels(outputs[0]),ref['legacy']);checks.append('drain-clears-pair')
                    run('disable-clears-pair',ref['legacy'])
                    a[0].sequence=b[0].sequence=0
                    run('zero-id-first',ref['legacy'],'uncached_calls');run('zero-id-again',ref['legacy'],'uncached_calls')
                    a[0].sequence=1;b[0].sequence=2;a[0].generation=b[0].generation=0
                    run('zero-generation',ref['legacy'],'uncached_calls')
                    # Native event error after real GPU completion; recover with
                    # the same IDs/views but known fresh pixels, without reset.
                    write(a,2);write(b,3);a[0].generation=b[0].generation=2
                    assert lib.aji_surface_async_enable_v1(ctx,1)==0
                    inject=C.CDLL(None).aji_test_cuda_fail_next_completed_event;inject.argtypes=[];inject.restype=None;inject()
                    ticket=submit(a,b,outputs[0],.5);assert lib.aji_surface_drain_v1(ctx,0)==0
                    failed=Completion();assert lib.aji_surface_complete_v1(ctx,ticket,1,C.byref(failed),C.sizeof(failed))==0
                    assert failed.state==3 and failed.status==-3 and b'CUDA completion event' in failed.message
                    assert lib.aji_surface_async_disable_v1(ctx)==0 and acquired==released and not any(held.values())
                    write(a,4);write(b,5);run('error-recovery',ref['legacy']);checks.append('failed-output-discarded')
            np.savez(out/'pixels.npz',**results)
            result=dict(passed=True,cache=s['cache'],checks=checks,owners_balanced=True,roi_and_padding_exact=True,
                stats=stats_now(),fps_not_measured=True,hardware_loss_not_provoked=True)
            (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return
        assert lib.aji_surface_async_enable_v1(ctx,3)==0
        stats=Stats();C.memset(C.byref(stats),0xa5,C.sizeof(stats));before=bytes(stats)
        assert lib.aji_surface_cache_stats_v1(ctx,1,C.byref(stats),C.sizeof(stats))==-4 and bytes(stats)==before
        tw=submit(a,b,warm,.5);assert lib.aji_surface_drain_v1(ctx,0)==0;consume(tw)
        # Preserve warmed plans/worker, reset pair through drain; new identities
        # make the measured burst a fresh pair in both ablation modes.
        a[0].sequence=10;b[0].sequence=11
        snapshots=[bytes(f[0]) for f in [a,b]+outputs];ck(cuda.cudaEventRecord(events[0],streams[0]));start=time.perf_counter()
        tickets=[submit(a,b,f,t,events[0]) for f,t in zip(outputs,[.25,.5,.75])]
        last_event=fence(tickets[-1]);fence_ready_ms=(time.perf_counter()-start)*1000
        ck(cuda.cudaStreamWaitEvent(streams[1],last_event,0));ck(cuda.cudaEventRecord(events[1],streams[1]));ck(cuda.cudaEventSynchronize(events[1]))
        wall_ms=(time.perf_counter()-start)*1000;elapsed=C.c_float();ck(cuda.cudaEventElapsedTime(C.byref(elapsed),*events))
        assert lib.aji_surface_drain_v1(ctx,0)==0
        for ticket in tickets:consume(ticket)
        assert snapshots==[bytes(f[0]) for f in [a,b]+outputs]
        values={f'phase-{i}':pixels(f) for i,f in enumerate(outputs)};np.savez(out/'pixels.npz',**values)
        assert acquired==released and all(v==0 for v in held.values())
        assert acquired[a[0].owner]==4 and acquired[b[0].owner]==4 and all(acquired[f[0].owner]==1 for f in outputs)
        assert lib.aji_surface_async_disable_v1(ctx)==0
        stats=Stats();assert lib.aji_surface_cache_stats_v1(ctx,1,C.byref(stats),C.sizeof(stats))==0 and stats.version==1 and stats.struct_size==72
        result=dict(passed=True,cache=s['cache'],phase_count=3,warmup_outputs=1,outputs=list(values),gpu_interval_ms=elapsed.value,burst_wall_ms=wall_ms,fence_ready_ms=fence_ready_ms,
            counters={n:getattr(stats,n) for n,_ in Stats._fields_ if n not in ['struct_size','version']},owners_once_per_job=True,roi_and_padding_exact=True,descriptors_unchanged=True,
            timing_scope='one warmed burst; CUDA event interval includes CPU enqueue gaps; not universal FPS')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:
        if ctx:lib.aji_destroy(C.byref(ctx))
        for event in events:ck(cuda.cudaEventDestroy(event))
        for stream in streams:ck(cuda.cudaStreamDestroy(stream))
        for allocation in allocations:ck(cuda.cudaFree(allocation))
if __name__=='__main__':main()
