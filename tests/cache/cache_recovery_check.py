#!/usr/bin/env python3
"""Stop only owned fixtures at a partial write, then test the next request."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path)
p.add_argument('--phase',choices=['portable','gpu','motion','collision'],required=True);a=p.parse_args()
s=json.loads(a.spec.read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True);records=[]
def write(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def until(test,process=None,seconds=30):
    deadline=time.monotonic()+seconds
    while not test():
        assert process is None or process.poll() is None,'fixture exited before checkpoint'
        assert time.monotonic()<deadline,'checkpoint timeout'
        time.sleep(.005)
def protected(parent,prefix):
    unknown=parent/(prefix+'user-preserve');unknown.mkdir(parents=True);(unknown/'keep').write_bytes(b'USER')
    other=parent/(prefix+'other-key');other.mkdir();(other/'.aji-stage-owner').write_text('aji-stage-owner-v1\nother-key\n');(other/'keep').write_bytes(b'OTHER')
    return unknown,other
def check_protected(paths):
    assert [p.joinpath('keep').read_bytes() for p in paths]==[b'USER',b'OTHER']
def interrupted_env(root,name,ready):
    return dict(os.environ,LD_PRELOAD=s['interposer'],AJI_INTERRUPT_ROOT=str(root),
                AJI_INTERRUPT_FILE=name,AJI_INTERRUPT_READY=str(ready))
def run(command,env=None):
    r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
    assert r.returncode==0,r.stderr[-2000:]
    return r.stdout.strip()

if a.phase=='collision':
    import onnx
    case=out/'metadata-collision';case.mkdir();source=case/'rife.onnx'
    model=onnx.load(s['rife'])
    onnx.save_model(model,str(source),save_as_external_data=True,all_tensors_to_one_file=True,
                    location='.aji-stage-owner',size_threshold=0)
    weight=case/'.aji-stage-owner';original=weight.read_bytes();assert original
    for kind in ['flow','model']:
        products=[]
        for label in ['before','after']:
            cache=case/(kind+'-'+label);cache.mkdir()
            command=[s['flow_'+label],str(source),str(cache)] if kind=='flow' else [s['model_'+label],'freeze',str(source),str(cache)]
            answer=run(command);final=Path(answer.splitlines()[-1]);final=final/'model.onnx' if kind=='model' else final
            assert (final.parent/'.aji-stage-owner').read_bytes()==original
            products.append(final.read_bytes())
        assert products[0]==products[1]
    assert weight.read_bytes()==original
    write(out/'collision-summary.json',dict(passed=True,graph_bytes_exact=True,external_weights_preserved=True))
    print('external weight named .aji-stage-owner preserved for flow and snapshots, bytes exact')
    sys.exit()

if a.phase=='portable':
    hashes={}
    for kind in ['flow','model']:
        for label in ['before','after']:
            revision='-'+s['candidate_revision'] if label=='after' and s.get('candidate_revision') else ''
            checkpoint=out/(kind+'-'+label+'-case'+revision+'.json')
            if checkpoint.exists():
                record=json.loads(checkpoint.read_text());records.append(record)
                hashes[kind+'-'+label]=record['sha256'];continue
            case=out/(kind+'-'+label+'-case'+revision);case.mkdir();cache=case/'cache';cache.mkdir()
            parent=cache/'rife-flow-v2' if kind=='flow' else cache;parent.mkdir(exist_ok=True)
            keep=protected(parent,'.part-');ready=case/'paused'
            command=[s['flow_'+label],s['rife'],str(cache)] if kind=='flow' else [s['model_'+label],'freeze',s['model'],str(cache)]
            env=interrupted_env(case,'rife.flow.onnx' if kind=='flow' else 'model.onnx',ready)
            with (case/'interrupted.log').open('w') as log:
                process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
                until(ready.exists,process)
                pid,path=ready.read_text().splitlines();assert int(pid)==process.pid
                partial=Path(path);partial_bytes=partial.stat().st_size;assert 0<partial_bytes<=64
                stage=partial.parent;process.kill();assert process.wait(timeout=3)==-signal.SIGKILL
            answer=run(command);final=Path(answer.splitlines()[-1]);final=final/'model.onnx' if kind=='model' else final
            assert final.stat().st_size>64
            remains=stage.exists();assert remains==(label=='before'),(kind,label,stage)
            check_protected(keep)
            digest=hashlib.sha256(final.read_bytes()).hexdigest();hashes[kind+'-'+label]=digest
            record=dict(kind=kind,label=label,command=command,partial_bytes=partial_bytes,orphan_remains=remains,sha256=digest)
            records.append(record);write(checkpoint,record)
        assert hashes[kind+'-before']==hashes[kind+'-after']
    # A crash after publication leaves a complete cache and only metadata in
    # staging. Recovery must be nonblocking while a producer owns the key.
    checkpoint=out/'published-orphan-case.json'
    if checkpoint.exists():records.append(json.loads(checkpoint.read_text()))
    else:
        folder=out/'published-orphan';folder.mkdir();final=folder/'unit.engine';keep=protected(folder,'.aji-build-')
        stage=Path(run([s['model_after'],'published-orphan',str(final)]))
        with Path(str(final)+'.key-lock').open('r+') as holder:
            fcntl.flock(holder,fcntl.LOCK_EX);start=time.perf_counter()
            run([s['model_after'],'recover',str(final)])
            assert time.perf_counter()-start<1 and stage.exists()
        run([s['model_after'],'recover',str(final)])
        assert not stage.exists() and final.read_bytes()==b'COMPLETE';check_protected(keep)
        record=dict(kind='published-orphan',complete_cache_preserved=True,live_lock_nonblocking=True,unknown_preserved=True)
        records.append(record);write(checkpoint,record)
    write(out/'portable-summary.json',records);print('flow/model orphans 1 -> 0; bytes exact; warm recovery preserves live/unknown/complete data')
    sys.exit()

worker=Path(__file__).with_name('key_lock_gpu_worker.py');env=dict(os.environ,LD_LIBRARY_PATH=s['runtime'])
def child_alive(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1][0]!='Z'
    except FileNotFoundError:return False
def builder(case):
    path=case/'builder';path.write_text('#!'+sys.executable+'\nimport os,sys\nos.execv('+repr(s['trtexec'])+',['+repr(s['trtexec'])+']+sys.argv[1:])\n');path.chmod(0o755);return path
def spawn(case,label,library,models,builder_path,extra=None,pause=False):
    base=case/label;spec=dict(library=library,models=str(models),conf=s['conf'],trtexec=str(builder_path),input=s['input'],
        output=str(base),start=str(base.with_suffix('.start')),
        trtexec_env=('env LD_LIBRARY_PATH=' if pause else 'LD_LIBRARY_PATH=')+s['runtime'])
    spec.update(extra or {});config=base.with_suffix('.spec.json');write(config,spec)
    log=base.with_suffix('.log').open('w');selected=dict(env)
    if pause:selected.update(interrupted_env(case,'model.engine',case/'paused'),LD_LIBRARY_PATH=s['runtime'])
    process=subprocess.Popen([sys.executable,str(worker),str(config)],env=selected,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    until(base.with_suffix('.ready').exists,process);base.with_suffix('.start').touch()
    return process,base,log
def finish(item):
    process,base,log=item;assert process.wait(timeout=30)==0,base.with_suffix('.log').read_text()[-2500:];log.close()
    return json.loads(base.with_suffix('.json').read_text())
def kill_parent(item,case,expect_child):
    process,base,log=item;ready=case/'paused';until(ready.exists,process)
    pid,path=ready.read_text().splitlines();pid=int(pid);partial=Path(path);stage=partial.parent
    assert 0<partial.stat().st_size<=64
    process.kill();assert process.wait(timeout=3)==-signal.SIGKILL;log.close()
    if expect_child:until(lambda:not child_alive(pid),seconds=2)
    surviving=child_alive(pid)
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    return stage,surviving

if a.phase=='gpu':
    for label in ['before','after']:
        case=out/('gpu-'+label);models=case/'models';models.mkdir(parents=True)
        shutil.copyfile(s['model'],models/Path(s['model']).name);keep=protected(models,'.aji-build-')
        item=spawn(case,'interrupted',s[label],models,builder(case),pause=True)
        stage,surviving=kill_parent(item,case,label=='after')
        assert not list(models.glob('aji-v2-*.engine'))
        result=finish(spawn(case,'recovered',s[label],models,case/'builder'));assert result['configure_status']==1
        remains=stage.exists();assert remains==(label=='before');check_protected(keep)
        records.append(dict(label=label,orphan_remains=remains,builder_survived_parent=surviving,recovery=result))
    import numpy as np
    before=np.load(out/'gpu-before/recovered.npy');after=np.load(out/'gpu-after/recovered.npy')
    changed=int(np.count_nonzero(before!=after))
    if changed:
        old=out/'gpu-before/models';new=out/'gpu-after/models'
        for file in old.glob('*.engine'):shutil.copyfile(file,new/file.name)
        for label,models in [('before',old),('after',new)]:
            assert finish(spawn(models.parent,'same-plan',s[label],models,'/bin/false'))['configure_status']==1
        assert np.array_equal(np.load(out/'gpu-before/same-plan.npy'),np.load(out/'gpu-after/same-plan.npy'))
    records.append(dict(independent_rebuild_changed_bytes=changed,
        comparison='same_plan' if changed else 'independent_rebuild_exact',
        same_plan_changed_bytes=0 if changed else None))
    # Killing only the child must report failure without publishing partial data.
    case=out/'killed-child';models=case/'models';models.mkdir(parents=True)
    shutil.copyfile(s['model'],models/Path(s['model']).name)
    item=spawn(case,'interrupted',s['after'],models,builder(case),pause=True);until((case/'paused').exists,item[0])
    pid,path=(case/'paused').read_text().splitlines();os.kill(int(pid),signal.SIGKILL)
    failed=finish(item);assert failed['configure_status']<0
    assert not Path(path).parent.exists() and not list(models.glob('aji-v2-*.engine'))
    records.append(dict(child_kill=failed,no_partial_published=True))
    write(out/'gpu-summary.json',records);print('TRT parent/child interruption safe; owned orphan removed; output exact')
else:
    case=out/'motion';models=case/'models';models.mkdir(parents=True);source=Path(s['motion_reference'])
    shutil.copyfile(s['model'],models/Path(s['model']).name)
    for file in Path(s['warm_models']).glob('*.engine'):shutil.copyfile(file,models/file.name)
    rife=case/'rife';rife.mkdir();shutil.copyfile(s['rife'],rife/Path(s['rife']).name)
    for file in source.glob('*.engine'):shutil.copyfile(file,rife/file.name)
    keep=protected(rife,'.aji-build-')
    extra=dict(rife=str(rife),conf=s['fast_conf'],require_motion=True)
    item=spawn(case,'interrupted',s['after'],models,'/bin/false',extra,pause=True)
    # Here the write is in the native caller, not a builder child.
    ready=case/'paused';until(ready.exists,item[0]);pid,path=ready.read_text().splitlines();assert int(pid)==item[0].pid
    item[0].kill();assert item[0].wait(timeout=3)==-signal.SIGKILL;item[2].close();stage=Path(path).parent
    result=finish(spawn(case,'recovered',s['after'],models,'/bin/false',extra));assert result['configure_status']==1
    final=next(rife.glob('*.motion-*.onnx'));assert final.read_bytes()==(source/final.name).read_bytes()
    assert not stage.exists();check_protected(keep)
    write(out/'motion-summary.json',dict(recovery=result,export_exact=True,orphan_removed=True,unknown_preserved=True))
    print('interrupted native motion export recovers exact bytes, Fast active')
