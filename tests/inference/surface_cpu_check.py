#!/usr/bin/env python3
"""Real C surface client: contract/lifetime checks and parity against acquired CPU outputs."""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import numpy as np

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
ptr=C.c_void_p;ownerfn=C.CFUNCTYPE(None,ptr)
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
class Plan(C.Structure):_fields_=[(n,C.c_int) for n in ['width','height','numerator','denominator','active']]
layout=json.loads(Path(s['layout']).read_text())
assert layout==dict(surface=C.sizeof(Surface),caps=C.sizeof(Caps),**{n:getattr(Surface,n).offset for n in ['color','planes','owner','pts']})
lib=C.CDLL(s['library']);lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=ptr
lib.aji_vk_configure.argtypes=[ptr,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
lib.aji_vk_process.argtypes=[ptr,ptr,C.c_ssize_t,ptr,C.c_ssize_t,C.c_double,ptr,C.c_ssize_t]
lib.aji_vk_source_ids.argtypes=[ptr,C.c_uint64,C.c_uint64,C.c_uint64]
lib.aji_vk_error.argtypes=[ptr];lib.aji_vk_error.restype=C.c_char_p;lib.aji_vk_destroy.argtypes=[ptr]
lib.aji_surface_query_v1.argtypes=[ptr,C.c_uint32,ptr,C.c_size_t]
lib.aji_surface_process_v1.argtypes=[ptr,ptr,ptr,C.c_double,ptr]
events=[];held={}
@ownerfn
def retain(owner):held[owner]=held.get(owner,0)+1;events.append(('retain',owner))
@ownerfn
def release(owner):held[owner]-=1;events.append(('release',owner))
def surface(array,w,h,seq=0,crop=None,offset=0):
    v=Surface();v.struct_size=C.sizeof(v);v.version=1;v.resource_kind=v.device_kind=1;v.format=1
    v.width=w;v.height=h;v.plane_count=1;v.color=Color(1,1,2,1,0,8,1,1)
    v.planes[0]=Plane(array.ctypes.data,array.nbytes,offset,array.strides[0] if array.ndim==2 else w*3)
    v.crop=Rect(*(crop or (0,0,0,0)));v.sequence=seq;v.generation=1
    v.pts=seq;v.duration=1;v.timebase_num=1;v.timebase_den=24;v.time_flags=3
    v.owner=seq+100;v.retain=retain;v.release=release
    return v
def clone(v):return Surface.from_buffer_copy(bytes(v))
def process(ctx,a,b,t,dst):
    snapshots=[bytes(v) for v in [a,b,dst] if v is not None]
    status=lib.aji_surface_process_v1(ctx,C.byref(a) if a is not None else None,C.byref(b),t,C.byref(dst))
    assert snapshots==[bytes(v) for v in [a,b,dst] if v is not None]
    assert all(n==0 for n in held.values()),held
    return status
def create(spec=None):
    return lib.aji_vk_create(*(os.fsencode(spec[k]) if spec else None for k in ['conf','models','rife']),
                             b'cpu+cpu' if spec and spec.get('fast_tiled') else b'cpu',None,1 if spec else 0)

if s['phase']=='contract':
    ctx=create();assert ctx;plan=Plan()
    try:
        caps=Caps();C.memset(C.byref(caps),0xa5,C.sizeof(caps));before=bytes(caps)
        assert lib.aji_surface_query_v1(ctx,1,C.byref(caps),C.sizeof(caps))==-2 and bytes(caps)==before
        assert lib.aji_vk_configure(ctx,4,2,24,C.byref(plan))==0
        assert lib.aji_surface_query_v1(ctx,1,C.byref(caps),C.sizeof(caps))==0
        assert caps.version==1 and caps.flags==31 and caps.format_mask==caps.resource_mask==2 and not caps.negative_stride
        for context,version,size in [(ctx,2,C.sizeof(caps)),(ctx,1,1),(None,1,C.sizeof(caps))]:
            C.memset(C.byref(caps),0xa5,C.sizeof(caps));before=bytes(caps)
            assert lib.aji_surface_query_v1(context,version,C.byref(caps),size)<0 and bytes(caps)==before
        assert lib.aji_surface_query_v1(ctx,1,None,0)<0
        src=np.arange(4*29+5,dtype=np.uint8);dst=np.full(6*35+7,0xa5,np.uint8)
        a=surface(src,8,4,1,(1,1,4,2),5);a.planes[0].row_stride=29
        b=surface(dst,10,6,2,(3,2,4,2),7);b.planes[0].row_stride=35
        expected=dst.copy()
        for y in range(2):expected[7+(y+2)*35+9:7+(y+2)*35+21]=src[5+(y+1)*29+3:5+(y+1)*29+15]
        assert process(ctx,None,a,1,b)==0 and np.array_equal(dst,expected)
        assert len(events)==4
        cases=[]
        for label,modify,code in [
            ('version',lambda v:setattr(v,'version',2),-1),
            ('short-size',lambda v:setattr(v,'struct_size',1),-1),
            ('extent',lambda v:setattr(v.planes[0],'bytes',4),-1),
            ('stride',lambda v:setattr(v.planes[0],'row_stride',-29),-1),
            ('crop',lambda v:setattr(v.crop,'x',7),-1),
            ('native-resource',lambda v:setattr(v,'resource_kind',2),-2),
            ('high-depth',lambda v:setattr(v,'format',3),-2),
            ('HDR',lambda v:setattr(v.color,'transfer',5),-2),
            ('timing',lambda v:setattr(v,'timebase_den',0),-1),
            ('ownership',lambda v:setattr(v,'release',ownerfn()),-1),
            ('address-overflow',lambda v:setattr(v.planes[0],'data',2**(8*C.sizeof(ptr))-8),-1),
        ]:
            v=clone(a);modify(v);dst.fill(0xa5);n=len(events)
            assert process(ctx,None,v,1,b)==code,(label,lib.aji_vk_error(ctx))
            assert np.all(dst==0xa5) and len(events)==n;cases.append(label)
        v=clone(b);v.color.dither=3;assert process(ctx,None,a,1,v)==-2
        v=clone(b);v.color.primaries=2;assert process(ctx,None,a,1,v)==-1
        v=clone(a);v.rotation=90;assert process(ctx,v,a,.5,b)==-1
        v=clone(a);v.generation=2;assert process(ctx,v,a,.5,b)==-1
        assert process(ctx,None,a,float('nan'),b)==-1
        assert process(ctx,None,a,1,a)==-1
        assert np.all(dst==0xa5)
        result=dict(passed=True,c_layout=layout,roi_copy_exact=True,descriptors_unchanged=True,
            capabilities_negotiated=True,owners_balanced=True,validation_before_writing=True,negative_cases=cases,
            models_executed=False)
    finally:lib.aji_vk_destroy(ctx)
else:
    spec=json.loads(Path(s['reference_spec']).read_text());ref=np.load(Path(spec['output']).with_suffix('.npz'))
    w=spec.get('width',128);h=72;ctx=create(spec);assert ctx;plan=Plan();arrays={}
    try:
        assert lib.aji_vk_configure(ctx,w,h,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
        assert (plan.width,plan.height,plan.numerator,plan.denominator)==(2*w,2*h,2,1)
        caps=Caps();assert lib.aji_surface_query_v1(ctx,1,C.byref(caps),C.sizeof(caps))==0
        y,x,ch=np.indices((h,w,3));frames=[]
        for i in range(4):
            f=np.full((h,3*w+17),0xa5,np.uint8);f[:,:3*w]=((x*3+y*7+ch*13+i*37)%256).astype(np.uint8).reshape(h,3*w);frames.append(f)
        pixels=np.full((2*h,6*w+19),0xa5,np.uint8)
        def run(label,previous,current,t,seq=None,transfer=2,geometry=None):
            a=surface(previous,w,h,seq[0] if seq else 0) if previous is not None else None
            b=surface(current,w,h,seq[1] if seq else 0)
            if geometry:b.width,b.height,b.crop=geometry
            dst=surface(pixels,2*w,2*h,10);dst.timebase_den=48
            for v in [a,b,dst]:
                if v is not None:v.color.transfer=transfer
            pixels.fill(0xa5);assert process(ctx,a,b,t,dst)==0,lib.aji_vk_error(ctx)
            assert np.all(pixels[:,6*w:]==0xa5)
            arrays[label]=pixels[:,:6*w].copy()
        run('source-0',None,frames[0],1,(0,1))
        for i in (1,2,3):
            run('warm-middle' if i==1 else 'middle-'+str(i),frames[i-1],frames[i],.5,(i,i+1))
            run('source-'+str(i),frames[i-1],frames[i],1,(i,i+1))
        # Reuse the last pair's IDs, but change semantic color and pixels. This
        # must invalidate endpoint/motion data rather than trusting old IDs.
        run('color-guard',frames[0],frames[1],.5,(3,4),transfer=3)
        assert np.array_equal(arrays['color-guard'],ref['warm-middle'])
        # Same ID/stride and color, different active ROI; no false source hit.
        roi=np.full((h+2,3*w+17),0xa5,np.uint8)
        roi[1:h+1,3:3+3*w]=frames[2][:,:3*w]
        run('view-guard',None,roi,1,(0,4),transfer=3,geometry=(w+2,h+2,Rect(1,1,w,h)))
        assert np.array_equal(arrays['view-guard'],ref['source-2'])
        # A legacy client can follow the new adapter, even with recycled IDs.
        lib.aji_vk_source_ids(ctx,1,0,4)
        assert lib.aji_vk_process(ctx,None,0,frames[3].ctypes.data,frames[3].strides[0],1,pixels.ctypes.data,pixels.strides[0])==0
        assert np.array_equal(pixels[:,:6*w],ref['source-3'])
        assert lib.aji_vk_configure(ctx,w,h,24,C.byref(plan))==0
        run('reconfigured-source',None,frames[0],1,(0,1))
        changed={k:int(np.count_nonzero(arrays[k]!=ref[k])) for k in ref.files};assert not any(changed.values()),changed
        # Error after ownership acquisition, before a real provider run. Only
        # the injected error path is exercised; no repeated successful model run.
        fault=C.CDLL(None).aji_test_ort_fail_next_run;fault()
        b=surface(frames[1],w,h,2);d=surface(pixels,2*w,2*h,10);n=len(events)
        assert process(ctx,None,b,1,d)==-3,lib.aji_vk_error(ctx)
        assert len(events)==n+4 and b'injected surface execution failure' in lib.aji_vk_error(ctx)
        np.savez(out/'outputs.npz',**arrays)
        result=dict(passed=True,real_rife_span_cpu=True,fast=spec.get('fast_tiled',False),
            reused_reference=spec['output'],reference_outputs=len(ref.files),changed_bytes=changed,
            metadata_view_legacy_guards_exact=True,descriptors_unchanged=True,owners_balanced=True,
            provider_error_owners_released=True,quality_loss=False,fps_claim=False)
    finally:lib.aji_vk_destroy(ctx)
receipt.write_text(json.dumps(result,indent=2)+'\n');print(receipt.read_text())
