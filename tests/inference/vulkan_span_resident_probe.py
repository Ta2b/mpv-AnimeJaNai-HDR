#!/usr/bin/env python3
"""One native Vulkan SPAN ablation; stop before timing if pixels differ.
SPEC: baseline, candidate, models, conf, resize_conf, output (existing private dir).
No model compilation, installation edits or concurrent GPU workloads.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time


class Plan(C.Structure):
    _fields_=[(k,C.c_int) for k in ('width','height','numerator','denominator','active')]


def main():
    spec=json.loads(Path(sys.argv[1]).read_text());out=Path(spec['output'])
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    identity={k:digest(spec[k]) for k in ('baseline','candidate','conf','resize_conf')}
    receipt=out/'receipt.json'
    if receipt.exists():
        saved=json.loads(receipt.read_text());assert saved['passed'] and saved['identity']==identity
        print('Matching conclusive receipt; no replay.');return
    os.environ['AJI_VK_CACHE']='0'
    libs={}
    for name in ('baseline','candidate'):
        lib=C.CDLL(spec[name],mode=os.RTLD_LOCAL)
        lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=C.c_void_p
        lib.aji_vk_configure.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
        lib.aji_vk_process.argtypes=[C.c_void_p,C.c_void_p,C.c_ssize_t,C.c_void_p,C.c_ssize_t,C.c_double,C.c_void_p,C.c_ssize_t]
        lib.aji_vk_error.argtypes=[C.c_void_p];lib.aji_vk_error.restype=C.c_char_p
        lib.aji_vk_stats_snapshot.argtypes=[C.c_void_p];lib.aji_vk_stats_snapshot.restype=C.c_char_p
        lib.aji_vk_destroy.argtypes=[C.c_void_p];lib.aji_vk_destroy.restype=None
        libs[name]=lib
    width=128;stride=width*3+16
    data=(C.c_ubyte*(stride*width))()
    for y in range(width):
        for x in range(width):
            for k in range(3):data[y*stride+x*3+k]=(x*3+y*2+k*30+(96 if x>=64 else 0))%256
    contexts=[]
    def create(name,resident,conf,models=None):
        os.environ['AJI_VK_RESIDENT_SPAN']='1' if resident else '0';lib=libs[name]
        ctx=lib.aji_vk_create(os.fsencode(conf),os.fsencode(models or spec['models']),b'',b'',b'',1)
        assert ctx,lib.aji_vk_error(None);contexts.append((lib,ctx));plan=Plan()
        assert lib.aji_vk_configure(ctx,width,width,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
        return lib,ctx,plan
    def process(state,success=True):
        lib,ctx,plan=state;row=plan.width*3;pitch=row+16
        buffer=(C.c_ubyte*(pitch*plan.height))();C.memset(buffer,0xa5,C.sizeof(buffer))
        start=time.perf_counter();status=lib.aji_vk_process(ctx,None,0,data,stride,1,buffer,pitch)
        ms=(time.perf_counter()-start)*1000
        assert (status==0)==success,(status,lib.aji_vk_error(ctx))
        raw=bytes(buffer)
        if not success:assert raw==b'\xa5'*len(raw);return lib.aji_vk_error(ctx).decode()
        assert all(raw[y*pitch+row:(y+1)*pitch]==b'\xa5'*16 for y in range(plan.height))
        active=b''.join(raw[y*pitch:y*pitch+row] for y in range(plan.height))
        return active,ms,lib.aji_vk_stats_snapshot(ctx).decode()
    result={'identity':identity,'input_sha256':hashlib.sha256(bytes(data)).hexdigest(),'source_size':[width,width]}
    try:
        baseline=create('baseline',False,spec['conf']);off=create('candidate',False,spec['conf']);on=create('candidate',True,spec['conf'])
        reference,_,_=process(baseline);before,_,off_stats=process(off);after,_,on_stats=process(on)
        assert reference==before==after,'First output differs; stop before timing'
        assert (on[2].width,on[2].height)==(512,512)
        assert 'SPAN resident segments: 1\n' in on_stats and 'SPAN host adapters: 0\n' in on_stats,on_stats
        assert 'SPAN explicit resident uploads: 1\n' in on_stats and 'SPAN explicit resident downloads: 1\n' in on_stats,on_stats
        assert 'SPAN inferences: 2\n' in on_stats and 'SPAN inferences: 2\n' in off_stats
        result.update(pixels_exact=True,output_sha256=hashlib.sha256(after).hexdigest(),first_off_stats=off_stats,first_on_stats=on_stats)
        # One short timing observation, after the first outputs warmed both paths.
        timing={'off':[],'on':[]}
        for _ in range(3):
            for label,state in (('off',off),('on',on)):
                pixels,ms,_stats=process(state);assert pixels==reference
                timing[label].append(ms)
        result['full_call_ms']=timing
        old_resize=create('baseline',False,spec['resize_conf']);new_resize=create('candidate',True,spec['resize_conf'])
        a,_,_=process(old_resize);b,_,stats=process(new_resize);assert a==b
        assert 'SPAN resident segments: 0\n' in stats and 'SPAN resident route: intermediate-resize\n' in stats,stats
        result['resize_fallback']={'pixels_exact':True,'output_sha256':hashlib.sha256(b).hexdigest(),'stats':stats}
        # A missing output at the second real SPAN leaves recorded commands
        # unsubmitted. Check no partial output, latched error, and reconfigure.
        bad=out/'error-models';bad.mkdir()
        for p in Path(spec['models']).iterdir():
            if p.suffix=='.param':shutil.copy2(p,bad/p.name)
            else:(bad/p.name).symlink_to(p.resolve())
        model=next(line.split('=',1)[1] for line in Path(spec['conf']).read_text().splitlines() if line.startswith('chain_1_model_2_name='))
        param=bad/(model+'.ncnn.param');original=param.read_text();assert 'out0' in original
        param.write_text(original.replace('out0','missing_expected_output'))
        failed=create('candidate',True,spec['conf'],bad)
        error=process(failed,False);assert 'resident inference failed' in error,error
        latched=process(failed,False);assert 'reconfigure before retry' in latched,latched
        param.write_text(original);lib,ctx,plan=failed
        assert lib.aji_vk_configure(ctx,width,width,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
        recovered,_,_=process(failed);assert recovered==reference
        result['controlled_error']={'before_submission':True,'output_untouched':True,'latched':True,'reconfigure_exact':True}
    finally:
        for lib,ctx in reversed(contexts):lib.aji_vk_destroy(ctx)
    assert identity=={k:digest(spec[k]) for k in identity},'inputs changed during qualification'
    result.update(passed=True,scope='Linux Vulkan RTX4070Ti, two real SPAN128->256->512, no RIFE/HDR/physical display or other-GPU qualification')
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
