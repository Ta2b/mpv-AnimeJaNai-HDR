#!/usr/bin/env python3
"""One controlled FRUC case: color packing, source preservation, SDK oracle.
Reuses an already acquired RIFE median; never reruns a neural plan. All source
bytes match between native and direct SDK clients; both request the median.
Native PTS rounding and direct rational SDK timestamps are recorded. No FPS claim.
"""
import ctypes as C,json,os,sys,time,subprocess,hashlib
from pathlib import Path
import numpy as np
from pipeline_cuda_check import Fixture,Create,Caps,Request,Done,Stats,ptr,wakeupfn
from vfi_candidate_probe import rgb_to_yuv444,yuv444_to_rgb
class View(C.Structure):
 _fields_=[('p',C.c_uint64*3),('pitch',C.c_uint64*3)]+[(n,C.c_int) for n in ['x','y','width','height','format','range']]+[('kr',C.c_float),('kb',C.c_float)]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 root=Path('/home/ta2b/Documents/mpv-AnimeJaNai-HDR/artifacts/performance/lots-20261016');out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
 if (out/'summary.json').exists():raise SystemExit('Existing receipt: do not repeat a conclusive case.')
 sdk=json.loads((root/'lot-45/sdk/summary.json').read_text());library='/home/ta2b/.animejanai-tools/work/pipeline-build-20261016/libaji_pipeline.so';kernel='/home/ta2b/.animejanai-tools/work/pipeline-build-20261016/aji_pipeline.fatbin';fruc='/home/ta2b/.animejanai-tools/work/fruc-provider-build-20261016/libaji_fruc.so';fruc_kernel='/home/ta2b/.animejanai-tools/work/fruc-provider-build-20261016/aji_fruc.fatbin'
 w,h=1280,720;f=Fixture(dict(width=w,height=h));driver=f.driver
 for name,args in {'cuModuleLoad':[ptr,C.c_char_p],'cuModuleGetFunction':[ptr,ptr,C.c_char_p],'cuModuleUnload':[ptr],'cuLaunchKernel':[ptr]+[C.c_uint]*7+[ptr,ptr,ptr]}.items():getattr(driver,name).argtypes=args;getattr(driver,name).restype=C.c_int
 module=ptr();pack=ptr();f.ck(driver.cuModuleLoad(C.byref(module),os.fsencode(fruc_kernel)));f.ck(driver.cuModuleGetFunction(C.byref(pack),module,b'aji_fruc_pack'))
 frames=np.fromfile(root/'lot-38/input-300s.rgb',np.uint8).reshape(-1,h,w,3);median=np.load(root/'lot-38/rife-result/003.npy');assert median.dtype==np.float32 and np.isfinite(median).all()
 original=[rgb_to_yuv444(frames[3].astype(np.float32)/255),rgb_to_yuv444(median)];sources=[];packed=[];pack_errors=[]
 ctx=ptr();lib=C.CDLL(library)
 for name,args in {'aji_pipeline_create_v1':[ptr,ptr,ptr,C.c_size_t],'aji_pipeline_query_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_submit_v1':[ptr,ptr,ptr],'aji_pipeline_complete_v1':[ptr,C.c_uint64,C.c_uint32,ptr,C.c_size_t],'aji_pipeline_drain_v1':[ptr,C.c_uint32],'aji_pipeline_stats_v1_get':[ptr,ptr,C.c_size_t],'aji_pipeline_last_error_v1':[ptr,ptr,C.c_size_t],'aji_pipeline_destroy_v1':[ptr]}.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if 'destroy' in name else C.c_int
 try:
  for index,planes in enumerate(original):
   item=f.surface(planes,7,index+1,index);item[0].timebase_den=48000;item[0].duration=1;sources.append(item);s=item[0]
   dest=C.c_uint64();f.ck(driver.cuMemAlloc_v2(C.byref(dest),w*h*4));f.allocations.append(dest.value)
   view=View(x=s.crop.x,y=s.crop.y,width=w,height=h,format=7,range=s.color.range,kr=.2126,kb=.0722)
   for i in range(3):view.p[i]=s.planes[i].data+s.planes[i].offset;view.pitch[i]=s.planes[i].row_stride
   args=(ptr*2)(C.cast(C.byref(view),ptr),C.cast(C.byref(dest),ptr));f.ck(driver.cuLaunchKernel(pack,(w+15)//16,(h+15)//16,1,16,16,1,0,None,args,None));f.ck(driver.cuCtxSynchronize())
   rgba=np.empty((h,w,4),np.uint8);f.ck(driver.cuMemcpyDtoH_v2(rgba.ctypes.data,dest.value,rgba.nbytes));assert (rgba[...,3]==1).all()
   decoded=yuv444_to_rgb(planes).astype(np.float64);oracle=np.floor(np.clip(decoded,0,1)*255+.5).astype(np.uint8);error=np.abs(rgba[...,:3].astype(np.int16)-oracle.astype(np.int16));pack_errors.append(int(error.max()));assert error.max()<=1,'Predeclared float/rounding tolerance:1 RGB8 code'
   packed.append(rgba)
  np.stack(packed).tofile(out/'exact-sdk-input.rgba')
  conf=out/'fruc-only.conf';base='chain_1_stage_1_';options={'id':'fruc','kind':'interpolate','method':'nvidia-fruc','runtime':'cuda','policy':'fast','factor_numerator':'2','factor_denominator':'1','sdk_library':sdk['installed_library'],'sdk_runtime':sdk['installed_runtime'],'kernel_fatbin':fruc_kernel}
  conf.write_text('[global]\nbackend=TensorRT\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\n'+''.join(base+k+'='+v+'\n' for k,v in options.items()))
  @wakeupfn
  def wake(_):pass
  params=Create(struct_size=C.sizeof(Create),version=1,width=w,height=h,slot=1,capacity=1,flags=1,generation=1,cuda_context=f.ctx,conf=os.fsencode(conf),fruc_library=os.fsencode(fruc),kernel_fatbin=os.fsencode(kernel),fps_numerator=48000,fps_denominator=1001,wakeup=wake)
  err=C.create_string_buffer(1024);assert lib.aji_pipeline_create_v1(C.byref(params),C.byref(ctx),err,len(err))==0,err.value
  caps=Caps();deadline=time.monotonic()+15
  while (code:=lib.aji_pipeline_query_v1(ctx,C.byref(caps),C.sizeof(caps)))==-4:
   assert time.monotonic()<deadline;time.sleep(.001)
  lib.aji_pipeline_last_error_v1(ctx,err,len(err));assert code==0,(code,err.value);assert (caps.factor,caps.stage_count)==(2,1)
  targets=[f.surface(None,7,100+i,i) for i in range(2)];captures=[];flags=[]
  for i in range(2):
   count=2 if i==0 else 1;r=Request(struct_size=C.sizeof(Request),version=1,flags=2 if i else 0,output_count=count,generation=1,previous=None if i else C.addressof(sources[0][0]),current=C.addressof(sources[1][0]))
   for j in range(count):
    target=targets[j][0];target.pts=i*2+j;target.duration=2 if i else 1;target.timebase_den=96000;r.outputs[j]=C.addressof(target)
   ticket=C.c_uint64();assert lib.aji_pipeline_submit_v1(ctx,C.byref(r),C.byref(ticket))==0
   assert lib.aji_pipeline_drain_v1(ctx,0)==0;done=Done();assert lib.aji_pipeline_complete_v1(ctx,ticket,1,C.byref(done),C.sizeof(done))==0;assert done.result.state==2,(done.result.state,done.result.message)
   for j in range(count):captures.append(np.stack(f.download(targets[j])));flags.append(done.output_flags[j])
   assert all(v==0 for v in f.held.values())
  assert np.array_equal(captures[0],np.stack(original[0])) and np.array_equal(captures[2],np.stack(original[1])),'Original/EOF frame changed'
  stat=Stats();assert lib.aji_pipeline_stats_v1_get(ctx,C.byref(stat),C.sizeof(stat))==0;stats={n:getattr(stat,n) for n,_ in stat._fields_};assert stats['fruc_predictions']==1 and stats['rife_predictions']==stats['spatial_predictions']==stats['cpu_pixel_copies']==0 and flags==[1,4,1]
  np.save(out/'native-yuv16.npy',np.stack(captures))
 finally:
  if ctx:lib.aji_pipeline_destroy_v1(ctx)
  f.ck(driver.cuModuleUnload(module));f.close()
 # Fresh independent SDK process, exactly the packed bytes observed above.
 env=dict(os.environ);env['LD_PRELOAD']=sdk['installed_runtime'];env['LD_LIBRARY_PATH']=str(Path(sdk['installed_runtime']).parent)+':'+env.get('LD_LIBRARY_PATH','')
 command=[str(root/'lot-38/fruc/probe-delivery'),sdk['installed_library'],str(out/'exact-sdk-input.rgba'),str(w),str(h),str(48000/1001),str(out/'direct')]
 with (out/'direct.log').open('wb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=20,env=env)
 direct=np.fromfile(out/'direct.rgba',np.uint8).reshape(h,w,4);expected=np.stack(rgb_to_yuv444(direct[...,:3].astype(np.float32)/255));delta=np.abs(captures[1].astype(np.int32)-expected.astype(np.int32))
 result=dict(passed=True,scope='One720p original→acquiredRIFE median pair; not user-specific playback or FPS qualification',source_hashes={'input_rgb':sha(root/'lot-38/input-300s.rgb'),'acquired_median':sha(root/'lot-38/rife-result/003.npy')},native_source_frames_bit_exact=True,final_duration_preserved=True,source_pack_max_rgb8_error=pack_errors,source_pack_tolerance_codes=1,native_vs_direct_sdk_yuv16_max=int(delta.max()),native_vs_direct_sdk_changed_components=int(np.count_nonzero(delta>1)),conversion_tolerance_codes=1,stats=stats,output_flags=flags,owners_balanced=True,exact_sdk_input_sha256=sha(out/'exact-sdk-input.rgba'),direct_command=command,sdk_repeatability_control_needed=bool(delta.max()>1))
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
