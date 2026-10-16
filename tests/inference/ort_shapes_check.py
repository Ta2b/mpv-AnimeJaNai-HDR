#!/usr/bin/env python3
"""Specialization off/on; completed pixel parity and independently captured compiler input/optimized graph."""
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
        capture=out/(label+'-capture');capture.mkdir(exist_ok=True)
        path = out / (label + '.spec.json'); path.write_text(json.dumps(spec, indent=2) + '\n')
        with (out / (label + '.log')).open('w') as log:
            p = subprocess.run([sys.executable, str(Path(__file__).with_name('ort_buffers_probe.py')), str(path)],
                env=dict(os.environ, AJI_ORT_PROVIDER='cpu', AJI_ORT_REUSE_BINDINGS='1', AJI_ORT_SPECIALIZE_SHAPES=enabled, AJI_TEST_ORT_CAPTURE=str(capture),
                    AJI_ORT_CACHE=str(out / (label + '-cache')), AJI_TEST_ORT_LIBRARY=s['ort_runtime'],
                    LD_LIBRARY_PATH=s['runtime'], LD_PRELOAD=s['interposer'], OPENBLAS_NUM_THREADS='2'),
                stdout=log, stderr=subprocess.STDOUT, timeout=90)
        assert p.returncode == 0, (out / (label + '.log')).read_text()[-3500:]
    rows[label] = json.loads(result.read_text())
a = np.load(out / 'before.npz'); b = np.load(out / 'after.npz')
assert a.files == b.files and all(np.array_equal(a[k], b[k]) for k in a.files)
# Captures are made by the C API shim at actual session construction, not by production counters.
import onnx
from collections import Counter
captures={}
for treatment in ['before','after']:
    entries=[]
    for raw_path in sorted((out/(treatment+'-capture')).glob('input-*.onnx')):
        index=raw_path.stem.split('-')[-1]
        raw=onnx.load(raw_path,load_external_data=False)
        optimized=onnx.load(raw_path.with_name('optimized-'+index+'.onnx'),load_external_data=False)
        metadata=list(optimized.graph.input)+list(optimized.graph.output)
        free_dims=sum(not d.HasField('dim_value') or d.dim_value<=0 for v in metadata for d in v.type.tensor_type.shape.dim)
        entries.append(dict(input_shape=[d.dim_value if d.HasField('dim_value') else d.dim_param for d in raw.graph.input[0].type.tensor_type.shape.dim],
            compiled_shape=raw_path.with_name('shapes-'+index+'.txt').read_text().strip(),
            free_input_output_dimensions=free_dims,nodes=len(optimized.graph.node),operators=dict(Counter(n.op_type for n in optimized.graph.node))))
    captures[treatment]=entries
assert len(captures['before'])==len(captures['after'])==(6 if s.get('fast') else 4),captures
for before_path in sorted((out/'before-capture').glob('input-*.onnx')):
    a_model=onnx.load(before_path,load_external_data=False)
    b_model=onnx.load(out/'after-capture'/before_path.name,load_external_data=False)
    # Replacing only the input shape must restore the entire original model.
    b_model.graph.input[0].type.tensor_type.shape.CopyFrom(a_model.graph.input[0].type.tensor_type.shape)
    assert a_model.SerializeToString()==b_model.SerializeToString()
for before,after in zip(captures['before'],captures['after']):
    assert all(int(v)>0 for v in after['compiled_shape'].split())
    if after['input_shape'][1]==11:
        assert '-1' in before['compiled_shape'] and '-1' not in after['compiled_shape']
        assert before['free_input_output_dimensions']>0 and after['free_input_output_dimensions']==0,(before,after)
summary=dict(passed=True,outputs=len(a.files),changed_bytes=0,before=rows['before'],after=rows['after'],captures=captures,
    usefulness='Anonymous RIFE input and inferred output dimensions fixed before compilation; static contract prerequisite',
    timing_benefit='non concluant: short observation and desktop/power state not controlled',fps_claimed=False)
receipt.write_text(json.dumps(summary, indent=2) + '\n'); print(json.dumps(summary, indent=2))
