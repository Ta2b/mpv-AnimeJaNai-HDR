#!/usr/bin/env python3
"""Short native two-SPAN Metal check. SPEC supplies baseline/candidate dylibs,
models, conf, resize_conf, output. Stop before timing if the first RGB differs.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import time


class Plan(C.Structure):
    _fields_=[(k,C.c_int) for k in ('width','height','numerator','denominator','active')]


def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(exist_ok=True)
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    identity={k:digest(s[k]) for k in ('baseline','candidate','conf','resize_conf')}
    receipt=out/'receipt.json'
    if receipt.exists():
        r=json.loads(receipt.read_text());assert r['passed'] and r['identity']==identity
        print('Matching conclusive receipt; no replay.');return
    libs={};contexts=[]
    for name in ('baseline','candidate'):
        lib=C.CDLL(s[name],mode=os.RTLD_LOCAL)
        lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=C.c_void_p
        lib.aji_vk_configure.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
        lib.aji_vk_process.argtypes=[C.c_void_p,C.c_void_p,C.c_ssize_t,C.c_void_p,C.c_ssize_t,C.c_double,C.c_void_p,C.c_ssize_t]
        lib.aji_vk_error.argtypes=[C.c_void_p];lib.aji_vk_error.restype=C.c_char_p
        lib.aji_vk_stats_snapshot.argtypes=[C.c_void_p];lib.aji_vk_stats_snapshot.restype=C.c_char_p
        lib.aji_vk_destroy.argtypes=[C.c_void_p];lib.aji_vk_destroy.restype=None
        libs[name]=lib
    size=128;pitch=size*3+16;source=(C.c_ubyte*(pitch*size))()
    for y in range(size):
        for x in range(size):
            for k in range(3):source[y*pitch+x*3+k]=(x*3+y*2+k*30+(x//16%2)*60)%256
    def create(name,resident,conf):
        os.environ['AJI_METAL_RESIDENT_SPAN']='1' if resident else '0';lib=libs[name]
        ctx=lib.aji_vk_create(os.fsencode(conf),os.fsencode(s['models']),b'',b'gpu',b'',1)
        assert ctx,lib.aji_vk_error(None);contexts.append((lib,ctx));plan=Plan()
        assert lib.aji_vk_configure(ctx,size,size,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
        return lib,ctx,plan
    def run(state):
        lib,ctx,plan=state;row=plan.width*3;stride=row+16
        output=(C.c_ubyte*(stride*plan.height))();C.memset(output,0xa5,C.sizeof(output))
        start=time.perf_counter();status=lib.aji_vk_process(ctx,None,0,source,pitch,1,output,stride);ms=(time.perf_counter()-start)*1000
        assert status==0,lib.aji_vk_error(ctx)
        raw=bytes(output);assert all(raw[y*stride+row:(y+1)*stride]==b'\xa5'*16 for y in range(plan.height))
        return b''.join(raw[y*stride:y*stride+row] for y in range(plan.height)),ms,lib.aji_vk_stats_snapshot(ctx).decode()
    def count(stats,key):return int(next(x.split(': ',1)[1] for x in stats.splitlines() if x.startswith(key+': ')))
    r={'identity':identity,'source_size':[size,size]}
    try:
        base=create('baseline',False,s['conf']);off=create('candidate',False,s['conf']);on=create('candidate',True,s['conf'])
        reference,_,_=run(base);a,_,off_stats=run(off);b,_,on_stats=run(on)
        assert reference==a==b,'First RGB differs; stop before timings'
        assert 'Resident SPAN eligible: yes\n' in on_stats and count(on_stats,'Resident SPAN segments')==1,on_stats
        assert count(off_stats,'Resident SPAN segments')==0,off_stats
        assert count(off_stats,'Executor host staging bytes')==(128*128+256*256)*3
        assert count(off_stats,'Executor explicit readback bytes')==(256*256+512*512)*3
        assert count(on_stats,'Executor host staging bytes')==128*128*3
        assert count(on_stats,'Executor explicit readback bytes')==512*512*3
        r.update(pixels_exact=True,output_sha256=hashlib.sha256(b).hexdigest(),off_stats=off_stats,on_stats=on_stats)
        times={'off':[],'on':[]}
        for _ in range(3):
            for label,state in [('off',off),('on',on)]:
                pixels,ms,_stats=run(state);assert pixels==reference;times[label].append(ms)
        r['full_call_ms']=times
        old_resize=create('baseline',False,s['resize_conf']);new_resize=create('candidate',True,s['resize_conf'])
        a,_,_=run(old_resize);b,_,stats=run(new_resize)
        assert a==b and 'Resident SPAN eligible: no\n' in stats and count(stats,'Resident SPAN segments')==0,stats
        r['resize_fallback']={'pixels_exact':True,'sha256':hashlib.sha256(b).hexdigest(),'stats':stats}
        # Reconfiguration drops the former graph/data lifetime and selects the
        # same resident route again; no replay of the timing or resize case.
        lib,ctx,plan=on;assert lib.aji_vk_configure(ctx,size,size,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
        recovered,_,stats=run(on);assert recovered==reference and count(stats,'Resident SPAN segments')==1
        r['reconfigure_exact']=True
    finally:
        for lib,ctx in reversed(contexts):lib.aji_vk_destroy(ctx)
    assert identity=={k:digest(s[k]) for k in identity}
    r.update(passed=True,scope='native Apple Metal, two real SPAN128->256->512; explicit host staging/readBytes removed, default graph options unchanged; no driver-internal-copy or other-backend claim')
    receipt.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))


if __name__=='__main__':main()
