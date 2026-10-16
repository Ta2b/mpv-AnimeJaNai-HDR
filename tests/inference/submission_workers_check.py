#!/usr/bin/env python3
"""Targeted real CPU parity and measured pthread-creation benefit; no timing reruns."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
for folder,model in [('models',s['model']),('rife',s['rife_model'])]:
    p=out/folder;p.mkdir(exist_ok=True);shutil.copyfile(model,p/Path(model).name)
conf=out/'quality.conf';conf.write_text('[global]\nbackend=CPU\nrife_engine=quality\nrife_drawings=no\nengine_reuse=off\nengine_boost=no\n[slot_1]\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_before_upscale=yes\nchain_1_rife_factor_numerator=2\nchain_1_rife_factor_denominator=1\nchain_1_rife_scene_detect_threshold=0\nchain_1_model_1_name='+Path(s['model']).stem+'\n')
if s.get('fast_tiled'):conf.write_text(conf.read_text().replace('rife_engine=quality','rife_engine=fast\nengine_tiles=2x1'))
rows={}
for label in ['before','after']:
    result=out/(label+'.json')
    if not result.exists():
        spec=dict(library=s[label],conf=str(conf),models=str(out/'models'),rife=str(out/'rife'),output=str(out/label),
            ort_runtime=s['ort_runtime'],device='cpu+cpu' if s.get('fast_tiled') else 'cpu',fast_tiled=s.get('fast_tiled',False),width=s.get('width',128))
        path=out/(label+'.spec.json');path.write_text(json.dumps(spec,indent=2)+'\n')
        with (out/(label+'.log')).open('w') as log:
            p=subprocess.run([sys.executable,str(Path(__file__).with_name('submission_workers_probe.py')),str(path)],
                env=dict(os.environ,AJI_ORT_PROVIDER='cpu',AJI_ORT_CACHE=str(out/(label+'-cache')),
                    LD_LIBRARY_PATH=s['runtime'],LD_PRELOAD=s['interposer'],OPENBLAS_NUM_THREADS='2'),
                stdout=log,stderr=subprocess.STDOUT,timeout=90)
        assert p.returncode==0,(out/(label+'.log')).read_text()[-3500:]
    rows[label]=json.loads(result.read_text())
a=np.load(out/'before.npz');b=np.load(out/'after.npz')
assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
expected=4 if s.get('fast_tiled') and s.get('width',128)>=224 else 2
assert rows['before']['thread_creations_during_measured_pairs']==expected,rows
assert rows['after']['thread_creations_during_measured_pairs']==0,rows
summary=dict(passed=True,outputs=len(a.files),changed_bytes=0,measured_pair_thread_creations_before=expected,
    measured_pair_thread_creations_after=0,reference=rows['before'],candidate=rows['after'],
    usefulness='Per-pair pthread creation removed; bounded persistent submission lane',
    timing_benefit='non concluant: short observation and desktop/power state not controlled',fps_claimed=False)
receipt.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
