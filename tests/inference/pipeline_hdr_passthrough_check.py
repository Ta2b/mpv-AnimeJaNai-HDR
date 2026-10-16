#!/usr/bin/env python3
"""One native HDR endpoint: no second conversion; reuse acquired HDR pixels."""
import ctypes as C
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists():raise SystemExit('Conclusive receipt exists; no replay.')
    build=Path('/home/ta2b/.animejanai-tools/work/pipeline-hdr-build-20261017')
    acquired=out.parent/'native-default/native-1-yuv16.npy';pixels=np.load(acquired);_,h,w=pixels.shape
    f=Fixture(dict(width=w,height=h));lib=C.CDLL(str(build/'libaji_pipeline.so'));ctx=ptr()
    for name,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_output_color_v1':[ptr,ptr,ptr,C.c_size_t,ptr],'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():
        getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if 'destroy' in name else C.c_int
    source=f.surface(pixels,7,1,17);target=f.surface(None,7,100,17)
    for v in [source,target]:
        v[0].timebase_den=24000;v[0].duration=1
        v[0].color.matrix=4;v[0].color.primaries=2;v[0].color.transfer=5;v[0].color.range=2
    Color=type(source[0].color);conf=out/'native-hdr.conf'
    conf.write_text('[global]\nbackend=TensorRT\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=hdr\nchain_1_stage_1_kind=hdr\nchain_1_stage_1_method=nvidia-truehdr\nchain_1_stage_1_runtime=cuda\n')
    @wakeupfn
    def wake(_):pass
    params=Create(struct_size=C.sizeof(Create),version=1,width=w,height=h,slot=1,capacity=1,flags=2,generation=1,cuda_context=f.ctx,conf=os.fsencode(conf),kernel_fatbin=os.fsencode(build/'aji_pipeline.fatbin'),fps_numerator=24000,fps_denominator=1001,wakeup=wake)
    err=C.create_string_buffer(1024)
    try:
        assert lib.aji_pipeline_create_v1(C.byref(params),C.byref(ctx),err,len(err))==0,err.value
        caps=Caps();deadline=time.monotonic()+10
        while (code:=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps)))==-4:
            assert time.monotonic()<deadline;time.sleep(.001)
        assert code==0
        queries=[]
        for transfer in [5,6]:
            color=Color();peak=C.c_double(-1);source[0].color.transfer=transfer
            assert lib.aji_pipeline_output_color_v1(ctx,C.byref(source[0].color),C.byref(color),C.sizeof(color),C.byref(peak))==0
            assert bytes(color)==bytes(source[0].color) and peak.value==0
            queries.append(transfer)
        source[0].color.transfer=5;descriptors=[bytes(v[0]) for v in [source,target]]
        request=Request(struct_size=C.sizeof(Request),version=1,flags=2,output_count=1,generation=1,current=C.addressof(source[0]));request.outputs[0]=C.addressof(target[0]);ticket=C.c_uint64()
        assert lib.aji_pipeline_submit_v1(ctx,C.byref(request),C.byref(ticket))==0
        assert lib.aji_pipeline_drain_v1(ctx,0)==0
        done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0 and done.result.state==2,(done.result.state,done.result.message)
        actual=np.stack(f.download(target));assert np.array_equal(actual,pixels)
        assert done.output_flags[0]==1 and all(v==0 for v in f.held.values())
        assert descriptors==[bytes(v[0]) for v in [source,target]]
        stats=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stats),C.sizeof(stats))==0
        assert stats.failed==stats.cpu_pixel_copies==stats.rife_predictions==stats.fruc_predictions==0
        result=dict(passed=True,native_hdr_bitexact=True,output_flags=[1],negotiated_peak=0,color_queries_preserved=queries,pts=17,duration=1,timebase=[1001,24000],descriptors_unchanged=True,owners_balanced=True,cpu_pixel_copies=0,library_sha256=hashlib.sha256((build/'libaji_pipeline.so').read_bytes()).hexdigest(),input_sha256=hashlib.sha256(acquired.read_bytes()).hexdigest(),scope='One native PQ GPU endpoint; PQ and HLG metadata negotiation. No SDR SDK reference replay or physical display claim.')
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
