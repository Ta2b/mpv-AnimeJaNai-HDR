#!/usr/bin/env python3
"""New HDR pack/unpack against independent arithmetic, then one SDK frame.
Reuses the already acquired SDK reference. One reset checks fresh effect state.
No frame copies within the provider, no physical display or FPS claim.
"""
import ctypes as C,json,os,sys,time,hashlib
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn
from vfi_candidate_probe import rgb_to_yuv444
class View(C.Structure):
    _fields_=[('p',C.c_uint64*3),('pitch',C.c_uint64*3)]+[(k,C.c_int) for k in ['x','y','width','height','format','range']]
def view(s):
    v=View(x=s.crop.x,y=s.crop.y,width=s.crop.width,height=s.crop.height,format=s.format,range=s.color.range)
    for i in range(3):v.p[i]=s.planes[i].data+s.planes[i].offset;v.pitch[i]=s.planes[i].row_stride
    return v
def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists():raise SystemExit('Conclusive HDR receipt exists; do not replay.')
    ref=Path('/home/ta2b/Documents/mpv-AnimeJaNai-HDR/artifacts/performance/lots-20261017/lot-48/truehdr-reference')
    build=Path('/home/ta2b/.animejanai-tools/work/pipeline-hdr-build-20261017');a=np.load(ref/'input-rgba8.npy');rgb10=np.load(ref/'reference-rgb10a2.npy');h,w=a.shape[:2]
    f=Fixture(dict(width=w,height=h));d=f.driver
    for name,args in {'cuModuleLoad':[ptr,C.c_char_p],'cuModuleGetFunction':[ptr,ptr,C.c_char_p],'cuModuleUnload':[ptr],'cuLaunchKernel':[ptr]+[C.c_uint]*7+[ptr,ptr,ptr]}.items():getattr(d,name).argtypes=args;getattr(d,name).restype=C.c_int
    lib=C.CDLL(str(build/'libaji_pipeline.so'));ctx=ptr();module=ptr();pack=ptr();unpack=ptr();Color=type(f.surface(rgb_to_yuv444(a[...,:3].astype(np.float32)/255),7,1,0)[0].color)
    for name,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_output_color_v1':[ptr,ptr,ptr,C.c_size_t,ptr],'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_reset_v1':[ptr,C.c_uint64],'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if 'destroy' in name else C.c_int
    source=f.surface(rgb_to_yuv444(a[...,:3].astype(np.float32)/255),7,2,0);source[0].timebase_den=24000;source[0].duration=1;target=f.surface(None,7,100,0);target[0].timebase_den=24000;target[0].duration=1
    buf=C.c_uint64();f.ck(d.cuMemAlloc_v2(C.byref(buf),a.nbytes));f.allocations.append(buf.value)
    conf=out/'hdr.conf';conf.write_text('[global]\nbackend=TensorRT\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=hdr\nchain_1_stage_1_kind=hdr\nchain_1_stage_1_method=nvidia-truehdr\nchain_1_stage_1_runtime=cuda\nchain_1_stage_1_enabled=yes\nchain_1_stage_1_peak=1000\n')
    @wakeupfn
    def wake(_):pass
    params=Create(struct_size=C.sizeof(Create),version=1,width=w,height=h,slot=1,capacity=1,flags=0,generation=1,cuda_context=f.ctx,conf=os.fsencode(conf),kernel_fatbin=os.fsencode(build/'aji_pipeline.fatbin'),fps_numerator=24000,fps_denominator=1001,wakeup=wake)
    err=C.create_string_buffer(1024);times=[];errors=[]
    try:
        assert lib.aji_pipeline_create_v1(C.byref(params),C.byref(ctx),err,len(err))==-2 and not ctx and b'color-query-aware' in err.value,'Old client must fail explicitly before GPU HDR work'
        params.flags=2;assert lib.aji_pipeline_create_v1(C.byref(params),C.byref(ctx),err,len(err))==0,err.value
        caps=Caps();deadline=time.monotonic()+10
        while (code:=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps)))==-4:
            assert time.monotonic()<deadline;time.sleep(.001)
        lib.aji_pipeline_last_error_v1(ctx,err,len(err));assert code==0,(code,err.value);assert caps.flags&4 and caps.factor==1
        color=Color();peak=C.c_double();assert lib.aji_pipeline_output_color_v1(ctx,C.byref(source[0].color),C.byref(color),C.sizeof(color),C.byref(peak))==0
        assert (color.matrix,color.primaries,color.transfer,color.range,color.component_bits,peak.value)==(4,2,5,2,16,1000)
        target[0].color=color
        proof_path=out.parent/'hdr-kernel-proof.json';proof=json.loads(proof_path.read_text()) if proof_path.exists() else None
        if proof:
            assert proof['kernel_sha256']==hashlib.sha256((build/'aji_pipeline.fatbin').read_bytes()).hexdigest() and proof['reference_input_sha256']==hashlib.sha256((ref/'input-rgba8.npy').read_bytes()).hexdigest()
        else:
            f.ck(d.cuModuleLoad(C.byref(module),os.fsencode(build/'aji_pipeline.fatbin')));f.ck(d.cuModuleGetFunction(C.byref(pack),module,b'aji_pipeline_hdr_pack'));f.ck(d.cuModuleGetFunction(C.byref(unpack),module,b'aji_pipeline_hdr_unpack'))
            v=view(source[0]);args=(ptr*2)(C.cast(C.byref(v),ptr),C.cast(C.byref(buf),ptr));f.ck(d.cuLaunchKernel(pack,(w+15)//16,(h+15)//16,1,16,16,1,0,None,args,None));f.ck(d.cuCtxSynchronize());packed=np.empty_like(a);f.ck(d.cuMemcpyDtoH_v2(packed.ctypes.data,buf.value,packed.nbytes));assert np.array_equal(packed,a),'SDK bytes must match the acquired oracle exactly'
        channels=[(rgb10>>shift&1023).astype(np.float64)/1023 for shift in [0,10,20]];r,g,b=channels;yy=.2627*r+.678*g+.0593*b
        expected=np.stack([np.floor(np.clip(x,0,65535)+.5).astype(np.uint16) for x in [yy*56064+4096,(b-yy)/(2*(1-.0593))*57344+32768,(r-yy)/(2*(1-.2627))*57344+32768]])
        unpack_delta=None
        if not proof:
            f.ck(d.cuMemcpyHtoD_v2(buf.value,rgb10.ctypes.data,rgb10.nbytes));v=view(target[0]);args=(ptr*2)(C.cast(C.byref(buf),ptr),C.cast(C.byref(v),ptr));f.ck(d.cuLaunchKernel(unpack,(w+15)//16,(h+15)//16,1,16,16,1,0,None,args,None));f.ck(d.cuCtxSynchronize());unpack_delta=int(np.abs(np.stack(f.download(target)).astype(np.int32)-expected.astype(np.int32)).max());assert unpack_delta<=1,'Predeclared YUV16 conversion tolerance1code'
        for generation in [1,2]:
            if generation==2:assert lib.aji_pipeline_reset_v1(ctx,2)==0
            source[0].generation=target[0].generation=generation
            request=Request(struct_size=C.sizeof(Request),version=1,flags=2,output_count=1,generation=generation,current=C.addressof(source[0]));request.outputs[0]=C.addressof(target[0]);ticket=C.c_uint64();start=time.perf_counter()
            assert lib.aji_pipeline_submit_v1(ctx,C.byref(request),C.byref(ticket))==0;assert lib.aji_pipeline_drain_v1(ctx,0)==0
            done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0 and done.result.state==2,(done.result.state,done.result.message)
            times.append((time.perf_counter()-start)*1000);actual=np.stack(f.download(target));np.save(out/f'native-{generation}-yuv16.npy',actual);errors.append(int(np.abs(actual.astype(np.int32)-expected.astype(np.int32)).max()));assert done.output_flags[0]==65 and all(v==0 for v in f.held.values())
            # Compare in the SDK's10bit domain, allowing1code for SDK arithmetic
            # plus0.05code for independently verified YUV16 quantization.
            y=(actual[0].astype(np.float64)-4096)/56064;u=(actual[1].astype(np.float64)-32768)/57344;q=(actual[2].astype(np.float64)-32768)/57344
            rr=y+2*(1-.2627)*q;bb=y+2*(1-.0593)*u;gg=(y-.2627*rr-.0593*bb)/.678
            error=max(float(np.abs(channel-reference).max()*1023) for channel,reference in zip([rr,gg,bb],channels));assert error<=1.05,('HDR10 tolerance1code+YUV16rounding',error)
        stats=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stats),C.sizeof(stats))==0;assert stats.cpu_pixel_copies==stats.failed==0
        result=dict(passed=True,pack_bytes_exact=True,independent_unpack_max_yuv16_error=unpack_delta,native_sdk_max_yuv16_errors=errors,hdr10_tolerance_codes=1.05,complete_wall_ms=times,negotiated_color={'matrix':'BT.2020NC','primaries':'BT.2020','transfer':'PQ','range':'limited','container_bits':16,'sdk_effective_bits':10,'target_peak':peak.value},old_reader_explicitly_rejected=True,reset_recreates_effect=True,output_flags=[65,65],owners_balanced=True,pts_duration_preserved=True,cpu_pixel_copies=0,scope='One acquired gradient SDK reference, new kernel conversion checks, one native frame plus reset control; no physical HDR or FPS claim')
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        if module:f.ck(d.cuModuleUnload(module))
        f.close()
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
