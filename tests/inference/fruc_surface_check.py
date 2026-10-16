#!/usr/bin/env python3
"""Targeted native FRUC checks; external SDK, no engine build or hidden replay.

python fruc_surface_check.py SPEC.json rgb|lifecycle|yuv-span
Successful matching receipts prevent repeating a conclusive case. Timing is
observational, not integrated player FPS. Test upload/download is outside the
provider; its pixel route must remain entirely on CUDA.
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
from surface_cuda_check import Surface, Color, Plane, Rect, ownerfn, ptr, Params

wakeupfn = C.CFUNCTYPE(None, ptr)
class Create(C.Structure):
    _fields_ = [(n,C.c_uint32) for n in ['struct_size','version','flags','width','height','device_index','capacity','reserved']] + [
        ('generation',C.c_uint64),('cuda_context',ptr),('sdk_library',C.c_char_p),('sdk_runtime',C.c_char_p),
        ('kernel_fatbin',C.c_char_p),('wakeup',wakeupfn),('wakeup_opaque',ptr)]
class Phase(C.Structure):
    _fields_ = [('kind',C.c_uint32),('reserved',C.c_uint32),('scalar',C.c_double),('map',ptr)]
class Dependency(C.Structure):
    _fields_ = [('kind',C.c_uint32),('reserved',C.c_uint32),('event',ptr),('value',C.c_uint64)]
class Request(C.Structure):
    _fields_ = [(n,C.c_uint32) for n in ['struct_size','version','flags','input_count','output_count','phase_count','dependency_count','reserved']] + [
        ('generation',C.c_uint64),('inputs',ptr*8),('outputs',ptr*8),('phases',Phase*8),('dependencies',Dependency*8)]
class Completion(C.Structure):
    _fields_ = [(n,C.c_uint32) for n in ['struct_size','version','state','flags']] + [
        ('ticket',C.c_uint64),('status',C.c_int32),('reserved',C.c_uint32),('message',C.c_char*256)]
class Caps(C.Structure):
    _fields_ = [(n,C.c_uint32) for n in ['struct_size','version','flags','min_inputs','max_inputs','lookahead','max_outputs','max_phases']] + [
        (n,C.c_uint64) for n in ['input_resource_mask','output_resource_mask','input_format_mask','output_format_mask','dependency_mask']] + [
        (n,C.c_uint32) for n in ['phase_mask','queue_capacity','device_index','effective_bits']] + [('device_uuid',C.c_uint8*16),('provider',C.c_char*64)]
class Stats(C.Structure):
    _fields_ = [('struct_size',C.c_uint32),('version',C.c_uint32)] + [(n,C.c_uint64) for n in [
        'submitted','finished','failed','cancelled','primes','resets','sdk_calls','input_conversions','repeated','owned_pixel_bytes','cpu_pixel_copies']]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()
class Client:
    def __init__(self,s):
        self.s=s;self.allocations=[];self.held={};self.owners=[];self.wakes=0;self.events=[];self.streams=[];self.ctx=ptr();self.handle=ptr()
        self.driver=C.CDLL('libcuda.so.1')
        signatures={
            'cuInit':([C.c_uint],C.c_int),'cuDeviceGet':([ptr,C.c_int],C.c_int),
            'cuDevicePrimaryCtxRetain':([ptr,C.c_int],C.c_int),'cuDevicePrimaryCtxRelease_v2':([C.c_int],C.c_int),
            'cuCtxSetCurrent':([ptr],C.c_int),'cuCtxSynchronize':([],C.c_int),
            'cuMemAlloc_v2':([ptr,C.c_size_t],C.c_int),'cuMemFree_v2':([C.c_uint64],C.c_int),
            'cuMemcpyHtoD_v2':([C.c_uint64,ptr,C.c_size_t],C.c_int),'cuMemcpyDtoH_v2':([ptr,C.c_uint64,C.c_size_t],C.c_int),
            'cuStreamCreate':([ptr,C.c_uint],C.c_int),'cuStreamDestroy_v2':([ptr],C.c_int),'cuStreamSynchronize':([ptr],C.c_int),
            'cuEventCreate':([ptr,C.c_uint],C.c_int),'cuEventRecord':([ptr,ptr],C.c_int),'cuEventDestroy_v2':([ptr],C.c_int),
            'cuLaunchHostFunc':([ptr,ptr,ptr],C.c_int)}
        for n,(a,r) in signatures.items():f=getattr(self.driver,n);f.argtypes=a;f.restype=r
        self.ck(self.driver.cuInit(0));device=C.c_int();self.ck(self.driver.cuDeviceGet(C.byref(device),0))
        self.ck(self.driver.cuDevicePrimaryCtxRetain(C.byref(self.ctx),device));self.ck(self.driver.cuCtxSetCurrent(self.ctx))
        self.lib=C.CDLL(s['provider'],mode=os.RTLD_LOCAL)
        signatures={
            'aji_fruc_create_v1':([ptr,ptr,ptr,C.c_size_t],C.c_int),
            'aji_interpolator_query_v1':([ptr,C.c_uint32,ptr,C.c_size_t],C.c_int),
            'aji_interpolator_submit_v1':([ptr,ptr,ptr],C.c_int),
            'aji_interpolator_complete_v1':([ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],C.c_int),
            'aji_interpolator_drain_v1':([ptr,C.c_uint32],C.c_int),
            'aji_interpolator_reset_v1':([ptr,C.c_uint64],C.c_int),
            'aji_interpolator_stats_v1_get':([ptr,ptr,C.c_size_t],C.c_int),
            'aji_interpolator_destroy_v1':([ptr],None)}
        for n,(a,r) in signatures.items():f=getattr(self.lib,n);f.argtypes=a;f.restype=r
        @ownerfn
        def retain(owner):self.held[owner]=self.held.get(owner,0)+1;self.owners.append(('retain',owner))
        @ownerfn
        def release(owner):self.held[owner]-=1;self.owners.append(('release',owner))
        @wakeupfn
        def wake(_):self.wakes+=1
        self.retain,self.release,self.wake=retain,release,wake
        p=Create(version=1,flags=1,width=s['width'],height=s['height'],capacity=2,generation=1,cuda_context=self.ctx,
            sdk_library=os.fsencode(s['sdk']),sdk_runtime=os.fsencode(s['runtime']),kernel_fatbin=os.fsencode(s['fatbin']),wakeup=wake)
        p.struct_size=C.sizeof(p);err=C.create_string_buffer(1024)
        # Reject Quality/default use before any GPU/SDK initialization.
        p.flags=0;assert self.lib.aji_fruc_create_v1(C.byref(p),C.byref(self.handle),err,len(err))==-2 and not self.handle
        p.flags=1;start=time.perf_counter();status=self.lib.aji_fruc_create_v1(C.byref(p),C.byref(self.handle),err,len(err))
        self.setup_ms=(time.perf_counter()-start)*1000
        assert status==0,(status,err.value)
        caps=Caps();assert self.lib.aji_interpolator_query_v1(self.handle,1,C.byref(caps),C.sizeof(caps))==0
        assert caps.provider==b'nvidia-fruc' and caps.flags==3 and caps.effective_bits==8 and caps.queue_capacity==2
        assert caps.min_inputs==caps.max_inputs==2 and caps.lookahead==caps.max_outputs==caps.max_phases==1
        assert caps.input_resource_mask==caps.output_resource_mask==4 and caps.phase_mask==2
        before=bytes(caps)
        assert self.lib.aji_interpolator_query_v1(self.handle,2,C.byref(caps),C.sizeof(caps))==-2 and bytes(caps)==before
        assert self.lib.aji_interpolator_query_v1(self.handle,1,C.byref(caps),1)==-1 and bytes(caps)==before
    def ck(self,r):
        if r:raise RuntimeError(f'CUDA driver status {r}')
    def surface(self,pixels,fmt,seq,pts,generation=1):
        w,h=self.s['width'],self.s['height'];aw,ah=w+4,h+4;x=y=2
        channels=3 if fmt==1 else 1;bpp=2 if fmt==7 else 1
        planes=1 if fmt==1 else 3 if fmt==7 else 2
        stride=aw*bpp*channels+32;v=Surface(struct_size=C.sizeof(Surface),version=1,resource_kind=2,device_kind=2,
            device_context=self.ctx,format=fmt,width=aw,height=ah,crop=Rect(x,y,w,h),plane_count=planes,
            color=Color(1 if fmt==1 else 3,1,2,1,1,8 if fmt!=7 else 16,1 if fmt==1 else 3,1),
            pts=pts,duration=2 if seq<100 else 1,timebase_num=1001,timebase_den=48000,time_flags=3,
            sequence=seq,generation=generation,owner=len(self.allocations)+1000,retain=self.retain,release=self.release)
        backups=[]
        for i in range(planes):
            sy=2 if fmt==5 and i else 1;offset=16;size=offset+stride*(ah//sy)
            raw=np.full(size,0xa5,np.uint8);start=offset+(y//sy)*stride+x*bpp*channels
            if pixels is not None:
                data=np.asarray(pixels if fmt==1 else pixels[i]).view(np.uint8).reshape(h//sy,w*bpp*channels)
                for row in range(h//sy):raw[start+row*stride:start+row*stride+w*bpp*channels]=data[row]
            p=C.c_uint64();self.ck(self.driver.cuMemAlloc_v2(C.byref(p),size));self.allocations.append(p.value)
            self.ck(self.driver.cuMemcpyHtoD_v2(p.value,raw.ctypes.data,size));v.planes[i]=Plane(p.value,size,offset,stride);backups.append(raw)
        return v,backups
    def download(self,item,padding=True):
        v,backups=item;r=v.crop;values=[]
        for i in range(v.plane_count):
            p=v.planes[i];sy=2 if v.format==5 and i else 1;bpp=2 if v.format==7 else 1;channels=3 if v.format==1 else 1
            raw=np.empty(p.bytes,np.uint8);self.ck(self.driver.cuMemcpyDtoH_v2(raw.ctypes.data,p.data,p.bytes));mask=np.ones(raw.size,bool);rows=[]
            start=p.offset+(r.y//sy)*p.row_stride+r.x*bpp*channels
            for row in range(r.height//sy):
                off=start+row*p.row_stride;n=r.width*bpp*channels;rows.append(raw[off:off+n].copy());mask[off:off+n]=False
            if padding:assert np.array_equal(raw[mask],backups[i][mask]),'Write outside active crop'
            data=np.stack(rows)
            if v.format==7:data=data.reshape(-1).view('<u2').reshape(r.height,r.width)
            elif v.format==1:data=data.reshape(r.height,r.width,3)
            values.append(data)
        return values[0] if v.format==1 else values
    def request(self,a,b,o):
        r=Request(struct_size=C.sizeof(Request),version=1,input_count=2,output_count=1,phase_count=1,generation=a.generation)
        r.inputs[0]=C.addressof(a);r.inputs[1]=C.addressof(b);r.outputs[0]=C.addressof(o);r.phases[0]=Phase(kind=1,scalar=.5)
        return r
    def submit(self,r):
        ticket=C.c_uint64();start=time.perf_counter();code=self.lib.aji_interpolator_submit_v1(self.handle,C.byref(r),C.byref(ticket))
        return code,ticket.value,(time.perf_counter()-start)*1000
    def complete(self,ticket,consume=1):
        v=Completion();assert self.lib.aji_interpolator_complete_v1(self.handle,ticket,consume,C.byref(v),C.sizeof(v))==0
        return v
    def finish(self,ticket):
        assert self.lib.aji_interpolator_drain_v1(self.handle,0)==0
        v=self.complete(ticket);assert v.state==2 and v.status==0,(v.state,v.status,v.message)
        assert all(x==0 for x in self.held.values());return v
    def stats(self):
        v=Stats();assert self.lib.aji_interpolator_stats_v1_get(self.handle,C.byref(v),C.sizeof(v))==0
        return {n:getattr(v,n) for n,_ in v._fields_}
    def close(self):
        if self.handle:self.lib.aji_interpolator_destroy_v1(self.handle);self.handle=ptr()
        self.ck(self.driver.cuCtxSetCurrent(self.ctx))
        for e in self.events:self.ck(self.driver.cuEventDestroy_v2(e))
        for s in self.streams:self.ck(self.driver.cuStreamDestroy_v2(s))
        for p in self.allocations:self.ck(self.driver.cuMemFree_v2(p))
        self.ck(self.driver.cuDevicePrimaryCtxRelease_v2(0))
        assert all(v==0 for v in self.held.values())

def rgb(c,s,out):
    frames=np.fromfile(s['input'],np.uint8).reshape(-1,s['height'],s['width'],3)
    ref=np.fromfile(s['reference'],np.uint8).reshape(-1,s['height'],s['width'],4)[...,:3]
    assert len(frames)==6 and len(ref)==5
    sources=[c.surface(p,1,i+1,2*i-100) for i,p in enumerate(frames)]
    target=c.surface(None,1,100,-99);calls=[];guards=[];captures=[]
    # Rejection tests do not execute the SDK or acquire owners.
    a,b=sources[0][0],sources[1][0];o=target[0]
    for name,modify,code in [
        ('three-inputs',lambda r:setattr(r,'input_count',3),-2),
        ('spatial-phase',lambda r:setattr(r.phases[0],'kind',2),-2),
        ('quarter-phase',lambda r:setattr(r.phases[0],'scalar',.25),-2),
        ('stale-generation',lambda r:setattr(r,'generation',2),-1)]:
        r=c.request(a,b,o);modify(r);n=len(c.owners);status,t,_=c.submit(r);assert status==code and not t and len(c.owners)==n,name;guards.append(name)
    for name,modify,code in [
        ('host-resource',lambda v:setattr(v,'resource_kind',1),-2),
        ('foreign-context',lambda v:setattr(v,'device_context',1),-2),
        ('short-allocation',lambda v:setattr(v.planes[0],'bytes',4),-1),
        ('HDR',lambda v:setattr(v.color,'transfer',5),-2),
        ('negative-pitch',lambda v:setattr(v.planes[0],'row_stride',-32),-1),
        ('bad-PTS',lambda v:setattr(v,'timebase_den',0),-1),
        ('unpaired-owner',lambda v:setattr(v,'release',ownerfn()),-1)]:
        v=Surface.from_buffer_copy(bytes(b));modify(v);r=c.request(a,v,o);n=len(c.owners);status,t,_=c.submit(r)
        assert status==code and not t and len(c.owners)==n,name;guards.append(name)
    for i in range(5):
        o.pts=2*i-99;o.sequence=100+i;r=c.request(sources[i][0],sources[i+1][0],o)
        snap=[bytes(x) for x in [sources[i][0],sources[i+1][0],o]];start=time.perf_counter();status,t,submit_ms=c.submit(r)
        assert status==0 and t;done=c.finish(t);wall=(time.perf_counter()-start)*1000
        actual=c.download(target);captures.append(actual.copy());delta=np.abs(actual.astype(int)-ref[i].astype(int))
        calls.append(dict(pair=i,submit_ms=submit_ms,complete_wall_ms=wall,changed_bytes=int(np.count_nonzero(delta)),max_delta=int(delta.max()),repeated=bool(done.flags&1)))
        assert snap==[bytes(x) for x in [sources[i][0],sources[i+1][0],o]]
        print(json.dumps(calls[-1]),flush=True)
    np.save(out/'native-rgb.npy',np.stack(captures));stats=c.stats()
    assert stats['finished']==5 and stats['primes']==1 and stats['input_conversions']==6 and stats['sdk_calls']==6
    assert stats['owned_pixel_bytes']==s['width']*s['height']*12 and stats['cpu_pixel_copies']==0
    (out/'rgb-observations.json').write_text(json.dumps(dict(calls=calls,stats=stats,guards=guards),indent=2)+'\n')
    # A difference is diagnostic, not silently widened into a passing tolerance.
    assert all(x['changed_bytes']==0 and not x['repeated'] for x in calls),'Native/prototype pixels differ; inspect before accepting'
    return dict(calls=calls,stats=stats,guards=guards,roi_padding_exact=True,descriptors_unchanged=True,owners_balanced=True,prototype_exact=True)

def lifecycle(c,s,out):
    frames=np.fromfile(s['input'],np.uint8).reshape(-1,s['height'],s['width'],3)
    sources=[c.surface(p,1,i+1,2*i-100) for i,p in enumerate(frames)]
    first=c.surface(None,1,100,-93);queued=c.surface(None,1,101,-91)
    r=c.request(sources[3][0],sources[4][0],first[0]);q=c.request(sources[4][0],sources[5][0],queued[0])
    gate=ptr();event=ptr();c.ck(c.driver.cuStreamCreate(C.byref(gate),1));c.streams.append(gate)
    c.ck(c.driver.cuEventCreate(C.byref(event),2));c.events.append(event)
    entered=threading.Event();release=threading.Event()
    @wakeupfn
    def wait(_):
        entered.set();release.wait(10) # No CUDA API from this host callback.
    c.ck(c.driver.cuLaunchHostFunc(gate,wait,None));c.ck(c.driver.cuEventRecord(event,gate))
    assert entered.wait(1),'Producer gate did not start'
    r.dependency_count=1;r.dependencies[0]=Dependency(kind=1,event=event)
    timer=None
    try:
        code,t1,ms=c.submit(r);assert code==0 and t1
        assert c.complete(t1,0).state==1 and sum(c.held.values())==3
        code,t2,_=c.submit(q);assert code==0 and t2>t1
        n=len(c.owners);code,t3,_=c.submit(q);assert code==-4 and t3==0 and len(c.owners)==n
        # Deliberately delayed producer, while Drain cancels the queued request.
        timer=threading.Timer(.05,release.set);timer.start()
        assert c.lib.aji_interpolator_drain_v1(c.handle,1)==0
        a=c.complete(t1,0);b=c.complete(t2,0)
        assert a.state==2 and a.status==0 and b.state==4 and b.status==-5
        assert all(v==0 for v in c.held.values())
        c.download(first);assert np.all(c.download(queued)==0xa5),'Cancelled output was written'
    finally:
        release.set()
        if timer:timer.join()
    assert c.lib.aji_interpolator_reset_v1(c.handle,2)==0
    v=Completion();assert c.lib.aji_interpolator_complete_v1(c.handle,t1,0,C.byref(v),C.sizeof(v))==-1
    code,t,_=c.submit(r);assert code==-1 and not t,'Stale generation accepted'
    for item in sources+[first,queued]:item[0].generation=2
    first[0].pts=-99;r=c.request(sources[0][0],sources[1][0],first[0])
    code,t4,_=c.submit(r);assert code==0 and t4>t2;c.finish(t4);seek_pixels=c.download(first)
    assert not np.array_equal(seek_pixels,frames[0]) and not np.array_equal(seek_pixels,frames[1])
    # Fail the output kernel, after real SDK processing completed. This tests
    # poisoning/owner cleanup without causing a GPU crash or device reset.
    fail=C.CDLL(None).aji_test_fruc_fail_kernel;fail.argtypes=[C.c_uint];fail.restype=None
    queued[0].pts=-97;q=c.request(sources[1][0],sources[2][0],queued[0]);fail(2)
    code,t5,_=c.submit(q);assert code==0 and t5>t4
    assert c.lib.aji_interpolator_drain_v1(c.handle,0)==0
    v=c.complete(t5);assert v.state==3 and v.status==-3 and v.message
    assert all(x==0 for x in c.held.values()) and np.all(c.download(queued)==0xa5)
    n=len(c.owners);code,t,_=c.submit(q);assert code==-4 and not t and len(c.owners)==n
    assert c.lib.aji_interpolator_reset_v1(c.handle,3)==0
    stats=c.stats();assert stats['finished']==2 and stats['cancelled']==1 and stats['failed']==1 and stats['primes']==2
    assert stats['owned_pixel_bytes']==s['width']*s['height']*12
    return dict(stats=stats,dependency_pending=True,capacity_bounded=True,cancelled_output_untouched=True,
        seek_generation=True,tickets_monotone=True,error_after_sdk=True,error_message=v.message.decode(),
        poisoned_until_reset=True,owners_balanced=True,first_submit_ms=ms)

class KernelView(C.Structure):
    _fields_=[('p',C.c_uint64*3),('pitch',C.c_uint64*3)]+[(n,C.c_int) for n in ['x','y','width','height','format','range']]+[('kr',C.c_float),('kb',C.c_float)]
def kernel_pack(c,s,item):
    d=c.driver
    for name,args in {
        'cuModuleLoad':[ptr,C.c_char_p],'cuModuleGetFunction':[ptr,ptr,C.c_char_p],'cuModuleUnload':[ptr],
        'cuLaunchKernel':[ptr,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_uint,ptr,ptr,ptr]}.items():
        getattr(d,name).argtypes=args;getattr(d,name).restype=C.c_int
    module=ptr();fn=ptr();p=C.c_uint64();w,h=s['width'],s['height'];v=item[0]
    c.ck(d.cuModuleLoad(C.byref(module),os.fsencode(s['fatbin'])))
    try:
        c.ck(d.cuModuleGetFunction(C.byref(fn),module,b'aji_fruc_pack'))
        c.ck(d.cuMemAlloc_v2(C.byref(p),w*h*4));c.allocations.append(p.value)
        view=KernelView(x=v.crop.x,y=v.crop.y,width=w,height=h,format=v.format,range=v.color.range,kr=.2126,kb=.0722)
        for i in range(v.plane_count):view.p[i]=v.planes[i].data+v.planes[i].offset;view.pitch[i]=v.planes[i].row_stride
        args=(ptr*2)(C.addressof(view),C.addressof(p))
        c.ck(d.cuLaunchKernel(fn,(w+15)//16,(h+15)//16,1,16,16,1,0,None,args,None));c.ck(d.cuCtxSynchronize())
        rgb=np.empty((h,w,4),np.uint8);c.ck(d.cuMemcpyDtoH_v2(rgb.ctypes.data,p.value,rgb.nbytes));return rgb
    finally:c.ck(d.cuModuleUnload(module))

def yuv_span(c,s,out):
    from vfi_candidate_probe import rgb_to_yuv444,yuv444_to_rgb
    sp=json.loads(Path(s['span_spec']).read_text());w,h=s['width'],s['height']
    frames=np.fromfile(s['input'],np.uint8).reshape(-1,h,w,3)
    # Source3 and the acquired RIFE median3 are the actual inputs of the first
    # extra quarter of this pair. No repeated RIFE inference.
    left=rgb_to_yuv444(frames[3].astype(np.float64)/255)
    right=rgb_to_yuv444(np.load(s['rife_median']).astype(np.float64))
    a=c.surface(left,7,4,-94);b=c.surface(right,7,5,-92);target=c.surface(None,7,100,-93)
    packed=kernel_pack(c,s,a);expected=np.floor(np.clip(yuv444_to_rgb(left).astype(np.float64),0,1)*255+.5).astype(np.uint8)
    delta=np.abs(packed[...,:3].astype(int)-expected.astype(int));assert delta.max()<=1 and np.all(packed[...,3]==1)
    yuv_delta=int(delta.max())
    # Defined before measuring: floating matrix rounding may differ by ONE RGB8
    # code from the independent float64 conversion. Check chroma ROI clamping.
    yy,xx=np.indices((h,w));y=((xx+3*yy)%220+16).astype(np.uint8)
    cy,cx=np.indices((h//2,w//2));uv=np.empty((h//2,w),np.uint8)
    uv[:,0::2]=((cx+cy)%33+112).astype(np.uint8);uv[:,1::2]=((2*cx-cy)%31+113).astype(np.uint8)
    nv=c.surface([y,uv],5,20,-94);nv[0].color.range=2;packed_nv=kernel_pack(c,s,nv)
    gx=np.arange(w)*.5;gy=np.arange(h)*.5-.25;ix=np.floor(gx).astype(int);iy=np.floor(gy).astype(int);fx=gx-ix;fy=gy-iy
    def sample(channel):
        p=uv[:,channel::2].astype(np.float64);x0=ix.clip(0,w//2-1);x1=(ix+1).clip(0,w//2-1);y0=iy.clip(0,h//2-1);y1=(iy+1).clip(0,h//2-1)
        return ((1-fy[:,None])*((1-fx[None,:])*p[y0[:,None],x0[None,:]]+fx[None,:]*p[y0[:,None],x1[None,:]])+
            fy[:,None]*((1-fx[None,:])*p[y1[:,None],x0[None,:]]+fx[None,:]*p[y1[:,None],x1[None,:]]))
    yy=(y.astype(np.float64)-16)/219;u=(sample(0)-128)/224;v=(sample(1)-128)/224
    rr=yy+2*(1-.2126)*v;bb=yy+2*(1-.0722)*u;gg=(yy-.2126*rr-.0722*bb)/.7152
    expected_nv=np.floor(np.clip(np.stack([rr,gg,bb],-1),0,1)*255+.5).astype(np.uint8)
    delta=np.abs(expected_nv.astype(int)-packed_nv[...,:3].astype(int));assert delta.max()<=1
    nv_delta=int(delta.max());n=len(c.owners)
    # NV12 kernel is checked above; exercise descriptor negotiation separately,
    # without another synthesis. Output NV12 is deliberately unsupported.
    invalid=Surface.from_buffer_copy(bytes(target[0]));invalid.format=5
    r=c.request(nv[0],nv[0],invalid);code,t,_=c.submit(r);assert code==-2 and not t and len(c.owners)==n
    r=c.request(a[0],b[0],target[0]);snap=[bytes(x[0]) for x in [a,b,target]]
    start=time.perf_counter();code,t,submit_ms=c.submit(r);assert code==0 and t;done=c.finish(t);fruc_ms=(time.perf_counter()-start)*1000
    assert not done.flags,'SDK returned repetition instead of synthesis'
    actual=c.download(target);assert snap==[bytes(x[0]) for x in [a,b,target]]
    # GPU RGB8->YUV444 output must encode the same 8-bit RGB reconstructed from
    # it, within one 16-bit code (matrix FP32 arithmetic). No Quality claim.
    rgb=yuv444_to_rgb(actual);rounded=np.floor(np.clip(rgb,0,1)*255+.5).astype(np.uint8)
    expected_yuv=rgb_to_yuv444(rounded.astype(np.float64)/255)
    out_delta=max(int(np.max(np.abs(x.astype(int)-y.astype(int)))) for x,y in zip(actual,expected_yuv));assert out_delta<=1
    np.save(out/'fruc-quarter-native.npy',rgb)
    # Load TensorRT AFTER SDK creation to exercise the CUDA11/CUDA13 coexistence.
    lib=C.CDLL(sp['library'],mode=os.RTLD_LOCAL)
    for name,args,ret in [
        ('aji_create',[ptr],ptr),('aji_configure',[ptr,C.c_int,C.c_int,C.c_double,ptr,ptr],C.c_int),
        ('aji_last_error',[ptr],C.c_char_p),('aji_current_log',[ptr],C.c_char_p),('aji_destroy',[ptr],None),
        ('aji_surface_query_v1',[ptr,C.c_uint32,ptr,C.c_size_t],C.c_int),
        ('aji_surface_process_v1',[ptr,ptr,ptr,C.c_double,ptr],C.c_int)]:
        getattr(lib,name).argtypes=args;getattr(lib,name).restype=ret
    p=Params(api_version=9,cuda_context=c.ctx,conf_path=os.fsencode(sp['conf']),model_dir=os.fsencode(sp['models']),
        trtexec=os.fsencode('/bin/false'),slot=1,rife_model_dir=os.fsencode(sp['rife']))
    ctx=ptr(lib.aji_create(C.byref(p)));assert ctx
    try:
        ow,oh=C.c_int(),C.c_int();assert lib.aji_configure(ctx,w,h,24,C.byref(ow),C.byref(oh))==1,lib.aji_last_error(ctx)
        assert (ow.value,oh.value)==(w*2,h*2)
        (out/'span-runtime.log').write_text(lib.aji_current_log(ctx).decode())
        # Same client helper, temporarily configured for the spatial output size.
        big=dict(c.s);c.s=dict(c.s,width=ow.value,height=oh.value)
        try:up=c.surface(None,7,200,-93)
        finally:c.s=big
        up[0].duration=target[0].duration
        snap=[bytes(target[0]),bytes(up[0])];start=time.perf_counter()
        status=lib.aji_surface_process_v1(ctx,None,C.byref(target[0]),1,C.byref(up[0]));c.ck(c.driver.cuCtxSynchronize())
        span_ms=(time.perf_counter()-start)*1000;assert status==0,(status,lib.aji_last_error(ctx))
        assert snap==[bytes(target[0]),bytes(up[0])];result=yuv444_to_rgb(c.download(up));assert np.isfinite(result).all()
        np.save(out/'span-native.npy',result)
    finally:lib.aji_destroy(C.byref(ctx))
    return dict(stats=c.stats(),fruc_submit_ms=submit_ms,fruc_complete_wall_ms=fruc_ms,span_wall_ms=span_ms,
        yuv444_pack_max_rgb8_delta=yuv_delta,nv12_limited_pack_max_rgb8_delta=nv_delta,yuv444_output_max_code_delta=out_delta,
        rife_median_reused=True,fruc_to_span_gpu=True,span_dimensions=[ow.value,oh.value],pts_duration_unchanged=True,
        descriptors_unchanged=True,roi_padding_exact=True,owners_balanced=True,precision='FRUC 8-bit Fast; YUV444P16 container')

def main():
    s=json.loads(Path(sys.argv[1]).read_text());case=sys.argv[2];out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
    receipt=out/f'{case}-summary.json';identity={k:sha(s[k]) for k in ['provider','fatbin','sdk','runtime','input','reference']}
    if case=='yuv-span':
        sp=json.loads(Path(s['span_spec']).read_text());identity.update({k:sha(s[k]) for k in ['span_spec','rife_median']})
        identity.update({f'span/{k}':sha(sp[k]) for k in ['library','conf']})
        identity.update({f'span/{k}':sha(v) for k,v in sp['identity_files'].items()})
    identity.update(case=case,width=s['width'],height=s['height'],client=sha(__file__))
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity,'Existing receipt differs; choose a new explicit case output'
        print('Conclusive matching receipt exists; no GPU replay.');return
    if case=='rgb' and (out/'rgb-observations.json').exists():
        raise RuntimeError('RGB observations already exist: inspect this diagnostic before explicitly choosing any new GPU case')
    c=Client(s)
    try:
        if case=='rgb':result=rgb(c,s,out)
        elif case=='lifecycle':result=lifecycle(c,s,out)
        elif case=='yuv-span':result=yuv_span(c,s,out)
        else:raise ValueError('Case not yet implemented')
        result.update(setup_ms=c.setup_ms,identity=identity,case=case,passed=True)
    finally:c.close()
    result['cleanup_success']=True;receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
