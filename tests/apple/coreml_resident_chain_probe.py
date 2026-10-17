#!/usr/bin/env python3
"""Native two-SPAN CoreML C ABI: exact reference, removed host conversions, repli.
SPEC: baseline,candidate,models,conf,resize_conf,output. No cache case replay.
"""
import ctypes as C
import hashlib,json,os,time
from pathlib import Path
import sys
class Plan(C.Structure):
 _fields_=[(k,C.c_int) for k in ('width','height','numerator','denominator','active')]
s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(exist_ok=True)
os.environ['AJI_COREML_NO_PLAN']='1';os.environ['AJI_METAL_RESIDENT_SPAN']='0'
libs={};contexts=[];r={'source':os.environ.get('GITHUB_SHA'),'cases':{}}
def save(name,value):
 r['cases'][name]=value;(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
for name in ('baseline','candidate'):
 lib=C.CDLL(s[name],mode=os.RTLD_LOCAL)
 lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=C.c_void_p
 lib.aji_vk_configure.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
 lib.aji_vk_process.argtypes=[C.c_void_p,C.c_void_p,C.c_ssize_t,C.c_void_p,C.c_ssize_t,C.c_double,C.c_void_p,C.c_ssize_t]
 lib.aji_vk_error.argtypes=[C.c_void_p];lib.aji_vk_error.restype=C.c_char_p
 lib.aji_vk_stats_snapshot.argtypes=[C.c_void_p];lib.aji_vk_stats_snapshot.restype=C.c_char_p
 lib.aji_vk_destroy.argtypes=[C.c_void_p];lib.aji_vk_destroy.restype=None
 libs[name]=lib
size=256;pitch=size*3+16;source=(C.c_ubyte*(pitch*size))()
for y in range(size):
 for x in range(size):
  for k in range(3):source[y*pitch+x*3+k]=(x*3+y*2+k*30+(x//16%2)*60)%256
def create(name,resident,conf):
 os.environ['AJI_COREML_RESIDENT_SPAN']='1' if resident else '0';lib=libs[name]
 ctx=lib.aji_vk_create(os.fsencode(conf),os.fsencode(s['models']),b'',b'cpu',b'',1);assert ctx,lib.aji_vk_error(None);contexts.append((lib,ctx));plan=Plan()
 assert lib.aji_vk_configure(ctx,size,size,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
 return lib,ctx,plan
def run(state):
 lib,ctx,plan=state;row=plan.width*3;stride=row+16;output=(C.c_ubyte*(stride*plan.height))();C.memset(output,0xa5,C.sizeof(output))
 start=time.perf_counter();code=lib.aji_vk_process(ctx,None,0,source,pitch,1,output,stride);ms=(time.perf_counter()-start)*1000
 assert code==0,lib.aji_vk_error(ctx)
 raw=bytes(output);assert all(raw[y*stride+row:(y+1)*stride]==b'\xa5'*16 for y in range(plan.height))
 return b''.join(raw[y*stride:y*stride+row] for y in range(plan.height)),ms,lib.aji_vk_stats_snapshot(ctx).decode()
def count(stats,key):return int(next(x.split(': ',1)[1] for x in stats.splitlines() if x.startswith(key+': ')))
try:
 base=create('baseline',False,s['conf']);off=create('candidate',False,s['conf']);on=create('candidate',True,s['conf'])
 reference,_,_=run(base);a,_,off_stats=run(off);b,_,on_stats=run(on)
 assert reference==a==b,'RGB differs: stop before timing or other cases'
 assert count(on_stats,'Resident SPAN segments')==1 and count(off_stats,'Resident SPAN segments')==0
 assert count(off_stats,'Executor RGB to BGRA bytes')==(256*256+512*512)*3
 assert count(off_stats,'Executor BGRA to RGB bytes')==(512*512+1024*1024)*3
 assert count(on_stats,'Executor RGB to BGRA bytes')==256*256*3
 assert count(on_stats,'Executor BGRA to RGB bytes')==1024*1024*3
 save('base_off_on',{'pixels_exact':True,'output_sha256':hashlib.sha256(b).hexdigest(),'off_stats':off_stats,'on_stats':on_stats,'Metal_ablation_independent':True})
 times={'off':[],'on':[]}
 for _ in range(3):
  for label,state in [('off',off),('on',on)]:
   pixels,ms,_stats=run(state);assert pixels==reference;times[label].append(ms)
 save('short_warm_calls_ms',times)
 old=create('baseline',False,s['resize_conf']);new=create('candidate',True,s['resize_conf'])
 a,_,_=run(old);b,_,stats=run(new);assert a==b and 'Resident SPAN eligible: no\n' in stats and count(stats,'Resident SPAN segments')==0
 save('resize_fallback',{'pixels_exact':True,'stats':stats})
 lib,ctx,plan=on;assert lib.aji_vk_configure(ctx,size,size,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
 b,_,stats=run(on);assert b==reference and count(stats,'Resident SPAN segments')==1
 save('reconfigure',{'pixels_exact':True})
 r['passed']=True;r['identity']={k:hashlib.sha256(Path(s[k]).read_bytes()).hexdigest() for k in ('baseline','candidate','conf','resize_conf')}
 r['scope']='macOS native CoreML CPU256->512->1024, RGB adapter work only; no claim about GPU/ANE/internal framework copies'
finally:
 for lib,ctx in reversed(contexts):lib.aji_vk_destroy(ctx)
 (out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
