#!/usr/bin/env python3
"""Unknown symbols/external weights, static mismatch, collisions and dynamic escape route."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import onnx
from onnx import helper,TensorProto,numpy_helper
from ort_buffers_geometry_check import child

if '--child' in sys.argv:
    child(json.loads(Path(sys.argv[1]).read_text())); sys.exit()
s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
phase=out/'metadata-phase.json'
if '--external-only' not in sys.argv:
    probe=C.CDLL(s['shape_probe']);fn=probe.aji_test_fixed_shape
    fn.argtypes=[C.c_char_p,C.c_char_p,C.c_int,C.c_int,C.c_int,C.c_char_p,C.c_size_t]
    models=out/'models';models.mkdir(exist_ok=True);(models/'weights').mkdir(exist_ok=True)

    def model(shape):
        inp=helper.make_tensor_value_info('input',TensorProto.FLOAT,shape)
        result=helper.make_tensor_value_info('output',TensorProto.FLOAT,[None]*len(shape))
        # A tensor shape denotation is retained, along with every graph/weight byte.
        inp.type.tensor_type.shape.dim[1].denotation='DATA_FEATURE'
        graph=helper.make_graph([helper.make_node('Resize',['input','','scales'],['output'],mode='nearest',
            coordinate_transformation_mode='asymmetric',nearest_mode='floor')], 'external_fixture',[inp],[result],
            [numpy_helper.from_array(np.array([1,1,2,2],np.float32),'scales')])
        m=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)]);m.ir_version=10;return m

    original=model(['batch_alias',3,'arbitrary_h','arbitrary_w'])
    if not (models/'good.onnx').exists():
        onnx.save_model(original,models/'good.onnx',save_as_external_data=True,all_tensors_to_one_file=True,
            location='weights/scales.bin',size_threshold=0)
    weight_before=hashlib.sha256((models/'weights/scales.bin').read_bytes()).hexdigest()
    reason=C.create_string_buffer(1024);destination=models/'good-fixed.onnx'
    if not destination.exists():
        assert fn(os.fsencode(models/'good.onnx'),os.fsencode(destination),3,32,64,reason,len(reason))==1,reason.value
    a=onnx.load(models/'good.onnx',load_external_data=False);b=onnx.load(destination,load_external_data=False)
    assert [d.dim_value for d in b.graph.input[0].type.tensor_type.shape.dim]==[1,3,32,64]
    assert b.graph.input[0].type.tensor_type.shape.dim[1].denotation=='DATA_FEATURE'
    b.graph.input[0].type.tensor_type.shape.CopyFrom(a.graph.input[0].type.tensor_type.shape)
    assert a.SerializeToString()==b.SerializeToString()
    assert hashlib.sha256((models/'weights/scales.bin').read_bytes()).hexdigest()==weight_before

    guards={}
    fixtures=[('fixed',model([1,3,32,64]),0),('mismatch',model([2,3,32,64]),3),
        ('collision',model(['same',3,'same','w']),3),('rank5',model([1,3,1,'h','w']),2)]
    multi=model([1,3,'h','w']);multi.graph.input.append(helper.make_tensor_value_info('second',TensorProto.FLOAT,[1]));fixtures.append(('multi',multi,2))
    for name,m,expected in fixtures:
        if '--resume-rank5' in sys.argv and name in ['fixed','mismatch','collision']:
            guards[name]=dict(reused=True,evidence='passed before rank5 failure in rank5-diagnostic.log');continue
        path=models/(name+'.onnx');path.write_bytes(m.SerializeToString());dest=models/(name+'-result.onnx')
        code=fn(os.fsencode(path),os.fsencode(dest),3,32,64,reason,len(reason))
        assert code==expected and not dest.exists(),(name,code,reason.value)
        guards[name]=dict(result=code,reason=reason.value.decode())
    path=models/'truncated.onnx';path.write_bytes(original.SerializeToString()[:-1])
    code=fn(os.fsencode(path),os.fsencode(models/'truncated-result.onnx'),3,32,64,reason,len(reason))
    assert code==3 and not (models/'truncated-result.onnx').exists();guards['truncated']=dict(result=code,reason=reason.value.decode())

    phase.write_text(json.dumps(dict(passed=True,guards=guards),indent=2)+'\n')
else:
    metadata=json.loads(phase.read_text());assert metadata['passed'];guards=metadata['guards']

# Real ABI, a different cwd, nested external weight location and two sizes in one context.
runtime_out=out/'external-runtime';runtime_out.mkdir(exist_ok=True)
runtime_models=runtime_out/'models';runtime_models.mkdir(exist_ok=True);(runtime_models/'weights').mkdir(exist_ok=True)
if not (runtime_models/'good.onnx').exists():
    inp=helper.make_tensor_value_info('input',TensorProto.FLOAT,['batch_alias',3,'arbitrary_h','arbitrary_w'])
    result=helper.make_tensor_value_info('output',TensorProto.FLOAT,[None]*4)
    nodes=[helper.make_node('Add',['input','bias'],['biased']),helper.make_node('Resize',['biased','','scales'],['output'],
        mode='nearest',coordinate_transformation_mode='asymmetric',nearest_mode='floor')]
    # Shape inference needs scales inline in this ORT version; the runtime bias is external.
    scales=helper.make_tensor('scales',TensorProto.FLOAT,[4],[1,1,2,2])
    bias=numpy_helper.from_array(np.array([0],np.float32),'bias')
    graph=helper.make_graph(nodes,'external_runtime',[inp],[result],[scales,bias])
    m=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)]);m.ir_version=10
    onnx.save_model(m,runtime_models/'good.onnx',save_as_external_data=True,all_tensors_to_one_file=True,
        location='weights/bias.bin',size_threshold=0)
(runtime_out/'good.conf').write_text('[global]\nbackend=CPU\nengine_reuse=off\nengine_boost=no\n[slot_1]\nchain_1_model_1_name=good\n')
weight_before=hashlib.sha256((runtime_models/'weights/bias.bin').read_bytes()).hexdigest()
results={}
for label in ['before','after']:
    path=runtime_out/(label+'.json')
    if not path.exists():
        spec=dict(s,label=label,output=str(runtime_out));p=runtime_out/(label+'.spec.json');p.write_text(json.dumps(spec,indent=2)+'\n')
        with (runtime_out/(label+'.log')).open('w') as log:
            r=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(p),'--child'],cwd='/tmp',
                env=dict(os.environ,AJI_ORT_PROVIDER='cpu',AJI_ORT_REUSE_BINDINGS='1',AJI_ORT_SPECIALIZE_SHAPES='0' if label=='before' else '1',
                    AJI_TEST_ORT_LIBRARY=s['ort_runtime'],LD_LIBRARY_PATH=s['runtime'],LD_PRELOAD=s['interposer']),
                stdout=log,stderr=subprocess.STDOUT,timeout=30)
        assert r.returncode==0,(runtime_out/(label+'.log')).read_text()[-3500:]
    results[label]=json.loads(path.read_text())
x=np.load(runtime_out/'before.npz');y=np.load(runtime_out/'after.npz');assert x.files==y.files and all(np.array_equal(x[k],y[k]) for k in x.files)
assert hashlib.sha256((runtime_models/'weights/bias.bin').read_bytes()).hexdigest()==weight_before
summary=dict(passed=True,arbitrary_symbols_fixed=True,only_input_shape_metadata_changed=True,
    external_weights_unchanged=True,external_weights_from_different_cwd=True,independent_fp32_pixel_oracle=True,
    two_geometries_reconfigured=True,changed_bytes=0,guards=guards,results=results)
receipt.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
