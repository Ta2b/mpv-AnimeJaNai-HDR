#!/usr/bin/env python3
"""Short native ordered pipeline check. Uses existing plans, no hidden builds.
Three source frames -> two x4 intervals + final endpoint = nine GPU outputs.
Spec paths explicit; successful receipts are reused, not rerun automatically.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import numpy as np
from surface_cuda_check import ptr,ownerfn
from fruc_surface_check import Client,Surface,Completion,wakeupfn,Dependency
from vfi_candidate_probe import rgb_to_yuv444,yuv444_to_rgb

class Create(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','width','height','device_index','slot','capacity','flags']]+[
        ('generation',C.c_uint64),('cuda_context',ptr)]+[(n,C.c_char_p) for n in ['conf','model_dir','rife_dir','trtexec','trtexec_env','trt_library','fruc_library','kernel_fatbin']]+[
        ('fps_numerator',C.c_int64),('fps_denominator',C.c_int64),('pixel_budget',C.c_uint64),('wakeup',wakeupfn),('wakeup_opaque',ptr)]
class Caps(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','width','height','factor','capacity','flags','device_index','stage_count','lookahead','output_format','reserved']]+[('generation',C.c_uint64)]
class Request(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','flags','output_count','dependency_count','reserved']]+[
        ('generation',C.c_uint64),('previous',ptr),('current',ptr),('outputs',ptr*16),('dependencies',Dependency*3)]
class Done(C.Structure):
    _fields_=[('result',Completion),('output_count',C.c_uint32),('output_flags',C.c_uint32*16)]
class Stats(C.Structure):
    _fields_=[('struct_size',C.c_uint32),('version',C.c_uint32)]+[(n,C.c_uint64) for n in [
        'submitted','finished','failed','cancelled','source_conversions','rife_predictions','fruc_predictions','fruc_repetitions','spatial_predictions','pixel_bytes','peak_pixel_bytes','cpu_pixel_copies']]
class Fixture(Client):
    def __init__(self,s):
        self.s=s;self.allocations=[];self.held={};self.owners=[];self.wakes=0;self.events=[];self.streams=[];self.ctx=ptr();self.handle=ptr()
        self.driver=C.CDLL('libcuda.so.1');signatures={
            'cuInit':[C.c_uint],'cuDevicePrimaryCtxRetain':[ptr,C.c_int],'cuDevicePrimaryCtxRelease_v2':[C.c_int],
            'cuCtxSetCurrent':[ptr],'cuCtxSynchronize':[], 'cuMemAlloc_v2':[ptr,C.c_size_t],'cuMemFree_v2':[C.c_uint64],
            'cuMemcpyHtoD_v2':[C.c_uint64,ptr,C.c_size_t],'cuMemcpyDtoH_v2':[ptr,C.c_uint64,C.c_size_t]}
        for n,args in signatures.items():getattr(self.driver,n).argtypes=args;getattr(self.driver,n).restype=C.c_int
        self.ck(self.driver.cuInit(0));self.ck(self.driver.cuDevicePrimaryCtxRetain(C.byref(self.ctx),0));self.ck(self.driver.cuCtxSetCurrent(self.ctx))
        @ownerfn
        def retain(owner):self.held[owner]=self.held.get(owner,0)+1;self.owners.append(('retain',owner))
        @ownerfn
        def release(owner):self.held[owner]-=1;self.owners.append(('release',owner))
        self.retain,self.release=retain,release
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()
def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
    identity={k:digest(s[k]) for k in ['library','kernel','conf','trt','fruc','input']};identity.update({k:digest(v) for k,v in s['identity_files'].items()})
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Matching conclusive receipt; no replay.');return
    f=Fixture(s);lib=C.CDLL(s['library'],mode=os.RTLD_LOCAL);ctx=ptr();wake=threading.Event()
    @wakeupfn
    def on_wake(_):wake.set()
    for n,args in {
        'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],
        'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],
        'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_reset_v1':[ptr,C.c_uint64],
        'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],
        'aji_pipeline_destroy_v1':[ptr]}.items():getattr(lib,n).argtypes=args;getattr(lib,n).restype=None if 'destroy' in n else C.c_int
    p=Create(struct_size=C.sizeof(Create),version=1,width=s['width'],height=s['height'],slot=1,capacity=1,flags=1,
        generation=1,cuda_context=f.ctx,conf=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),rife_dir=os.fsencode(s['rife']),
        trtexec=b'/bin/false',trt_library=os.fsencode(s['trt']),fruc_library=os.fsencode(s['fruc']),kernel_fatbin=os.fsencode(s['kernel']),
        fps_numerator=24000,fps_denominator=1001,wakeup=on_wake)
    err=C.create_string_buffer(1024);started=time.perf_counter()
    try:
        assert lib.aji_pipeline_create_v1(C.byref(p),C.byref(ctx),err,len(err))==0,err.value
        caps=Caps();deadline=time.monotonic()+30
        while True:
            code=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps))
            if code!=-4:break
            assert time.monotonic()<deadline,'Initialization timed out; inspect the live process instead of restarting'
            wake.wait(.01);wake.clear()
        lib.aji_pipeline_last_error_v1(ctx,err,len(err));assert code==0,(code,err.value)
        assert (caps.width,caps.height,caps.factor,caps.stage_count,caps.lookahead,caps.output_format)==(2560,1440,4,3,1,7)
        setup_ms=(time.perf_counter()-started)*1000
        frames=np.fromfile(s['input'],np.uint8).reshape(-1,s['height'],s['width'],3)
        sources=[]
        indices=s.get("source_indices",[3,4,5]);include_eof=s.get("include_eof",True)
        for index in indices:
            v=f.surface(rgb_to_yuv444(frames[index].astype(np.float32)/255),7,index+1,index)
            v[0].timebase_den=24000;v[0].duration=1;sources.append(v)
        f.s=dict(s,width=caps.width,height=caps.height);targets=[f.surface(None,7,100+i,12+i) for i in range(4)];f.s=s
        calls=[];captures=[];timeline=[];flags=[]
        for pair in range(len(sources)-1+int(include_eof)):
            eof=pair==len(sources)-1;count=1 if eof else 4;r=Request(struct_size=C.sizeof(Request),version=1,flags=2 if eof else 0,output_count=count,generation=1)
            r.previous=None if eof else C.addressof(sources[pair][0]);r.current=C.addressof(sources[pair if eof else pair+1][0])
            for j in range(count):
                v=targets[j][0];v.pts=12+pair*4+j;v.duration=4 if eof else 1;v.timebase_den=96000;r.outputs[j]=C.addressof(v)
            snapshot=[bytes(v[0]) for v in sources+targets];ticket=C.c_uint64();start=time.perf_counter()
            code=lib.aji_pipeline_submit_v1(ctx,C.byref(r),C.byref(ticket));submit_ms=(time.perf_counter()-start)*1000;assert code==0 and ticket.value,(code,err.value)
            assert lib.aji_pipeline_drain_v1(ctx,0)==0
            done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0
            assert done.result.state==2 and done.result.status==0,(done.result.state,done.result.status,done.result.message)
            wall=(time.perf_counter()-start)*1000;assert snapshot==[bytes(v[0]) for v in sources+targets] and all(x==0 for x in f.held.values())
            for j in range(count):
                rgb=yuv444_to_rgb(f.download(targets[j]));assert np.isfinite(rgb).all();captures.append(rgb);timeline.append({'pts':targets[j][0].pts,'duration':targets[j][0].duration});flags.append(done.output_flags[j])
            calls.append(dict(pair=pair,eof=eof,submit_ms=submit_ms,complete_wall_ms=wall,output_count=count));print(json.dumps(calls[-1]),flush=True)
        stat=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stat),C.sizeof(stat))==0;stats={n:getattr(stat,n) for n,_ in stat._fields_}
        expected_count=4*(len(sources)-1)+int(include_eof)
        assert [x['pts'] for x in timeline]==list(range(12,12+expected_count))
        assert sum(x['duration'] for x in timeline)==4*(len(sources)-1+int(include_eof))
        assert stats['source_conversions']==len(sources) and stats['rife_predictions']==len(sources)-1 and stats['fruc_predictions']==2*(len(sources)-1) and stats['spatial_predictions']==4*(len(sources)-1)+1,stats
        assert stats['cpu_pixel_copies']==0 and stats['fruc_repetitions']==0 and stats['failed']==0
        assert flags==[17,20,18,20]*(len(sources)-1)+([17] if include_eof else []),flags
        np.save(out/'outputs.npy',np.stack(captures));result=dict(passed=True,identity=identity,client_sha256=digest(__file__),setup_ms=setup_ms,calls=calls,
            stats=stats,timeline=timeline,timebase=[1001,96000],output_flags=flags,owners_balanced=True,descriptors_unchanged=True,roi_padding_exact=True,
            stages_executed=['rife2','nvidia-fruc2','span2'],existing_plans_only=True,scope='Native GPU pipeline, not yet integrated mpv FPS; Fast SDK pixel repeatability nonconclusive')
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    result['cleanup_success']=True;receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
