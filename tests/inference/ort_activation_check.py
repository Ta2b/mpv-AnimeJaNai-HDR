#!/usr/bin/env python3
"""Native LeakyRelu graph prototype; measure and retain failures without any product activation."""
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
if s.get('reuse_reference'):
    reference=Path(s['reuse_reference'])
    reference_label=s.get('reference_label','before')
    assert json.loads((reference/(reference_label+'.json')).read_text())['real_ort_cpu']
    for p in reference.glob(reference_label+'.*'):
        dest=out/('before'+p.name[len(reference_label):])
        assert not dest.exists();shutil.copyfile(p,dest)
    shutil.copytree(reference/(reference_label+'-capture'),out/'before-capture')
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
        rife_dir=out/(label+'-rife');rife_dir.mkdir(exist_ok=True)
        shutil.copyfile(s['rife_model'] if label=='before' else s['candidate_rife'],rife_dir/Path(s['rife_model']).name)
        spec = dict(library=s['library'], conf=str(conf), models=str(out / 'models'), rife=str(rife_dir),
            output=str(out / label), ort_runtime=s['ort_runtime'], device='cpu+cpu' if s.get('fast') else 'cpu',
            fast_tiled=s.get('fast', False), width=256 if s.get('fast') else 128)
        capture=out/(label+'-capture');capture.mkdir(exist_ok=True)
        path = out / (label + '.spec.json'); path.write_text(json.dumps(spec, indent=2) + '\n')
        with (out / (label + '.log')).open('w') as log:
            probe='ort_cpu_layout_probe.py' if s.get('profile',True) else 'ort_buffers_probe.py'
            p = subprocess.run([sys.executable, str(Path(__file__).with_name(probe)), str(path)],
                env=dict(os.environ, AJI_ORT_PROVIDER='cpu', AJI_ORT_REUSE_BINDINGS='1', AJI_ORT_SPECIALIZE_SHAPES='1', AJI_ORT_OPT='3', AJI_ORT_SPAN_OPT='3', AJI_ORT_RIFE_OPT='3', AJI_RIFE_PROFILE='1' if s.get('profile',True) else '0', AJI_TEST_ORT_CAPTURE=str(capture),
                    AJI_ORT_CACHE=str(out / (label + '-cache')), AJI_TEST_ORT_LIBRARY=s['ort_runtime'],
                    LD_LIBRARY_PATH=s['runtime'], LD_PRELOAD=s['interposer'], OPENBLAS_NUM_THREADS='2',
                    AJI_TEST_ORT_RIFE_DISABLE=s.get('disabled_rife_optimizers',''),
                    AJI_TEST_ORT_OP_LIBRARY=s.get('custom_op_library','')),
                stdout=log, stderr=subprocess.STDOUT, timeout=90)
        assert p.returncode == 0, (out / (label + '.log')).read_text()[-3500:]
    rows[label] = json.loads(result.read_text())
a = np.load(out / 'before.npz'); b = np.load(out / 'after.npz')
assert a.files == b.files
changed={k:dict(bytes=int(np.count_nonzero(a[k]!=b[k])),maximum_error=int(np.abs(a[k].astype(np.int16)-b[k].astype(np.int16)).max())) for k in a.files}
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
for before,after in zip(captures['before'],captures['after']):
    assert all(int(v)>0 for v in after['compiled_shape'].split())
    if after['input_shape'][1]==11:
        assert before['compiled_shape']==after['compiled_shape']
        pass # record the actual graph rather than assuming a successful fusion
    else:
        assert before==after,('SPAN must remain unchanged',before,after)
total_changed=sum(v['bytes'] for v in changed.values())
summary=dict(passed=True,experiment_completed=True,pixels_exact=total_changed==0,outputs=len(a.files),changed_bytes=total_changed,quality=changed,
    before=rows['before'],after=rows['after'],captures=captures,
    decision='prototype only; no product change; decide from fidelity, actual graph and timings',
    timing_benefit='short controlled treatment; desktop/power state not measured, no universal FPS claim',fps_claimed=False)
receipt.write_text(json.dumps(summary, indent=2) + '\n'); print(json.dumps(summary, indent=2))
