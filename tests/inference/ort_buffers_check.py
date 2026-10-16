#!/usr/bin/env python3
"""Off/on in the same binary; compare completed pixels and real application ORT API calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

s = json.loads(Path(sys.argv[1]).read_text())
out = Path(s['output']); out.mkdir(parents=True, exist_ok=True)
receipt = out / 'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed']
    print('Conclusive receipt exists; no repeat.'); sys.exit()
for folder, model in [('models', s['model']), ('rife', s['rife_model'])]:
    p = out / folder; p.mkdir(exist_ok=True); shutil.copyfile(model, p / Path(model).name)
conf = out / 'quality.conf'
conf.write_text('[global]\nbackend=CPU\nrife_engine=' + ('fast\nengine_tiles=2x1' if s.get('fast') else 'quality') +
    '\nrife_drawings=no\nengine_reuse=off\nengine_boost=no\n[slot_1]\nchain_1_rife=yes\nchain_1_rife_model=426\n'
    'chain_1_rife_before_upscale=yes\nchain_1_rife_factor_numerator=2\nchain_1_rife_factor_denominator=1\n'
    'chain_1_rife_scene_detect_threshold=0\nchain_1_model_1_name=' + Path(s['model']).stem + '\n')
rows = {}
for label, enabled in [('before', '0'), ('after', '1')]:
    result = out / (label + '.json')
    if not result.exists():
        spec = dict(library=s['library'], conf=str(conf), models=str(out / 'models'), rife=str(out / 'rife'),
            output=str(out / label), ort_runtime=s['ort_runtime'], device='cpu+cpu' if s.get('fast') else 'cpu',
            fast_tiled=s.get('fast', False), width=256 if s.get('fast') else 128)
        path = out / (label + '.spec.json'); path.write_text(json.dumps(spec, indent=2) + '\n')
        with (out / (label + '.log')).open('w') as log:
            p = subprocess.run([sys.executable, str(Path(__file__).with_name('ort_buffers_probe.py')), str(path)],
                env=dict(os.environ, AJI_ORT_PROVIDER='cpu', AJI_ORT_REUSE_BINDINGS=enabled,
                    AJI_ORT_CACHE=str(out / (label + '-cache')), AJI_TEST_ORT_LIBRARY=s['ort_runtime'],
                    LD_LIBRARY_PATH=s['runtime'], LD_PRELOAD=s['interposer'], OPENBLAS_NUM_THREADS='2'),
                stdout=log, stderr=subprocess.STDOUT, timeout=90)
        assert p.returncode == 0, (out / (label + '.log')).read_text()[-3500:]
    rows[label] = json.loads(result.read_text())
a = np.load(out / 'before.npz'); b = np.load(out / 'after.npz')
assert a.files == b.files and all(np.array_equal(a[k], b[k]) for k in a.files)
before, after = (rows[k]['ort_api_calls'] for k in ['before', 'after'])
assert before['runs'] == after['runs'] and before['runs'] > 0
for key in ['cpu_memory_descriptors', 'tensor_descriptors', 'owned_shape_handles', 'null_output_requests']:
    assert before[key] > 0 and after[key] == 0, (key, rows)
assert before['borrowed_shape_queries'] == 0 and after['borrowed_shape_queries'] > 0
summary = dict(passed=True, outputs=len(a.files), changed_bytes=0, before=rows['before'], after=rows['after'],
    usefulness='Repeated application ORT descriptor/metadata creation and null-output requests removed',
    internal_ort_heap_allocations='not measured; no zero-allocation claim',
    timing_benefit='non concluant: short observation and desktop/power state not controlled', fps_claimed=False)
receipt.write_text(json.dumps(summary, indent=2) + '\n'); print(json.dumps(summary, indent=2))
