#!/usr/bin/env python3
"""Test fixture only: promote FP16 types/weights exactly to FP32, never installed models.

This exercises the FP32 motion storage. Off/on use the same promoted graph;
its pixels are not claimed equivalent to the shipped FP16 graph.
"""
import sys
from pathlib import Path
import numpy as np
import onnx
from onnx import TensorProto, AttributeProto, numpy_helper

source, destination = map(Path, sys.argv[1:])
assert source.resolve() != destination.resolve() and not destination.exists()
model = onnx.load(source)
def promote_tensor(t):
    if t.data_type == TensorProto.FLOAT16:
        t.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), t.name))
def promote_graph(g):
    for v in list(g.input) + list(g.output) + list(g.value_info):
        if v.type.tensor_type.elem_type == TensorProto.FLOAT16:
            v.type.tensor_type.elem_type = TensorProto.FLOAT
    for t in g.initializer: promote_tensor(t)
    for node in g.node:
        for a in node.attribute:
            if node.op_type == 'Cast' and a.name == 'to' and a.i == TensorProto.FLOAT16:
                a.i = TensorProto.FLOAT
            if a.type == AttributeProto.TENSOR: promote_tensor(a.t)
            elif a.type == AttributeProto.TENSORS:
                for t in a.tensors: promote_tensor(t)
            elif a.type == AttributeProto.GRAPH: promote_graph(a.g)
            elif a.type == AttributeProto.GRAPHS:
                for graph in a.graphs: promote_graph(graph)
promote_graph(model.graph)
onnx.checker.check_model(model)
destination.parent.mkdir(parents=True, exist_ok=True)
onnx.save(model, destination)
print('FP32 test fixture created; installed models unchanged')
