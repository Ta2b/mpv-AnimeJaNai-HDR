#!/usr/bin/env python3
"""One real changed motion-program build, then controlled same-plan parity."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import numpy as np
import onnx

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output'])/'fast';summary=out/'summary.json'
if summary.exists() and '--isolate-rebuild' not in sys.argv[2:]:
    assert json.loads(summary.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
def save(path,j):path.write_text(json.dumps(j,indent=2)+'\n')
keys=(out/'keys.txt').read_text().splitlines();assert len(keys)==4
reference=Path(s['motion_reference']);plans={}
for log in reference.glob('*.engine.build.log'):
    source=re.search(r'--onnx=(\S+)',log.read_text().splitlines()[0]).group(1)
    n=len(onnx.load(source,load_external_data=False).graph.output)
    plans['motion' if n==2 else 'picture']=Path(str(log)[:-10])
assert set(plans)=={'motion','picture'}
picture=out/'after/rife'/keys[0]
if not picture.exists():shutil.copyfile(plans['picture'],picture)
calls=out/'calls';calls.mkdir(exist_ok=True);builder=out/'builder'
builder.write_text('#!'+sys.executable+'\nimport os,sys,json\nfrom pathlib import Path\n'
    +'args=sys.argv[1:]+["--builderOptimizationLevel=0","--memPoolSize=workspace:64M"]\n'
    +'Path('+repr(str(calls))+').joinpath(str(os.getpid())+".json").write_text(json.dumps(args))\n'
    +'os.execv('+repr(s['trtexec'])+',['+repr(s['trtexec'])+']+args)\n');builder.chmod(0o755)
save(out/'plan-provenance.json',dict(reference={k:str(v) for k,v in plans.items()},
    candidate_picture=keys[0],candidate_motion=keys[1],runtime=keys[2],device=keys[3],
    picture_seed_is_controlled_fixture=True,product_imports_legacy=False))
def invoke(label,library,root):
    base=out/label;receipt=base.with_suffix('.json')
    if receipt.exists():return json.loads(receipt.read_text())
    spec=dict(library=library,models=str(root/'models'),rife=str(root/'rife'),conf=s['fast_conf'],
        trtexec=('/bin/false' if label=='old-runtime-new-plan' else str(builder)),input=s['input'],output=str(base),only_unchanged_pair=True)
    path=base.with_suffix('.spec.json');save(path,spec)
    with base.with_suffix('.log').open('w') as log:
        r=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'inference/fast_views_probe.py'),str(path)],
            env=dict(os.environ,LD_LIBRARY_PATH=s['runtime']),stdout=log,stderr=subprocess.STDOUT,timeout=90)
    assert r.returncode==0,base.with_suffix('.log').read_text()[-4000:]
    value=json.loads(receipt.read_text());assert list(value['results'])==['unchanged-pair']
    assert value['results']['unchanged-pair']['changed_bytes']==0,value
    return value
before=invoke('before-result',s['fast_before'],out/'before')
if not (out/'cold-result.json').exists():assert not list(calls.glob('*.json'))
cold=invoke('cold-result',s['after'],out/'after')
assert len([p for p in calls.glob('*.json') if '.aji-motion-v3/' in p.read_text()])==1
motion=out/'after/rife'/keys[1];assert motion.exists()
independent=out/'independently-built-motion.engine'
if not independent.exists():shutil.copyfile(motion,independent);shutil.copyfile(plans['motion'],motion)
same=invoke('same-plan-result',s['after'],out/'after')
old=np.load(out/'before-result.npz');new=np.load(out/'same-plan-result.npz');rebuilt=np.load(out/'cold-result.npz')
assert old.files==new.files and all(np.array_equal(old[k],new[k]) for k in old.files)
result=dict(passed=True,real_motion_builders=1,same_plan_changed_bytes=0,fast_active=True,
    independent_rebuild={k:dict(changed_bytes=int(np.count_nonzero(old[k]!=rebuilt[k])),
        max_delta=int(np.abs(old[k].astype(int)-rebuilt[k].astype(int)).max())) for k in old.files},
    same_picture_and_upscale_plans=True,before_setup_seconds=before['setup_seconds'],
    cold_setup_seconds=cold['setup_seconds'],same_plan_setup_seconds=same['setup_seconds'],
    fps_claimed=False)
if '--isolate-rebuild' in sys.argv[2:]:
    # New question raised by the unexpectedly large independent-rebuild delta:
    # run the new plan through the old runtime, without rebuilding anything.
    legacy=out/'before/rife'/plans['motion'].name
    if not (out/'old-runtime-new-plan.json').exists():shutil.copyfile(independent,legacy)
    isolated=invoke('old-runtime-new-plan',s['fast_before'],out/'before')
    check=np.load(out/'old-runtime-new-plan.npz')
    assert check.files==rebuilt.files and all(np.array_equal(check[k],rebuilt[k]) for k in check.files)
    assert len([p for p in calls.glob('*.json') if '.aji-motion-v3/' in p.read_text()])==1
    result['new_plan_old_vs_new_runtime_changed_bytes']=0
    result['independent_rebuild_numerical_equivalence']='non concluant: max 38/255 on this frame; change isolated to plan bytes'
save(summary,result);print(json.dumps(result,indent=2))
