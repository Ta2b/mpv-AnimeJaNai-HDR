#!/usr/bin/env python3
"""Targeted storage failures. space runs in an isolated user/mount namespace."""
import argparse
import ctypes as C
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import onnx

p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path)
p.add_argument('--phase',choices=['portable','space'],required=True);a=p.parse_args()
s=json.loads(a.spec.read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True);records=[]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(cmd,env=None,expected=0):
    start=time.perf_counter();r=subprocess.run(cmd,env=env or dict(os.environ,LC_ALL='C'),capture_output=True,text=True,timeout=15)
    row=dict(command=list(map(str,cmd)),returncode=r.returncode,seconds=time.perf_counter()-start,stdout=r.stdout,stderr=r.stderr)
    records.append(row)
    (out/('records-'+a.phase+'.json')).write_text(json.dumps(records,indent=2)+'\n')
    assert (r.returncode==0)==(expected==0),row
    return r.stdout.strip(),r.stderr
def snapshot(exe,source,cache,**kwargs):return run([exe,'freeze',str(source),str(cache)],**kwargs)
def flow(exe,source,cache,**kwargs):return run([exe,str(source),str(cache)],**kwargs)
def variant(source,target):
    model=onnx.load(source);model.producer_version='disk-error-fixture';onnx.save_model(model,str(target));return target
def fill(cache,leave):
    free=os.statvfs(cache).f_bavail*os.statvfs(cache).f_frsize
    size=free-leave;assert size>0
    path=cache/'fixture-filler'
    with path.open('wb') as file:
        chunk=b'\0'*(1024*1024)
        while size:
            n=min(size,len(chunk));file.write(chunk[:n]);size-=n
    return path

if a.phase=='portable':
    assert os.geteuid()!=0,'permission checks require ordinary host user'
    changed=variant(s['model'],out/'variant.onnx')
    for label in ['before','after']:
        case=out/('portable-'+label);case.mkdir();cache=case/'cache';cache.mkdir()
        exe=s['model_'+label]
        reference=Path(snapshot(exe,s['model'],cache)[0].splitlines()[-1])/'model.onnx';expected=digest(reference)
        env=dict(os.environ,LC_ALL='C',LD_PRELOAD=s['interposer'],AJI_INTERRUPT_ROOT=str(case),
                 AJI_INTERRUPT_FILE='model.onnx',AJI_INJECT_ERRNO=str(errno.EDQUOT))
        _,diagnostic=snapshot(exe,changed,cache,env=env,expected=1)
        assert digest(reference)==expected and not list(cache.glob('.part-*'))
        if label=='after':assert 'quota' in diagnostic.lower() and 'reopen' in diagnostic.lower(),diagnostic
        recovered=Path(snapshot(exe,changed,cache)[0].splitlines()[-1])/'model.onnx'
        assert recovered.read_bytes()==changed.read_bytes()
        # A different key needs a lock/staging write; no cache reference may be
        # removed when ordinary Unix permissions reject it.
        model=onnx.load(changed);model.producer_version='permission-fixture';target=case/'permission.onnx';onnx.save_model(model,str(target))
        cache.chmod(0o500)
        try:_,diagnostic=snapshot(exe,target,cache,expected=1)
        finally:cache.chmod(0o755)
        assert digest(reference)==expected
        if label=='after':assert 'permission' in diagnostic.lower() and 'reopen' in diagnostic.lower(),diagnostic
        assert Path(snapshot(exe,target,cache)[0].splitlines()[-1]).joinpath('model.onnx').read_bytes()==target.read_bytes()
        pub=case/'publication';pub.mkdir();result=json.loads(run([s['publication_'+label],str(pub)])[0])
        assert result['reference']=='REFERENCE'
        assert result['published']==(label=='before'),result
        if label=='after':
            assert result['owner_preserved'] and not result['stage_remains']
            assert 'permission' in result['error'].lower(),result
    Path(out/'portable-summary.json').write_text(json.dumps(dict(passed=True,quota_injected_errno=errno.EDQUOT,
        publication_false_success_fixed=True,reference_preserved=True,records=records),indent=2)+'\n')
    print('EDQUOT and permission diagnostics actionable; refused publication true -> false; references intact')
else:
    assert os.geteuid()==0,'invoke space inside unshare -Urnm'
    changed=variant(s['rife'],out/'rife-variant.onnx');products=[]
    for label in ['before','after']:
        prior=out/'before-space-assertions.json'
        reuse=label=='before' and prior.exists()
        case=out/('flow-readonly-before' if reuse else 'flow-space-'+label);case.mkdir();cache=case/'volume';cache.mkdir()
        subprocess.run(['mount','-t','tmpfs','-o','size=32m,mode=0700','tmpfs',str(cache)],check=True)
        try:
            if not reuse:
                reference=Path(flow(s['flow_'+label],s['rife'],cache)[0]);expected=digest(reference)
                filler=fill(cache,256*1024)
                _,diagnostic=flow(s['flow_'+label],changed,cache,expected=1)
                assert digest(reference)==expected and not list((cache/'rife-flow-v2').glob('.part-*'))
                if label=='after':assert 'No space left on device' in diagnostic and 'reopen' in diagnostic.lower(),diagnostic
                filler.unlink()
            final=Path(flow(s['flow_'+label],changed,cache)[0]);products.append(digest(final))
            # Avoid util-linux replaying a host UID from mountinfo into the
            # single-ID user namespace. A direct remount retains the UID.
            libc=C.CDLL(None,use_errno=True)
            libc.mount.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_ulong,C.c_void_p]
            assert libc.mount(None,os.fsencode(cache),None,32|1,None)==0,C.get_errno()
            answer,diagnostic=flow(s['flow_'+label],changed,cache,expected=1 if label=='before' else 0)
            if label=='after':assert digest(Path(answer))==products[-1]
        finally:subprocess.run(['umount',str(cache)],check=True)
    assert products[0]==products[1]
    Path(out/'space-summary.json').write_text(json.dumps(dict(passed=True,real_enospc=True,
        readonly_complete_cache_restored=True,graph_exact=True,reference_preserved=True,records=records),indent=2)+'\n')
    print('real ENOSPC rollback/recovery; complete flow cache works read-only; graph bytes exact')
