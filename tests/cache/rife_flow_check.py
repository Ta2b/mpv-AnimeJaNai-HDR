#!/usr/bin/env python3
"""Short content, corruption and publication checks using the real cache exporter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import onnx
from onnx import helper, TensorProto

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);root=Path(__file__).resolve().parents[2]
exe=out/'flow-cache'
subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
    str(root/'tests/cache/rife_flow_cli.cpp'),str(root/'native/linux-ort/rife_flow_cache.cpp'),
    str(root/'native/linux-ort/onnx_flow.cpp'),'-o',str(exe)],check=True)
models=out/'models';(models/'weights').mkdir(parents=True,exist_ok=True)
weights=models/'weights/data.bin';weights.write_bytes(bytes(range(16)))
tensor=TensorProto(name='raw-flow',data_type=TensorProto.FLOAT,dims=[4],data_location=TensorProto.EXTERNAL)
tensor.external_data.add(key='location',value='weights/data.bin')
nodes=[helper.make_node('Reshape',['raw-flow','shape'],['reshape']),
    helper.make_node('Cast',['reshape'],['cast'],to=1),helper.make_node('Mul',['cast','scale'],['scaled']),
    helper.make_node('Add',['scaled','mesh'],['xy']),helper.make_node('Transpose',['xy'],['grid']),
    helper.make_node('GridSample',['img0','grid'],['warped']),helper.make_node('Sigmoid',['mask-in'],['mask'])]
graph=helper.make_graph(nodes,'fixture',[],[helper.make_tensor_value_info('warped',TensorProto.FLOAT,[1,3,16,16])],[tensor])
model=helper.make_model(graph);source=models/'rife.onnx';source.write_bytes(model.SerializeToString())
cache=out/'cache';cache.mkdir(exist_ok=True)
legacy=cache/'rife.flow.onnx';legacy.write_bytes(b'legacy stale flow must be ignored')
def run(*args,ok=True):
    r=subprocess.run([str(exe),*map(str,args)],capture_output=True,text=True)
    assert (r.returncode==0)==ok,r.stderr
    return r.stdout.strip(),r.stderr
first,_=run(source,cache);first=Path(first)
assert legacy.read_bytes()==b'legacy stale flow must be ignored'
expanded=onnx.load(first,load_external_data=False)
assert [o.name for o in expanded.graph.output]==['warped','raw-flow','mask']
assert expanded.graph.initializer[0].SerializeToString()==tensor.SerializeToString()
assert (first.parent/'weights/data.bin').read_bytes()==weights.read_bytes()
stamp=weights.stat();weights.write_bytes(bytes(reversed(range(16))))
os.utime(weights,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
changed,_=run(source,cache);changed=Path(changed);assert changed!=first
model.producer_version='new graph';source.write_bytes(model.SerializeToString())
new_graph,_=run(source,cache);new_graph=Path(new_graph);assert new_graph!=changed
assert onnx.load(new_graph,load_external_data=False).producer_version=='new graph'

# Corrupt bytes, not just absence: exporter must preserve and replace the damaged entry.
correct=new_graph.read_bytes();new_graph.write_bytes(b'corrupt')
repaired,diagnostic=run(source,cache);assert Path(repaired).read_bytes()==correct
assert any(f.read_bytes()==b'corrupt' for f in (cache/'rife-flow-v3').glob('.invalid-*/preserved/rife.flow.onnx'))
assert 'rife-flow-outputs-v2' in diagnostic
warm_stamp=Path(repaired).stat().st_mtime_ns;warm,_=run(source,cache)
assert warm==repaired and Path(warm).stat().st_mtime_ns==warm_stamp

# Two independent builders of one key: both return the same complete result.
parallel=out/'parallel-cache'
processes=[subprocess.Popen([str(exe),str(source),str(parallel)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
results=[p.communicate(timeout=10) for p in processes]
assert all(p.returncode==0 for p in processes),results
assert len(set(r[0].strip() for r in results))==1
assert Path(results[0][0].strip()).read_bytes()==correct
assert not list(parallel.rglob('.part-*'))

# Exercise traversal of sparse tensors, nested graphs and local function attributes.
extra=TensorProto();extra.CopyFrom(tensor);extra.external_data[0].value='nested.bin'
nested=helper.make_graph([],'nested',[],[],[extra])
attribute=onnx.AttributeProto(name='body',type=onnx.AttributeProto.GRAPH);attribute.g.CopyFrom(nested)
model.graph.node[0].attribute.append(attribute)
sparse=model.graph.sparse_initializer.add();sparse.values.CopyFrom(extra);sparse.indices.CopyFrom(extra)
function=model.functions.add(name='local',domain='fixture');function.attribute_proto.add().CopyFrom(attribute)
source.write_bytes(model.SerializeToString())
locations,_=run('--locations',source);assert locations.splitlines()==['nested.bin','weights/data.bin']

# Missing weights, unsafe relative locations and truncated metadata fail closed.
run(source,cache,ok=False)
model.graph.initializer[0].external_data[0].value='../outside.bin'
source.write_bytes(model.SerializeToString());run(source,cache,ok=False)
source.write_bytes(b'\x3a\xff');run(source,cache,ok=False)
summary=dict(passed=True,source_weights_change_invalidates=True,source_graph_change_invalidates=True,
    legacy_cache_ignored_and_preserved=True,export_preserves_graph_and_weights=True,
    damaged_cache_preserved_and_repaired=True,warm_hit_does_not_rewrite=True,
    simultaneous_builders_complete=True,nested_sparse_function_weights_detected=True,
    missing_unsafe_truncated_inputs_refused=True,flow_transform_version='rife-flow-outputs-v2')
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
