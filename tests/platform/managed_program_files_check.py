#!/usr/bin/env python3
"""Bounded offline update/ownership fixtures; never opens the user's install."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[2]
cli = sys.argv[1:] or ['dotnet', str(repo/'AnimeJaNaiPlatform/bin/Release/net10.0/AnimeJaNaiPlatform.dll')]
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)
def run(*args, success=True):
    result = subprocess.run([*cli, *map(str,args)], capture_output=True, text=True)
    assert (result.returncode == 0) == success, (args,result.stderr)
    return json.loads(result.stdout) if success else result.stderr

def write(root, name, content):
    path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)

def inventory(root): run('--write-managed-program-inventory','--root',root)
def sync(package, target, success=True):
    return run('--sync-managed-programs','--package-root',package,'--root',target,success=success)

with tempfile.TemporaryDirectory(prefix='ajn-managed-fixture-') as tmp:
    base=Path(tmp); package=base/'package'; target=base/'target'; package.mkdir(); target.mkdir()
    script='portable_config/scripts/'
    for name in ['keep.lua','retired.lua','edited.lua','retired-edited.lua']:
        write(package,script+name,'v1')
    write(package,'animejanai/preparation/worker.py','worker-v1')
    write(package,'portable_config/profiles/nvidia/animejanai.conf','not managed')
    inventory(package)
    data=json.loads((package/'managed-program-files.json').read_text())
    check('inventory excludes user profiles',len(data['files'])==5 and not any('profiles' in x for x in data['files']))
    first=sync(package,target)
    check('first install has five managed programs',len(first['installed'])==5)
    state=(target/'.managed-program-files.json').read_bytes()
    # Edits/SDK/model/profile files must survive an update and a retirement.
    write(target,script+'edited.lua','my edit')
    write(target,script+'retired-edited.lua','my retired edit')
    write(target,script+'my-script.lua','my script')
    protected={'animejanai/models/model.engine':'engine','animejanai/sdk/lib.so':'sdk',
        'portable_config/profiles/nvidia/animejanai.conf':'profile'}
    for path,content in protected.items():write(target,path,content)
    for name in ['retired.lua','retired-edited.lua']:(package/script/name).unlink()
    for name in ['keep.lua','edited.lua','new.lua']:write(package,script+name,'v2')
    inventory(package); result=sync(package,target)
    check('owned obsolete script removed',not (target/script/'retired.lua').exists())
    check('owned current script updated',(target/script/'keep.lua').read_text()=='v2')
    check('new managed script copied',(target/script/'new.lua').read_text()=='v2')
    check('modified current script preserved',(target/script/'edited.lua').read_text()=='my edit' and result['conflicts'])
    check('modified retired script preserved',(target/script/'retired-edited.lua').read_text()=='my retired edit')
    check('user script untouched',(target/script/'my-script.lua').read_text()=='my script')
    check('profiles SDK and models untouched',all((target/p).read_text()==v for p,v in protected.items()))
    # Simulate interruption after program publication but before receipt replace.
    (target/'.managed-program-files.json').write_bytes(state)
    recovered=sync(package,target)
    check('interrupted receipt converges',not recovered['installed'] and not recovered['removed'])
    repeated=sync(package,target)
    check('idempotent second run',not repeated['installed'] and not repeated['removed'])
    # A known byte catalogue permits safe migration; arbitrary legacy bytes don't.
    legacy=base/'legacy'; legacy.mkdir()
    write(legacy,script+'keep.lua','v1');write(legacy,script+'retired.lua','v1');write(legacy,script+'edited.lua','legacy custom')
    catalogue={'schema':data['schema'],'files':{script+n:[hashlib.sha256(b'v1').hexdigest()] for n in ['keep.lua','retired.lua','edited.lua']}}
    (package/'legacy-managed-program-files.json').write_text(json.dumps(catalogue))
    migrated=sync(package,legacy)
    check('known legacy program updated',(legacy/script/'keep.lua').read_text()=='v2')
    check('known obsolete legacy program removed',not (legacy/script/'retired.lua').exists())
    check('unknown legacy edit preserved',(legacy/script/'edited.lua').read_text()=='legacy custom' and migrated['legacy_migration'])
    # Invalid manifest is rejected before copying a legitimate newly added file.
    write(package,script+'newer.lua','v3');inventory(package)
    manifest=package/'managed-program-files.json'; valid=manifest.read_bytes();invalid=json.loads(valid)
    invalid['files']['../escape.lua']='0'*64;manifest.write_text(json.dumps(invalid))
    sync(package,target,False)
    check('invalid path rejects before mutation',not (target/script/'newer.lua').exists())
    manifest.write_bytes(valid);(package/script/'newer.lua').write_text('tampered')
    sync(package,target,False)
    check('source hash rejects before mutation',not (target/script/'newer.lua').exists())
    (package/script/'newer.lua').write_text('v3')
    # Existing user symlinks (file and parent) are never followed or removed.
    outside=base/'outside';outside.mkdir();write(outside,'sentinel','external')
    (target/script/'newer.lua').symlink_to(outside/'sentinel')
    result=sync(package,target)
    check('file symlink and target untouched',(target/script/'newer.lua').is_symlink() and (outside/'sentinel').read_text()=='external')
    write(package,'portable_config/shaders/new.hook','shader');inventory(package)
    (target/'portable_config/shaders').symlink_to(outside,target_is_directory=True)
    sync(package,target)
    check('directory symlink not traversed',not (outside/'new.hook').exists())
    # The receipt itself is also user-owned if replaced by a link.
    receipt=target/'.managed-program-files.json';receipt.unlink();receipt.symlink_to(outside/'sentinel')
    sync(package,target,False)
    check('receipt symlink refuses sync',(outside/'sentinel').read_text()=='external')
    print(json.dumps({'passed':len(checks),'checks':checks,'gpu_exercised':False}))
