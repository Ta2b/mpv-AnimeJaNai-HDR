#!/usr/bin/env python3
"""Short, explicit GMFSS/RIFE/SPAN evaluation; requires external models/runtimes.

Run: python vfi_candidate_probe.py SPEC.json gmfss|rife|span
Input: consecutive RGB24 frames at spec width/height, never a synthetic FPS claim.
Successful matching receipts are reused. No automatic repetitions or soak tests.
"""
import ctypes as C
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def identity(spec, mode):
    files = dict(spec.get('identity_files', {}))
    files['input'] = spec['input']
    if mode == 'gmfss':
        source = Path(spec['gmfss_source'])
        for p in sorted((source / 'model').rglob('*.py')):
            files['source/' + str(p.relative_to(source))] = str(p)
        for p in sorted(Path(spec['weights']).glob('*.pkl')):
            files['weights/' + p.name] = str(p)
    else:
        files.update(library=spec['library'], conf=spec['conf'])
        if mode == 'span':
            files.update({f'span_input/{i}': p for i, p in enumerate(spec['span_inputs'])})
    return {'mode': mode, 'width': spec['width'], 'height': spec['height'],
            'files': {label: digest(p) for label, p in files.items()}}


def save_rgb(out, index, rgb):
    rgb = np.asarray(rgb, np.float32)
    if not np.isfinite(rgb).all():
        raise RuntimeError('Nonfinite model output')
    np.save(out / f'{index:03}.npy', rgb)
    # Same truncation as the official GMFSS inference_video.py presentation path.
    Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).save(out / f'{index:03}.png')


def gmfss(spec, out, frames):
    import torch
    torch.set_num_threads(1)
    torch.set_grad_enabled(False)
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision('highest')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required for this RTX evaluation')
    sys.path.insert(0, spec['gmfss_source'])
    module = importlib.import_module('model.GMFSS_infer_b')
    if not module.HAS_CUDA:
        raise RuntimeError('CuPy CUDA softsplat unavailable; do not silently change the reference')
    setup_start = time.perf_counter()
    model = module.Model()
    model.load_model(spec['weights'], -1)
    model.eval()
    model.device()
    torch.cuda.synchronize()
    setup_ms = (time.perf_counter() - setup_start) * 1000
    w, h = spec['width'], spec['height']
    padding = (0, (-w) % 64, 0, (-h) % 64)
    # Only the previous/current source and their prepared pair stay alive.
    def source(i):
        x = torch.from_numpy(frames[i].copy()).permute(2, 0, 1).unsqueeze(0).cuda().float() / 255
        return torch.nn.functional.pad(x, padding)
    # Record actual softsplat work on the same stream used by the official kernel.
    warp = module.warp
    splats = []
    def counted_warp(*args, **kwargs):
        a, b = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        a.record(); value = warp(*args, **kwargs); b.record()
        splats.append((a, b))
        return value
    module.warp = counted_warp
    left = source(0)
    calls = []
    torch.cuda.reset_peak_memory_stats()
    for i in range(1, len(frames)):
        right = source(i)
        torch.cuda.synchronize()
        start, prepared, done = [torch.cuda.Event(enable_timing=True) for _ in range(3)]
        splats.clear()
        wall = time.perf_counter()
        start.record()
        pair = model.reuse(left, right, 1.0)
        prepared.record()
        value = model.inference(left, right, pair, 0.5)
        done.record()
        done.synchronize()
        wall_ms = (time.perf_counter() - wall) * 1000
        calls.append({'pair': i - 1, 'cold': i == 1, 'phase': 0.5,
                      'prepare_stream_ms': start.elapsed_time(prepared),
                      'synthesis_stream_ms': prepared.elapsed_time(done),
                      'complete_wall_ms': wall_ms, 'softsplat_calls': len(splats),
                      'softsplat_stream_ms': sum(a.elapsed_time(b) for a, b in splats)})
        assert len(splats) == 8
        rgb = value[0, :, :h, :w].permute(1, 2, 0).float().cpu().numpy()
        save_rgb(out, i - 1, rgb)
        del pair, value
        left = right
        print(json.dumps(calls[-1]), flush=True)
    import cupy
    return {'provider': 'official GMFSS Fortuna, eager PyTorch FP32 + CUDA CuPy softsplat',
            'torch': torch.__version__, 'cupy': cupy.__version__, 'cuda': torch.version.cuda,
            'device': torch.cuda.get_device_name(0), 'setup_ms': setup_ms, 'calls': calls,
            'peak_torch_allocated_bytes': torch.cuda.max_memory_allocated(),
            'peak_torch_reserved_bytes': torch.cuda.max_memory_reserved(),
            'memory_scope': 'PyTorch allocator only; CUDA/CuPy/driver allocations are additional',
            'outputs': len(calls), 'padding': list(padding), 'scale': 1.0,
            'precision': 'FP32, TF32 disabled; weights unmodified', 'passed': True}


def rgb_to_yuv444(rgb):
    # Canonical RGB source -> 16-bit full-range BT.709, no chroma subsampling.
    r, g, b = [rgb[..., i].astype(np.float64) for i in range(3)]
    y = .2126 * r + .7152 * g + .0722 * b
    cb = (b - y) / (2 * (1 - .0722))
    cr = (r - y) / (2 * (1 - .2126))
    return [np.clip(np.rint(x * 65535 + offset), 0, 65535).astype('<u2')
            for x, offset in ((y, 0), (cb, 32768), (cr, 32768))]


def yuv444_to_rgb(planes):
    y = planes[0].astype(np.float64) / 65535
    cb, cr = [(p.astype(np.float64) - 32768) / 65535 for p in planes[1:]]
    r = y + 2 * (1 - .2126) * cr
    b = y + 2 * (1 - .0722) * cb
    g = (y - .2126 * r - .0722 * b) / .7152
    return np.stack([r, g, b], -1).astype(np.float32)


def native(spec, out, frames, mode):
    from surface_cuda_check import Frame, Params, ptr
    cuda = C.CDLL('libcudart.so.13')
    signatures = {'cudaMalloc': ([C.POINTER(ptr), C.c_size_t], C.c_int),
                  'cudaFree': ([ptr], C.c_int),
                  'cudaMemcpy': ([ptr, ptr, C.c_size_t, C.c_int], C.c_int),
                  'cudaStreamSynchronize': ([ptr], C.c_int),
                  'cudaMemGetInfo': ([C.POINTER(C.c_size_t), C.POINTER(C.c_size_t)], C.c_int)}
    for name, (args, result) in signatures.items():
        getattr(cuda, name).argtypes = args; getattr(cuda, name).restype = result
    def ck(code):
        if code: raise RuntimeError(f'CUDA status {code}')
    lib = C.CDLL(spec['library'])
    signatures = {'aji_create': ([C.POINTER(Params)], ptr),
                  'aji_configure': ([ptr, C.c_int, C.c_int, C.c_double, ptr, ptr], C.c_int),
                  'aji_destroy': ([C.POINTER(ptr)], None), 'aji_last_error': ([ptr], C.c_char_p),
                  'aji_current_log': ([ptr], C.c_char_p),
                  'aji_infer': ([ptr, ptr, ptr, ptr], C.c_int),
                  'aji_infer_rife': ([ptr, ptr, ptr, C.c_double, ptr, ptr], C.c_int),
                  'aji_rife_begin_pair': ([ptr, C.c_uint64, C.c_uint64], None)}
    for name, (args, result) in signatures.items():
        getattr(lib, name).argtypes = args; getattr(lib, name).restype = result
    allocated = []
    def allocate(w, h):
        # AJI_FMT_YUV444P16=3, AJI_MATRIX_BT709=2, AJI_RANGE_FULL=2.
        f = Frame(width=w, height=h, format=3, matrix=2, range=2, siting=1)
        for k in range(3):
            p = ptr(); ck(cuda.cudaMalloc(C.byref(p), w * h * 2)); allocated.append(p)
            f.plane[k] = p.value; f.stride[k] = w * 2
        return f
    def upload(f, rgb):
        planes = rgb_to_yuv444(rgb)
        for k, plane in enumerate(planes):
            ck(cuda.cudaMemcpy(f.plane[k], plane.ctypes.data, plane.nbytes, 1))
    def download(f):
        planes = [np.empty((f.height, f.width), '<u2') for _ in range(3)]
        for k, plane in enumerate(planes):
            ck(cuda.cudaMemcpy(plane.ctypes.data, f.plane[k], plane.nbytes, 2))
        return yuv444_to_rgb(planes)
    p = Params(api_version=9, conf_path=os.fsencode(spec['conf']), model_dir=os.fsencode(spec['models']),
               trtexec=os.fsencode(spec.get('trtexec', '/bin/false')), slot=1,
               rife_model_dir=os.fsencode(spec['rife']), async_build=0)
    # No unexpected builder work is allowed during measured inference.
    assert any(Path(spec['rife' if mode == 'rife' else 'models']).glob('*.engine')), 'Prepare the engine before measuring'
    ck(cuda.cudaFree(None))
    free_before, total = C.c_size_t(), C.c_size_t()
    ck(cuda.cudaMemGetInfo(C.byref(free_before), C.byref(total)))
    ctx = ptr(lib.aji_create(C.byref(p)))
    assert ctx
    try:
        w, h = spec['width'], spec['height']
        ow, oh = C.c_int(), C.c_int()
        status = lib.aji_configure(ctx, w, h, spec.get('fps', 24), C.byref(ow), C.byref(oh))
        assert status == (0 if mode == 'rife' else 1), lib.aji_last_error(ctx)
        log = lib.aji_current_log(ctx).decode(); (out / 'runtime.log').write_text(log)
        a, b, result = allocate(w, h), allocate(w, h), allocate(ow.value, oh.value)
        calls = []
        if mode == 'rife': upload(a, frames[0].astype(np.float32) / 255)
        sources = range(1, len(frames)) if mode == 'rife' else range(len(spec['span_inputs']))
        for i in sources:
            rgb = frames[i].astype(np.float32) / 255 if mode == 'rife' else np.load(spec['span_inputs'][i])
            upload(b, rgb); ck(cuda.cudaStreamSynchronize(None))
            if mode == 'rife': lib.aji_rife_begin_pair(ctx, i, i + 1)
            start = time.perf_counter()
            if mode == 'rife': status = lib.aji_infer_rife(ctx, C.byref(a), C.byref(b), .5, C.byref(result), None)
            else: status = lib.aji_infer(ctx, C.byref(b), C.byref(result), None)
            ck(cuda.cudaStreamSynchronize(None))
            ms = (time.perf_counter() - start) * 1000
            assert status == 0, (status, lib.aji_last_error(ctx))
            index = i - 1 if mode == 'rife' else i
            save_rgb(out, index, download(result))
            calls.append({'pair_or_input': index, 'cold': index == 0, 'complete_wall_ms': ms})
            if mode == 'rife': a, b = b, a
            print(json.dumps(calls[-1]), flush=True)
        free_after = C.c_size_t()
        ck(cuda.cudaMemGetInfo(C.byref(free_after), C.byref(total)))
        return {'provider': 'native TensorRT Quality', 'calls': calls, 'outputs': len(calls),
                'client_allocated_bytes': (w * h * 2 * 3 * 2 + ow.value * oh.value * 2 * 3),
                'device_free_delta_bytes': free_before.value - free_after.value,
                'memory_scope': 'Global device free-memory delta after CUDA init; includes this context but may include other processes',
                'dimensions': [ow.value, oh.value], 'format': 'YUV444P16 full-range BT.709',
                'color_conversion': 'canonical RGB24 input -> 16-bit YUV444; no subsampling, <=1 RGB8 code roundtrip expected',
                'passed': True}
    finally:
        lib.aji_destroy(C.byref(ctx))
        for p in allocated: ck(cuda.cudaFree(p))


def main():
    started = time.perf_counter()
    spec = json.loads(Path(sys.argv[1]).read_text()); mode = sys.argv[2]
    assert mode in ('gmfss', 'rife', 'span')
    out = Path(spec['output']); out.mkdir(parents=True, exist_ok=True)
    receipt = out / 'summary.json'
    ident = identity(spec, mode)
    if receipt.exists():
        prior = json.loads(receipt.read_text())
        assert prior['passed'] and prior['identity'] == ident, 'Receipt belongs to different inputs/configuration'
        print('Conclusive matching receipt exists; no repeat.'); return
    frames = np.fromfile(spec['input'], np.uint8).reshape(-1, spec['height'], spec['width'], 3)
    assert len(frames) >= 2
    result = gmfss(spec, out, frames) if mode == 'gmfss' else native(spec, out, frames, mode)
    result['identity'] = ident
    result['client_sha256'] = digest(__file__)
    result['input_sources'] = len(frames)
    result['execution_wall_seconds'] = time.perf_counter() - started
    result['scope'] = 'Short exploratory comparison on one machine; not an integrated player or universal quality/FPS qualification'
    tmp = receipt.with_suffix('.tmp'); tmp.write_text(json.dumps(result, indent=2) + '\n'); tmp.replace(receipt)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
