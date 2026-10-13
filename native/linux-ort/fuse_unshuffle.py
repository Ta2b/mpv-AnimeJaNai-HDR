#!/usr/bin/env python3
"""Rewrites the pixel-unshuffle of an AnimeJaNai model as one strided convolution.

The models unshuffle with Reshape (rank 6) -> Transpose -> Reshape. Core ML refuses tensors of
rank above 5, so ONNX Runtime cuts the graph in two Core ML parts with these nodes on the CPU in
between. A 2x2 convolution with stride 2 and one-hot weights computes exactly the same thing:
    out[c*4 + dy*2 + dx, y, x] = in[c, 2y + dy, 2x + dx]
and lets Core ML take the whole graph.

usage: fuse_unshuffle.py INPUT.onnx OUTPUT.onnx
"""
import sys
import numpy as np
import onnx
from onnx import helper, numpy_helper

src, dst = sys.argv[1], sys.argv[2]
model = onnx.load(src)
graph = model.graph
producer = {out: node for node in graph.node for out in node.output}
consumers = {}
for node in graph.node:
    for name in node.input:
        consumers.setdefault(name, []).append(node)

elem = graph.input[0].type.tensor_type.elem_type
dtype = np.float16 if elem == onnx.TensorProto.FLOAT16 else np.float32
channels = graph.input[0].type.tensor_type.shape.dim[1].dim_value
assert channels > 0, 'the model input must have a fixed channel count'

fused = 0
for transpose in [n for n in graph.node if n.op_type == 'Transpose']:
    perm = next((list(a.ints) for a in transpose.attribute if a.name == 'perm'), None)
    if perm != [0, 1, 3, 5, 2, 4]:
        continue
    before = producer.get(transpose.input[0])
    after = consumers.get(transpose.output[0], [])
    if not before or before.op_type != 'Reshape' or len(after) != 1 or after[0].op_type != 'Reshape':
        continue
    weights = np.zeros((channels * 4, channels, 2, 2), dtype=dtype)
    for c in range(channels):
        for dy in range(2):
            for dx in range(2):
                weights[c * 4 + dy * 2 + dx, c, dy, dx] = 1
    name = 'aji_unshuffle_weight_%d' % fused
    graph.initializer.append(numpy_helper.from_array(weights, name))
    conv = helper.make_node('Conv', [before.input[0], name], [after[0].output[0]], name='aji_unshuffle_%d' % fused,
                            kernel_shape=[2, 2], strides=[2, 2], pads=[0, 0, 0, 0])
    index = list(graph.node).index(before)
    for node in (before, transpose, after[0]):
        graph.node.remove(node)
    graph.node.insert(index, conv)
    fused += 1
assert fused >= 1, 'no pixel-unshuffle pattern found in ' + src

# Drop the shape arithmetic that only fed the removed nodes.
while True:
    used = {name for node in graph.node for name in node.input} | {o.name for o in graph.output}
    dead = [node for node in graph.node if not any(out in used for out in node.output)]
    if not dead:
        break
    for node in dead:
        graph.node.remove(node)
used = {name for node in graph.node for name in node.input}
for init in [i for i in graph.initializer if i.name not in used]:
    graph.initializer.remove(init)
del graph.value_info[:]

# The surviving nodes must still be in a valid order: the convolution took the first Reshape's place.
onnx.checker.check_model(model)
onnx.save(model, dst)
ops = {}
for node in graph.node:
    ops[node.op_type] = ops.get(node.op_type, 0) + 1
print('%s: %d unshuffle fused, nodes %s' % (dst, fused, ops))
