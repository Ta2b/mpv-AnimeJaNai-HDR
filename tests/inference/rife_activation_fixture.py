#!/usr/bin/env python3
"""Prototype only: give ORT a native FP32 LeakyRelu between explicit FP16 casts.

Original weights and FP16 I/O remain intact. Alpha stays its original FLOAT
attribute: ORT_ALL3's captured expansion already uses that FLOAT value.
No equivalence or acceleration is claimed until the actual compiled outputs pass.
"""
import sys
from pathlib import Path
import onnx
from onnx import helper, TensorProto

source, destination = map(Path,sys.argv[1:])
assert source.resolve()!=destination.resolve() and not destination.exists()
model=onnx.load(source);before=[t.SerializeToString() for t in model.graph.initializer]
assert model.graph.input[0].type.tensor_type.elem_type==TensorProto.FLOAT16
names={v for n in model.graph.node for v in list(n.input)+list(n.output)}
nodes=[];count=0
for node in model.graph.node:
    if node.op_type!='LeakyRelu' or node.domain not in ['', 'ai.onnx']:
        nodes.append(node);continue
    assert len(node.input)==len(node.output)==1
    prefix=f'aji_cpu_leaky_{count}';x=prefix+'_float_in';y=prefix+'_float_out'
    assert x not in names and y not in names
    alpha=next((a.f for a in node.attribute if a.name=='alpha'),0.01)
    nodes.extend([helper.make_node('Cast',[node.input[0]],[x],name=prefix+'_cast_in',to=TensorProto.FLOAT),
        helper.make_node('LeakyRelu',[x],[y],name=prefix+'_native',alpha=alpha),
        helper.make_node('Cast',[y],[node.output[0]],name=prefix+'_cast_out',to=TensorProto.FLOAT16)])
    count+=1
assert count==53,count
del model.graph.node[:];model.graph.node.extend(nodes)
assert [t.SerializeToString() for t in model.graph.initializer]==before
onnx.checker.check_model(model);destination.parent.mkdir(parents=True,exist_ok=True);onnx.save(model,destination)
print(f'{count} prototype activations; original weights preserved, installed models unchanged')
