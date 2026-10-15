#!/usr/bin/env python3
"""One paused real-player frame before/after the CLI and Lua export entry points."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

p=argparse.ArgumentParser()
for name in ['player','helper','clip','vf','library-path','report']: p.add_argument('--'+name,required=True)
a=p.parse_args(); out=Path(a.report).resolve().parent; out.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[2]
script=root/'BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/scripts/animejanai_reference.lua'
with tempfile.TemporaryDirectory(prefix='aji-ref-live-') as temp:
    ipc=Path(temp)/'mpv.sock'
    env=dict(os.environ,LD_LIBRARY_PATH=a.library_path,ANIMEJANAI_ROOT=str(Path(a.helper).resolve().parent))
    command=[a.player,'--no-config','--load-scripts=no','--script='+str(script),
        '--hwdec=nvdec','--vo=gpu-next','--gpu-api=vulkan','--geometry=480x270',
        '--pause=yes','--keep-open=yes','--idle=yes','--audio=no','--framedrop=no',
        '--interpolation=no','--osd-level=0','--sub=no','--screenshot-high-bit-depth=yes',
        '--screenshot-png-compression=0','--vf='+a.vf,'--input-ipc-server='+str(ipc),a.clip]
    env['ANIMEJANAI_IPC_PATH']=str(ipc)
    with (out/'player.log').open('w') as log:
        player=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); connection.settimeout(5)
        deadline=time.monotonic()+10
        while not ipc.exists():
            if player.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Player did not start')
            time.sleep(.02)
        connection.connect(str(ipc)); stream=connection.makefile('rwb',buffering=0); index=0
        def cmd(*args):
            global index
            index+=1;request=index
            stream.write((json.dumps(dict(command=args,request_id=request))+'\n').encode())
            while True:
                result=json.loads(stream.readline())
                if result.get('request_id')==request:
                    if result['error']!='success':raise RuntimeError(str(result))
                    return result.get('data')
        try:
            while True:
                try:
                    params=cmd('get_property','video-out-params');pts=cmd('get_property','time-pos')
                    if params and pts is not None:break
                except RuntimeError:pass
                if time.monotonic()>deadline:raise RuntimeError('No decoded picture')
                time.sleep(.02)
            assert cmd('get_property','hwdec-current')=='nvdec'
            def capture(label):
                file=out/(label+'.png');cmd('screenshot-to-file',str(file),'video')
                return dict(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                    pts=cmd('get_property','time-pos'),bit_depth=file.read_bytes()[24])
            before=capture('before-export')
            started=time.monotonic()
            result=subprocess.run([a.helper,'--export-reference','--mpv-ipc',str(ipc),
                '--root',str(Path(a.helper).resolve().parent),'--output',str(out/'reference.json')],
                env=env,text=True,capture_output=True,timeout=30)
            seconds=time.monotonic()-started
            assert result.returncode==0,result.stderr
            report=json.loads((out/'reference.json').read_text())
            assert report['consistent_observed_state'],report['changed_during_capture']
            assert report['observed_properties']['video-out-params']==params
            assert report['filters'] and report['artifacts']
            for artifact in report['artifacts']:
                assert artifact['sha256']==hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest()
            # Different entry point: shipped Lua must call the helper and produce a new report.
            diagnostics=Path(a.helper).resolve().parent/'animejanai/diagnostics'
            old=set(diagnostics.glob('reference-*.json'))
            cmd('script-message','animejanai-export-reference')
            deadline=time.monotonic()+30
            while not (set(diagnostics.glob('reference-*.json'))-old):
                if time.monotonic()>deadline:raise RuntimeError('Lua export did not finish')
                time.sleep(.02)
            lua_file=next(iter(set(diagnostics.glob('reference-*.json'))-old))
            lua_report=json.loads(lua_file.read_text())
            assert lua_report['consistent_observed_state']
            after=capture('after-export')
            assert before==after and before['bit_depth']==16
            summary=dict(passed=True,before=before,after=after,same_pixels_and_pts=True,
                cli_export_seconds=seconds,lua_report=str(lua_file),artifacts_hashed=len(report['artifacts']),
                observed_dimensions=params,qualification=report['qualification'],
                fps_gain_claimed=False,command=command)
            Path(a.report).write_text(json.dumps(summary,indent=2)+'\n')
            print(json.dumps({k:v for k,v in summary.items() if k!='command'},indent=2))
        finally:
            cmd('quit');player.wait(timeout=10);stream.close();connection.close()
