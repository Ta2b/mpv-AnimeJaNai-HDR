#!/usr/bin/env python3
"""Actual shared CLI, macOS file/routing contract only. No video/API benchmark."""
from pathlib import Path
import json,subprocess,sys,tempfile
cli=sys.argv[1:3];checks=[]
with tempfile.TemporaryDirectory(prefix='aji-mac-plan-') as temp:
 root=Path(temp);data=root/'animejanai';models=root/'selected models';rife=root/'selected rife';inf=root/'bundle inference'
 for p in (data,models,rife,inf):p.mkdir()
 for n in ('libaji_ort.dylib','libonnxruntime.1.dylib'):(inf/n).touch()
 (models/'OTHER.onnx').touch();(rife/'rife_v4.26.onnx').touch()
 conf=data/'animejanai.conf'
 def stage(kind='upscale',method='onnx',runtime='coremlnative',model='SPAN',extra=''):
  return '\n'.join(' chain_1_stage_1_'+k+' = '+v for k,v in dict(id='s',kind=kind,method=method,runtime=runtime,model=model,policy='quality').items())+'\n'+extra
 def resolve(body,backend='CoreMLNative',device='AUTO'):
  conf.write_text('[global]\n backend = '+backend+'\n apple_device = '+device+'\n rife_engine = fast\n default_slot = 1\n[slot_1]\n profile_name = Test\n chain_1_pipeline_version = 1\n chain_1_stage_count = 1\n'+body)
  raw=subprocess.check_output([*cli,'--profile-plan','--root',str(root),'--conf',str(conf),'--platform','macos','--slot','1','--rule','1','--inference-dir',str(inf),'--models-dir',str(models),'--rife-dir',str(rife)],text=True)
  result=json.loads(raw);assert result['schema']=='animejanai.profile-plan.v1';return result
 def check(name,value):assert value,name;checks.append(name)
 body=stage();r=resolve(body);check('unrelated ONNX cannot satisfy exact CoreML model',not r['plan']['can_execute'] and any(q['identity']=='SPAN.mlpatch' and not q['present'] for q in r['requirements']))
 (models/'SPAN.mlpatch').touch();r=resolve(body);check('table without matching package refused',not r['plan']['can_execute'] and any(q['identity']=='SPAN.mlpackage' and not q['present'] for q in r['requirements']))
 (models/'SPAN.mlpackage').mkdir();check('native CoreML does not require unrelated ONNX',resolve(body)['plan']['can_execute'])
 metal=stage(runtime='metal');check('Metal CPU actually resolves CoreML template files',resolve(metal,'Metal','CPU')['plan']['can_execute'])
 (models/'SPAN.ajm').touch();r=resolve(metal,'Metal','GPU');check('Metal graph without exact weights refused',not r['plan']['can_execute'] and any(q['identity']=='SPAN.ajw' and not q['present'] for q in r['requirements']))
 (models/'SPAN.ajw').touch();check('Metal GPU and NPU needs both native representations',resolve(metal,'Metal','GPU+NPU')['plan']['can_execute'])
 (inf/'libonnxruntime.1.dylib').unlink();check('linked runtime absence visible before playback',not resolve(metal,'Metal','GPU')['plan']['can_execute'])
 hdr=stage('hdr','mpv','gpu-next','');r=resolve(hdr);check('mpv HDR alone needs no inference runtime or SDK',r['plan']['can_execute'] and not r['requirements'])
 disabled=stage('interpolate','nvidia-fruc','cuda','',extra='chain_1_stage_1_enabled=no\n');r=resolve(disabled);check('disabled imported stage has no runtime dependency',r['plan']['can_execute'] and not r['requirements'])
 (inf/'libonnxruntime.1.dylib').touch();r=resolve(stage('interpolate','rife','coremlnative','426',extra='chain_1_stage_1_factor_numerator=2\n'));check('exact alternate RIFE directory and stage Quality despite global Fast',r['plan']['can_execute'] and r['plan']['legacy_compatible'] and any(q['path']==str(rife/'rife_v4.26.onnx') for q in r['requirements']))
 receipt={'passed':True,'checks':checks,'scope':'Actual CLI with simulated macOS files/platform; no hardware execution or model validity claim'}
 print(json.dumps(receipt,indent=2))
 if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(receipt,indent=2)+'\n')
