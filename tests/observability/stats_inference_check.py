#!/usr/bin/env python3
"""A small real-input comparison, run once per producer and revision."""
import argparse,ctypes as C,hashlib,json,os,time
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
for name in ['library','config','models','rife','input','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--width',type=int,required=True);p.add_argument('--height',type=int,required=True);p.add_argument('--device',default='cpu');a=p.parse_args()
out=a.output;out.mkdir(parents=True,exist_ok=True);stats=out/'stats.txt'
class Plan(C.Structure):_fields_=[(n,C.c_int) for n in ['width','height','numerator','denominator','active']]
lib=C.CDLL(str(a.library.resolve()));ptr=C.c_void_p;bytep=C.POINTER(C.c_ubyte)
lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=ptr
lib.aji_vk_configure.argtypes=[ptr,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
lib.aji_vk_process.argtypes=[ptr,bytep,C.c_ssize_t,bytep,C.c_ssize_t,C.c_double,bytep,C.c_ssize_t]
lib.aji_vk_error.argtypes=[ptr];lib.aji_vk_error.restype=C.c_char_p
lib.aji_vk_destroy.argtypes=[ptr]
live=getattr(lib,'aji_vk_stats_snapshot',None)
if live:live.argtypes=[ptr];live.restype=C.c_char_p
ctx=lib.aji_vk_create(os.fsencode(a.config),os.fsencode(a.models),os.fsencode(a.rife),a.device.encode(),os.fsencode(stats),1);assert ctx
revisions=[];live_frames=[];outputs={};began=time.perf_counter()
def observe():
 if stats.exists():
  text=stats.read_text();sha=hashlib.sha256(text.encode()).hexdigest()
  if not revisions or sha!=revisions[-1]:revisions.append(sha)
try:
 plan=Plan();assert lib.aji_vk_configure(ctx,a.width,a.height,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
 assert plan.active and (plan.numerator,plan.denominator)==(4,1)
 observe();frames=np.fromfile(a.input,dtype=np.uint8).reshape(-1,a.height,a.width*3)
 result=np.zeros((plan.height,plan.width*3+19),np.uint8)
 previous=np.zeros((a.height,a.width*3+17),np.uint8);current=previous.copy()
 for i in range(3):
  previous[:,:a.width*3]=frames[i];current[:,:a.width*3]=frames[i+1]
  for j,t in enumerate([.25,.5,.75]):
   assert lib.aji_vk_process(ctx,previous.ctypes.data_as(bytep),previous.strides[0],current.ctypes.data_as(bytep),current.strides[0],t,result.ctypes.data_as(bytep),result.strides[0])==0,lib.aji_vk_error(ctx)
   outputs[f'{i}-{j}']=result[:,:plan.width*3].copy();observe()
   if live:
    text=live(ctx).decode();count=int(next(l[8:] for l in text.splitlines() if l.startswith('Frames: ')));assert count==len(outputs);live_frames.append(count)
finally:lib.aji_vk_destroy(ctx)
observe();final=stats.read_text();assert '\nFrames: 9\n' in final
if live:
 assert 'Stats state: stopped\n' in final
 # Immediate error state on an off context: no model build or inference repeated.
 error_stats=out/'error.txt'
 ctx=lib.aji_vk_create(os.fsencode(a.config),os.fsencode(a.models),os.fsencode(a.rife),a.device.encode(),os.fsencode(error_stats),0);assert ctx
 try:
  assert lib.aji_vk_configure(ctx,a.width,a.height,24,C.byref(plan))==0
  assert lib.aji_vk_process(ctx,None,0,None,0,1,None,0)==-1
  assert 'Stats state: error\n' in error_stats.read_text() and 'Invalid frame arguments' in error_stats.read_text()
 finally:lib.aji_vk_destroy(ctx)
np.savez(out/'outputs.npz',**outputs)
x={'outputs':len(outputs),'file_revisions':len(revisions),'live_frames':live_frames,'final_frames':9,'elapsed_seconds':time.perf_counter()-began,'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest(),'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'config_sha256':hashlib.sha256(a.config.read_bytes()).hexdigest(),'immediate_error_checked':bool(live),'fps_claim':False}
(out/'summary.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
