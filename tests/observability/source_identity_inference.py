#!/usr/bin/env python3
"""Short source-ID comparison, including recycled buffers and counter reset."""
import argparse,ctypes as C,hashlib,json,os,time
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
for name in ['library','config','models','rife','input','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--ids',action='store_true');p.add_argument('--width',type=int,required=True);p.add_argument('--height',type=int,required=True);p.add_argument('--device',default='cpu');a=p.parse_args()
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
ids=getattr(lib,'aji_vk_source_ids',None)
if ids:ids.argtypes=[ptr,C.c_uint64,C.c_uint64,C.c_uint64]
if a.ids:assert ids
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
   if a.ids:ids(ctx,1,i+1,i+2)
   assert lib.aji_vk_process(ctx,previous.ctypes.data_as(bytep),previous.strides[0],current.ctypes.data_as(bytep),current.strides[0],t,result.ctypes.data_as(bytep),result.strides[0])==0,lib.aji_vk_error(ctx)
   outputs[f'{i}-{j}']=result[:,:plan.width*3].copy();observe()
   if live:
    text=live(ctx).decode();count=int(next(l[8:] for l in text.splitlines() if l.startswith('Frames: ')));assert count==len(outputs);live_frames.append(count)
 # The same address now carries other bytes. Forgetting the generation at
 # seek must fail closed; a later larger counter cannot re-enable this epoch.
 for label,generation,sequence,frame_index,padding,provide in [
  ('regressed',1,1,0,17,True),('poisoned-epoch',1,5,1,17,True),
  ('fresh-epoch',2,1,2,17,True),('new-stride',2,1,2,31,True),
  ('legacy-one-call',0,0,3,17,False)]:
  source=np.zeros((a.height,a.width*3+padding),np.uint8);source[:,:a.width*3]=frames[frame_index]
  if a.ids and provide:ids(ctx,generation,0,sequence)
  assert lib.aji_vk_process(ctx,None,0,source.ctypes.data_as(bytep),source.strides[0],1,result.ctypes.data_as(bytep),result.strides[0])==0,lib.aji_vk_error(ctx)
  outputs[label]=result[:,:plan.width*3].copy()
 memory=live(ctx).decode()
 counters={}
 for line in memory.splitlines():
  if line.startswith(('Source ID hits:','Source byte comparisons:','Source ID rejected calls:')):
   k,v=line.split(': ',1);counters[k]=int(v)
 if a.ids:assert counters['Source ID hits']>0 and counters['Source ID rejected calls']==2
finally:lib.aji_vk_destroy(ctx)
observe();final=stats.read_text();assert '\nFrames: 14\n' in final
np.savez(out/'outputs.npz',**outputs)
x={'outputs':len(outputs),'file_revisions':len(revisions),'live_frames':live_frames,'final_frames':14,'source_counters':counters,'ids_enabled':a.ids,'elapsed_seconds':time.perf_counter()-began,'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest(),'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'config_sha256':hashlib.sha256(a.config.read_bytes()).hexdigest(),'immediate_error_checked':False,'fps_claim':False}
(out/'summary.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
