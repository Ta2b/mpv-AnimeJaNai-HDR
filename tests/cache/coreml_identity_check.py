#!/usr/bin/env python3
"""Short before/after cache identity and package fidelity check, no Apple runtime needed.
Usage: coreml_identity_check.py --output ARTIFACT_DIRECTORY
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[2]
reference=out/'mlpatch-reference.cpp'
reference.write_bytes(subprocess.check_output(['git','show','55bbc85:native/linux-ort/mlpatch.cpp'],cwd=root))
executables={}
for name,source in [('before',reference),('after',root/'native/linux-ort/mlpatch.cpp')]:
    exe=out/name
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread',
        '-I'+str(root/'native/linux-ort'),str(root/'tests/cache/coreml_identity_cli.cpp'),str(source),'-o',str(exe)],check=True)
    executables[name]=exe
def call(name,*args,ok=True):
    started=time.perf_counter()
    result=subprocess.run([str(executables[name]),*map(str,args)],text=True,capture_output=True)
    assert (result.returncode==0)==ok,result.stderr
    return result.stdout.strip(),(time.perf_counter()-started)*1000

# Independent standard SHA-256 oracle, including padding boundaries and many blocks.
vectors=[b'',b'abc',b'a'*55,b'a'*56,b'a'*64,bytes(range(256))*4096]
for i,data in enumerate(vectors):
    file=out/f'vector-{i}';file.write_bytes(data)
    digest,_=call('after','--sha',file)
    assert digest==hashlib.sha256(data).hexdigest()

models=out/'models';models.mkdir(exist_ok=True);model='test'
package=models/'test.mlpackage';weights=package/'Data/weights/weight.bin';weights.parent.mkdir(parents=True,exist_ok=True)
weights.write_bytes(bytes(range(256))*65536)  # 16 MiB, same workload before/after
spec=package/'Data/model.mlmodel';spec.write_bytes(b'\x80\x04\x80\x04')
(package/'Manifest.json').write_text('{"model":"Data/model.mlmodel"}\n')
(models/'test.mlpatch').write_text('AJP 1\ntemplate 512 512\nmodel Data/model.mlmodel 4\nh 1 0\nw 1 2\n')
old,old_ms=call('before',models,model);new,new_ms=call('after',models,model)
assert new.startswith('v2-') and len(new)==67
stamp=weights.stat()
with weights.open('r+b') as f:f.seek(12345);f.write(b'changed!')
os.utime(weights,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
old_changed,_=call('before',models,model);new_changed,_=call('after',models,model)
assert old_changed==old and new_changed!=new
# Independent framed-content oracle: logical names and sizes, not absolute paths.
resources={'table':models/'test.mlpatch'}
resources.update({'package/'+file.relative_to(package).as_posix():file for file in package.rglob('*') if file.is_file()})
h=hashlib.sha256()
def text(value):
    data=value.encode();h.update(struct.pack('>Q',len(data)));h.update(data)
text('animejanai-content-v1');text('coreml-native-template-v2');h.update(struct.pack('>Q',len(resources)))
for name,file in sorted(resources.items()):
    text(name);data=file.read_bytes();h.update(struct.pack('>Q',len(data)));h.update(data)
assert new_changed=='v2-'+h.hexdigest()

# A moved installation must keep the identity; resource rename must invalidate it.
copy=out/'moved';shutil.copytree(models,copy,dirs_exist_ok=True)
moved,_=call('after',copy,model);assert moved==new_changed
renamed=weights.with_name('other.bin');weights.rename(renamed)
rename_tag,_=call('after',models,model);assert rename_tag!=new_changed
renamed.rename(weights)
restored,_=call('after',models,model);assert restored==new_changed
spec_saved=spec.read_bytes();spec.unlink();call('after',models,model,ok=False);spec.write_bytes(spec_saved)

# The identity change must not change the package written for inference.
before_pkg=out/'before.mlpackage';after_pkg=out/'after.mlpackage'
for label,destination in [('before',before_pkg),('after',after_pkg)]:
    call(label,'--write',models,model,destination,1024,768)
def contents(directory):
    return {f.relative_to(directory).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
        for f in directory.rglob('*') if f.is_file()}
assert contents(before_pkg)==contents(after_pkg)
assert (after_pkg/'Data/model.mlmodel').read_bytes()==b'\x80\x06\x80\x08'
assert (after_pkg/'Data/weights/weight.bin').read_bytes()==weights.read_bytes()
summary=dict(passed=True,before_tag=old,before_changed_weights_tag=old_changed,
    after_tag=new,after_changed_weights_tag=new_changed,sha256_oracle=True,
    same_size_mtime_replacement_detected=True,relocation_stable=True,resource_rename_detected=True,
    missing_description_rejected=True,generated_package_bytes_identical=True,
    identity_process_ms_before=old_ms,identity_process_ms_after=new_ms,weights_bytes=weights.stat().st_size,
    measurement='one cold-ish process each, includes startup; not FPS; no repeated timing',
    apple_runtime_qualified=False)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
