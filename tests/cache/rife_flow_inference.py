#!/usr/bin/env python3
"""One real RIFE source pair at three instants; before/after shared-engine bytes."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

p=argparse.ArgumentParser()
for name in ['reference','candidate','models','rife','input','output']:p.add_argument('--'+name,required=True,type=Path)
p.add_argument('--worker',choices=['before','after']);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if not a.worker:
    for label in ['before','after']:
        env=dict(os.environ,AJI_ORT_PROVIDER='cpu',AJI_ORT_CACHE=str(out/(label+'-cache')))
        with (out/(label+'.log')).open('w') as log:
            subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker',label],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
    before=np.load(out/'before.npz');after=np.load(out/'after.npz')
    assert before.files==after.files and len(before.files)==3
    assert all(np.array_equal(before[k],after[k]) for k in before.files)
    old_flow=next((out/'before-cache').glob('*.flow.onnx'))
    new_flow=next((out/'after-cache').glob('rife-flow-v2/*/rife.flow.onnx'))
    assert old_flow.read_bytes()==new_flow.read_bytes()
    summary=dict(passed=True,outputs=3,changed_output_bytes=0,flow_graph_bytes_identical=True,
        source_model_sha256=hashlib.sha256((a.rife/'rife_v4.26.onnx').read_bytes()).hexdigest(),
        before=json.loads((out/'before.json').read_text()),after=json.loads((out/'after.json').read_text()),
        fps_gain_claimed=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));sys.exit()

class Plan(C.Structure):
    _fields_=[(n,C.c_int) for n in ['width','height','numerator','denominator','active']]
config=out/'fast.conf'
config.write_text('[global]\nbackend=OpenVINO\nrife_engine=fast\nengine_reuse=off\nrife_drawings=no\nengine_boost=no\n[slot_1]\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_before_upscale=yes\nchain_1_rife_factor_numerator=4\nchain_1_rife_factor_denominator=1\nchain_1_rife_scene_detect_threshold=0.150\nchain_1_model_1_name=2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16\n')
lib=C.CDLL(str((a.reference if a.worker=='before' else a.candidate).resolve()))
bytep=C.POINTER(C.c_ubyte)
lib.aji_vk_create.argtypes=[C.c_char_p]*5+[C.c_int];lib.aji_vk_create.restype=C.c_void_p
lib.aji_vk_configure.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_double,C.POINTER(Plan)]
lib.aji_vk_process.argtypes=[C.c_void_p,bytep,C.c_ssize_t,bytep,C.c_ssize_t,C.c_double,bytep,C.c_ssize_t]
lib.aji_vk_error.argtypes=[C.c_void_p];lib.aji_vk_error.restype=C.c_char_p
lib.aji_vk_destroy.argtypes=[C.c_void_p]
stats=out/(a.worker+'.stats');started=time.perf_counter()
context=lib.aji_vk_create(os.fsencode(config),os.fsencode(a.models),os.fsencode(a.rife),b'cpu',os.fsencode(stats),1)
assert context,lib.aji_vk_error(None)
outputs={};times=[]
try:
    plan=Plan();assert lib.aji_vk_configure(context,128,72,24,C.byref(plan))==0,lib.aji_vk_error(context)
    configure_ms=(time.perf_counter()-started)*1000
    assert (plan.numerator,plan.denominator)==(4,1)
    frames=np.fromfile(a.input,dtype=np.uint8).reshape(-1,72,384)
    previous=np.zeros((72,401),np.uint8);current=previous.copy()
    previous[:,:384]=frames[2];current[:,:384]=frames[3]
    result=np.zeros((plan.height,plan.width*3+19),np.uint8)
    for instant in [.25,.5,.75]:
        then=time.perf_counter()
        assert lib.aji_vk_process(context,previous.ctypes.data_as(bytep),previous.strides[0],current.ctypes.data_as(bytep),current.strides[0],instant,result.ctypes.data_as(bytep),result.strides[0])==0,lib.aji_vk_error(context)
        times.append((time.perf_counter()-then)*1000);outputs[str(instant)]=result[:,:plan.width*3].copy()
finally:lib.aji_vk_destroy(context)
assert 'motion applied to the upscaled pictures:' in stats.read_text(),stats.read_text()
np.savez(out/(a.worker+'.npz'),**outputs)
(out/(a.worker+'.json')).write_text(json.dumps(dict(configure_ms=configure_ms,call_ms=times,outputs=3,fast_motion_active=True),indent=2)+'\n')
