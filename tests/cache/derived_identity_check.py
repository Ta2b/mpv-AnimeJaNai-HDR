#!/usr/bin/env python3
"""Targeted motion source and same-size temporal metadata regression cases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import onnx
from onnx import helper,TensorProto

p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path)
p.add_argument('--phase',choices=['motion','temporal','static'],required=True);a=p.parse_args()
s=json.loads(a.spec.read_text());out=Path(s['output']);summary=out/(a.phase+'-summary.json')
if summary.exists():
    assert json.loads(summary.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
if a.phase=='motion':
    case=out/'motion';case.mkdir(exist_ok=True);exe=s['motion_cli']
    def invoke(label,*args):
        receipt=case/(label+'.json')
        if receipt.exists():return json.loads(receipt.read_text())['stdout'].strip().splitlines()
        r=subprocess.run([exe,*map(str,args)],text=True,capture_output=True,timeout=20)
        save(receipt,dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr));assert r.returncode==0,r.stderr
        return r.stdout.strip().splitlines()
    raw=case/'old-transform.onnx';invoke('transform','transform',s['rife'],raw)
    content,folder,scheme=invoke('new','freeze',s['rife'],case/'cache');graph=Path(folder)/'model.onnx'
    assert graph.read_bytes()==raw.read_bytes();stamp=(graph.stat().st_ino,graph.stat().st_mtime_ns)
    assert invoke('warm','freeze',s['rife'],case/'cache')==[content,folder,scheme]
    assert stamp==(graph.stat().st_ino,graph.stat().st_mtime_ns)
    external=case/'external';external.mkdir(exist_ok=True);source=external/'rife.onnx';weights=external/'weights.bin'
    if not source.exists():
        model=onnx.load(s['rife']);onnx.save_model(model,str(source),save_as_external_data=True,
            all_tensors_to_one_file=True,location='weights.bin',size_threshold=0)
    first=invoke('external-first','freeze',source,case/'external-cache');original=weights.read_bytes()
    first_weights=Path(first[1])/'weights.bin';assert first_weights.read_bytes()==original
    old_graph=source.read_bytes();stamp=weights.stat()
    if not (case/'external-changed.json').exists():
        data=bytearray(original);data[0]^=1;weights.write_bytes(data);os.utime(weights,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    second=invoke('external-changed','freeze',source,case/'external-cache')
    assert first[0]!=second[0] and first[1]!=second[1] and source.read_bytes()==old_graph
    assert first_weights.read_bytes()==original and (Path(second[1])/'weights.bin').read_bytes()==weights.read_bytes()
    result=dict(passed=True,motion_graph_changed_bytes=0,warm_rewrites=0,
        same_graph_external_weights_invalidate=True,old_snapshot_preserved=True,
        semantic_scheme=scheme,source_sha256=sha(Path(s['rife'])))
else:
    case=out/('temporal-dynamic' if a.phase=='temporal' else 'temporal');case.mkdir(exist_ok=True)
    def fixture(t,dtype):
        h,w=('h','w') if a.phase=='temporal' else (96,128)
        graph=helper.make_graph([helper.make_node('ReduceMean',['input'],['output'],axes=[1],keepdims=0)],
            'temporal-fixture',[helper.make_tensor_value_info('input',dtype,[1,t,3,h,w])],
            [helper.make_tensor_value_info('output',dtype,[1,3,h,w])])
        model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)],ir_version=10)
        onnx.checker.check_model(model);return model.SerializeToString()
    variants={}
    for name,t,dtype in [('three',3,TensorProto.FLOAT16),('five',5,TensorProto.FLOAT16),('fp32',5,TensorProto.FLOAT)]:
        path=case/(name+'.onnx');path.write_bytes(fixture(t,dtype));variants[name]=path
    assert len({x.stat().st_size for x in variants.values()})==1
    conf=case/'temporal.conf';conf.write_text(Path(s['conf']).read_text().replace(Path(s['model']).stem,'temporal-fixture'))
    def invoke(label,library,initial,replacement=None,post=None,seed=None):
        root=case/label;root.mkdir(exist_ok=True);models=root/'models';models.mkdir(exist_ok=True)
        target=models/'temporal-fixture.onnx'
        if not target.exists():shutil.copyfile(initial,target)
        if seed:
            for plan in seed.glob('*.engine'):
                if not (models/plan.name).exists():shutil.copyfile(plan,models/plan.name)
        start=root/'start';start.touch();receipt=root/'result.json'
        if receipt.exists():return json.loads(receipt.read_text()),models
        spec=dict(library=library,models=str(models),conf=str(conf),trtexec=s['trtexec'],input=s['input'],
            output=str(root/'result'),start=str(start),replacement_target=str(target))
        if replacement:spec['model_replacement']=str(replacement)
        if post:spec['post_model_replacement']=str(post)
        path=root/'spec.json';save(path,spec)
        with (root/'process.log').open('w') as log:
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('key_lock_gpu_worker.py')),str(path)],
                env=dict(os.environ,LD_LIBRARY_PATH=s['runtime']),stdout=log,stderr=subprocess.STDOUT,timeout=45)
        assert r.returncode==0,(root/'process.log').read_text()[-3000:]
        return json.loads(receipt.read_text()),models
    if a.phase=='static':
        before=json.loads((case/'before/result.json').read_text())
        assert before['configure_status']<0
        after,_=invoke('static-after',s['after'],variants['three'])
        assert after['configure_status']==1 and after['initial_radius']==1,after
        save(summary,dict(passed=True,before_status=before['configure_status'],after_status=1,
            static_temporal_auto_profiles_removed=True,synthetic_model=True))
        print('Static temporal regression qualified');sys.exit()
    before,seed=invoke('before',s['before'],variants['three'],variants['five'])
    assert before['configure_status']==1 and before['initial_radius']==1 and before['reconfigured_status']<0,before
    after,models=invoke('after',s['after'],variants['three'],variants['five'],variants['fp32'],seed)
    assert after['configure_status']==after['reconfigured_status']==1 and after['reconfigured_radius']==2,after
    assert after['post_reconfigure_status']<0 and 'fp32' in after['post_reconfigure_error'],after
    fresh,_=invoke('fresh',s['after'],variants['five'],seed=models)
    assert fresh['configure_status']==1 and fresh['initial_radius']==2
    assert np.array_equal(np.load(case/'after/result.npy'),np.load(case/'fresh/result.npy'))
    result=dict(passed=True,same_size_mtime_window_change_reclassified=True,before_status=before['reconfigured_status'],
        after_status=after['reconfigured_status'],after_radius=after['reconfigured_radius'],
        same_size_mtime_type_change_refused_before_builder=True,same_plan_changed_bytes=0,
        synthetic_model=True,real_temporal_model_quality_claimed=False)
save(summary,result);print(json.dumps(result,indent=2))
