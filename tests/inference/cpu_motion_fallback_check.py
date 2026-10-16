#!/usr/bin/env python3
"""Configure-only off/failure controls; reuse conclusive frame comparisons."""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import onnx

s = json.loads(Path(sys.argv[1]).read_text())
out = Path(s['output']); out.mkdir(parents=True, exist_ok=True)
if '--child' in sys.argv:
    class Plan(C.Structure):
        _fields_ = [(n, C.c_int) for n in ['width', 'height', 'numerator', 'denominator', 'active']]
    lib = C.CDLL(s['library']); ptr = C.c_void_p
    lib.aji_vk_create.argtypes = [C.c_char_p] * 5 + [C.c_int]; lib.aji_vk_create.restype = ptr
    lib.aji_vk_configure.argtypes = [ptr, C.c_int, C.c_int, C.c_double, C.POINTER(Plan)]
    lib.aji_vk_error.argtypes = [ptr]; lib.aji_vk_error.restype = C.c_char_p
    lib.aji_vk_stats_snapshot.argtypes = [ptr]; lib.aji_vk_stats_snapshot.restype = C.c_char_p
    lib.aji_vk_destroy.argtypes = [ptr]
    ctx = lib.aji_vk_create(os.fsencode(s['conf']), os.fsencode(s['models']), os.fsencode(s['rife']), b'cpu+cpu', None, 1)
    assert ctx
    try:
        plan = Plan()
        assert lib.aji_vk_configure(ctx, 256, 72, 24, C.byref(plan)) == 0, lib.aji_vk_error(ctx)
        assert (plan.width, plan.height, plan.numerator, plan.denominator) == (512, 144, 2, 1)
        stats = lib.aji_vk_stats_snapshot(ctx).decode()
        assert 'motion applied to the upscaled pictures:' in stats, stats
    finally:
        lib.aji_vk_destroy(ctx)
    sys.exit()
receipt = out / 'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed']
    print('Conclusive receipt exists; no repeat.'); sys.exit()
rows = []
for name, flag, fail, ref_key, expected in [
    ('off', '0', False, 'reference_activation_on', 378),
    ('compile-fallback', '1', True, 'reference_activation_off', 484),
]:
    folder = out / name; folder.mkdir(exist_ok=True)
    capture = folder / 'capture'; capture.mkdir(exist_ok=True)
    spec = dict(s, output=str(folder)); path = folder / 'spec.json'
    path.write_text(json.dumps(spec, indent=2) + '\n')
    env = dict(os.environ, AJI_ORT_PROVIDER='cpu', AJI_ORT_CPU_ACTIVATIONS='1',
               AJI_ORT_CPU_MOTION_ONLY=flag, AJI_ORT_SPECIALIZE_SHAPES='1', AJI_ORT_RIFE_OPT='3',
               AJI_TEST_ORT_LIBRARY=s['ort_runtime'], AJI_TEST_ORT_CAPTURE=str(capture),
               LD_LIBRARY_PATH=s['runtime'], LD_PRELOAD=s['interposer'])
    env.pop('AJI_TEST_ORT_PROFILE_ALL', None)
    env.pop('AJI_TEST_ORT_ACTIVATION_COMPILE_FAIL', None)
    if fail: env['AJI_TEST_ORT_ACTIVATION_COMPILE_FAIL'] = '1'
    with (folder / 'run.log').open('w') as log:
        p = subprocess.run([sys.executable, __file__, str(path), '--child'], env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=30)
    assert p.returncode == 0, (folder / 'run.log').read_text()[-2500:]
    model = onnx.load(capture / 'input-2.onnx', load_external_data=False)
    reference = onnx.load(Path(s[ref_key]) / 'input-2.onnx', load_external_data=False)
    assert model.SerializeToString() == reference.SerializeToString()
    optimized = onnx.load(capture / 'optimized-2.onnx', load_external_data=False)
    assert len(optimized.graph.node) == expected and len(optimized.graph.output) == 3
    if fail:
        assert 'CPU motion compile failed; keeping reference graph' in (folder / 'run.log').read_text()
    rows.append(dict(case=name, reference_graph_restored=True, interpolation_active=True,
                     outputs=3, nodes=expected))
receipt.write_text(json.dumps(dict(passed=True, results=rows), indent=2) + '\n')
print(receipt.read_text())
