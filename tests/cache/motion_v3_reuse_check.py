#!/usr/bin/env python3
"""The hardened motion exporter must preserve a fully matching ordinary v3 TensorRT plan."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output'])/'preserve-v3';out.mkdir(exist_ok=True)
summary=out/'summary.json'
if summary.exists():
    assert json.loads(summary.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
models=out/'models';models.mkdir(exist_ok=True);rife=out/'rife';rife.mkdir(exist_ok=True)
shutil.copyfile(s['model'],models/Path(s['model']).name);shutil.copyfile(s['rife'],rife/Path(s['rife']).name)
q=subprocess.run([s['v3_keys'],s['rife'],str(out/'key-cache'),'11.3.0-headers-build99'],
    env=dict(os.environ,LD_LIBRARY_PATH=s['runtime']),text=True,capture_output=True,check=True,timeout=15)
keys=q.stdout.strip().splitlines();assert len(keys)==4
(out/'keys.txt').write_text(q.stdout)
old=json.loads((Path(s['output'])/'fast/plan-provenance.json').read_text())['reference']
# Fixture seeding only: all plans were compiled from these exact ONNX bytes,
# settings, same TRT/CUDA/GPU. The product never imports an unkeyed/v2 plan.
for kind,key in zip(['picture','motion'],keys):shutil.copyfile(old[kind],rife/key)
for plan in (Path(s['output'])/'fast/after/models').glob('aji-v3-*.engine'):shutil.copyfile(plan,models/plan.name)
initial={str(p.relative_to(out)):p.read_bytes() for folder in [models,rife] for p in folder.glob('*.engine')}
def invoke(label,library):
    receipt=out/(label+'.json')
    if receipt.exists():return json.loads(receipt.read_text())
    spec=dict(library=library,models=str(models),rife=str(rife),conf=s['fast_conf'],trtexec='/bin/false',
        input=s['input'],output=str(out/label),only_unchanged_pair=True)
    path=out/(label+'.spec.json');path.write_text(json.dumps(spec,indent=2)+'\n')
    with (out/(label+'.log')).open('w') as log:
        p=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'inference/fast_views_probe.py'),str(path)],
            env=dict(os.environ,LD_LIBRARY_PATH=s['runtime']),stdout=log,stderr=subprocess.STDOUT,timeout=30)
    assert p.returncode==0,(out/(label+'.log')).read_text()[-3000:]
    j=json.loads(receipt.read_text());assert j['results']['unchanged-pair']['changed_bytes']==0
    return j
before=invoke('before',s['v3_before']);after=invoke('after',s['after'])
a=np.load(out/'before.npz');b=np.load(out/'after.npz');assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
assert initial=={str(p.relative_to(out)):p.read_bytes() for folder in [models,rife] for p in folder.glob('*.engine')}
assert list((rife/'.aji-motion-v3').glob('*/model.onnx')),'Hardened export must actually be produced'
result=dict(passed=True,same_v3_plan_keys=True,engine_bytes_unchanged=True,builders=0,
    same_plan_changed_bytes=0,before_setup_seconds=before['setup_seconds'],after_setup_seconds=after['setup_seconds'],
    hardened_export_produced=True,v2_plan_imported_by_product=False,controlled_plan_fixture=True,
    recipe_converter_version=1,engine_converter_version=1,engine_source_scheme='onnx-source-v2',
    independent_rebuild_equivalence='non concluant; not forced by this change',fps_claimed=False)
summary.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
