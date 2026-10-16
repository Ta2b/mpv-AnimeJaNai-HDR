#!/usr/bin/env python3
"""One native downscale pair+EOF against independent 3:2 area weights.
No neural engine, driver service change or hidden plan build. ROI/padding/owners
and rational timestamps are checked using the existing surface client.
"""
import ctypes as C
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def reference(a):
    # For each consecutive three samples, the two pixel footprints have
    # weights (2/3,1/3) and (1/3,2/3). Apply horizontally then vertically.
    a=a.astype(np.float64);c,h,w=a.shape
    b=a.reshape(c,h,w//3,3)
    b=np.stack(((2*b[...,0]+b[...,1])/3,(b[...,1]+2*b[...,2])/3),axis=-1).reshape(c,h,w*2//3)
    b=b.reshape(c,h//3,3,w*2//3)
    b=np.stack(((2*b[:,:,0,:]+b[:,:,1,:])/3,(b[:,:,1,:]+2*b[:,:,2,:])/3),axis=2).reshape(c,h*2//3,w*2//3)
    return np.floor(b+.5).astype(np.uint16)
def main():
    spec=json.loads(Path(sys.argv[1]).read_text());out=Path(spec['output']);out.mkdir(parents=True,exist_ok=True)
    identity={k:sha(spec[k]) for k in ('library','kernel')}
    receipt=out/'summary.json'
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Matching receipt, no replay.');return
    conf=out/'downscale.conf';conf.write_text('[global]\nbackend=TensorRT\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=down720\nchain_1_stage_1_kind=resize\nchain_1_stage_1_method=area\nchain_1_stage_1_runtime=cuda\nchain_1_stage_1_factor_numerator=1\nchain_1_stage_1_factor_denominator=1\nchain_1_stage_1_target_height=720\n')
    s=dict(width=1920,height=1080);f=Fixture(s);lib=C.CDLL(spec['library']);ctx=ptr()
    for n,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():
        getattr(lib,n).argtypes=args;getattr(lib,n).restype=None if 'destroy' in n else C.c_int
    @wakeupfn
    def wake(_):pass
    p=Create(struct_size=C.sizeof(Create),version=1,width=1920,height=1080,slot=1,capacity=1,generation=1,cuda_context=f.ctx,conf=os.fsencode(conf),kernel_fatbin=os.fsencode(spec['kernel']),fps_numerator=24000,fps_denominator=1001,wakeup=wake)
    err=C.create_string_buffer(1024);timings=[];differences=[];flags=[]
    try:
        assert lib.aji_pipeline_create_v1(C.byref(p),C.byref(ctx),err,len(err))==0,err.value
        caps=Caps();deadline=time.monotonic()+10
        while (code:=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps)))==-4:
            assert time.monotonic()<deadline;time.sleep(.001)
        lib.aji_pipeline_last_error_v1(ctx,err,len(err));assert code==0,(code,err.value)
        assert (caps.width,caps.height,caps.factor,caps.stage_count)==(1280,720,1,1)
        y,x=np.indices((1080,1920));image=np.stack(((x*73+y*19)%65536,np.where((x+y)%2,65535,0),np.where(x<960,32768,16384))).astype(np.uint16)
        images=[image,np.roll(image,3,axis=2)];sources=[]
        for i,a in enumerate(images):
            v=f.surface(a,7,i+1,i);v[0].timebase_den=24000;v[0].duration=1;sources.append(v)
        f.s=dict(width=1280,height=720);target=f.surface(None,7,100,0);f.s=s
        for i in range(2):
            target[0].pts=i;target[0].duration=1;target[0].timebase_den=24000
            r=Request(struct_size=C.sizeof(Request),version=1,flags=2 if i else 0,output_count=1,generation=1,previous=None if i else C.addressof(sources[0][0]),current=C.addressof(sources[1][0]));r.outputs[0]=C.addressof(target[0])
            descriptors=[bytes(v[0]) for v in sources+[target]];ticket=C.c_uint64();start=time.perf_counter()
            assert lib.aji_pipeline_submit_v1(ctx,C.byref(r),C.byref(ticket))==0
            assert lib.aji_pipeline_drain_v1(ctx,0)==0
            done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0
            timings.append((time.perf_counter()-start)*1000);assert done.result.state==2,(done.result.state,done.result.message)
            actual=np.stack(f.download(target));ref=reference(images[i]);delta=np.abs(actual.astype(np.int32)-ref.astype(np.int32));differences.append(int(delta.max()))
            assert delta.max()<=1,'Fixed predeclared tolerance: <=1 16-bit code at rounding ties'
            assert descriptors==[bytes(v[0]) for v in sources+[target]] and all(v==0 for v in f.held.values())
            flags.append(done.output_flags[0]);assert flags[-1]==33
            for v in sources:f.download(v) # input padding intact too
        stat=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stat),C.sizeof(stat))==0
        stats={n:getattr(stat,n) for n,_ in stat._fields_};assert stats['source_conversions']==2 and stats['cpu_pixel_copies']==stats['rife_predictions']==stats['spatial_predictions']==stats['failed']==0
        assert len([a for a in f.owners if a[0]=='retain'])==len([a for a in f.owners if a[0]=='release'])
        result=dict(passed=True,identity=identity,geometry=[1920,1080,1280,720],max_error_codes=differences,tolerance_codes=1,complete_wall_ms=timings,stats=stats,output_flags=flags,source_pts=[0,1],output_pts=[0,1],timebase=[1001,24000],final_duration_preserved=True,roi_padding_intact=True,owners_balanced=True,descriptors_unchanged=True,scope='Pure native resize, gradients/high-frequency/chroma; neural cost/quality qualification pending')
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
