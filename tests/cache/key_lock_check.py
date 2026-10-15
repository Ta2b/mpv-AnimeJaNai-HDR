#!/usr/bin/env python3
"""Necessary short builder coordination checks; phases never repeat each other."""
import argparse
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('spec',type=Path);p.add_argument('--phase',choices=['flow','gpu','remaining','motion','repair'],required=True)
a=p.parse_args();s=json.loads(a.spec.read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
records=[]
def until(predicate, seconds=15):
    deadline=time.monotonic()+seconds
    while not predicate():
        assert time.monotonic()<deadline,'coordination signal timeout'
        time.sleep(.005)
def write(path,data):path.write_text(json.dumps(data,indent=2)+'\n')

if a.phase=='flow':
    libc=C.CDLL(None,use_errno=True)
    libc.inotify_init1.argtypes=[C.c_int];libc.inotify_add_watch.argtypes=[C.c_int,C.c_char_p,C.c_uint]
    for label in ['before','after']:
        cache=out/('flow-cache-'+label);parent=cache/'rife-flow-v2';parent.mkdir(parents=True)
        fd=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC);assert fd>=0
        assert libc.inotify_add_watch(fd,os.fsencode(parent),0x100)>=0
        cmd=[s['flow_'+label],s['rife'],str(cache)]
        start=time.perf_counter()
        processes=[subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        results=[process.communicate(timeout=10) for process in processes]
        assert all(process.returncode==0 for process in processes),results
        paths=[Path(r[0].strip()) for r in results];assert paths[0]==paths[1]
        events=b''
        try:
            while True:events+=os.read(fd,65536)
        except BlockingIOError:pass
        finally:os.close(fd)
        stages=[];offset=0
        while offset<len(events):
            wd,mask,cookie,n=struct.unpack_from('iIII',events,offset);offset+=16
            name=events[offset:offset+n].split(b'\0',1)[0].decode();offset+=n
            if name.startswith('.part-') and mask&0x40000000:stages.append(name)
        assert not list(parent.glob('.part-*'))
        record=dict(label=label,command=cmd,seconds=time.perf_counter()-start,stages_created=len(stages),
                    sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),paths=list(map(str,paths)),logs=results)
        records.append(record)
    assert records[0]['sha256']==records[1]['sha256']
    assert records[1]['stages_created']==1,records
    write(out/'flow-summary.json',records)
    print('flow stages:',*[r['stages_created'] for r in records],'; graph bytes exact')
    sys.exit()

worker=Path(__file__).with_name('key_lock_gpu_worker.py')
env=dict(os.environ,LD_LIBRARY_PATH=s['runtime'])
def models(case):
    folder=out/case/'models';folder.mkdir(parents=True)
    shutil.copyfile(s['model'],folder/Path(s['model']).name)
    return folder
def wrapper(case,fail=False):
    folder=out/case;calls=folder/'calls';calls.mkdir(exist_ok=True)
    path=folder/('fail-builder' if fail else 'builder')
    code='#!'+sys.executable+'\nimport json,os,subprocess,sys,time\nfrom pathlib import Path\n'
    code+='folder=Path('+repr(str(calls))+')\nfile=folder/(str(os.getpid())+".json")\n'
    code+='file.write_text(json.dumps({"started":time.time(),"arguments":sys.argv[1:]}))\n'
    if fail:
        code+='deadline=time.monotonic()+15\nwhile not Path('+repr(str(folder/'fail-release'))+').exists():\n assert time.monotonic()<deadline\n time.sleep(.005)\nsys.exit(1)\n'
    else:code+='sys.exit(subprocess.run(['+repr(s['trtexec'])+']+sys.argv[1:]).returncode)\n'
    path.write_text(code);path.chmod(0o755);return path
def spawn(label,library,folder,builder,async_build=0,**extra):
    base=folder.parent/label
    spec=dict(library=library,models=str(folder),conf=s['conf'],trtexec=str(builder),input=s['input'],
              output=str(base),start=str(base.with_suffix('.start')),async_build=async_build,quit=str(base.with_suffix('.quit')))
    spec.update(extra)
    config=base.with_suffix('.spec.json');write(config,spec)
    log=base.with_suffix('.log').open('w')
    process=subprocess.Popen([sys.executable,str(worker),str(config)],env=env,stdout=log,stderr=subprocess.STDOUT)
    return process,base,log
def release(item):
    process,base,log=item;until(lambda:base.with_suffix('.ready').exists())
    base.with_suffix('.start').touch()
def finish(item):
    process,base,log=item;rc=process.wait(timeout=30);log.close()
    assert rc==0,base.with_suffix('.log').read_text()[-2000:]
    result=json.loads(base.with_suffix('.json').read_text());records.append(dict(output=str(base),**result));return result
def opened_lock(item,path):
    try:return any(os.readlink(f)==str(path) for f in Path('/proc/'+str(item[0].pid)+'/fd').iterdir())
    except (FileNotFoundError,PermissionError):return False

if a.phase=='repair':
    folder=models('repair')
    engine=next((out/'after/models').glob('*.engine')).name
    (folder/engine).write_bytes(b'broken cached engine')
    builder=wrapper('repair')
    items=[spawn(str(i),s['after'],folder,builder) for i in range(2)]
    for item in items:until(lambda item=item:item[1].with_suffix('.ready').exists())
    for item in items:item[1].with_suffix('.start').touch()
    assert all(finish(item)['configure_status']==1 for item in items)
    assert len(list((folder.parent/'calls').glob('*.json')))==1
    import numpy as np
    assert np.array_equal(np.load(folder.parent/'0.npy'),np.load(folder.parent/'1.npy'))
    write(out/'repair-summary.json',records)
    print('invalid cache repaired by one real builder; both consumers exact')
elif a.phase=='motion':
    folder=models('motion')
    for file in (out/'after/models').glob('*.engine'):shutil.copyfile(file,folder/file.name)
    rife=folder.parent/'rife';rife.mkdir()
    source=Path(s['motion_reference'])
    shutil.copyfile(s['rife'],rife/Path(s['rife']).name)
    for file in source.glob('*.engine'):shutil.copyfile(file,rife/file.name)
    items=[spawn(str(i),s['after'],folder,'/bin/false',rife=str(rife),conf=s['fast_conf'],require_motion=True) for i in range(2)]
    for item in items:until(lambda item=item:item[1].with_suffix('.ready').exists())
    for item in items:item[1].with_suffix('.start').touch()
    assert all(finish(item)['configure_status']==1 for item in items)
    exported=next(rife.glob('*.motion-*.onnx'))
    assert exported.read_bytes()==(source/exported.name).read_bytes()
    assert not list(rife.glob('*.part'))
    import numpy as np
    assert np.array_equal(np.load(folder.parent/'0.npy'),np.load(folder.parent/'1.npy'))
    write(out/'motion-summary.json',records)
    print('two native Fast configurations succeed; motion export exact and complete; no builder invoked')
elif a.phase=='gpu':
    for label in ['before','after']:
        folder=models(label);builder=wrapper(label)
        items=[spawn(str(i),s[label],folder,builder) for i in range(2)]
        for item in items:until(lambda item=item:item[1].with_suffix('.ready').exists())
        start=time.perf_counter()
        for item in items:item[1].with_suffix('.start').touch()
        results=[finish(item) for item in items]
        assert all(r['configure_status']==1 for r in results),results
        count=len(list((folder.parent/'calls').glob('*.json')))
        records.append(dict(case=label,real_builders=count,seconds=time.perf_counter()-start))
        assert count==(2 if label=='before' else 1),records
        if label=='after':
            import numpy as np
            assert np.array_equal(np.load(folder.parent/'0.npy'),np.load(folder.parent/'1.npy'))
    # Compare the libraries with the exact same winner plan (rebuild timing is
    # nondeterministic). Two warm consumers answer only this quality question.
    baseline=out/'before/models';candidate=out/'after/models'
    for file in baseline.glob('*.engine'):shutil.copyfile(file,candidate/file.name)
    for label,folder in [('before',baseline),('after',candidate)]:
        item=spawn('same-plan',s[label],folder,'/bin/false');release(item);assert finish(item)['configure_status']==1
    import numpy as np
    assert np.array_equal(np.load(out/'before/same-plan.npy'),np.load(out/'after/same-plan.npy'))
    write(out/'gpu-summary.json',records);print('real TRT builders 2 -> 1; shared-plan outputs exact')
else:
    # A failed real subprocess releases the key for the next successful builder.
    folder=models('failure');bad=spawn('bad',s['after'],folder,wrapper('failure',True));release(bad)
    until(lambda:bool(list((folder.parent/'calls').glob('*.json'))))
    engine=next((out/'after/models').glob('*.engine')).name;lock=folder/(engine+'.key-lock')
    good=spawn('good',s['after'],folder,wrapper('failure'));release(good)
    until(lambda:opened_lock(good,lock));(folder.parent/'fail-release').touch()
    assert finish(bad)['configure_status']<0
    assert finish(good)['configure_status']==1
    assert len(list((folder.parent/'calls').glob('*.json')))==2
    # Closing an async context waiting on another process must not join forever.
    folder=models('cancel');lock=folder/(engine+'.key-lock')
    with lock.open('w') as holder:
        fcntl.flock(holder,fcntl.LOCK_EX)
        item=spawn('waiting',s['after'],folder,wrapper('cancel'),1);release(item)
        until(lambda:opened_lock(item,lock));item[1].with_suffix('.quit').touch()
        cancelled=finish(item);assert cancelled['destroy_seconds']<1,cancelled
    assert not list((folder.parent/'calls').glob('*.json'))
    assert not list(folder.glob('.aji-build-*'))
    # The lock inode remains stable and the next producer can complete.
    item=spawn('recovered',s['after'],folder,wrapper('cancel'));release(item)
    assert finish(item)['configure_status']==1
    assert not list(folder.glob('.aji-build-*'))
    write(out/'remaining-summary.json',records);print('failed producer releases key; async wait cancelled; next builder succeeds')
