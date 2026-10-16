#!/usr/bin/env python3
"""Actual legacy RIFE5/2+SPAN before/after stage-schema migration, same binary.
No model builds, no FPS claim. SHA256 frame hashes include all output pixels.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
from pipeline_player_check import digest
def main():
    s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']).parent/'legacy-player';out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
    identity={k:digest(s[k]) for k in ['mpv','input_video','conf','trt','library','kernel']}
    if receipt.exists():
        old=json.loads(receipt.read_text());assert old['passed'] and old['identity']==identity;print('Conclusive matching receipt; no replay.');return
    text=Path(s['conf']).read_text();text='\n'.join(line for line in text.splitlines() if not re.match(r'chain_1_(stage_|stage_count|pipeline_version)',line))+'\n'
    model=next(line.split('=',1)[1] for line in Path(s['conf']).read_text().splitlines() if line.startswith('chain_1_stage_3_model='))
    text+=f'chain_1_rife_factor_numerator=5\nchain_1_rife_factor_denominator=2\nchain_1_rife_before_upscale=yes\nchain_1_model_1_name={model}\n'
    stages='chain_1_pipeline_version=1\nchain_1_stage_count=2\n'
    values=[dict(id='legacy-rife',kind='interpolate',method='rife',runtime='tensorrt',model='426',factor_numerator='5',factor_denominator='2',policy='quality',ensemble='no',scene_detect_threshold='1'),
        dict(id='legacy-model-1',kind='upscale',method='onnx',runtime='tensorrt',model=model,factor_numerator='1',factor_denominator='1',policy='quality')]
    for i,step in enumerate(values,1):
        for k,v in step.items():stages+=f'chain_1_stage_{i}_{k}={v}\n'
    results={}
    for label,content in [('before',text),('after',text+stages)]:
        conf=out/(label+'.conf');conf.write_text(content);video=out/(label+'.nut');log=out/(label+'.log')
        params={'conf':str(conf),'model-dir':s['models'],'rife-model-dir':s['rife'],'lib':s['trt'],'pipeline-lib':s['library'],
            'pipeline-kernels':s['kernel'],'fruc-lib':s['fruc'],'trtexec':'/bin/false','slot':'1','passthrough':'no','output-444':'yes'}
        vf='@aji:animejanai='+':'.join(k+'=%'+str(len(v.encode()))+'%'+v for k,v in params.items())
        args=[s['mpv'],'--no-config','--load-scripts=no','--audio=no','--ao=null','--hwdec=nvdec','--hwdec-codecs=all',
            '--stop-screensaver=no',f'--log-file={log}','--msg-level=all=v',f'--vf={vf}',f'--o={video}','--of=nut','--ovc=rawvideo',s['input_video']]
        with (out/(label+'-stdout.log')).open('wb') as f:run=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=30)
        assert run.returncode==0,(label,run.returncode)
        evidence=log.read_text();assert 'RIFE active: 5/2' in evidence and 'Ordered GPU pipeline active' not in evidence,evidence[-1800:]
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-of','json',str(video)]))
        assert probe['streams'][0]['width']==2560 and probe['streams'][0]['height']==1440
        hashes=subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-f','framehash','-hash','sha256','-'],text=True)
        records=[x for x in hashes.splitlines() if x and not x.startswith('#')]
        assert records;results[label]=dict(frame_hashes=records,pts=[f['pts'] for f in probe['frames']],timebase=probe['streams'][0]['time_base'],args=args)
    assert results['before']['frame_hashes']==results['after']['frame_hashes'] and results['before']['pts']==results['after']['pts']
    result=dict(passed=True,identity=identity,frames=len(results['before']['pts']),pixels_exact=True,pts_exact=True,
        legacy_route_retained=True,factor=[5,2],models=['RIFE4.26',model],results=results)
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
