#!/usr/bin/env python3
"""Short v2/v3 migration checks, with a receipt for each completed invocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('spec',type=Path);p.add_argument('--phase',choices=['flow','gpu'],required=True)
a=p.parse_args();s=json.loads(a.spec.read_text());out=Path(s['output'])
summary=out/(a.phase+'-summary.json')
if summary.exists():
    assert json.loads(summary.read_text())['passed'];print('Conclusive receipt already exists; no repeat.');sys.exit()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
records=[]
if a.phase=='flow':
    cache=out/'flow-cache';cache.mkdir(exist_ok=True)
    def flow(label,exe):
        result=out/('flow-'+label+'.json')
        if result.exists():return Path(json.loads(result.read_text())['path'])
        t=time.perf_counter();r=subprocess.run([exe,s['rife'],str(cache)],text=True,capture_output=True,timeout=15)
        save(result,dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,seconds=time.perf_counter()-t,path=r.stdout.strip()))
        assert r.returncode==0,r.stderr
        return Path(r.stdout.strip())
    before=flow('before',s['flow_before']);before_hash=sha(before)
    after=flow('after',s['flow_after']);stamp=(after.stat().st_ino,after.stat().st_mtime_ns)
    warm=flow('warm',s['flow_after'])
    assert before!=after and before_hash==sha(after) and sha(before)==before_hash
    assert 'rife-flow-v2' in str(before) and 'rife-flow-v3' in str(after)
    assert warm==after and stamp==(warm.stat().st_ino,warm.stat().st_mtime_ns)
    result=dict(passed=True,legacy_preserved=True,flow_graph_changed_bytes=0,warm_rewrites=0,
                source_sha256=sha(Path(s['rife'])),native_gpu_provider_qualified=False)
else:
    case=out/'gpu';case.mkdir(exist_ok=True);models=case/'models';models.mkdir(exist_ok=True)
    shutil.copyfile(s['model'],models/Path(s['model']).name)
    reference=Path(s['warm_models'])/s['warm_plan'];old=models/reference.name
    if not old.exists():shutil.copyfile(reference,old)
    old_hash=sha(old);assert old_hash==sha(reference)
    calls=case/'calls';calls.mkdir(exist_ok=True);builder=case/'builder'
    builder.write_text('#!'+sys.executable+'\nimport os,sys,json\nfrom pathlib import Path\n'
        +'Path('+repr(str(calls))+').joinpath(str(os.getpid())+".json").write_text(json.dumps(sys.argv[1:]))\n'
        +'os.execv('+repr(s['trtexec'])+',['+repr(s['trtexec'])+']+sys.argv[1:])\n');builder.chmod(0o755)
    def invoke(label,library):
        base=case/label;receipt=base.with_suffix('.json')
        if receipt.exists():
            assert json.loads(base.with_suffix('.process.json').read_text())['library_sha256']==sha(Path(library))
            return json.loads(receipt.read_text())
        start=base.with_suffix('.start');start.touch()
        spec=dict(library=library,models=str(models),conf=s['conf'],trtexec=str(builder),input=s['input'],output=str(base),start=str(start))
        path=base.with_suffix('.spec.json');save(path,spec)
        t=time.perf_counter()
        with base.with_suffix('.log').open('w') as log:
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('key_lock_gpu_worker.py')),str(path)],
                env=dict(os.environ,LD_LIBRARY_PATH=s['runtime']),stdout=log,stderr=subprocess.STDOUT,timeout=30)
        save(base.with_suffix('.process.json'),dict(returncode=r.returncode,seconds=time.perf_counter()-t,library_sha256=sha(Path(library))))
        assert r.returncode==0,base.with_suffix('.log').read_text()[-3000:]
        value=json.loads(receipt.read_text());assert value['active_status']==1,value
        return value
    before=invoke('before',s['before'])
    if not (case/'cold.json').exists():assert not list(calls.glob('*.json'))
    cold=invoke('cold',s['after']);new=list(models.glob('aji-v3-*.engine'))
    assert len(new)==1 and len(list(calls.glob('*.json')))==1 and sha(old)==old_hash
    new=new[0];stamp=(new.stat().st_ino,new.stat().st_mtime_ns)
    warm=invoke('warm',s['after'])
    assert stamp==(new.stat().st_ino,new.stat().st_mtime_ns) and len(list(calls.glob('*.json')))==1
    baseline=np.load(case/'before.npy');rebuilt=np.load(case/'cold.npy')
    assert np.array_equal(rebuilt,np.load(case/'warm.npy'))
    # Controlled arithmetic comparison: same trusted reference plan bytes,
    # deliberately copied only in this fixture, never imported by the product.
    if not (case/'independently-built.engine').exists():
        shutil.copyfile(new,case/'independently-built.engine');shutil.copyfile(old,new)
    same=invoke('same-plan',s['after']);candidate=np.load(case/'same-plan.npy')
    assert np.array_equal(baseline,candidate) and sha(old)==old_hash
    result=dict(passed=True,legacy_preserved=True,cold_builders=1,warm_builders=0,warm_changed_bytes=0,
        independent_rebuild_changed_bytes=int(np.count_nonzero(baseline!=rebuilt)),
        independent_rebuild_max_u8_delta=int(np.abs(baseline.astype(int)-rebuilt.astype(int)).max()),
        same_plan_changed_bytes=0,before=before,cold=cold,warm=warm,same_plan=same,
        candidate_sha256=sha(Path(s['after'])),source_sha256=sha(Path(s['model'])))
save(summary,result);print(json.dumps(result,indent=2))
