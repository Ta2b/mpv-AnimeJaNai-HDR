#!/usr/bin/env python3
"""One short explicit fusion comparison, exact GPU outputs and per-stage trace.
Uses isolated existing plans and immutable input. Initialization is reported
separately; the middle interval is the warm observation, never a playback FPS.
"""
import ctypes as C,json,os,sys,time,threading,hashlib
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn
from vfi_candidate_probe import rgb_to_yuv444
def main():
 s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
 assert not (out/'summary.json').exists(),'Conclusive receipt exists; no replay'
 f=Fixture(dict(width=s['width'],height=s['height']));lib=C.CDLL(s['library'],mode=os.RTLD_LOCAL);ctx=ptr();wake=threading.Event()
 @wakeupfn
 def notify(_):wake.set()
 signatures={'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],
  'aji_pipeline_output_color_v1':[ptr,ptr,ptr,C.c_size_t,ptr],'aji_pipeline_submit_v1':[ptr,ptr,ptr],
  'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],
  'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}
 for name,args in signatures.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if 'destroy' in name else C.c_int
 p=Create(struct_size=C.sizeof(Create),version=1,width=s['width'],height=s['height'],slot=1,capacity=1,flags=3,generation=1,cuda_context=f.ctx,
  conf=os.fsencode(s['conf']),model_dir=os.fsencode(s['models']),rife_dir=os.fsencode(s['rife']),trtexec=os.fsencode(s.get('trtexec','/bin/false')),
  trt_library=os.fsencode(s['trt']),kernel_fatbin=os.fsencode(s['kernel']),fps_numerator=24000,fps_denominator=1001,wakeup=notify)
 error=C.create_string_buffer(2048);start=time.perf_counter();calls=[];hashes=[];timeline=[];flags=[]
 try:
  code=lib.aji_pipeline_create_v1(C.byref(p),C.byref(ctx),error,len(error));assert code==0,(code,error.value)
  caps=Caps();deadline=time.monotonic()+45
  while True:
   code=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps))
   if code!=-4:break
   assert time.monotonic()<deadline,'Initialization timed out; missing plan is not a benchmark'
   wake.wait(.01);wake.clear()
  lib.aji_pipeline_last_error_v1(ctx,error,len(error));assert code==0,(code,error.value)
  setup_ms=(time.perf_counter()-start)*1000
  frames=np.fromfile(s['input'],np.uint8).reshape(-1,s['height'],s['width'],3)
  sources=[]
  for position,i in enumerate(s.get('source_indices',[2,3,4,5])):
   v=f.surface(rgb_to_yuv444(frames[i].astype(np.float32)/255),7,i+1,position*4)
   v[0].timebase_num=1001;v[0].timebase_den=96000;v[0].duration=4;sources.append(v)
  color=type(sources[0][0].color)();peak=C.c_double()
  assert lib.aji_pipeline_output_color_v1(ctx,C.byref(sources[0][0].color),C.byref(color),C.sizeof(color),C.byref(peak))==0
  f.s=dict(width=caps.width,height=caps.height);targets=[f.surface(None,7,100+i,i) for i in range(caps.factor)]
  for v,_ in targets:v.color=color;v.timebase_num=1001;v.timebase_den=96000
  defer_download=bool(s.get('defer_download',False));save_outputs=bool(s.get('save_outputs',True));target_batches=[targets];all_targets=list(targets);deferred=[]
  if defer_download:
   for pair in range(1,len(sources)):
    count=1 if pair==len(sources)-1 else caps.factor
    batch=[f.surface(None,7,100+pair*caps.factor+i,pair*4+i*4//caps.factor) for i in range(count)]
    for v,_ in batch:v.color=color;v.timebase_num=1001;v.timebase_den=96000
    target_batches.append(batch);all_targets.extend(batch)
  for pair in range(len(sources)):
   if defer_download:targets=target_batches[pair]
   eof=pair==len(sources)-1;count=1 if eof else caps.factor
   request=Request(struct_size=C.sizeof(Request),version=1,flags=2 if eof else 0,output_count=count,generation=1)
   request.previous=None if eof else C.addressof(sources[pair][0]);request.current=C.addressof(sources[pair if eof else pair+1][0])
   for i in range(count):
    v=targets[i][0];v.pts=pair*4+i*4//caps.factor;v.duration=4 if eof else 4//caps.factor;request.outputs[i]=C.addressof(v)
   snapshot=[bytes(v[0]) for v in sources+all_targets];ticket=C.c_uint64();started=time.perf_counter()
   code=lib.aji_pipeline_submit_v1(ctx,C.byref(request),C.byref(ticket));assert code==0,code
   assert lib.aji_pipeline_drain_v1(ctx,0)==0
   done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0
   ms=(time.perf_counter()-started)*1000
   assert done.result.state==2 and done.result.status==0,(done.result.status,done.result.message)
   assert snapshot==[bytes(v[0]) for v in sources+all_targets] and all(x==0 for x in f.held.values())
   for i in range(count):
    if not save_outputs:hashes.append(None) # timing-only run (AH-396): no download, no file
    elif defer_download:deferred.append(targets[i])
    else:
     pixels=np.asarray(f.download(targets[i]));np.save(out/f'{len(hashes):03d}.npy',pixels)
     hashes.append(hashlib.sha256(pixels.tobytes()).hexdigest())
    timeline.append([targets[i][0].pts,targets[i][0].duration]);flags.append(done.output_flags[i])
   calls.append(dict(pair=pair,eof=eof,complete_wall_ms=ms,outputs=count));print(json.dumps(calls[-1]),flush=True)
  for target in deferred:
   pixels=np.asarray(f.download(target));np.save(out/f'{len(hashes):03d}.npy',pixels)
   hashes.append(hashlib.sha256(pixels.tobytes()).hexdigest())
  stats=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stats),C.sizeof(stats))==0
  result=dict(passed=True,spec=s,setup_ms=setup_ms,calls=calls,dimensions=[caps.width,caps.height],factor=caps.factor,stage_count=caps.stage_count,
   color=[getattr(color,n) for n,_ in color._fields_],peak=peak.value,hashes=hashes,timeline=timeline,flags=flags,
   stats={n:getattr(stats,n) for n,_ in stats._fields_},scope='Short native GPU chain, warm interval observation; no displayed FPS or universal claim')
  if s.get('check_reset',False):
   assert len(sources)>=2,'Reset check requires a non-EOF source pair'
   lib.aji_pipeline_reset_v1.argtypes=[ptr,C.c_uint64];lib.aji_pipeline_reset_v1.restype=C.c_int
   previous_ticket=ticket.value
   assert lib.aji_pipeline_reset_v1(ctx,2)==0
   reset_caps=Caps();assert lib.aji_pipeline_query_v1(ctx,C.byref(reset_caps),C.sizeof(reset_caps))==0
   assert reset_caps.generation==2
   for v,_ in sources+all_targets:v.generation=2
   if defer_download:targets=target_batches[-2]
   pair=len(sources)-2;count=caps.factor;offset=pair*count
   expected_hashes=hashes[offset:offset+count];expected_timeline=timeline[offset:offset+count]
   request=Request(struct_size=C.sizeof(Request),version=1,output_count=count,generation=2,
    previous=C.addressof(sources[pair][0]),current=C.addressof(sources[pair+1][0]))
   for i in range(count):
    v=targets[i][0];v.pts,v.duration=expected_timeline[i];request.outputs[i]=C.addressof(v)
   snapshot=[bytes(v[0]) for v in sources+all_targets];ticket=C.c_uint64()
   assert lib.aji_pipeline_submit_v1(ctx,C.byref(request),C.byref(ticket))==0 and ticket.value>previous_ticket
   assert lib.aji_pipeline_drain_v1(ctx,0)==0
   done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0
   assert done.result.state==2 and done.result.status==0,(done.result.status,done.result.message)
   assert done.output_count==count
   assert snapshot==[bytes(v[0]) for v in sources+all_targets] and all(x==0 for x in f.held.values())
   reset_hashes=[hashlib.sha256(np.asarray(f.download(targets[i])).tobytes()).hexdigest() for i in range(count)]
   reset_timeline=[[targets[i][0].pts,targets[i][0].duration] for i in range(count)]
   assert reset_hashes==expected_hashes,('Reset changed output pixels',reset_hashes,expected_hashes)
   assert reset_timeline==expected_timeline
   assert list(done.output_flags[:count])==flags[offset:offset+count]
   result.update(reset_exact=True,reset_check=dict(pair=pair,generation=2,outputs=count,
    hashes=reset_hashes,timeline=reset_timeline,owners_balanced=True,descriptors_unchanged=True,tickets_monotone=True))
 finally:
  if ctx:lib.aji_pipeline_destroy_v1(ctx)
  f.close()
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS',out)
if __name__=='__main__':main()
