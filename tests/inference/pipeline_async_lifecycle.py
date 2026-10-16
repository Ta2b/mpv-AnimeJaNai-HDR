#!/usr/bin/env python3
"""New pipeline worker: pending dependency, bounded cancel, reset and deferred error.
LD_PRELOAD the owned pipeline-failure.so in this dedicated process only.
One real burst, one queued cancel and one controlled failed output copy.
"""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import threading
import time
import numpy as np
from pipeline_cuda_check import Create,Caps,Request,Done,Stats,Fixture,ptr,wakeupfn,digest,rgb_to_yuv444,yuv444_to_rgb
from fruc_surface_check import Dependency
def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']).parent/'async-lifecycle';out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
    identity={k:digest(s[k]) for k in ['library','kernel','trt','conf','input']}
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Conclusive matching receipt; no replay.');return
    f=Fixture(s);lib=C.CDLL(s['library'],mode=os.RTLD_LOCAL);ctx=ptr();wake_event=threading.Event()
    @wakeupfn
    def wake(_):wake_event.set()
    for n,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],
        'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],
        'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_reset_v1':[ptr,C.c_uint64],
        'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():
        getattr(lib,n).argtypes=args;getattr(lib,n).restype=None if 'destroy' in n else C.c_int
    p=Create(struct_size=C.sizeof(Create),version=1,width=s['width'],height=s['height'],slot=1,capacity=2,flags=1,generation=1,cuda_context=f.ctx,
        conf=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),rife_dir=os.fsencode(s['rife']),trtexec=b'/bin/false',
        trt_library=os.fsencode(s['trt']),fruc_library=os.fsencode(s['fruc']),kernel_fatbin=os.fsencode(s['kernel']),
        fps_numerator=24000,fps_denominator=1001,wakeup=wake)
    message=C.create_string_buffer(1024);release=threading.Event();timer=None
    try:
        assert lib.aji_pipeline_create_v1(C.byref(p),C.byref(ctx),message,len(message))==0,message.value
        caps=Caps();deadline=time.monotonic()+10
        while True:
            code=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps))
            if code!=-4:break
            assert time.monotonic()<deadline;wake_event.wait(.01);wake_event.clear()
        assert code==0 and caps.factor==4 and caps.capacity==2
        frames=np.fromfile(s['input'],np.uint8).reshape(-1,s['height'],s['width'],3);sources=[]
        for i in range(3):
            item=f.surface(rgb_to_yuv444(frames[3+i].astype(np.float32)/255),7,i+1,i)
            item[0].timebase_den=24000;item[0].duration=1;sources.append(item)
        f.s=dict(s,width=caps.width,height=caps.height)
        targets=[[f.surface(None,7,100+4*k+j,4*k+j) for j in range(4)] for k in range(2)];f.s=s
        for group in targets:
            for item in group:item[0].timebase_den=96000;item[0].duration=1
        def request(a,b,group):
            r=Request(struct_size=C.sizeof(Request),version=1,generation=a[0].generation,previous=C.addressof(a[0]),current=C.addressof(b[0]),output_count=4)
            for j,v in enumerate(group):r.outputs[j]=C.addressof(v[0])
            return r
        def submit(r):
            t=C.c_uint64();code=lib.aji_pipeline_submit_v1(ctx,C.byref(r),C.byref(t));return code,t.value
        def complete(t,consume=1):
            d=Done();assert lib.aji_pipeline_complete_v1(ctx,t,consume,C.byref(d),C.sizeof(d))==0;return d
        for name,args in {'cuStreamCreate':[ptr,C.c_uint],'cuStreamDestroy_v2':[ptr],
            'cuEventCreate':[ptr,C.c_uint],'cuEventRecord':[ptr,ptr],'cuEventDestroy_v2':[ptr],
            'cuLaunchHostFunc':[ptr,ptr,ptr]}.items():getattr(f.driver,name).argtypes=args;getattr(f.driver,name).restype=C.c_int
        stream=ptr();event=ptr();f.ck(f.driver.cuStreamCreate(C.byref(stream),1));f.streams.append(stream)
        f.ck(f.driver.cuEventCreate(C.byref(event),2));f.events.append(event);entered=threading.Event()
        @wakeupfn
        def gate(_):entered.set();release.wait(10)
        f.ck(f.driver.cuLaunchHostFunc(stream,gate,None));f.ck(f.driver.cuEventRecord(event,stream));assert entered.wait(1)
        r=request(sources[0],sources[1],targets[0]);r.dependency_count=1;r.dependencies[0]=Dependency(kind=1,event=event)
        code,t1=submit(r);assert code==0 and complete(t1,0).result.state==1 and sum(f.held.values())==6
        q=request(sources[1],sources[2],targets[1]);code,t2=submit(q);assert code==0 and t2>t1
        n=len(f.owners);code,t=submit(q);assert code==-4 and t==0 and len(f.owners)==n
        timer=threading.Timer(.05,release.set);timer.start();assert lib.aji_pipeline_drain_v1(ctx,1)==0;timer.join();timer=None
        first=complete(t1);cancelled=complete(t2);assert first.result.state==2 and cancelled.result.state==4 and cancelled.result.status==-5
        assert all(v==0 for v in f.held.values())
        for item in targets[1]:assert all(np.all(plane==0xa5a5) for plane in f.download(item))
        actual=yuv444_to_rgb(f.download(targets[0][2]));reference=np.load(s['common_median_reference'])
        assert np.array_equal(actual,reference),'Shared Quality median after same SPAN differs'
        assert lib.aji_pipeline_reset_v1(ctx,2)==0
        for item in sources+targets[0]+targets[1]:item[0].generation=2
        for j,item in enumerate(targets[1]):item[0].pts=j
        fail=C.CDLL(None).aji_test_pipeline_fail_copy;fail.argtypes=[C.c_uint];fail.restype=None;fail(1)
        r=request(sources[0],sources[1],targets[1]);code,t3=submit(r);assert code==0 and t3>t2
        assert lib.aji_pipeline_drain_v1(ctx,0)==0;failed=complete(t3)
        assert failed.result.state==3 and failed.result.status==-3 and failed.result.message
        assert all(v==0 for v in f.held.values())
        n=len(f.owners);code,t=submit(r);assert code==-3 and not t and len(f.owners)==n
        assert lib.aji_pipeline_reset_v1(ctx,3)==0
        stats=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stats),C.sizeof(stats))==0
        counts={n:getattr(stats,n) for n,_ in stats._fields_};assert counts['finished']==counts['cancelled']==counts['failed']==1
        result=dict(passed=True,identity=identity,stats=counts,dependency_pending=True,capacity_bounded=True,queued_cancel=True,
            cancelled_output_untouched=True,tickets_monotone=True,reset_generation=True,deferred_copy_failure=True,
            error_message=failed.result.message.decode(),poisoned_until_reset=True,owners_balanced=True,common_quality_median_exact=True)
    finally:
        release.set()
        if timer:timer.join()
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
