#!/usr/bin/env python3
"""AH357: one bounded native RIFE burst, then reset/new-pair/legacy fallback.
Separate build-only invocation; never time while TensorRT is building.
"""
import ctypes as C
import hashlib,json,os,re,sys,time
from pathlib import Path
import numpy as np
from surface_cuda_check import Frame,Params,ptr
from vfi_candidate_probe import rgb_to_yuv444
spec=json.loads(Path(sys.argv[1]).read_text());root=Path(spec['output']);root.mkdir(exist_ok=True)
rejected=root/'runtime-rejected.json'
if rejected.exists() and not spec.get('build_only'):
 old=json.loads(rejected.read_text())
 assert old['binary_sha256']=={k:hashlib.sha256(Path(spec[k]).read_bytes()).hexdigest() for k in ('before','candidate')}
 print('Conclusive rejection already recorded; target a distinct failed-case diagnosis instead of repeating.');sys.exit(0)
logs=[];allocated=[]
logfn=C.CFUNCTYPE(None,ptr,C.c_int,C.c_char_p)
@logfn
def report(_,level,message):logs.append(message.decode(errors='replace'))
cuda=C.CDLL('libcudart.so.13')
for name,args in {'cudaSetDevice':[C.c_int],'cudaMalloc':[ptr,C.c_size_t],'cudaFree':[ptr],
 'cudaMemcpy':[ptr,ptr,C.c_size_t,C.c_int],'cudaStreamSynchronize':[ptr],
 'cudaStreamCreateWithFlags':[ptr,C.c_uint],'cudaStreamDestroy':[ptr]}.items():getattr(cuda,name).argtypes=args;getattr(cuda,name).restype=C.c_int
def ck(status):assert status==0,('CUDA',status)
ck(cuda.cudaSetDevice(0));stream=ptr();ck(cuda.cudaStreamCreateWithFlags(C.byref(stream),1))
def library(path):
 lib=C.CDLL(path,mode=os.RTLD_LOCAL)
 for name,(args,ret) in {'aji_create':([ptr],ptr),'aji_configure':([ptr,C.c_int,C.c_int,C.c_double,ptr,ptr],C.c_int),
  'aji_infer_rife':([ptr,ptr,ptr,C.c_double,ptr,ptr],C.c_int),'aji_rife_begin_pair':([ptr,C.c_uint64,C.c_uint64],None),
  'aji_last_error':([ptr],C.c_char_p),'aji_destroy':([ptr],None)}.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=ret
 return lib
def context(lib,on,build=False):
 os.environ['AJI_RIFE_ENCODER_CACHE']='1' if on else '0'
 p=Params(api_version=9,conf_path=os.fsencode(spec['conf']),model_dir=os.fsencode(spec['rife']),rife_model_dir=os.fsencode(spec['rife']),
  trtexec=os.fsencode(spec['trtexec'] if build else '/bin/false'),slot=1,log=C.cast(report,ptr))
 handle=ptr(lib.aji_create(C.byref(p)));assert handle
 w,h=C.c_int(),C.c_int();status=lib.aji_configure(handle,1280,720,24,C.byref(w),C.byref(h))
 assert status==0 and (w.value,h.value)==(1280,720),(status,lib.aji_last_error(handle))
 return handle
def image(planes=None):
 frame=Frame(width=1280,height=720,format=3,matrix=2,range=2,siting=1)
 for i in range(3):
  p=ptr();ck(cuda.cudaMalloc(C.byref(p),1280*720*2));allocated.append(p)
  frame.plane[i]=p.value;frame.stride[i]=1280*2
  if planes is not None:ck(cuda.cudaMemcpy(p,planes[i].ctypes.data,planes[i].nbytes,1))
 return frame
def pixels(frame):
 planes=[]
 for i in range(3):
  raw=np.empty((720,1280),'<u2');ck(cuda.cudaMemcpy(raw.ctypes.data,frame.plane[i],raw.nbytes,2));planes.append(raw)
 return np.stack(planes)
def phase(lib,handle,a,b,out,t):
 status=lib.aji_infer_rife(handle,C.byref(a),C.byref(b),t,C.byref(out),stream)
 assert status==0,(status,lib.aji_last_error(handle))
def burst(lib,handle,a,b,out,left=1,right=2):
 lib.aji_rife_begin_pair(handle,left,right)
 for t in (.25,.5,.75):phase(lib,handle,a,b,out,t)
 ck(cuda.cudaStreamSynchronize(stream))
candidate=library(spec['candidate']);handles=[]
try:
 if spec.get('build_only'):
  handle=context(candidate,True,True);handles.append((candidate,handle))
  assert any('shared encoder ready' in line for line in logs),'\n'.join(logs[-20:])
  (root/'build-complete.json').write_text(json.dumps({'passed':True,'scope':'configure/compile only, no inference or measurement','candidate_sha256':hashlib.sha256(Path(spec['candidate']).read_bytes()).hexdigest()},indent=2)+'\n')
 else:
  assert not (root/'runtime-receipt.json').exists(),'Conclusive case must not be repeated'
  old=library(spec['before']);reference=context(old,False);handles.append((old,reference))
  plain=context(candidate,False);handles.append((candidate,plain))
  split=context(candidate,True);handles.append((candidate,split));assert any('shared encoder ready' in line for line in logs)
  rgb=np.fromfile(spec['input'],np.uint8).reshape(2,720,1280,3)
  a,b=[image(rgb_to_yuv444(x.astype(np.float32)/255)) for x in rgb];out=image();expected=[]
  old.aji_rife_begin_pair(reference,1,2)
  for t in (.25,.5,.75):phase(old,reference,a,b,out,t);ck(cuda.cudaStreamSynchronize(stream));expected.append(pixels(out))
  for label,lib,handle in [('candidate-off',candidate,plain),('candidate-on',candidate,split)]:
   lib.aji_rife_begin_pair(handle,1,2)
   for i,t in enumerate((.25,.5,.75)):
    phase(lib,handle,a,b,out,t);ck(cuda.cudaStreamSynchronize(stream));actual=pixels(out)
    assert np.array_equal(expected[i],actual),(label,t,int(np.count_nonzero(expected[i]!=actual)),int(np.max(np.abs(expected[i].astype(np.int32)-actual.astype(np.int32)))))
  # Same addresses with a new explicit identity must not retain old features.
  candidate.aji_rife_begin_pair(split,3,4);phase(candidate,split,a,b,out,.5);ck(cuda.cudaStreamSynchronize(stream));assert np.array_equal(expected[1],pixels(out))
  candidate.aji_rife_begin_pair(split,0,0);phase(candidate,split,a,b,out,.25);ck(cuda.cudaStreamSynchronize(stream));assert np.array_equal(expected[0],pixels(out))
  w,h=C.c_int(),C.c_int();assert candidate.aji_configure(split,1280,720,24,C.byref(w),C.byref(h))==0
  candidate.aji_rife_begin_pair(split,5,6);phase(candidate,split,a,b,out,.75);ck(cuda.cudaStreamSynchronize(stream));assert np.array_equal(expected[2],pixels(out))
  # Warm each route after reset before one short, alternating timing sequence.
  burst(candidate,plain,a,b,out,10,11);burst(candidate,split,a,b,out,10,11)
  timing=[]
  for on in (False,True,True,False):
   handle=split if on else plain;started=time.perf_counter();burst(candidate,handle,a,b,out,20+len(timing)*2,21+len(timing)*2)
   timing.append({'encoder_cache':on,'burst_wall_ms':(time.perf_counter()-started)*1000})
  result={'passed':True,'scope':'Actual ABI9 RIFE Quality x4 burst incl preparation/post; not full player/SPAN/HDR FPS','binary_sha256':{k:hashlib.sha256(Path(spec[k]).read_bytes()).hexdigest() for k in ('candidate','before')},
   'output_sha256':[hashlib.sha256(x.tobytes()).hexdigest() for x in expected],'phases_exact':3,'elements_per_phase':int(expected[0].size),
   'new_pair_exact':True,'legacy_no_ids_fallback_exact':True,'reconfigure_exact':True,'feature_bytes':1280*768*16,'timing':timing}
finally:
 for lib,handle in reversed(handles):lib.aji_destroy(C.byref(handle))
 for p in allocated:ck(cuda.cudaFree(p))
 ck(cuda.cudaStreamDestroy(stream));(root/('build-config.log' if spec.get('build_only') else 'runtime.log')).write_text('\n'.join(logs)+'\n')
if not spec.get('build_only'):
 counts=[tuple(map(int,m)) for m in re.findall(r'shared encoder: (\d+) encoded, (\d+) reused;', '\n'.join(logs))]
 assert counts and counts[0]==(2,2),counts # first split context before reconfigure
 result['encoder_counters']=counts
 (root/'runtime-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
