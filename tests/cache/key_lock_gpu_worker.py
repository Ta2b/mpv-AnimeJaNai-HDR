#!/usr/bin/env python3
"""One tiny real TensorRT builder/consumer; coordinated by key_lock_check.py."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

class Params(C.Structure):
    _fields_ = [('api_version', C.c_uint32), ('cuda_context', C.c_void_p),
        ('conf_path', C.c_char_p), ('model_dir', C.c_char_p), ('trtexec', C.c_char_p),
        ('trtexec_env', C.c_char_p), ('slot', C.c_int), ('rife_model_dir', C.c_char_p),
        ('async_build', C.c_int), ('d3d11_device', C.c_void_p), ('engine_path', C.c_char_p),
        ('max_width', C.c_int), ('max_height', C.c_int), ('log', C.c_void_p), ('log_opaque', C.c_void_p)]
class Frame(C.Structure):
    _fields_ = [('width', C.c_int), ('height', C.c_int), ('format', C.c_int),
        ('matrix', C.c_int), ('range', C.c_int), ('siting', C.c_int),
        ('plane', C.c_void_p * 3), ('stride', C.c_ssize_t * 3)]

s = json.loads(Path(sys.argv[1]).read_text()); out = Path(s['output']); ptr = C.c_void_p
lib = C.CDLL(s['library']); cuda = C.CDLL('libcudart.so.13')
for name, args, rest in [
    ('aji_create', [C.POINTER(Params)], ptr),
    ('aji_configure', [ptr, C.c_int, C.c_int, C.c_double, C.POINTER(C.c_int), C.POINTER(C.c_int)], C.c_int),
    ('aji_infer', [ptr, C.POINTER(Frame), C.POINTER(Frame), ptr], C.c_int),
    ('aji_flush', [ptr, ptr], C.c_uint64), ('aji_wait', [ptr, C.c_uint64], C.c_int),
    ('aji_destroy', [C.POINTER(ptr)], None), ('aji_last_error', [ptr], C.c_char_p),
    ('aji_current_log', [ptr], C.c_char_p),
    ('aji_poll', [ptr], C.c_int),
]:
    f = getattr(lib, name); f.argtypes = args; f.restype = rest
for name, args in [('cudaMalloc', [C.POINTER(ptr), C.c_size_t]), ('cudaFree', [ptr]),
    ('cudaMemcpy', [ptr, ptr, C.c_size_t, C.c_int]), ('cudaStreamCreate', [C.POINTER(ptr)]),
    ('cudaStreamSynchronize', [ptr]), ('cudaStreamDestroy', [ptr])]:
    getattr(cuda, name).argtypes = args
logger_type = C.CFUNCTYPE(None, ptr, C.c_int, C.c_char_p)
@logger_type
def logger(_, level, message): print(level, message.decode(errors='replace'), flush=True)
context, allocated, stream = ptr(), [], ptr()
def wait_file(path):
    deadline = time.monotonic() + 15
    while not Path(path).exists():
        assert time.monotonic() < deadline, 'controller signal missing'
        time.sleep(.005)
try:
    params = Params(api_version=9, conf_path=os.fsencode(s['conf']), model_dir=os.fsencode(s['models']),
        trtexec=os.fsencode(s['trtexec']), rife_model_dir=os.fsencode(s['rife']) if s.get('rife') else None,
        trtexec_env=os.fsencode(s['trtexec_env']) if s.get('trtexec_env') else None,
        slot=1, async_build=s.get('async_build', 0), log=C.cast(logger, ptr))
    context = ptr(lib.aji_create(C.byref(params))); assert context
    out.with_suffix('.ready').touch(); wait_file(s['start'])
    started = time.perf_counter(); ow, oh = C.c_int(), C.c_int()
    status = lib.aji_configure(context, 128, 72, 24, C.byref(ow), C.byref(oh))
    result = {'configure_status': status, 'configure_seconds': time.perf_counter()-started,
              'error': lib.aji_last_error(context).decode()}
    if s.get('require_motion'):
        result['active_configuration'] = lib.aji_current_log(context).decode()
        assert 'Motion applied to the upscaled pictures' in result['active_configuration'], result
    if s.get('async_probe') and status==0:
        deadline=time.monotonic()+20
        while not lib.aji_poll(context):
            assert time.monotonic()<deadline,'build timeout'
            time.sleep(.005)
        result['poll_error']=lib.aji_last_error(context).decode()
        status=lib.aji_configure(context,128,72,24,C.byref(ow),C.byref(oh))
        result['reload_status']=status
        result['current_log']=lib.aji_current_log(context).decode()
        if status==0 and 'FAILED' not in result['current_log'] and s.get('observe_second_call'):
            calls=Path(s['observe_second_call'])
            while len(list(calls.glob('*.json')))<2:
                assert time.monotonic()<deadline,'second build not observed'
                time.sleep(.005)
    elif s.get('async_build'):
        assert status == 0
        out.with_suffix('.waiting').touch(); wait_file(s['quit'])
        started = time.perf_counter(); lib.aji_destroy(C.byref(context))
        result['destroy_seconds'] = time.perf_counter()-started
    if status == 1:
        assert cuda.cudaStreamCreate(C.byref(stream)) == 0
        def allocate(w, h):
            f = Frame(width=w, height=h, format=1, matrix=2, range=1, siting=1)
            for i, rows in enumerate((h, h//2)):
                memory = ptr(); assert cuda.cudaMalloc(C.byref(memory), w*rows)==0
                allocated.append(memory); f.plane[i] = memory; f.stride[i] = w
            return f
        source, target = allocate(128,72), allocate(ow.value,oh.value)
        data = Path(s['input']).read_bytes(); pos = 0
        for i, rows in enumerate((72,36)):
            chunk = np.frombuffer(data[pos:pos+128*rows],np.uint8)
            assert cuda.cudaMemcpy(source.plane[i],chunk.ctypes.data,chunk.nbytes,1)==0
            pos += chunk.nbytes
        assert cuda.cudaStreamSynchronize(None)==0
        assert lib.aji_infer(context,C.byref(source),C.byref(target),stream)==0
        assert lib.aji_wait(context,lib.aji_flush(context,stream))==0
        planes = []
        for i, rows in enumerate((oh.value,oh.value//2)):
            plane = np.empty(ow.value*rows,np.uint8)
            assert cuda.cudaMemcpy(plane.ctypes.data,target.plane[i],plane.nbytes,2)==0
            planes.append(plane)
        np.save(out.with_suffix('.npy'), np.concatenate(planes))
        result['engines']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(s['models']).glob('aji-v2-*.engine')}
    result['active_status']=status
    result['final_error']=lib.aji_last_error(context).decode() if context else ''
    result['engine_sizes']={f.name:f.stat().st_size for f in Path(s['models']).glob('aji-v2-*.engine')}
    out.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
finally:
    if context: lib.aji_destroy(C.byref(context))
    for memory in allocated: cuda.cudaFree(memory)
    if stream: cuda.cudaStreamDestroy(stream)
