#!/usr/bin/env python3
"""One actual rank-5 TensorRT window: reuse versus fresh, order, reset and adjacent cuts."""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import numpy as np

class Params(C.Structure):
    _fields_ = [('api_version', C.c_uint32), ('cuda_context', C.c_void_p),
        ('conf_path', C.c_char_p), ('model_dir', C.c_char_p), ('trtexec', C.c_char_p),
        ('trtexec_env', C.c_char_p), ('slot', C.c_int), ('rife_model_dir', C.c_char_p),
        ('async_build', C.c_int), ('d3d11_device', C.c_void_p), ('engine_path', C.c_char_p),
        ('max_width', C.c_int), ('max_height', C.c_int), ('log', C.c_void_p), ('log_opaque', C.c_void_p)]
class Frame(C.Structure):
    _fields_ = [('width', C.c_int), ('height', C.c_int), ('format', C.c_int),
        ('matrix', C.c_int), ('range', C.c_int), ('siting', C.c_int),
        ('plane', C.c_void_p * 3), ('stride', C.c_ssize_t * 3)]
s=json.loads(Path(sys.argv[1]).read_text()); out=Path(s['output']);ptr=C.c_void_p
lib=C.CDLL(s['library']);cuda=C.CDLL('libcudart.so.13')
for name,args,rest in [
    ('aji_create',[C.POINTER(Params)],ptr),
    ('aji_configure',[ptr,C.c_int,C.c_int,C.c_double,C.POINTER(C.c_int),C.POINTER(C.c_int)],C.c_int),
    ('aji_ingest',[ptr,C.POINTER(Frame),C.c_uint64,ptr],C.c_int),
    ('aji_infer_seq',[ptr,C.c_uint64,C.POINTER(Frame),ptr],C.c_int),
    ('aji_temporal_reset',[ptr],None),('aji_temporal_radius',[ptr],C.c_int),
    ('aji_last_error',[ptr],C.c_char_p),('aji_destroy',[C.POINTER(ptr)],None),
    ('aji_flush',[ptr,ptr],C.c_uint64),('aji_wait',[ptr,C.c_uint64],C.c_int)]:
    f=getattr(lib,name);f.argtypes=args;f.restype=rest
for name,args in [('cudaMalloc',[C.POINTER(ptr),C.c_size_t]),('cudaFree',[ptr]),
    ('cudaMemcpy',[ptr,ptr,C.c_size_t,C.c_int]),('cudaStreamCreateWithFlags',[C.POINTER(ptr),C.c_uint]),
    ('cudaStreamDestroy',[ptr]),('cudaStreamSynchronize',[ptr])]:getattr(cuda,name).argtypes=args
allocated=[];streams=[];ctx=ptr();results={};arrays={}
def ck(code):assert code==0,(code,lib.aji_last_error(ctx))
def allocate(data=None):
    f=Frame(width=128,height=72,format=1,matrix=2,range=1,siting=1)
    pos=0
    for plane,rows in enumerate((72,36)):
        memory=ptr();ck(cuda.cudaMalloc(C.byref(memory),192*rows));allocated.append(memory)
        f.plane[plane]=memory;f.stride[plane]=192
        if data is not None:
            packed=np.full((rows,192),0xA5,np.uint8);size=128*rows
            packed[:,:128]=np.frombuffer(data[pos:pos+size],np.uint8).reshape(rows,128)
            ck(cuda.cudaMemcpy(memory,packed.ctypes.data,packed.nbytes,1));pos+=size
    return f
def uniform(y):return bytes([y])*(128*72)+bytes([128])*(128*36)
def configure(conf):
    global ctx
    if ctx:lib.aji_destroy(C.byref(ctx))
    p=Params(api_version=9,conf_path=os.fsencode(conf),model_dir=os.fsencode(s['models']),
             trtexec=os.fsencode(s['trtexec']),slot=1)
    ctx=ptr(lib.aji_create(C.byref(p)));assert ctx
    w,h=C.c_int(),C.c_int();assert lib.aji_configure(ctx,128,72,24,C.byref(w),C.byref(h))==1,lib.aji_last_error(ctx)
    assert (w.value,h.value)==(128,72) and lib.aji_temporal_radius(ctx)==1
def ingest(window,stream=None):
    stream=streams[0] if stream is None else stream
    for seq,f in window:ck(lib.aji_ingest(ctx,C.byref(f),seq,stream))
def infer(center,stream=None,expect_error=False):
    stream=streams[0] if stream is None else stream
    status=lib.aji_infer_seq(ctx,center,C.byref(output),stream)
    if expect_error:assert status<0;return status
    ck(status);ck(lib.aji_wait(ctx,lib.aji_flush(ctx,stream)))
    planes=[]
    for plane,rows in enumerate((72,36)):
        packed=np.empty((rows,192),np.uint8);ck(cuda.cudaMemcpy(packed.ctypes.data,output.plane[plane],packed.nbytes,2))
        planes.append(packed[:,:128].reshape(-1))
    return np.concatenate(planes)
def reset():lib.aji_temporal_reset(ctx)
def compare(name,got,fresh):
    delta=np.abs(got.astype(np.int16)-fresh.astype(np.int16))
    results[name]=dict(changed_bytes=int(np.count_nonzero(delta)),max_delta=int(delta.max()))
    arrays[name]=got;arrays[name+'-fresh']=fresh
try:
    for _ in range(2):
        stream=ptr();ck(cuda.cudaStreamCreateWithFlags(C.byref(stream),1));streams.append(stream)
    output=allocate()
    if not s.get('cut_only'):
        raw=Path(s['input']).read_bytes();size=128*72*3//2
        frames=[allocate(raw[i*size:(i+1)*size]) for i in range(3)]
        alternate=allocate(raw[size:2*size])
        configure(s['conf']);window=list(zip((10,11,12),frames))
        ingest(window);base=infer(11);ingest(window);compare('same-window',infer(11),base)
        for name,changed in [('neighbor-color',frames[0]),('neighbor-view',alternate)]:
            reset();ingest(window);infer(11)
            if name=='neighbor-color':changed.matrix=1;changed.range=2
            ck(lib.aji_ingest(ctx,C.byref(changed),10,streams[0]));got=infer(11)
            reset();ingest([(10,changed),*window[1:]]);compare(name,got,infer(11))
            frames[0].matrix=2;frames[0].range=1
        reset();ingest(window);normal=infer(11)
        ingest(list(zip((10,11,12),reversed(frames))));reused=infer(11)
        reset();ingest(list(zip((10,11,12),reversed(frames))));reverse=infer(11)
        assert np.count_nonzero(normal!=reverse)>0,'Weighted model must distinguish window order'
        arrays['ordered-window']=normal;arrays['reversed-window']=reverse
        compare('window-order',reused,reverse)
        results['window-order']['distinct_from_original']=int(np.count_nonzero(normal!=reverse))
        reset();infer(11,expect_error=True)
        # Recycled sequence numbers in a new generation cannot retain old frames.
        ingest([(11,alternate)]);new_generation=infer(11)
        reset();ingest([(11,alternate)]);compare('reset-generation',new_generation,infer(11))
        # Serial calls, two streams, no host wait between ingest and the consumer.
        reset();ingest(window,streams[0]);got=infer(11,streams[1])
        reset();ingest(window,streams[1]);compare('stream-transition',got,infer(11,streams[1]))
    # A replaced predecessor must refresh the next frame's scene-cut metric.
    configure(s['cut_conf']);black=allocate(uniform(16));near=allocate(uniform(120));gray=allocate(uniform(128))
    ingest([(10,black),(11,gray),(12,gray)]);infer(11)
    ck(lib.aji_ingest(ctx,C.byref(near),10,streams[0]));got=infer(11)
    reset();ingest([(10,near),(11,gray),(12,gray)]);compare('adjacent-cut',got,infer(11))
    results['adjacent-cut']['fresh_luma']=int(arrays['adjacent-cut-fresh'][0])
    assert results['adjacent-cut']['fresh_luma']!=128,'Cut fixture must include the replaced predecessor'
    if not s.get('cut_only'):
        # The endpoint is not part of a new timing run: only overflow/clamp correctness.
        reset();maximum=2**63-1;ingest([(maximum,gray)]);edge=infer(maximum)
        reset();ingest([(11,gray)]);compare('sequence-end-clamp',edge,infer(11))
    np.savez(out.with_suffix('.npz'),**arrays)
    out.with_suffix('.json').write_text(json.dumps(dict(results=results,real_rank5=True,synthetic_model=True,
        real_temporal_model_quality_claimed=False,fps_claimed=False),indent=2)+'\n')
    print(json.dumps(results,indent=2))
finally:
    for stream in streams:cuda.cudaStreamSynchronize(stream)
    if ctx:lib.aji_destroy(C.byref(ctx))
    for memory in allocated:cuda.cudaFree(memory)
    for stream in streams:cuda.cudaStreamDestroy(stream)
