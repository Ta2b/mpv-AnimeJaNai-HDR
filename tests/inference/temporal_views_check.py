#!/usr/bin/env python3
"""Build one small shared plan, then qualify temporal guards before/after without rebuilding."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import onnx
from onnx import helper, numpy_helper, TensorProto

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
summary=out/'summary.json'
if summary.exists():
    assert json.loads(summary.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
models=out/'models';models.mkdir(exist_ok=True)
graph=helper.make_graph([
    helper.make_node('Mul',['input','weights'],['weighted']),
    helper.make_node('ReduceSum',['weighted','axes'],['output'],keepdims=0)],
    'temporal-weighted-window',
    [helper.make_tensor_value_info('input',TensorProto.FLOAT16,[1,3,3,'h','w'])],
    [helper.make_tensor_value_info('output',TensorProto.FLOAT16,[1,3,'h','w'])],
    initializer=[numpy_helper.from_array(np.array([.1,.3,.6],np.float16).reshape(1,3,1,1,1),'weights'),
                 numpy_helper.from_array(np.array([1],np.int64),'axes')])
model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)],ir_version=10)
onnx.checker.check_model(model);onnx.save(model,models/'temporal-fixture.onnx')
base='[global]\nbackend=TensorRT\nlogging=yes\ntrt_engine_settings=--stronglyTyped --optShapes=input:%video_resolution% --builderOptimizationLevel=0 --memPoolSize=workspace:64M --skipInference\n[slot_1]\nchain_1_model_1_name=temporal-fixture\nchain_1_rife=no\nchain_1_model_1_temporal_scene_threshold='
for name,threshold in [('test.conf','0'),('cut.conf','0.1')]: (out/name).write_text(base+threshold+'\n')
calls=out/'calls';calls.mkdir(exist_ok=True);builder=out/'builder'
builder.write_text('#!'+sys.executable+'\nimport os,sys,json\nfrom pathlib import Path\n'
    +'Path('+repr(str(calls))+').joinpath(str(os.getpid())+".json").write_text(json.dumps(sys.argv[1:]))\n'
    +'os.execv('+repr(s['trtexec'])+',['+repr(s['trtexec'])+']+sys.argv[1:])\n');builder.chmod(0o755)
def invoke(label,library,build):
    result=out/(label+'.json')
    if result.exists():return json.loads(result.read_text())
    spec=dict(library=library,models=str(models),conf=str(out/'test.conf'),cut_conf=str(out/'cut.conf'),
        input=s['input'],output=str(out/label),trtexec=str(builder) if build else '/bin/false',cut_only=label=='after-cut-fix')
    path=out/(label+'.spec.json');path.write_text(json.dumps(spec,indent=2)+'\n')
    with (out/(label+'.log')).open('w') as log:
        p=subprocess.run([sys.executable,str(Path(__file__).with_name('temporal_views_probe.py')),str(path)],
            env=dict(os.environ,LD_LIBRARY_PATH=s['runtime']),stdout=log,stderr=subprocess.STDOUT,timeout=75)
    assert p.returncode==0,(out/(label+'.log')).read_text()[-3500:]
    return json.loads(result.read_text())
before=invoke('before',s['before'],True)
plans={p.name:p.read_bytes() for p in models.glob('*.engine')};assert len(plans)==1 and len(list(calls.glob('*.json')))==1
after=invoke('after',s['after'],False)
if '--cut-fix' in sys.argv[2:]:
    fixed=invoke('after-cut-fix',s['after'],False)
    after['results'].update(fixed['results'])
assert {p.name:p.read_bytes() for p in models.glob('*.engine')}==plans and len(list(calls.glob('*.json')))==1
assert before['results']['neighbor-color']['changed_bytes']>0
assert before['results']['neighbor-view']['changed_bytes']>0
assert before['results']['window-order']['changed_bytes']>0
assert before['results']['adjacent-cut']['changed_bytes']>0
assert all(v['changed_bytes']==0 for v in after['results'].values()),after
b=np.load(out/'before.npz');a=np.load(out/'after.npz')
assert np.array_equal(b['same-window'],a['same-window'])
result=dict(passed=True,real_rank5=True,synthetic_model=True,same_plan=True,real_builders=1,
    before=before['results'],after=after['results'],unchanged_window_changed_bytes=0,
    cut_fix_only_retest='--cut-fix' in sys.argv[2:],
    fps_claimed=False,real_temporal_model_quality_claimed=False)
summary.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
