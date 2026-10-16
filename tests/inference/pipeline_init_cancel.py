#!/usr/bin/env python3
"""Cancel a real backend build launch held by an owned stub, no real compilation.
Uses a fresh private cache and the actual TensorRT backend/typed build-status API.
"""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import time
from pipeline_cuda_check import Create,Caps,Fixture,ptr,wakeupfn,digest
def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']).parent/'init-cancel';out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
    identity={k:digest(s[k]) for k in ['library','kernel','trt','conf']}
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Conclusive matching receipt; no replay.');return
    rife=out/'rife';rife.mkdir(exist_ok=True)
    for source in Path(s['rife']).glob('*.onnx'):
        dest=rife/source.name
        if not dest.exists():dest.symlink_to(source)
    assert not list(rife.glob('*.engine')),'Cache must remain private and empty for the cancellation check'
    marker=out/'owned-builder.pid';assert not marker.exists(),'Inspect prior owned builder before restarting'
    stub=out/'owned-trtexec-stub.py';stub.write_text('#!/usr/bin/python3\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(str(os.getpid()))\nwhile True: time.sleep(.05)\n');stub.chmod(0o700)
    f=Fixture(s);ctx=ptr();lib=C.CDLL(s['library'],mode=os.RTLD_LOCAL)
    lib.aji_pipeline_create_v1.argtypes=[ptr,ptr,ptr,C.c_size_t];lib.aji_pipeline_create_v1.restype=C.c_int
    lib.aji_pipeline_query_v1.argtypes=[ptr,ptr,C.c_size_t];lib.aji_pipeline_query_v1.restype=C.c_int
    lib.aji_pipeline_destroy_v1.argtypes=[ptr];lib.aji_pipeline_destroy_v1.restype=None
    lib.aji_pipeline_last_error_v1.argtypes=[ptr,ptr,C.c_size_t]
    @wakeupfn
    def wake(_):pass
    p=Create(struct_size=C.sizeof(Create),version=1,width=s['width'],height=s['height'],slot=1,capacity=1,flags=1,generation=1,
        cuda_context=f.ctx,conf=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),rife_dir=os.fsencode(rife),
        trtexec=os.fsencode(stub),trt_library=os.fsencode(s['trt']),fruc_library=os.fsencode(s['fruc']),kernel_fatbin=os.fsencode(s['kernel']),
        fps_numerator=24000,fps_denominator=1001,wakeup=wake)
    message=C.create_string_buffer(1024);start=time.monotonic()
    try:
        code=lib.aji_pipeline_create_v1(C.byref(p),C.byref(ctx),message,len(message));assert code==0,message.value
        create_ms=(time.monotonic()-start)*1000;end=time.monotonic()+6
        while not marker.exists():
            caps=Caps();status=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps))
            lib.aji_pipeline_last_error_v1(ctx,message,len(message));assert status==-4,(status,message.value)
            assert time.monotonic()<end,'Builder did not launch; inspect state before restarting';time.sleep(.01)
        pid=int(marker.read_text());caps=Caps();caps.factor=0xabcdef;snapshot=bytes(caps)
        assert lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps))==-4 and bytes(caps)==snapshot
        start=time.monotonic();lib.aji_pipeline_destroy_v1(ctx);ctx=ptr();destroy_ms=(time.monotonic()-start)*1000
        alive=Path(f'/proc/{pid}').exists();assert not alive,'Owned builder survived destruction'
        assert not list(rife.glob('*.engine')) and not list(rife.glob('*.stage-*'))
        result=dict(passed=True,identity=identity,real_backend_launch=True,owned_stub_only=True,actual_compilation=False,
            query_pending_untouched=True,create_ms=create_ms,destroy_ms=destroy_ms,owned_builder_gone=True,partial_plan_not_published=True)
    finally:
        if ctx:lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
