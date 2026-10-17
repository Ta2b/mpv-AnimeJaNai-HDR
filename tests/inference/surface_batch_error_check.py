#!/usr/bin/env python3
"""One new batch error/ownership check, existing plans only; no benchmark."""
import ctypes as C
import json,os,sys
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture
from surface_cuda_check import Params,ptr

class BatchCaps(C.Structure):_fields_=[(n,C.c_uint32) for n in ['struct_size','version','max_jobs','flags']]
class Job(C.Structure):
    _fields_=[('struct_size',C.c_uint32),('version',C.c_uint32),('previous',ptr),('current',ptr),('output',ptr),('timestep',C.c_double)]

def main():
    s=json.loads(Path(sys.argv[1]).read_text());receipt=Path(s['output'])
    assert not receipt.exists(),'Conclusive receipt already exists; no repeat'
    f=Fixture({'width':1280,'height':720});lib=C.CDLL(s['library'],mode=os.RTLD_LOCAL);ctx=ptr()
    for name,(args,result) in {
        'aji_create':([ptr],ptr),'aji_configure':([ptr,C.c_int,C.c_int,C.c_double,ptr,ptr],C.c_int),
        'aji_last_error':([ptr],C.c_char_p),'aji_destroy':([ptr],None),
        'aji_surface_batch_query_v1':([ptr,C.c_uint32,ptr,C.c_size_t],C.c_int),
        'aji_surface_process_batch_v1':([ptr,C.c_uint32,ptr,C.c_size_t],C.c_int),
        'aji_surface_process_v1':([ptr,ptr,ptr,C.c_double,ptr],C.c_int)}.items():
        getattr(lib,name).argtypes=args;getattr(lib,name).restype=result
    try:
        params=Params(api_version=9,cuda_context=f.ctx,conf_path=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),rife_model_dir=os.fsencode(s['rife']),trtexec=b'/bin/false',slot=1)
        ctx=ptr(lib.aji_create(C.byref(params)));assert ctx
        w,h=C.c_int(),C.c_int();code=lib.aji_configure(ctx,1280,720,24,C.byref(w),C.byref(h));assert code==1,(code,lib.aji_last_error(ctx))
        caps=BatchCaps();assert lib.aji_surface_batch_query_v1(ctx,1,C.byref(caps),C.sizeof(caps))==0 and caps.max_jobs==17
        original=bytes(caps)
        assert lib.aji_surface_batch_query_v1(ctx,2,C.byref(caps),C.sizeof(caps))==-2 and bytes(caps)==original
        assert lib.aji_surface_batch_query_v1(ctx,1,C.byref(caps),1)==-1 and bytes(caps)==original
        # Nonuniform deterministic YUV16 endpoints, same configured shapes/plans.
        yy,xx=np.indices((720,1280));pixels=np.stack([((xx+yy)%220+16)*256,np.full_like(xx,32768),np.full_like(xx,32768)]).astype(np.uint16)
        a=f.surface(pixels,7,1,0);b=f.surface(pixels,7,2,1)
        f.s={'width':w.value,'height':h.value}
        first=f.surface(None,7,3,0);second=f.surface(None,7,4,1);reference=f.surface(None,7,5,0)
        jobs=(Job*2)()
        for i,out in enumerate([first,second]):jobs[i]=Job(C.sizeof(Job),1,C.addressof(a[0]),C.addressof(b[0]),C.addressof(out[0]),0)
        initial=[bytes(v[0]) for v in [a,b,first,second,reference]]
        n=len(f.owners)
        assert lib.aji_surface_process_batch_v1(ctx,1,jobs,0)==-1
        assert lib.aji_surface_process_batch_v1(ctx,1,jobs,18)==-1
        assert lib.aji_surface_process_batch_v1(ctx,2,jobs,2)==-2
        jobs[1].version=2
        assert lib.aji_surface_process_batch_v1(ctx,1,jobs,2)==-1 and len(f.owners)==n
        jobs[1].version=1;jobs[1].timestep=-.1
        code=lib.aji_surface_process_batch_v1(ctx,1,jobs,2)
        assert code==-1,(code,lib.aji_last_error(ctx))
        assert len(f.owners)-n==18 and all(v==0 for v in f.held.values()),f.owners[n:]
        assert initial==[bytes(v[0]) for v in [a,b,first,second,reference]]
        # The queued first job completed before the error return. Compare its
        # result to one ordinary sync call; the application still discards an
        # entire failed batch by contract, rather than publishing this image.
        expected=np.asarray(f.download(first)).copy()
        assert lib.aji_surface_process_v1(ctx,C.byref(a[0]),C.byref(b[0]),0,C.byref(reference[0]))==0
        assert np.array_equal(expected,np.asarray(f.download(reference)))
        assert all(v==0 for v in f.held.values())
        receipt.parent.mkdir(parents=True,exist_ok=True)
        result={'passed':True,'caps_short_and_version_untouched':True,'bounds_and_job_headers':True,
            'later_job_error_drained':True,'owner_callbacks_balanced':True,'callbacks_on_failed_batch':18,
            'descriptors_unchanged':True,'normal_call_after_error_exact':True,'fps_claimed':False}
        receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:
        if ctx:lib.aji_destroy(C.byref(ctx))
        f.close()
if __name__=='__main__':main()
