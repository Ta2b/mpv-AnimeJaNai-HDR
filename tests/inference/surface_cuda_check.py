#!/usr/bin/env python3
"""One targeted native CUDA surface comparison per requested case, no engine builds.

Consumes a JSON spec (library, before, conf, models, rife, width, height,
format, mode=spatial|rife, output). Uses identical plans/inputs/options for both
modules. Successful receipts prevent repetition. No universal FPS assertion.
"""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

ptr=C.c_void_p
ownerfn=C.CFUNCTYPE(None,ptr)
class Rect(C.Structure):_fields_=[(n,C.c_int32) for n in ['x','y','width','height']]
class Color(C.Structure):_fields_=[(n,C.c_uint32) for n in ['matrix','primaries','transfer','range','siting','component_bits','quantization','dither']]
class Plane(C.Structure):_fields_=[('data',ptr),('bytes',C.c_uint64),('offset',C.c_uint64),('row_stride',C.c_int64)]
class Surface(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','resource_kind','format','device_kind','device_index']]+[
        ('device_context',ptr),('device_uuid',C.c_uint8*16),('device_luid',C.c_uint64),('resource',ptr),('subresource',C.c_uint64),
        ('width',C.c_int32),('height',C.c_int32),('crop',Rect)]+[(n,C.c_uint32) for n in ['plane_count','rotation','vertical_flip','reserved']]+[
        ('color',Color),('pts',C.c_int64),('duration',C.c_int64),('timebase_num',C.c_int32),('timebase_den',C.c_int32),
        ('time_flags',C.c_uint32),('reserved_time',C.c_uint32),('sequence',C.c_uint64),('generation',C.c_uint64),
        ('planes',Plane*4),('owner',ptr),('retain',ownerfn),('release',ownerfn)]
class Caps(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['struct_size','version','flags','max_dimension']]+[
        ('resource_mask',C.c_uint64),('format_mask',C.c_uint64)]+[(n,C.c_uint32) for n in ['max_planes','negative_stride','device_kind','device_index']]
class Frame(C.Structure):
    _fields_=[(n,C.c_int) for n in ['width','height','format','matrix','range','siting']]+[('plane',ptr*3),('stride',C.c_ssize_t*3)]
class Params(C.Structure):
    _fields_=[('api_version',C.c_uint32),('cuda_context',ptr)]+[(n,C.c_char_p) for n in ['conf_path','model_dir','trtexec','trtexec_env']]+[
        ('slot',C.c_int),('rife_model_dir',C.c_char_p),('async_build',C.c_int),('d3d11_device',ptr),('engine_path',C.c_char_p),
        ('max_width',C.c_int),('max_height',C.c_int),('log',ptr),('log_opaque',ptr)]

def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
    receipt=out/'summary.json'
    if receipt.exists():
        assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');return
    cuda=C.CDLL('libcudart.so.13');cuda.cudaGetErrorString.restype=C.c_char_p
    sig={'cudaMalloc':([C.POINTER(ptr),C.c_size_t],C.c_int),'cudaFree':([ptr],C.c_int),
        'cudaMemcpy':([ptr,ptr,C.c_size_t,C.c_int],C.c_int),'cudaMemset':([ptr,C.c_int,C.c_size_t],C.c_int),
        'cudaStreamCreateWithFlags':([C.POINTER(ptr),C.c_uint],C.c_int),'cudaStreamSynchronize':([ptr],C.c_int),
        'cudaStreamDestroy':([ptr],C.c_int)}
    for name,(args,ret) in sig.items():getattr(cuda,name).argtypes=args;getattr(cuda,name).restype=ret
    def ck(v):
        if v:raise RuntimeError(cuda.cudaGetErrorString(v).decode())
    libs=[C.CDLL(s[k],mode=os.RTLD_LOCAL) for k in ['before','library']]
    for lib in libs:
        sig={'aji_create':([C.POINTER(Params)],ptr),'aji_configure':([ptr,C.c_int,C.c_int,C.c_double,ptr,ptr],C.c_int),
            'aji_destroy':([C.POINTER(ptr)],None),'aji_last_error':([ptr],C.c_char_p),
            'aji_infer':([ptr,ptr,ptr,ptr],C.c_int),'aji_infer_rife':([ptr,ptr,ptr,C.c_double,ptr,ptr],C.c_int),
            'aji_rife_before_upscale':([ptr],C.c_int),'aji_rife_begin_pair':([ptr,C.c_uint64,C.c_uint64],None),
            'aji_temporal_reset':([ptr],None),'aji_current_log':([ptr],C.c_char_p)}
        for name,(args,ret) in sig.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=ret
    lib=libs[1];lib.aji_surface_query_v1.argtypes=[ptr,C.c_uint32,ptr,C.c_size_t]
    lib.aji_surface_process_v1.argtypes=[ptr,ptr,ptr,C.c_double,ptr]
    held={};events=[];allocated=[];contexts=[];stream=ptr();results={}
    @ownerfn
    def retain(owner):held[owner]=held.get(owner,0)+1;events.append(('retain',owner))
    @ownerfn
    def release(owner):held[owner]-=1;events.append(('release',owner))
    fmt=s['format'];bpp=1 if fmt==1 else 2;planes=3 if fmt==3 else 2
    def allocate(w,h,seq,value,destination=False,roi=True):
        # The active view has even crop and nonzero offsets inside larger native allocations.
        aw,ah=(w+4,h+4) if roi else (w,h);x=y=2 if roi else 0;stride=aw*bpp+32
        f=Frame(width=w,height=h,format=fmt,matrix=s.get('matrix',2),range=s.get('range',1),siting=s.get('siting',1))
        v=Surface();v.struct_size=C.sizeof(v);v.version=1;v.resource_kind=v.device_kind=2
        v.format={1:5,2:6,3:7}[fmt];v.width=aw;v.height=ah;v.crop=Rect(x,y,w,h);v.plane_count=planes
        v.color=Color(f.matrix+1,s.get('primaries',1),s.get('transfer',2),2 if f.range==1 else 1,f.siting,8 if fmt==1 else 10 if fmt==2 else 16,3,1)
        v.sequence=seq;v.generation=1;v.pts=seq;v.duration=1;v.timebase_num=1;v.timebase_den=24;v.time_flags=3
        v.owner=seq+100;v.retain=retain;v.release=release;backups=[]
        for i in range(planes):
            sy=2 if planes==2 and i else 1;rows=ah//sy;offset=16
            p=ptr();size=offset+stride*rows;ck(cuda.cudaMalloc(C.byref(p),size));allocated.append(p)
            raw=np.full(size,0xa5,np.uint8)
            active=offset+(y//sy)*stride+x*bpp
            if not destination:
                yy,xx=np.indices((h//sy,w));sample=(xx*3+yy*7+i*31+value*17)%220+16 if i==0 else (xx+yy+value*3)%31+112
                if bpp==2:sample=(sample.astype(np.uint16) << 8).astype('<u2')
                else:sample=sample.astype(np.uint8)
                for row in range(h//sy):raw[active+row*stride:active+row*stride+w*bpp]=sample[row].view(np.uint8).reshape(-1)
            ck(cuda.cudaMemcpy(p,raw.ctypes.data,raw.nbytes,1))
            v.planes[i]=Plane(p.value,size,offset,stride);f.plane[i]=p.value+active;f.stride[i]=stride;backups.append(raw)
        ck(cuda.cudaStreamSynchronize(None));return f,v,backups
    def download(frame,check_padding=False):
        f,v,backups=frame;values=[]
        for i in range(planes):
            raw=np.empty(v.planes[i].bytes,np.uint8);ck(cuda.cudaMemcpy(raw.ctypes.data,v.planes[i].data,raw.nbytes,2))
            sy=2 if planes==2 and i else 1;start=f.plane[i]-v.planes[i].data;mask=np.ones(raw.size,bool)
            for y in range(f.height//sy):
                off=start+y*f.stride[i];values.append(raw[off:off+f.width*bpp].copy());mask[off:off+f.width*bpp]=False
            if check_padding:assert np.array_equal(raw[mask],backups[i][mask]),'CUDA output wrote outside active ROI'
        return np.concatenate(values)
    try:
        ck(cuda.cudaStreamCreateWithFlags(C.byref(stream),1));w,h=s['width'],s['height']
        dimensions=[]
        for module in libs:
            p=Params(api_version=9,conf_path=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),
                trtexec=os.fsencode(s.get('trtexec','/bin/false')),slot=1,rife_model_dir=os.fsencode(s['rife']))
            ctx=ptr(module.aji_create(C.byref(p)));assert ctx;contexts.append(ctx)
            ow,oh=C.c_int(),C.c_int();status=module.aji_configure(ctx,w,h,24,C.byref(ow),C.byref(oh))
            assert status==(0 if s.get('rife_only') else 1),(status,module.aji_last_error(ctx));dimensions.append((ow.value,oh.value))
            print(module.aji_current_log(ctx).decode(),flush=True)
        assert dimensions[0]==dimensions[1];ow,oh=dimensions[0]
        caps=Caps();assert lib.aji_surface_query_v1(contexts[1],1,C.byref(caps),C.sizeof(caps))==0
        assert caps.resource_mask==4 and caps.format_mask==224 and caps.device_kind==2 and caps.max_planes==3
        assert caps.flags&64 and bool(caps.flags&128)==(s['mode']=='rife')
        before=bytes(caps)
        assert lib.aji_surface_query_v1(contexts[1],2,C.byref(caps),C.sizeof(caps))==-2 and bytes(caps)==before
        assert lib.aji_surface_query_v1(contexts[1],1,C.byref(caps),1)==-1 and bytes(caps)==before
        left=allocate(w,h,1,0);right=allocate(w,h,2,1);old=allocate(ow,oh,3,0,True);new=allocate(ow,oh,4,0,True)
        if s.get('error_only'):
            fail=C.CDLL(None).aji_test_cuda_fail_next_allocation;fail.argtypes=[];fail.restype=None
            snapshots=[bytes(x[1]) for x in [left,right,new]];n=len(events);fail()
            status=lib.aji_surface_process_v1(contexts[1],C.byref(left[1]),C.byref(right[1]),.5,C.byref(new[1]))
            assert status==-3 and b'CUDA temporary allocation' in lib.aji_last_error(contexts[1])
            assert len(events)-n==6 and all(v==0 for v in held.values())
            assert snapshots==[bytes(x[1]) for x in [left,right,new]]
            assert np.all(download(new,True)==0xa5)
            result=dict(passed=True,injected_allocation_error=True,owners_balanced=True,
                output_untouched=True,descriptors_unchanged=True,models_executed=False)
            receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return
        if s.get('reference_output'):
            expected=np.load(s['reference_output'])['before'];old_ms=None
        else:
            # Independently drive the established ABI9 sequence on the original binary.
            a,b=left[0],right[0];module=libs[0];ctx=contexts[0]
            module.aji_temporal_reset(ctx);module.aji_rife_begin_pair(ctx,1,2)
            middle=[];start=time.perf_counter()
            if s['mode']=='spatial':status=module.aji_infer(ctx,C.byref(b),C.byref(old[0]),stream)
            elif s.get('rife_only'):status=module.aji_infer_rife(ctx,C.byref(a),C.byref(b),.5,C.byref(old[0]),stream)
            elif module.aji_rife_before_upscale(ctx):
                middle=allocate(w,h,5,0,True,False)
                status=module.aji_infer_rife(ctx,C.byref(a),C.byref(b),.5,C.byref(middle[0]),stream)
                assert status==0,(status,module.aji_last_error(ctx));status=module.aji_infer(ctx,C.byref(middle[0]),C.byref(old[0]),stream)
            else:
                ma,mb=allocate(ow,oh,5,0,True,False),allocate(ow,oh,6,0,True,False)
                assert module.aji_infer(ctx,C.byref(a),C.byref(ma[0]),stream)==0
                assert module.aji_infer(ctx,C.byref(b),C.byref(mb[0]),stream)==0
                status=module.aji_infer_rife(ctx,C.byref(ma[0]),C.byref(mb[0]),.5,C.byref(old[0]),stream)
            assert status==(1 if s.get('expect_scene') else 0),(status,module.aji_last_error(ctx));ck(cuda.cudaStreamSynchronize(stream));old_ms=(time.perf_counter()-start)*1000
            expected=download(ma if s.get('expect_scene') else old,True)
        snapshots=[bytes(x[1]) for x in [left,right,new]];n=len(events)
        start=time.perf_counter();status=lib.aji_surface_process_v1(contexts[1],C.byref(left[1]) if s['mode']=='rife' else None,
            C.byref(right[1]),.5 if s['mode']=='rife' else 1,C.byref(new[1]));new_ms=(time.perf_counter()-start)*1000
        assert status==0,(status,lib.aji_last_error(contexts[1]));actual=download(new,True)
        changed=int(np.count_nonzero(expected!=actual));np.savez(out/'pixels.npz',before=expected,after=actual)
        assert not changed,{'changed':changed,'max_delta':int(np.max(np.abs(expected.astype(int)-actual.astype(int))))}
        assert snapshots==[bytes(x[1]) for x in [left,right,new]] and all(x==0 for x in held.values())
        owners=3 if s['mode']=='rife' else 2;assert len(events)-n==owners*2
        cases=[]
        if s.get('guards'):
            for label,modify,code in [
                ('host-resource',lambda v:setattr(v,'resource_kind',1),-2),
                ('wrong-device',lambda v:setattr(v,'device_index',99),-2),
                ('wrong-context',lambda v:setattr(v,'device_context',1),-2),
                ('wrong-uuid',lambda v:v.device_uuid.__setitem__(0,1),-2),
                ('short-extent',lambda v:setattr(v.planes[0],'bytes',4),-1),
                ('negative-stride',lambda v:setattr(v.planes[0],'row_stride',-10),-1),
                ('bad-crop',lambda v:setattr(v.crop,'x',1),-1),
                ('bad-pointer',lambda v:setattr(v.planes[0],'data',1),-1),
                ('HDR',lambda v:setattr(v.color,'transfer',5),-2),
                ('added-dither',lambda v:setattr(v.color,'dither',2),-2),
                ('unpaired-callback',lambda v:setattr(v,'release',ownerfn()),-1),
                ('bad-timing',lambda v:setattr(v,'timebase_den',0),-1)]:
                v=Surface.from_buffer_copy(bytes(right[1]));modify(v);n=len(events)
                assert lib.aji_surface_process_v1(contexts[1],None,C.byref(v),1,C.byref(new[1]))==code,label
                assert len(events)==n and np.array_equal(download(new,True),actual);cases.append(label)
            assert lib.aji_surface_process_v1(contexts[1],None,C.byref(right[1]),float('nan'),C.byref(new[1]))==-1
            # Same geometry as source required for a precise overlap test.
            overlap=Surface.from_buffer_copy(bytes(new[1]));overlap.planes[0]=new[1].planes[1]
            assert lib.aji_surface_process_v1(contexts[1],None,C.byref(right[1]),1,C.byref(overlap))==-1
            assert lib.aji_configure(contexts[1],1,h,24,None,None)<0
            assert lib.aji_surface_query_v1(contexts[1],1,C.byref(caps),C.sizeof(caps))==-2
        results=dict(passed=True,changed_bytes=changed,format=fmt,mode=s['mode'],roi_and_padding_exact=True,
            descriptors_unchanged=True,owners_balanced=True,native_gpu_memory=True,negative_cases=cases,
            before_wall_ms=old_ms,after_wall_ms=new_ms,timing_conclusion='not an FPS benchmark; first-use adapter allocations included')
        receipt.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))
    finally:
        for module,ctx in zip(libs,contexts):module.aji_destroy(C.byref(ctx))
        if stream:ck(cuda.cudaStreamDestroy(stream))
        for p in allocated:ck(cuda.cudaFree(p))
if __name__=='__main__':main()
