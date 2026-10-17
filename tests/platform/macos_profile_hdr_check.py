#!/usr/bin/env python3
"""Only the newly found no-rule/profile-HDR boundary; prior model cases reused."""
import json,subprocess,sys,tempfile
from pathlib import Path
cli=sys.argv[1:3]
with tempfile.TemporaryDirectory(prefix='aji-mac-hdr-') as temp:
 root=Path(temp);conf=root/'profile.conf'
 def call(method,runtime,version='1'):
  conf.write_text('[global]\nbackend=CoreMLNative\n[slot_1]\nchain_1_pipeline_version='+version+'\nchain_1_stage_count=2\nchain_1_stage_1_id=inactive\nchain_1_stage_1_kind=upscale\nchain_1_stage_1_method=onnx\nchain_1_stage_1_runtime=coremlnative\nchain_1_stage_1_model=ABSENT\nchain_1_stage_1_policy=quality\nchain_1_stage_2_id=h\nchain_1_stage_2_kind=hdr\nchain_1_stage_2_method='+method+'\nchain_1_stage_2_runtime='+runtime+'\nchain_1_stage_2_policy=quality\n')
  return json.loads(subprocess.check_output([*cli,'--profile-plan','--root',str(root),'--conf',str(conf),'--platform','macos','--slot','1','--rule','0'],text=True))
 r=call('mpv','gpu-next');assert r['plan'] is None and not r['requirements'] and not r['issues'] and r['profile_hdr']['can_execute']
 r=call('nvidia-truehdr','rtx-video');assert r['plan'] is None and r['issues'] and not r['profile_hdr']['can_execute']
 r=call('mpv','gpu-next','2');assert r['issues'] and r['profile_hdr'] is None
 result={'passed':True,'checks':['No matching rule requests no inactive inference model','Profile mpv HDR remains available without runtime','Profile TrueHDR unavailable on macOS even without matching inference rule','Future HDR pipeline version refused'],'scope':'Actual CLI CPU routing, no GPU/video'}
 print(json.dumps(result,indent=2))
 if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+'\n')
