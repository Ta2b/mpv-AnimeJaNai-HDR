#!/usr/bin/env python3
"""Two model-free configure checks; no pixel inference or repeated quality test."""
import ctypes as C
import json
import os
from pathlib import Path
import sys
import threading
import time
from pipeline_cuda_check import Fixture,Create,Caps,ptr,wakeupfn

spec=json.loads(Path(sys.argv[1]).read_text())
out=Path(spec['output']).with_name('spline36-geometry');out.mkdir(parents=True,exist_ok=True)
assert not (out/'summary.json').exists(),'Conclusive receipt exists; no replay'
lib=C.CDLL(spec['library'],mode=os.RTLD_LOCAL)
for name,args in {
 'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],
 'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],
 'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],
 'aji_pipeline_destroy_v1':[ptr],
}.items():
 getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if 'destroy' in name else C.c_int
cases=[]
fixtures=[(64,32,36,(64,32))] if '--identity-only' in sys.argv[2:] else [(128,54,36,(84,36)),(64,32,36,(64,32))]
for width,height,target,expected in fixtures:
 fixture=Fixture(dict(width=width,height=height));ctx=ptr();wake=threading.Event()
 @wakeupfn
 def notify(_):wake.set()
 conf=out/f'{width}x{height}.conf'
 conf.write_text('[global]\nbackend=TensorRT\nlogging=no\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=down\nchain_1_stage_1_kind=resize\nchain_1_stage_1_method=spline36\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_target_height='+str(target)+'\n')
 params=Create(struct_size=C.sizeof(Create),version=1,width=width,height=height,slot=1,capacity=1,generation=1,
  cuda_context=fixture.ctx,conf=os.fsencode(conf),model_dir=b'',rife_dir=b'',trtexec=b'/bin/false',
  trt_library=os.fsencode(spec['trt']),kernel_fatbin=os.fsencode(spec['kernel']),fps_numerator=24,fps_denominator=1,wakeup=notify)
 error=C.create_string_buffer(2048)
 try:
  assert lib.aji_pipeline_create_v1(C.byref(params),C.byref(ctx),error,len(error))==0,error.value
  caps=Caps();deadline=time.monotonic()+15
  while True:
   code=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps))
   if code!=-4:break
   assert time.monotonic()<deadline,'Model-free configure timeout'
   wake.wait(.01);wake.clear()
  lib.aji_pipeline_last_error_v1(ctx,error,len(error));assert code==0,(code,error.value)
  assert (caps.width,caps.height,caps.factor)==(*expected,1),(caps.width,caps.height,caps.factor)
  cases.append(dict(source=[width,height],height_ceiling=target,output=list(expected)))
 finally:
  if ctx:lib.aji_pipeline_destroy_v1(ctx)
  fixture.close()
result=dict(passed=True,cases=cases,model_or_plan_builds=0,pixel_inferences=0,
 scope='Independent height ceiling preserves aspect with native even-pixel rounding, no hidden16:9 box; smaller source unchanged')
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
