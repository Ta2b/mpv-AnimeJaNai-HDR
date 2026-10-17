#!/usr/bin/env python3
"""New GPU artifact metric on cached SDK outputs, then one protected interval.
No neural plan, format diagnosis or conclusive SDK reference is replayed.
"""
import ctypes as C,json,os,sys,time,hashlib
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn
from vfi_candidate_probe import rgb_to_yuv444
ROOT=Path('/home/ta2b/Documents/mpv-AnimeJaNai-HDR/artifacts/performance')
BUILD=Path('/home/ta2b/.animejanai-tools/work/fruc-protection-build-20261017')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def metric(out):
    f=Fixture(dict(width=32,height=32));d=f.driver;module=ptr();kernel=ptr();start=ptr();stop=ptr();cases=[]
    for name,args in {'cuModuleLoad':[ptr,C.c_char_p],'cuModuleGetFunction':[ptr,ptr,C.c_char_p],'cuModuleUnload':[ptr],'cuLaunchKernel':[ptr]+[C.c_uint]*7+[ptr,ptr,ptr],'cuMemsetD8_v2':[C.c_uint64,C.c_ubyte,C.c_size_t],'cuEventCreate':[ptr,C.c_uint],'cuEventRecord':[ptr,ptr],'cuEventSynchronize':[ptr],'cuEventElapsedTime':[ptr,ptr,ptr],'cuEventDestroy_v2':[ptr]}.items():getattr(d,name).argtypes=args;getattr(d,name).restype=C.c_int
    f.ck(d.cuModuleLoad(C.byref(module),os.fsencode(BUILD/'aji_fruc.fatbin')));f.ck(d.cuModuleGetFunction(C.byref(kernel),module,b'aji_fruc_guard_analyze'));f.ck(d.cuEventCreate(C.byref(start),0));f.ck(d.cuEventCreate(C.byref(stop),0))
    references=json.loads((ROOT/'lots-20261017/lot-52-fruc-protection/edge-prototype.json').read_text())['results']
    try:
        for name,folder,inputs,synthesis,w,h in [('beam','beam','source-pair.rgba','sdk-direct.rgba',1920,1080),('ordinary','path','exact-sdk-input.rgba','direct.rgba',1280,720)]:
            base=ROOT/'lots-20261016/lot-46'/folder;pair=np.fromfile(base/inputs,np.uint8).reshape(2,h,w,4);synth=np.fromfile(base/synthesis,np.uint8).reshape(h,w,4);buffers=[]
            for array in [pair[0],pair[1],synth,np.zeros(3,np.uint64)]:
                p=C.c_uint64();f.ck(d.cuMemAlloc_v2(C.byref(p),array.nbytes));f.allocations.append(p.value);f.ck(d.cuMemcpyHtoD_v2(p.value,array.ctypes.data,array.nbytes));buffers.append(p)
            width=C.c_int(w);height=C.c_int(h);args=(ptr*6)(*[C.cast(C.byref(p),ptr) for p in buffers],C.cast(C.byref(width),ptr),C.cast(C.byref(height),ptr))
            f.ck(d.cuEventRecord(start,None));f.ck(d.cuLaunchKernel(kernel,(w+15)//16,(h+15)//16,1,16,16,1,0,None,args,None));f.ck(d.cuEventRecord(stop,None));f.ck(d.cuEventSynchronize(stop));elapsed=C.c_float();f.ck(d.cuEventElapsedTime(C.byref(elapsed),start,stop));sums=np.zeros(3,np.uint64);f.ck(d.cuMemcpyDtoH_v2(sums.ctypes.data,buffers[3].value,sums.nbytes));assert sums.tolist()==references[name]['bright_edge_energy'],(name,sums.tolist());trigger=int(sums[2])>2*max(int(sums[0]),int(sums[1]));assert trigger==(name=='beam')
            cases.append(dict(case=name,integer_sums=sums.tolist(),threshold_ratio=2,trigger=trigger,gpu_metric_ms=elapsed.value,input_sha256=sha(base/inputs),cached_sdk_sha256=sha(base/synthesis)))
        return dict(passed=True,cases=cases,scope='One new GPU metric interval per cached case; exact independent integer oracle, no SDK replay; isolated overhead only, no FPS claim.')
    finally:
        if module:f.ck(d.cuModuleUnload(module))
        for event in [start,stop]:
            if event:f.ck(d.cuEventDestroy_v2(event))
        f.close()
def native(out):
    w,h=1920,1080;pair=np.fromfile(ROOT/'lots-20261016/lot-46/beam/source-pair.rgba',np.uint8).reshape(2,h,w,4);planes=[rgb_to_yuv444(a[...,:3].astype(np.float32)/255) for a in pair];f=Fixture(dict(width=w,height=h));lib=C.CDLL(str(BUILD/'libaji_pipeline.so'));ctx=ptr();sources=[]
    for name,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if 'destroy' in name else C.c_int
    sdk=json.loads((ROOT/'lots-20261016/lot-45/sdk/summary.json').read_text());values={'id':'fruc-protected','kind':'interpolate','method':'nvidia-fruc','runtime':'cuda','policy':'fast','factor_numerator':'2','sdk_library':sdk['installed_library'],'sdk_runtime':sdk['installed_runtime'],'kernel_fatbin':str(BUILD/'aji_fruc.fatbin'),'artifact_protection':'yes'};conf=out/'protected.conf';conf.write_text('[global]\nbackend=TensorRT\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\n'+''.join('chain_1_stage_1_'+k+'='+v+'\n' for k,v in values.items()))
    for i,pixels in enumerate(planes):
        item=f.surface(pixels,7,i+1,41000000*i);item[0].timebase_num=1;item[0].timebase_den=1000000000;item[0].duration=41000000;sources.append(item)
    targets=[f.surface(None,7,100+i,20500000*i) for i in range(2)]
    @wakeupfn
    def wake(_):pass
    params=Create(struct_size=C.sizeof(Create),version=1,width=w,height=h,slot=1,capacity=1,flags=1,generation=1,cuda_context=f.ctx,conf=os.fsencode(conf),fruc_library=os.fsencode(BUILD/'libaji_fruc.so'),kernel_fatbin=os.fsencode(BUILD/'aji_pipeline.fatbin'),fps_numerator=1000,fps_denominator=41,wakeup=wake);err=C.create_string_buffer(1024);flags=[];captures=[];times=[]
    try:
        assert lib.aji_pipeline_create_v1(C.byref(params),C.byref(ctx),err,len(err))==0,err.value;caps=Caps();deadline=time.monotonic()+15
        while (code:=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps)))==-4:assert time.monotonic()<deadline;time.sleep(.001)
        lib.aji_pipeline_last_error_v1(ctx,err,len(err));assert code==0,(code,err.value)
        for i in range(2):
            count=2 if i==0 else 1;r=Request(struct_size=C.sizeof(Request),version=1,flags=2 if i else 0,output_count=count,generation=1,previous=None if i else C.addressof(sources[0][0]),current=C.addressof(sources[1][0]))
            for j in range(count):
                s=targets[j][0];s.timebase_num=1;s.timebase_den=1000000000;s.pts=41000000 if i else j*20500000;s.duration=41000000 if i else 20500000;r.outputs[j]=C.addressof(s)
            before=[bytes(s[0]) for s in sources+targets];ticket=C.c_uint64();t=time.perf_counter();assert lib.aji_pipeline_submit_v1(ctx,C.byref(r),C.byref(ticket))==0;assert lib.aji_pipeline_drain_v1(ctx,0)==0;done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0 and done.result.state==2,(done.result.state,done.result.message);times.append((time.perf_counter()-t)*1000)
            assert before==[bytes(s[0]) for s in sources+targets] and all(v==0 for v in f.held.values())
            for j in range(count):captures.append(np.stack(f.download(targets[j])));flags.append(done.output_flags[j])
        assert flags==[1,140,1],flags
        assert np.array_equal(captures[0],planes[0]) and np.array_equal(captures[1],planes[0]) and np.array_equal(captures[2],planes[1]),'Protected frame must repeat the exact YUV16 endpoint, not introduce blur/ghosting or RGB8 quantization'
        stats=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stats),C.sizeof(stats))==0;assert stats.fruc_predictions==1 and stats.fruc_repetitions==1 and stats.cpu_pixel_copies==stats.failed==0
        np.save(out/'protected-yuv16.npy',np.stack(captures));return dict(passed=True,output_flags=flags,source_originals_and_protected_frame_bitexact=True,pts_ns=[0,20500000,41000000],durations_ns=[20500000,20500000,41000000],complete_wall_ms=times,owners_balanced=True,roi_padding_intact=True,descriptors_unchanged=True,fruc_sdk_predictions=1,policy_repeats=1,cpu_pixel_copies=0,scope='One new protected beam interval plus EOF; no direct SDK/format/neural reference replay. Local fluidity reduced to original cadence for the protected interval.')
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists():raise SystemExit('Conclusive receipt exists; do not replay.')
    result=(metric if sys.argv[2]=='metric' else native)(out);result['identity']={name:sha(BUILD/name) for name in ['libaji_fruc.so','aji_fruc.fatbin','libaji_pipeline.so','aji_pipeline.fatbin']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
