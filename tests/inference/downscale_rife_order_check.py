#!/usr/bin/env python3
"""One three-source comparison: RIFE1080->Area720 vs Area720->RIFE720.
Identical sources/model/policy, no automatic repeat. Engine initialization can
compile missing plans on the provider worker; the caller runs this in background.
"""
import ctypes as C
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn
from vfi_candidate_probe import rgb_to_yuv444,yuv444_to_rgb

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(spec,order):
    out=Path(spec['output'])/order;out.mkdir(exist_ok=True)
    if (out/'summary.json').exists():
        old=json.loads((out/'summary.json').read_text());assert old['passed'] and old['identity']=={k:sha(spec[k]) for k in ['input','library','kernel','trt']},'Existing receipt belongs to another module/input; review before another trial';return old
    definitions={
        'area':dict(id='area720',kind='resize',method='area',runtime='cuda',target_height='720'),
        'rife':dict(id='rife426',kind='interpolate',method='rife',runtime='tensorrt',model='426',factor_numerator='2',factor_denominator='1',policy='quality',ensemble='no',scene_detect_threshold='0.150')}
    conf=out/'pipeline.conf';text='[global]\nbackend=TensorRT\nrife_engine=quality\nrife_drawings=no\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=2\n'
    for i,key in enumerate(order.split('-'),1):
        for k,v in definitions[key].items():text+=f'chain_1_stage_{i}_{k}={v}\n'
    conf.write_text(text);f=Fixture(spec);ctx=ptr();lib=C.CDLL(spec['library'])
    for n,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():
        getattr(lib,n).argtypes=args;getattr(lib,n).restype=None if 'destroy' in n else C.c_int
    @wakeupfn
    def wake(_):pass
    p=Create(struct_size=C.sizeof(Create),version=1,width=1920,height=1080,slot=1,capacity=1,generation=1,cuda_context=f.ctx,conf=os.fsencode(conf),model_dir=os.fsencode(spec['models']),rife_dir=os.fsencode(spec['rife']),trtexec=os.fsencode(spec['trtexec']),trt_library=os.fsencode(spec['trt']),kernel_fatbin=os.fsencode(spec['kernel']),fps_numerator=24000,fps_denominator=1001,wakeup=wake)
    err=C.create_string_buffer(1024);begin=time.perf_counter();captures=[];calls=[];flags=[]
    try:
        assert lib.aji_pipeline_create_v1(C.byref(p),C.byref(ctx),err,len(err))==0,err.value
        caps=Caps();deadline=time.monotonic()+1200
        while (code:=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps)))==-4:
            assert time.monotonic()<deadline,'Initialization timeout; do not restart automatically'
            time.sleep(.1)
        lib.aji_pipeline_last_error_v1(ctx,err,len(err));assert code==0,(code,err.value)
        assert (caps.width,caps.height,caps.factor)==(1280,720,2)
        setup=(time.perf_counter()-begin)*1000
        frames=np.fromfile(spec['input'],np.uint8).reshape(3,1080,1920,3);sources=[]
        for i,a in enumerate(frames):
            source=f.surface(rgb_to_yuv444(a.astype(np.float32)/255),7,i+1,i);source[0].timebase_den=24000;source[0].duration=1;sources.append(source)
        f.s=dict(width=1280,height=720);targets=[f.surface(None,7,100+i,i) for i in range(2)];f.s=spec
        for pair in range(3):
            eof=pair==2;count=1 if eof else 2
            request=Request(struct_size=C.sizeof(Request),version=1,flags=2 if eof else 0,output_count=count,generation=1,previous=None if eof else C.addressof(sources[pair][0]),current=C.addressof(sources[pair if eof else pair+1][0]))
            for j in range(count):
                target=targets[j][0];target.pts=pair*2+j;target.duration=2 if eof else 1;target.timebase_den=48000;request.outputs[j]=C.addressof(target)
            descriptors=[bytes(v[0]) for v in sources+targets];ticket=C.c_uint64();start=time.perf_counter()
            assert lib.aji_pipeline_submit_v1(ctx,C.byref(request),C.byref(ticket))==0
            assert lib.aji_pipeline_drain_v1(ctx,0)==0
            done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0
            wall=(time.perf_counter()-start)*1000;assert done.result.state==2,(done.result.state,done.result.message)
            assert descriptors==[bytes(v[0]) for v in sources+targets] and all(v==0 for v in f.held.values())
            for j in range(count):captures.append(np.stack(f.download(targets[j])));flags.append(done.output_flags[j])
            calls.append(dict(pair=pair,eof=eof,cold=pair==0,complete_wall_ms=wall,outputs=count));print(order,json.dumps(calls[-1]),flush=True)
        stats=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stats),C.sizeof(stats))==0;values={n:getattr(stats,n) for n,_ in stats._fields_}
        # Provenance marks operations applied to this output itself. A RIFE
        # prediction at720p is not subsequently resized in Area->RIFE.
        expected_flags=[33,34,33,34,33] if order=='rife-area' else [33,2,33,2,33]
        assert values['rife_predictions']==2 and values['cpu_pixel_copies']==values['failed']==0 and flags==expected_flags,(values,flags)
        np.save(out/'outputs-yuv16.npy',np.stack(captures))
        result=dict(passed=True,order=order,setup_ms=setup,calls=calls,stats=values,flags=flags,pts=[0,1,2,3,4],durations=[1,1,1,1,2],timebase=[1001,48000],owners_balanced=True,descriptors_unchanged=True,identity={k:sha(spec[k]) for k in ['input','library','kernel','trt']},model_sha256=sha(Path(spec['rife'])/'rife_v4.26.onnx'))
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return result
def main():
    spec=json.loads(Path(sys.argv[1]).read_text());out=Path(spec['output']);receipt=out/'summary.json'
    if receipt.exists():raise SystemExit('Conclusive order receipt exists; do not replay.')
    reference=run(spec,'rife-area');candidate=run(spec,'area-rife')
    a=np.load(out/'rife-area/outputs-yuv16.npy');b=np.load(out/'area-rife/outputs-yuv16.npy');assert np.array_equal(a[::2],b[::2]),'Original and EOF endpoints must match'
    delta=np.abs(a[1::2].astype(np.int32)-b[1::2].astype(np.int32));montage=Image.new('RGB',(1280*2,720*2))
    for i in range(2):
        for j,arr in enumerate([a,b]):
            rgb=yuv444_to_rgb(list(arr[1+2*i]));im=Image.fromarray(np.floor(np.clip(rgb,0,1)*255+.5).astype(np.uint8));montage.paste(im,(j*1280,i*720))
            ImageDraw.Draw(montage).text((j*1280+12,i*720+12),['RIFE1080 > Area720','Area720 > RIFE720'][j],fill='white')
    montage.save(out/'quality-comparison.png')
    ref=reference['calls'][1]['complete_wall_ms'];cand=candidate['calls'][1]['complete_wall_ms']
    result=dict(passed=True,reference=reference,candidate=candidate,original_eof_bit_exact=True,synthesis_max_delta_codes=int(delta.max()),synthesis_mean_abs_delta_codes=float(delta.mean()),warm_pair_ms=dict(reference=ref,candidate=cand),local_time_reduction_percent=100*(ref-cand)/ref,scope='Two intervals and EOF on one machine; one warm interval per order, no universal FPS or quality parity claim. Downscale is explicit and never enabled automatically.')
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
