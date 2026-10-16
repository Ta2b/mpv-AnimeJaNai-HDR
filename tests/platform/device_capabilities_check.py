#!/usr/bin/env python3
"""Targeted optional-module probe checks. No neural inference or repeated FPS runs."""
import ctypes as C
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

s = json.loads(Path(sys.argv[1]).read_text())
out = Path(s['output']); out.mkdir(parents=True, exist_ok=True)
receipt = out / 'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed']
    print('Conclusive receipt exists; no repeat.'); sys.exit()

def cli(name, root, *args):
    with (out / (name + '.log')).open('w') as log:
        p = subprocess.run([s['dotnet'], s['platform'], '--device-capabilities', '--root', str(root), *args],
                           stdout=subprocess.PIPE, stderr=log, check=True, timeout=30)
    value = json.loads(p.stdout)
    (out / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
    return value

def fixture(name, cpu=None, cuda=None):
    root = out / name
    lib = root / 'animejanai/inference'; lib.mkdir(parents=True)
    for source, dest in [(cpu, 'libaji_ort.so'), (cuda, 'libaji_trt.so')]:
        if source: shutil.copyfile(source, lib / dest)
    return root

# The successful available-device report is already acquired once. Reuse it.
actual = json.loads(Path(s['actual_report']).read_text())
assert actual['ort_cpu']['evidence']['compatible_conversion']
gpu = actual['tensorrt_cuda']['evidence']
assert gpu['compatible_kernel'] and gpu['device_name'] == s['device_name']
assert gpu['compute_capability'] == s['compute_capability']

legacy = cli('legacy', fixture('legacy-fixture', s['legacy_cpu'], s['legacy_cuda']))
assert all(legacy[k]['state'] == 'probe-unavailable' for k in ['ort_cpu', 'tensorrt_cuda'])
missing = cli('missing', fixture('missing-fixture'))
assert all(missing[k]['state'] == 'absent' for k in ['ort_cpu', 'tensorrt_cuda'])
broken = fixture('broken-fixture')
(broken / 'animejanai/inference/libaji_trt.so').write_bytes(b'not an ELF module')
assert cli('broken', broken)['tensorrt_cuda']['state'] == 'load-failed'
invalid = cli('invalid-device', fixture('invalid-fixture', cuda=s['cuda']), '--cuda-device', '65535')
e = invalid['tensorrt_cuda']['evidence']
assert not e['compatible_kernel'] and e['status'] < 0 and e['driver_error'] != 0
assert e['compute_capability'] is None and e['integrated'] is None

libraries = [C.CDLL(s[k]) for k in ['cpu', 'cuda']]
for library, symbol, gpu_probe in [(libraries[0], 'aji_ort_probe_v1', False), (libraries[1], 'aji_trt_probe_v1', True)]:
    fn = getattr(library, symbol)
    fn.argtypes = ([C.c_int] if gpu_probe else []) + [C.c_void_p, C.c_size_t]
    guard = C.create_string_buffer(b'untouched')
    prefix = [0] if gpu_probe else []
    assert fn(*prefix, guard, 1) < 0 and guard.value == b'untouched'
    assert fn(*prefix, None, 0) < 0

# Exercise the lifetime contract in a different caller context, rather than
# repeating the already conclusive default-context compatibility case.
driver = C.CDLL('libcuda.so.1')
driver.cuCtxCreate_v2.argtypes = [C.POINTER(C.c_void_p), C.c_uint, C.c_int]
driver.cuCtxGetCurrent.argtypes = [C.POINTER(C.c_void_p)]
driver.cuCtxDestroy_v2.argtypes = [C.c_void_p]
assert driver.cuInit(0) == 0
prior = C.c_void_p(); assert driver.cuCtxGetCurrent(C.byref(prior)) == 0
caller = C.c_void_p(); assert driver.cuCtxCreate_v2(C.byref(caller), 0, 0) == 0
try:
    raw = C.create_string_buffer(468)
    assert libraries[1].aji_trt_probe_v1(0, raw, len(raw)) == 0
    now = C.c_void_p(); assert driver.cuCtxGetCurrent(C.byref(now)) == 0
    assert now.value == caller.value
finally:
    assert driver.cuCtxDestroy_v2(caller) == 0
restored = C.c_void_p(); assert driver.cuCtxGetCurrent(C.byref(restored)) == 0
assert restored.value == prior.value
result = dict(passed=True, legacy_modules_unknown=True, missing_modules_explicit=True,
              load_error_explicit=True, invalid_device_unknown=True, short_null_outputs_safe=True,
              caller_cuda_context_preserved=True, cpu_conversion=True, shipped_cuda_kernel=True,
              models_executed=False, quality_claim=False, fps_claim=False)
receipt.write_text(json.dumps(result, indent=2) + '\n'); print(receipt.read_text())
