#!/usr/bin/env python3
"""One short actual mpv/NVDEC ordered-chain check, no engine builds.
Uses a three-frame720p source and a720p maximum; verifies identity+EOF.
Checks native frame durations separately from encoder packet durations.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from fractions import Fraction
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()
def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
    identity={k:digest(s[k]) for k in ['mpv','input_video','conf','trt','library','kernel','fruc']}
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Conclusive matching receipt, no replay.');return
    video=out/'sequence.nut';log=out/'mpv.log'
    params={'conf':s['conf'],'model-dir':s['models'],'rife-model-dir':s['rife'],'lib':s['trt'],
        'pipeline-lib':s['library'],'pipeline-kernels':s['kernel'],'fruc-lib':s['fruc'],
        'trtexec':'/bin/false','slot':'1','passthrough':'no','output-444':'yes'}
    # mpv's native suboption length quoting handles literal paths safely.
    vf='@aji:animejanai='+':'.join(k+'=%'+str(len(v.encode()))+'%'+v for k,v in params.items())
    args=[s['mpv'],'--no-config','--load-scripts=no','--audio=no','--ao=null','--hwdec=nvdec','--hwdec-codecs=all',
        '--stop-screensaver=no','--msg-level=all=v,ffmpeg=warn,vf=debug',f'--log-file={log}',f'--vf={vf}',
        f'--o={video}','--of=nut','--ovc=rawvideo',s['input_video']]
    start=time.monotonic()
    env=dict(os.environ);env['LD_LIBRARY_PATH']=s['runtime']+':'+env.get('LD_LIBRARY_PATH','')
    with (out/'stdout.log').open('wb') as f:run=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=30,env=env)
    assert run.returncode==0,run.returncode
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-of','json',str(video)]))
    source=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-of','json',s['input_video']]))
    frames=probe['frames'];stream=probe['streams'][0];text=log.read_text();assert len(frames)==3,(len(frames),text[-2000:])
    assert (stream['width'],stream['height'],stream['pix_fmt'])==(1280,720,'yuv444p16le')
    assert 'cuda[nv12]' in text and 'Ordered GPU pipeline active: 1 stages, x1' in text
    native=[(float(a),float(b),int(c)) for a,b,c in re.findall(r'Ordered output pts=([0-9.-]+) duration=([0-9.-]+) provenance=([0-9]+)',text)]
    assert len(native)==3 and [v[2] for v in native]==[1,1,1],native
    source_tb=Fraction(source['streams'][0]['time_base']);first=Fraction(source['frames'][0]['pts'])*source_tb
    period=Fraction(1001,24000);tb=Fraction(stream['time_base']);encoded=[Fraction(f['pts'])*tb for f in frames]
    # Native rational phase planning rounds once to nanoseconds; encoding has
    # a separate muxer timebase. Neither permits cumulative timestamp drift.
    for i,(pts,duration,_) in enumerate(native):
        expected=first+period*i
        assert abs(pts-float(expected))<=1e-9,(i,pts,expected)
        assert abs(duration-float(period))<=1e-9,(i,duration)
        assert abs(float(encoded[i]-expected))<=float(tb),('encoder PTS',i,encoded[i],expected)
    assert abs(sum(v[1] for v in native)-float(period*3))<=9e-9
    result=dict(passed=True,identity=identity,args=args,output_frames=3,source_frames=3,native_nvdec=True,stages=1,factor=1,
        output_dimensions=[1280,720],output_format=stream['pix_fmt'],native_pts_durations=native,encoder_timebase=stream['time_base'],
        encoded_pts=[str(x) for x in encoded],native_duration_matches_source=True,scope='Actual headless mpv pipeline/encoding, not physical display/HDR/FPS qualification',
        execution_wall_seconds=time.monotonic()-start,returncode=run.returncode)
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
