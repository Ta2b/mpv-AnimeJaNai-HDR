#!/usr/bin/env python3
"""Short ABI9 cache checks against a fresh calculation using identical plans.

Run once per library. This does not claim FPS or Fast/Quality equivalence.
"""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import time
import numpy as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('spec', type=Path)
a = p.parse_args()
s = json.loads(a.spec.read_text())
class Params(C.Structure):
    _fields_ = [('api_version', C.c_uint32), ('cuda_context', C.c_void_p),
                ('conf_path', C.c_char_p), ('model_dir', C.c_char_p),
                ('trtexec', C.c_char_p), ('trtexec_env', C.c_char_p),
                ('slot', C.c_int), ('rife_model_dir', C.c_char_p),
                ('async_build', C.c_int), ('d3d11_device', C.c_void_p),
                ('engine_path', C.c_char_p), ('max_width', C.c_int),
                ('max_height', C.c_int), ('log', C.c_void_p), ('log_opaque', C.c_void_p)]

class Frame(C.Structure):
    _fields_ = [('width', C.c_int), ('height', C.c_int), ('format', C.c_int),
                ('matrix', C.c_int), ('range', C.c_int), ('siting', C.c_int),
                ('plane', C.c_void_p * 3), ('stride', C.c_ssize_t * 3)]

ptr = C.c_void_p
cuda = C.CDLL('libcudart.so.13')
lib = C.CDLL(s['library'])
for name, args, rest in [
    ('aji_create', [C.POINTER(Params)], ptr),
    ('aji_configure', [ptr, C.c_int, C.c_int, C.c_double, C.POINTER(C.c_int), C.POINTER(C.c_int)], C.c_int),
    ('aji_infer', [ptr, C.POINTER(Frame), C.POINTER(Frame), ptr], C.c_int),
    ('aji_infer_rife', [ptr, C.POINTER(Frame), C.POINTER(Frame), C.c_double, C.POINTER(Frame), ptr], C.c_int),
    ('aji_rife_begin_pair', [ptr, C.c_uint64, C.c_uint64], None),
    ('aji_temporal_reset', [ptr], None), ('aji_current_log', [ptr], C.c_char_p),
    ('aji_last_error', [ptr], C.c_char_p), ('aji_flush', [ptr, ptr], C.c_uint64),
    ('aji_wait', [ptr, C.c_uint64], C.c_int), ('aji_destroy', [C.POINTER(ptr)], None),
]:
    f = getattr(lib, name); f.argtypes = args; f.restype = rest
for name, args in [
    ('cudaMalloc', [C.POINTER(ptr), C.c_size_t]), ('cudaFree', [ptr]),
    ('cudaMemcpy', [ptr, ptr, C.c_size_t, C.c_int]),
    ('cudaStreamCreateWithFlags', [C.POINTER(ptr), C.c_uint]),
    ('cudaStreamSynchronize', [ptr]), ('cudaStreamDestroy', [ptr]),
]:
    getattr(cuda, name).argtypes = args

def ck(code):
    assert code == 0, code

allocated, streams, outputs, results = [], [], {}, {}
logger_type = C.CFUNCTYPE(None, ptr, C.c_int, C.c_char_p)
@logger_type
def logger(_, level, message):
    print(level, message.decode(errors='replace'), flush=True)
context = ptr()
start = time.perf_counter()
try:
    params = Params(api_version=9, conf_path=os.fsencode(s['conf']),
                    model_dir=os.fsencode(s['models']), rife_model_dir=os.fsencode(s['rife']),
                    trtexec=os.fsencode(s.get('trtexec', '/bin/false')), slot=1, log=C.cast(logger, ptr))
    context = ptr(lib.aji_create(C.byref(params)))
    assert context
    ow, oh = C.c_int(), C.c_int()
    assert lib.aji_configure(context, 128, 72, 24, C.byref(ow), C.byref(oh)) == 1, lib.aji_last_error(context)
    config = lib.aji_current_log(context).decode()
    print(config, flush=True)
    quality = s.get('quality', False)
    if not quality:
        assert 'Motion applied to the upscaled pictures' in config, 'Fast not active'
    setup_seconds = time.perf_counter() - start
    for _ in range(2):
        stream = ptr(); ck(cuda.cudaStreamCreateWithFlags(C.byref(stream), 1)); streams.append(stream)

    def allocate(w, h):
        f = Frame(width=w, height=h, format=1, matrix=2, range=1, siting=1)
        for plane, rows in enumerate((h, h // 2)):
            memory = ptr(); ck(cuda.cudaMalloc(C.byref(memory), (w + 64) * rows))
            allocated.append(memory); f.plane[plane] = memory; f.stride[plane] = w + 64
        return f

    def upload(f, data):
        pos = 0
        for plane, rows in enumerate((f.height, f.height // 2)):
            packed = np.full((rows, f.stride[plane]), 0xA5, np.uint8)
            size = f.width * rows
            packed[:, :f.width] = np.frombuffer(data[pos:pos+size], np.uint8).reshape(rows, f.width)
            ck(cuda.cudaMemcpy(f.plane[plane], packed.ctypes.data, packed.nbytes, 1)); pos += size
        ck(cuda.cudaStreamSynchronize(None))

    def wait(stream):
        ck(lib.aji_wait(context, lib.aji_flush(context, stream)))

    def download(f):
        planes = []
        for plane, rows in enumerate((f.height, f.height // 2)):
            packed = np.empty((rows, f.stride[plane]), np.uint8)
            ck(cuda.cudaMemcpy(packed.ctypes.data, f.plane[plane], packed.nbytes, 2))
            planes.append(packed[:, :f.width].reshape(-1))
        return np.concatenate(planes)

    sources = [allocate(128, 72) for _ in range(3)]
    mid, final = allocate(128, 72), allocate(ow.value, oh.value)
    raw = Path(s['input']).read_bytes(); n = 128 * 72 * 3 // 2
    assert len(raw) >= n * 3
    data = [raw[i*n:(i+1)*n] for i in range(3)]

    def reset():
        lib.aji_temporal_reset(context)
        for f in [*sources, mid]:
            f.matrix, f.range, f.siting = 2, 1, 1
        for f, d in zip(sources, data): upload(f, d)

    def infer(left, right, ids=(1, 2), instant=.5, stream=None, finish=True):
        stream = streams[0] if stream is None else stream
        if ids is not None: lib.aji_rife_begin_pair(context, *ids)
        status = lib.aji_infer_rife(context, C.byref(left), C.byref(right), instant, C.byref(mid), stream)
        assert status == 0, (status, lib.aji_last_error(context))
        ck(lib.aji_infer(context, C.byref(mid), C.byref(final), stream))
        if finish:
            wait(stream)
            return download(final)

    def record(case, got, fresh):
        d = np.abs(got.astype(np.int16) - fresh.astype(np.int16))
        outputs[case] = got; outputs[case + '-fresh'] = fresh
        results[case] = {'changed_bytes': int(np.count_nonzero(d)), 'max_delta': int(d.max())}

    if not s.get('remaining_only'):
        reset()
        infer(*sources[:2], instant=.25)
        cached = infer(*sources[:2])
        lib.aji_temporal_reset(context)
        record('unchanged-pair', cached, infer(*sources[:2]))

    if not quality and not s.get('remaining_only'):
        for field, value in [('range', 2), ('matrix', 1)]:
            reset(); infer(*sources[:2], instant=.25)
            for f in [*sources[:2], mid]: setattr(f, field, value)
            got = infer(*sources[:2])
            lib.aji_temporal_reset(context)
            record('changed-' + field, got, infer(*sources[:2]))

        reset(); infer(*sources[:2], instant=.25)
        for f in [sources[1], sources[2], mid]: f.range = 2
        got = infer(*sources[1:], ids=(2, 3))
        lib.aji_temporal_reset(context)
        record('promotion-changed-range', got, infer(*sources[1:], ids=(2, 3)))

        reset(); infer(*sources[:2], instant=.25)
        sources[1].range = 2
        ck(lib.aji_infer(context, C.byref(sources[1]), C.byref(final), streams[0])); wait(streams[0])
        got = download(final)
        lib.aji_temporal_reset(context)
        ck(lib.aji_infer(context, C.byref(sources[1]), C.byref(final), streams[0])); wait(streams[0])
        record('endpoint-changed-range', got, download(final))

        reset(); infer(*sources[:2], ids=None, instant=.25)
        upload(sources[0], data[2]); upload(sources[1], data[0])
        got = infer(*sources[:2], ids=None)
        lib.aji_temporal_reset(context)
        record('recycled-no-ids', got, infer(*sources[:2], ids=None))

        reset(); infer(*sources[:2], instant=.25, finish=False)
        got = infer(*sources[:2], stream=streams[1])
        lib.aji_temporal_reset(context)
        record('changed-stream', got, infer(*sources[:2], stream=streams[1]))

        reset(); infer(*sources[:2], instant=.25)
        lib.aji_temporal_reset(context)
        upload(sources[0], data[2]); upload(sources[1], data[0])
        got = infer(*sources[:2], ids=(11, 12))
        lib.aji_temporal_reset(context)
        record('reset-recycled-storage', got, infer(*sources[:2], ids=(11, 12)))

        reset(); lib.aji_rife_begin_pair(context, 1, 2)
        ck(lib.aji_infer_rife(context, C.byref(sources[0]), C.byref(sources[1]), .5, C.byref(mid), streams[0]))
        mid.range = 2
        rejected = lib.aji_infer(context, C.byref(mid), C.byref(final), streams[0])
        results['handoff-changed-range'] = {'status': rejected, 'error': lib.aji_last_error(context).decode()}
        wait(streams[0])

    if s.get('remaining_only'):
        reset(); infer(*sources[:2], instant=.25)
        got = infer(*sources[1:], ids=(2, 3))
        lib.aji_temporal_reset(context)
        record('valid-promotion', got, infer(*sources[1:], ids=(2, 3)))

        reset(); upload(mid, data[2]); lib.aji_rife_begin_pair(context, 1, 2)
        ck(lib.aji_infer_rife(context, C.byref(sources[0]), C.byref(sources[1]), .5, C.byref(mid), streams[0]))
        final.width += 2
        assert lib.aji_infer(context, C.byref(mid), C.byref(final), streams[0]) == -2
        final.width -= 2
        ck(lib.aji_infer(context, C.byref(mid), C.byref(final), streams[0])); wait(streams[0])
        got = download(final)
        lib.aji_temporal_reset(context)
        ck(lib.aji_infer(context, C.byref(mid), C.byref(final), streams[0])); wait(streams[0])
        record('validation-error-cancels-handoff', got, download(final))

        reset(); infer(*sources[:2], instant=.25)
        assert lib.aji_configure(context, 128, 72, 24, C.byref(ow), C.byref(oh)) == 1
        upload(sources[0], data[2]); upload(sources[1], data[0])
        got = infer(*sources[:2])
        lib.aji_temporal_reset(context)
        record('reconfigure-recycled-storage', got, infer(*sources[:2]))

    elapsed = time.perf_counter() - start
    Path(s['output']).parent.mkdir(parents=True, exist_ok=True)
    np.savez(s['output'] + '.npz', **outputs)
    Path(s['output'] + '.json').write_text(json.dumps({'results': results, 'setup_seconds': setup_seconds,
        'total_seconds': elapsed, 'quality': quality, 'library': s['library']}, indent=2) + '\n')
finally:
    if context: lib.aji_destroy(C.byref(context))
    for memory in allocated: cuda.cudaFree(memory)
    for stream in streams: cuda.cudaStreamDestroy(stream)
