#!/usr/bin/env python3
"""Short actual mpv pause/seek/slot lifecycle, with ownership at shutdown."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import tempfile
from pipeline_player_check import digest
def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']).parent/'player-lifecycle';out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
    identity={k:digest(s[k]) for k in ['mpv','input_video','conf','trt','library','kernel','fruc']}
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Conclusive matching receipt; no replay.');return
    ipc_directory=tempfile.TemporaryDirectory(prefix='aji-pipeline-seek-')
    endpoint=Path(ipc_directory.name)/'ipc.sock'
    params={'conf':s['conf'],'model-dir':s['models'],'rife-model-dir':s['rife'],'lib':s['trt'],
        'pipeline-lib':s['library'],'pipeline-kernels':s['kernel'],'fruc-lib':s['fruc'],'trtexec':'/bin/false','slot':'1','output-444':'yes','passthrough':'no'}
    vf='@aji:animejanai='+':'.join(k+'=%'+str(len(v.encode()))+'%'+v for k,v in params.items())
    log=out/'mpv.log';args=[s['mpv'],'--no-config','--load-scripts=no','--vo=null','--audio=no','--ao=null',
        '--pause=yes','--keep-open=yes','--idle=yes','--hwdec=nvdec','--hwdec-codecs=all','--stop-screensaver=no',
        f'--input-ipc-server={endpoint}',f'--log-file={log}','--msg-level=all=v',f'--vf={vf}',s['input_video']]
    stdout=(out/'stdout.log').open('wb');p=subprocess.Popen(args,stdout=stdout,stderr=subprocess.STDOUT);conn=None;counter=0
    try:
        deadline=time.monotonic()+10
        while not endpoint.exists():
            assert p.poll() is None and time.monotonic()<deadline;time.sleep(.01)
        conn=socket.socket(socket.AF_UNIX);conn.settimeout(4);conn.connect(str(endpoint));reader=conn.makefile('rb')
        def cmd(command):
            nonlocal counter
            counter+=1;conn.sendall((json.dumps({'command':command,'request_id':counter})+'\n').encode())
            while True:
                line=reader.readline();assert line,'IPC disconnected';r=json.loads(line)
                if r.get('request_id')==counter:return r
        def prop(name):return cmd(['get_property',name]).get('data')
        def state():return dict(pause=prop('pause'),time=prop('time-pos'),meta=prop('vf-metadata/aji') or {},video=prop('video-out-params') or {})
        def until(fn):
            end=time.monotonic()+6;last={}
            while time.monotonic()<end:
                assert p.poll() is None;last=state()
                if fn(last):return last
                time.sleep(.01)
            (out/'diagnostic.json').write_text(json.dumps(last,indent=2)+'\n');raise AssertionError(last)
        initial=until(lambda x:x['time'] is not None and x['meta'].get('pipeline-active')=='yes' and x['video'].get('w')==2560)
        assert initial['pause'] is True and int(initial['meta']['surface-worker-live-owners'])==0
        generation=int(initial['meta']['surface-worker-generation'])
        assert cmd(['seek',str(1001/24000),'absolute+exact'])['error']=='success'
        sought=until(lambda x:x['time'] is not None and x['time']>=.04 and x['meta'].get('pipeline-active')=='yes' and
            int(x['meta'].get('surface-worker-generation',0))>generation and x['video'].get('w')==2560 and
            int(x['meta'].get('surface-worker-live-owners',-1))==0 and
            int(x['meta'].get('surface-worker-completed',0))>int(initial['meta'].get('surface-worker-completed',0)))
        (out/'seek-observation.json').write_text(json.dumps(sought,indent=2)+'\n')
        assert sought['pause'] is True and int(sought['meta']['surface-worker-live-owners'])==0
        assert cmd(['vf-command','aji','slot','0'])['error']=='success'
        assert cmd(['seek','0','relative+exact'])['error']=='success'
        disabled=until(lambda x:x['meta'].get('pipeline-active')=='no' and x['video'].get('w')==1280)
        assert cmd(['vf-command','aji','slot','1'])['error']=='success'
        assert cmd(['seek','0','relative+exact'])['error']=='success'
        enabled=until(lambda x:x['meta'].get('pipeline-active')=='yes' and x['video'].get('w')==2560)
        assert enabled['pause'] is True
        cmd(['quit']);p.wait(timeout=6);assert p.returncode==0
        ownership=re.findall(r'Surface worker shutdown ownership: live=(\d+) retain=(\d+) release=(\d+)',log.read_text())
        assert ownership and all(live=='0' and retained==released and int(retained)>0 for live,retained,released in ownership),ownership
        result=dict(passed=True,identity=identity,initial=initial,seek=sought,disabled=disabled,reenabled=enabled,
            shutdown_ownership=ownership,native_nvdec=True,paused_seek_generation=True,slot_roundtrip=True,args=args)
        receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    finally:
        if conn:conn.close()
        if p.poll() is None:p.terminate();p.wait(timeout=5)
        stdout.close();ipc_directory.cleanup()
if __name__=='__main__':main()
