#!/usr/bin/env python3
"""Acquire one existing TrueHDR SDK gradient frame as an integration oracle.
User-owned SDK and adapter; no model/SDK redistribution or physical HDR claim.
"""
import ctypes as C,hashlib,json,sys,time
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,ptr
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
if (out/'summary.json').exists():raise SystemExit('Existing reference, no replay.')
f=Fixture(dict(width=1280,height=720))
libpath='/home/ta2b/.local/share/AnimeJaNai-HDR-linux/animejanai/inference/libaji_rtx.so'
lib=C.CDLL(libpath);lib.aji_rtx_create.argtypes=[ptr,ptr,C.c_int,C.c_int];lib.aji_rtx_create.restype=C.c_int
lib.aji_rtx_eval.argtypes=[ptr,ptr]+[C.c_int]*9;lib.aji_rtx_eval.restype=C.c_int
lib.aji_rtx_shutdown.argtypes=[];lib.aji_rtx_shutdown.restype=None
w,h=1280,720;x=np.linspace(0,255,w).astype(np.uint8)
a=np.empty((h,w,4),np.uint8);a[...,:3]=x[None,:,None];a[...,3]=255
for i,color in enumerate([[255,0,0],[0,255,0],[0,0,255],[255,255,255]]):a[:h//4,i*w//4:(i+1)*w//4,:3]=color
buffers=[];created=False
try:
    for i in range(2):
        p=C.c_uint64();f.ck(f.driver.cuMemAlloc_v2(C.byref(p),a.nbytes));buffers.append(p.value);f.allocations.append(p.value)
    f.ck(f.driver.cuMemcpyHtoD_v2(buffers[0],a.ctypes.data,a.nbytes))
    start=time.perf_counter();created=lib.aji_rtx_create(f.ctx,None,1,0)==1;setup=(time.perf_counter()-start)*1000
    assert created,'SDK create failed'
    start=time.perf_counter();ok=lib.aji_rtx_eval(buffers[0],buffers[1],w,h,w,h,1,100,100,50,1000)
    f.ck(f.driver.cuCtxSynchronize());ms=(time.perf_counter()-start)*1000;assert ok==1,'SDK run failed'
    b=np.empty((h,w),np.uint32);f.ck(f.driver.cuMemcpyDtoH_v2(b.ctypes.data,buffers[1],b.nbytes))
    np.save(out/'input-rgba8.npy',a);np.save(out/'reference-rgb10a2.npy',b)
    rgb=np.stack([b&1023,(b>>10)&1023,(b>>20)&1023],axis=-1);assert np.ptp(rgb)>0
    result=dict(passed=True,provider=libpath,library_sha256=hashlib.sha256(Path(libpath).read_bytes()).hexdigest(),dimensions=[w,h],tunables=dict(contrast=100,saturation=100,middle_gray=50,peak=1000),setup_ms=setup,run_including_load_ms=ms,rgb10_min=rgb.min(axis=(0,1)).tolist(),rgb10_max=rgb.max(axis=(0,1)).tolist(),black_rgb10=rgb[-1,0].tolist(),white_rgb10=rgb[-1,-1].tolist(),scope='One real SDK gradient/patch frame, acquired as integration oracle; no physical HDR or FPS claim')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
finally:
    if created:lib.aji_rtx_shutdown()
    f.close()
