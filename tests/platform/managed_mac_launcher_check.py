#!/usr/bin/env python3
"""Execute the macOS launcher's shell with fake mpv/helper under a temporary HOME.
This checks file migration only; it does not qualify macOS APIs or video.
"""
from pathlib import Path
import json, os, shlex, shutil, subprocess, sys, tempfile
repo=Path(__file__).resolve().parents[2]
cli=sys.argv[1:] or ['dotnet',str(repo/'AnimeJaNaiPlatform/bin/Release/net10.0/AnimeJaNaiPlatform.dll')]
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
def write(root,path,text):
    file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text);return file
with tempfile.TemporaryDirectory(prefix='ajn-mac-shell-') as tmp:
    base=Path(tmp);home=base/'home';home.mkdir();scratch=base/'tmp';scratch.mkdir()
    app=base/'first App.app';res=app/'Contents/Resources';mac=app/'Contents/MacOS';mac.mkdir(parents=True)
    conf='portable_config/'
    write(res,conf+'mpv.conf','# default');write(res,conf+'script-opts/animejanai_mac.conf','# default')
    write(res,conf+'script-opts/animejanai_hdr_auto.conf','linux_hdr_output=sdr\n')
    write(res,'animejanai/animejanai.conf','profile')
    for name in ['keep.lua','retired.lua','edited.lua']:write(res,conf+'scripts/'+name,'v1')
    write(res,conf+'hdr-tools/tool.lua','tool');write(res,conf+'user-shaders/shader.hook','shader')
    write(res,'animejanai/preparation/worker.py','worker')
    helper=write(res,'AnimeJaNaiPlatform','#!/bin/sh\nexec '+shlex.join(cli)+' "$@"\n');helper.chmod(0o755)
    fake=write(mac,'mpv','#!/bin/sh\nprintf "%s" "$MPV_HOME" > "$CAPTURE"\n');fake.chmod(0o755)
    launch=mac/'mpv-animejanai';shutil.copyfile(repo/'installer/macos/launcher.sh',launch);launch.chmod(0o755)
    env=os.environ.copy();env.update(HOME=str(home),TMPDIR=str(scratch),ANIMEJANAI_DISPLAY_PROBE='/bin/true',CAPTURE=str(base/'captured'))
    def run():
        subprocess.run([*cli,'--write-managed-program-inventory','--root',str(res)],check=True,capture_output=True)
        subprocess.run([str(launch)],check=True,env=env,capture_output=True)
    run();data=home/'Library/Application Support/AnimeJaNai';target=data/'portable_config'
    check('mac launcher sets writable MPV_HOME',(base/'captured').read_text()==str(target))
    check('preparation installed',(data/'animejanai/preparation/worker.py').read_text()=='worker')
    write(target,'scripts/user.lua','user');write(target,'scripts/edited.lua','custom');write(data,'animejanai/sdk/sentinel','SDK')
    (res/conf/'scripts/retired.lua').unlink();write(res,conf+'scripts/keep.lua','v2');write(res,conf+'scripts/edited.lua','v2')
    run()
    check('mac obsolete owned script removed',not (target/'scripts/retired.lua').exists())
    check('mac owned script updated',(target/'scripts/keep.lua').read_text()=='v2')
    check('mac custom script survives',(target/'scripts/user.lua').read_text()=='user')
    check('mac modified script survives',(target/'scripts/edited.lua').read_text()=='custom')
    check('mac SDK survives',(data/'animejanai/sdk/sentinel').read_text()=='SDK')
    helper.unlink();write(res,conf+'scripts/added.lua','missing only')
    subprocess.run([str(launch)],check=True,env=env,capture_output=True)
    check('manual no-helper package seeds missing program',(target/'scripts/added.lua').read_text()=='missing only')
    check('manual no-helper package preserves local edit',(target/'scripts/edited.lua').read_text()=='custom')
    print(json.dumps({'passed':len(checks),'checks':checks,'platform_execution':'macOS shell simulated on Linux, no macOS APIs'}))
