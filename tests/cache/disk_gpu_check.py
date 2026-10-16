#!/usr/bin/env python3
"""GPU storage integration; run space with unshare -Urnm, host normally."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np

p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path)
p.add_argument('--phase',choices=['space','host'],required=True);a=p.parse_args()
s=json.loads(a.spec.read_text());out=Path(s['output']);records=[]
worker=Path(__file__).with_name('key_lock_gpu_worker.py');env=dict(os.environ,LD_LIBRARY_PATH=s['runtime'],LC_ALL='C')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def models(case):
    folder=case/'models';folder.mkdir(parents=True)
    shutil.copyfile(s['model'],folder/Path(s['model']).name)
    for file in Path(s['warm_models']).glob('*.engine'):shutil.copyfile(file,folder/file.name)
    return folder
def invoke(case,label,library,folder,conf,builder='/bin/false',async_probe=False,calls=None):
    base=case/label;start=base.with_suffix('.start');start.touch()
    spec=dict(library=library,models=str(folder),conf=str(conf),trtexec=str(builder),input=s['input'],
              output=str(base),start=str(start),async_build=int(async_probe),async_probe=async_probe)
    if calls:spec['observe_second_call']=str(calls)
    path=base.with_suffix('.spec.json');path.write_text(json.dumps(spec,indent=2)+'\n')
    wall=time.perf_counter()
    with base.with_suffix('.log').open('w') as log:
        r=subprocess.run([sys.executable,str(worker),str(path)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    assert r.returncode==0,base.with_suffix('.log').read_text()[-3000:]
    result=json.loads(base.with_suffix('.json').read_text())
    records.append(dict(output=str(base),wall_seconds=time.perf_counter()-wall,result=result))
    (out/('gpu-records-'+a.phase+'.json')).write_text(json.dumps(records,indent=2)+'\n')
    return result
def wrapper(case,folder,fake=False):
    calls=case/'calls';calls.mkdir();path=case/'builder'
    code='#!'+sys.executable+'\nimport json,os,sys\nfrom pathlib import Path\n'
    code+='Path('+repr(str(calls))+').joinpath(str(os.getpid())+".json").write_text(json.dumps(sys.argv[1:]))\n'
    if fake:
        source=next(Path(s['warm_models']).glob('*.engine'))
        code+='target=next(a.split("=",1)[1] for a in sys.argv[1:] if a.startswith("--saveEngine="))\n'
        code+='Path(target).write_bytes(Path('+repr(str(source))+').read_bytes()[:64])\n'
    else:
        code+='cache=Path('+repr(str(folder.parent))+')\nfiller=cache/"fixture-filler"\n'
        code+='if not Path('+repr(str(case/'disable-fill'))+').exists() and not filler.exists():\n'
        code+=' st=os.statvfs(cache);n=st.f_bavail*st.f_frsize-262144\n with filler.open("wb") as f:\n  chunk=b"\\0"*1048576\n  while n>0:\n   k=min(n,len(chunk));f.write(chunk[:k]);n-=k\n'
        code+='os.execv('+repr(s['trtexec'])+',['+repr(s['trtexec'])+']+sys.argv[1:])\n'
    path.write_text(code);path.chmod(0o755);return path,calls
variant=out/'gpu-variant.conf'
if not variant.exists():variant.write_text(Path(s['conf']).read_text().replace('--stronglyTyped --optShapes','--stronglyTyped  --optShapes'))
assert variant.read_text()!=Path(s['conf']).read_text()

if a.phase=='space':
    assert os.geteuid()==0
    for label in ['before','after']:
        case=out/('gpu-space-'+label);case.mkdir();volume=case/'volume';volume.mkdir()
        subprocess.run(['mount','-t','tmpfs','-o','size=32m,mode=0700','tmpfs',str(volume)],check=True)
        try:
            folder=models(volume);reference=next(folder.glob('*.engine'));expected=digest(reference)
            assert invoke(case,'baseline',s[label],folder,s['conf'])['active_status']==1
            build,calls=wrapper(case,folder)
            failed=invoke(case,'full',s[label],folder,variant,build,True,calls)
            assert failed['active_status']<=0 and digest(reference)==expected
            if label=='after':
                text=failed.get('poll_error','')+failed.get('current_log','')
                assert 'cache available bytes' in text and 'reopen' in text,text
                assert len(list(calls.glob('*.json')))==1
                assert list(folder.glob('*.engine'))==[reference],failed
            (volume/'fixture-filler').unlink();(case/'disable-fill').touch()
            recovered=invoke(case,'recovered',s[label],folder,variant,build,True)
            assert recovered['active_status']==1 and digest(reference)==expected
            libc=C.CDLL(None,use_errno=True);libc.mount.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_ulong,C.c_void_p]
            assert libc.mount(None,os.fsencode(volume),None,33,None)==0,C.get_errno()
            readonly=invoke(case,'readonly',s[label],folder,s['conf'])
            assert (readonly['active_status']==1)==(label=='after'),readonly
            if label=='after':assert np.array_equal(np.load(case/'baseline.npy'),np.load(case/'readonly.npy'))
        finally:subprocess.run(['umount',str(volume)],check=True)
    result=dict(passed=True,real_enospc=True,reference_preserved=True,readonly_cached_output_exact=True,records=records)
else:
    assert os.geteuid()!=0
    for label in ['before','after']:
        case=out/('gpu-unreadable-'+label);case.mkdir();folder=models(case)
        reference=next(folder.glob('*.engine'));expected=digest(reference);inode=reference.stat().st_ino
        assert invoke(case,'baseline',s[label],folder,s['conf'])['active_status']==1
        # Count a real builder if the old backend mistakes read failure for
        # permission to replace a completed reference.
        builder=case/'builder';calls=case/'calls';calls.mkdir()
        builder.write_text('#!'+sys.executable+'\nimport os,sys\nfrom pathlib import Path\nPath('+repr(str(calls))+').joinpath(str(os.getpid())+".json").touch()\nos.execv('+repr(s['trtexec'])+',['+repr(s['trtexec'])+']+sys.argv[1:])\n');builder.chmod(0o755)
        reference.chmod(0)
        try:failed=invoke(case,'unreadable',s[label],folder,s['conf'],builder)
        finally:reference.chmod(0o644)
        if label=='after':
            assert failed['active_status']<0 and digest(reference)==expected and reference.stat().st_ino==inode
            assert not list(calls.glob('*.json'))
            assert 'permission' in failed['final_error'].lower() and 'reopen' in failed['final_error'].lower()
        else:assert len(list(calls.glob('*.json')))==1 and reference.stat().st_ino!=inode
        assert invoke(case,'restored',s[label],folder,s['conf'])['active_status']==1
        if label=='after':assert np.array_equal(np.load(case/'baseline.npy'),np.load(case/'restored.npy'))

    for label in ['before','after']:
        case=out/('gpu-truncated-'+label);case.mkdir();folder=models(case);reference=next(folder.glob('*.engine'));expected=digest(reference)
        build,calls=wrapper(case,folder,True)
        failed=invoke(case,'zero-exit',s[label],folder,variant,build,True,calls)
        assert failed['active_status']==0 and digest(reference)==expected
        if label=='after':
            assert len(list(calls.glob('*.json')))==1
            assert list(folder.glob('*.engine'))==[reference]
            assert 'FAILED' in failed['current_log'] and 'incomplete or unusable' in failed['current_log']
        else:
            assert len(list(calls.glob('*.json')))>=2
            assert any(f.stat().st_size==64 for f in folder.glob('*.engine'))
    result=dict(passed=True,unreadable_reference_preserved=True,zero_exit_partial_not_published=True,
                failed_async_build_latches_without_loop=True,quality_reference_exact=True,records=records)
(out/('gpu-'+a.phase+'-summary.json')).write_text(json.dumps(result,indent=2)+'\n')
print(a.phase,'GPU storage checks passed')
