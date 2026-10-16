#!/usr/bin/env python3
"""Targeted ORT bindings ablation through actual RIFE+SPAN on CPU."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import sys
import time
import numpy as np

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);ptr=C.c_void_p;bytep=C.POINTER(C.c_ubyte)
w=s.get('width',128);h=72
class Plan(C.Structure): _fields_=[(n,C.c_int) for n in ('width','height','numerator','denominator','active')]
lib=C.CDLL(s['library']);counter=C.CDLL(None).aji_test_ort_counters
counter.argtypes=[C.POINTER(C.c_uint64)]
def snapshot():
    values=(C.c_uint64*6)();counter(values);return np.array(list(values),dtype=np.int64)
lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=ptr
lib.aji_vk_configure.argtypes=[ptr,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
lib.aji_vk_process.argtypes=[ptr,bytep,C.c_ssize_t,bytep,C.c_ssize_t,C.c_double,bytep,C.c_ssize_t]
lib.aji_vk_error.argtypes=[ptr];lib.aji_vk_error.restype=C.c_char_p
lib.aji_vk_stats_snapshot.argtypes=[ptr];lib.aji_vk_stats_snapshot.restype=C.c_char_p
lib.aji_vk_destroy.argtypes=[ptr]
ctx=lib.aji_vk_create(os.fsencode(s['conf']),os.fsencode(s['models']),os.fsencode(s['rife']),
    os.fsencode(s.get('device','cpu')),None,1)
assert ctx,lib.aji_vk_error(None)
arrays={};samples=[];pairs=[]
try:
    plan=Plan();assert lib.aji_vk_configure(ctx,w,h,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
    assert (plan.width,plan.height,plan.numerator,plan.denominator)==(2*w,2*h,2,1)
    y,x,ch=np.indices((h,w,3))
    frames=[]
    for i in range(4):
        f=np.full((h,3*w+17),0xA5,np.uint8);f[:,:3*w]=((x*3+y*7+ch*13+i*37)%256).astype(np.uint8).reshape(h,3*w)
        frames.append(f)
    output=np.zeros((plan.height,plan.width*3+19),np.uint8)
    def process(label,previous,current,instant,phase):
        start=time.perf_counter()
        status=lib.aji_vk_process(ctx,previous.ctypes.data_as(bytep) if previous is not None else None,
            previous.strides[0] if previous is not None else 0,current.ctypes.data_as(bytep),current.strides[0],
            instant,output.ctypes.data_as(bytep),output.strides[0])
        elapsed=(time.perf_counter()-start)*1000;assert status==0,lib.aji_vk_error(ctx)
        arrays[label]=output[:,:plan.width*3].copy();samples.append(dict(phase=phase,completed=True,duration_ms=elapsed))
    process('source-0',None,frames[0],1,'warmup')
    process('warm-middle',frames[0],frames[1],.5,'warmup');process('source-1',frames[0],frames[1],1,'warmup')
    stats_before=lib.aji_vk_stats_snapshot(ctx).decode()
    calls_before=snapshot();wall_start=time.perf_counter()
    for i in (2,3):
        start=time.perf_counter();process('middle-'+str(i),frames[i-1],frames[i],.5,'measure')
        process('source-'+str(i),frames[i-1],frames[i],1,'measure')
        pairs.append(dict(phase='measure',completed=True,cost_ms=(time.perf_counter()-start)*1000))
    wall_seconds=time.perf_counter()-wall_start;api_calls=(snapshot()-calls_before).tolist()
    stats=lib.aji_vk_stats_snapshot(ctx).decode();assert 'RIFE:' in stats and 'CPU' in stats,stats
    def timings(text):
        keys=['RIFE measured runs','RIFE preparation total ms','RIFE inference total ms','RIFE output total ms','RIFE overlap wait total ms']
        return {k:float(re.search('^'+re.escape(k)+r': ([0-9.eE+-]+)$',text,re.M).group(1)) for k in keys}
    a,b=timings(stats_before),timings(stats)
    rife_window={k:b[k]-a[k] for k in a};assert rife_window['RIFE measured runs']==2,rife_window
    if s.get('fast_tiled'): assert 'motion applied to the upscaled pictures:' in stats,stats
    if s.get('fast_tiled') and w>=224: assert 'Tiles: 2x1' in stats and stats.count('[ONNX Runtime/CPU:')==2,stats
    # Reconfigure lifetime, outside the measured interval; no stale queued source work.
    assert lib.aji_vk_configure(ctx,w,h,24,C.byref(plan))==0,lib.aji_vk_error(ctx)
    process('reconfigured-source',None,frames[0],1,'warmup')
    np.savez(out.with_suffix('.npz'),**arrays);out.with_suffix('.stats').write_text(stats)
    trace=dict(schema='animejanai.measurements.v1',scope='chain_offscreen',data_origin='measurement',
        sample_unit='output',timing_source='wall_completion',warmup_policy='first source and first RIFE pair excluded',
        identity=dict(media_sha256=hashlib.sha256(b''.join(f[:,:3*w].tobytes() for f in frames)).hexdigest(),
            models_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for folder in [Path(s['models']),Path(s['rife'])] for p in folder.glob('*.onnx')},
            settings_sha256=hashlib.sha256(Path(s['conf']).read_bytes()).hexdigest(),machine_id=os.uname().nodename,
            runtime='ONNX Runtime: '+str(Path(s['ort_runtime']).resolve()),driver='CPU / no GPU driver used',output_contract=f'RGB24 {plan.width}x{plan.height}'),
        session=dict(desktop_load='unknown',player_state='isolated CPU chain without display',power_mode='unknown'),
        provenance=dict(library=s['library'],library_sha256=hashlib.sha256(Path(s['library']).read_bytes()).hexdigest()),
        window=dict(wall_seconds=wall_seconds,media_seconds=2/24,excludes_compile_warmup=True),samples=samples,pairs=pairs,
        resources={},
        auxiliary_observations=dict(process_peak_ram_bytes=dict(value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            source='Linux getrusage peak RSS',scope='process lifetime including configure/warmup/reconfigure; not a measured-window peak')),
        quality=dict(status='separate comparison of all output arrays required'))
    out.with_suffix('.trace.json').write_text(json.dumps(trace,indent=2)+'\n')
    result=dict(real_ort_cpu=True,real_rife_and_span=True,quality_mode=not s.get('fast_tiled',False),outputs=len(arrays),
        measured_pairs=2,rife_profile_window=rife_window,ort_api_calls=dict(zip(['cpu_memory_descriptors','tensor_descriptors','owned_shape_handles','null_output_requests','runs','borrowed_shape_queries'],api_calls)),wall_seconds=wall_seconds,
        pair_cost_ms=[p['cost_ms'] for p in pairs],fps_claimed=False,desktop_load_measured=False)
    out.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
finally:lib.aji_vk_destroy(ctx)
