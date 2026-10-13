#!/usr/bin/env python3
"""Prepares the AnimeJaNai SPAN models for the two native Apple engines.

For each 2x SPAN model (pixel-unshuffle -> convolutions -> pixel-shuffle) this writes, next to
each other in OUTPUT:

  NAME.ajm / NAME.ajw   the network as a list of operations and its weights in half floats,
                        read by the Metal engine (and by the reference executor of the tests);
  NAME.mlpackage        a Core ML ML Program built by coremltools for a template size, with an
                        8-bit image in and an 8-bit image out;
  NAME.mlpatch          where that template stores its sizes, so that the engine can make the
                        model for any tile size at run time without coremltools.

The models only accept even sizes here: the engines cut frames in even tiles, so the reflect
padding and the final crop of the ONNX graph (odd sizes) are left out.

Why a patch table: Core ML is fastest with a fixed input size, and the size depends on the video.
Every size in the saved model is a protobuf varint. Sizes from 128 to 16383 take two bytes, so a
model converted for another size has the same bytes everywhere else: the table lists the offsets
of those two-byte values (found by converting twice and comparing), and a third conversion checks
that a patched template is byte for byte what coremltools writes for that size.

usage: convert_models.py ONNX_DIR OUTPUT [--no-coreml] [--only SUBSTRING] [--keep-check DIR]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import onnx
from onnx import numpy_helper

# Template sizes (height, width). Each size and its half and double must be a two-byte varint,
# and the six values of a template must differ so that a changed value names its kind.
TEMPLATE = (1016, 2040)
OTHER = (616, 1240)
CHECK = (720, 1280)
KINDS = ('h', 'w', 'h2', 'w2', 'hh', 'ww')


def kind_values(size):
    h, w = size
    return {'h': h, 'w': w, 'h2': h // 2, 'w2': w // 2, 'hh': 2 * h, 'ww': 2 * w}


def attributes(node):
    return {a.name: onnx.helper.get_attribute_value(a) for a in node.attribute}


def read_network(path):
    """The ONNX graph as a list of operations on numbered tensors. Tensor 0 is the RGB input,
    planar, 0..1. Returns (operations, weights, output tensor)."""
    model = onnx.load(path)
    graph = model.graph
    init = {t.name: numpy_helper.to_array(t) for t in graph.initializer}
    nodes = list(graph.node)
    first = next(i for i, n in enumerate(nodes) if n.op_type == 'Conv')
    last = next(i for i, n in enumerate(nodes) if n.op_type == 'DepthToSpace')
    unshuffle = [n for n in nodes[:first] if n.op_type == 'Transpose' and attributes(n).get('perm') == [0, 1, 3, 5, 2, 4]]
    assert len(unshuffle) == 1, 'not a pixel-unshuffle SPAN model: ' + str(path)
    assert init[nodes[first].input[1]].shape[1] == 12, 'the first convolution must take the unshuffled RGB (12 channels)'
    shuffle = attributes(nodes[last])
    assert shuffle.get('mode') == b'CRD' and shuffle.get('blocksize') == 4, 'unsupported pixel shuffle'
    assert all(n.op_type == 'Slice' for n in nodes[last + 1:]), 'unsupported output transform'

    ids = {nodes[first].input[0]: 1}       # tensor 1: the unshuffled input
    ops = [('unshuffle', 1, 0, 2)]
    weights = []                           # numpy arrays, float16, in file order

    def tensor(name):
        assert name in ids, 'operand is not a tensor of the network: ' + name
        return ids[name]

    def new(name):
        ids[name] = len(ids) + 1
        return ids[name]

    offset = 0
    for node in nodes[first:last]:
        a = attributes(node)
        if node.op_type == 'Conv':
            w = init[node.input[1]].astype(np.float16)
            b = init[node.input[2]].astype(np.float16)
            o, i, kh, kw = w.shape
            pads = list(a.get('pads', [0, 0, 0, 0]))
            assert kh == kw and a.get('group', 1) == 1 and list(a.get('strides', [1, 1])) == [1, 1]
            assert list(a.get('dilations', [1, 1])) == [1, 1] and pads == [pads[0]] * 4 and b.shape == (o,)
            assert a.get('auto_pad', b'NOTSET') == b'NOTSET' and pads[0] == (kh - 1) // 2, 'convolutions must keep the size'
            source = tensor(node.input[0])
            ops.append(('conv', new(node.output[0]), source, o, i, kh, 1, pads[0], offset, offset + w.size))
            weights += [w, b]
            offset += w.size + b.size
        elif node.op_type in ('Relu', 'Tanh', 'Sigmoid'):
            source = tensor(node.input[0])
            ops.append((node.op_type.lower(), new(node.output[0]), source))
        elif node.op_type in ('Add', 'Mul'):
            x, y = tensor(node.input[0]), tensor(node.input[1])
            ops.append((node.op_type.lower(), new(node.output[0]), x, y))
        elif node.op_type == 'Concat':
            assert a['axis'] == 1
            sources = [tensor(x) for x in node.input]
            ops.append(('concat', new(node.output[0]), len(sources), *sources))
        else:
            raise AssertionError('unsupported operator in a SPAN model: ' + node.op_type)
    source = tensor(nodes[last].input[0])
    out = new(nodes[last].output[0])
    ops.append(('shuffle', out, source, 4))
    return ops, weights, out


def write_ajm(ops, weights, out, name, folder):
    lines = ['AJM 1', 'scale 2', 'weights %s.ajw float16 %d' % (name, sum(w.size for w in weights)),
             'tensors %d' % (max(op[1] for op in ops) + 1), 'output %d' % out]
    lines += ['op ' + ' '.join(str(x) for x in op) for op in ops]
    (folder / (name + '.ajm')).write_text('\n'.join(lines) + '\n')
    with open(folder / (name + '.ajw'), 'wb') as f:
        for w in weights:
            f.write(w.astype('<f2').tobytes())


def rebuilt_onnx(ops, weights, out, h, w):
    """The operation list as an ONNX model of fixed size, to compare with the original."""
    from onnx import helper, TensorProto
    flat = np.concatenate([x.reshape(-1) for x in weights]).astype(np.float32)
    nodes, inits = [], []
    name = lambda t: 't%d' % t
    for op in ops:
        kind, dst = op[0], op[1]
        if kind == 'unshuffle':
            # out[c*4 + dy*2 + dx, y, x] = in[c, 2y + dy, 2x + dx]
            k = np.zeros((12, 3, 2, 2), np.float32)
            for c in range(3):
                for dy in range(2):
                    for dx in range(2):
                        k[c * 4 + dy * 2 + dx, c, dy, dx] = 1
            inits.append(numpy_helper.from_array(k, 'unshuffle_w'))
            nodes.append(helper.make_node('Conv', [name(op[2]), 'unshuffle_w'], [name(dst)], kernel_shape=[2, 2], strides=[2, 2]))
        elif kind == 'conv':
            _, _, src, o, i, k, stride, pad, w_off, b_off = op
            inits.append(numpy_helper.from_array(flat[w_off:w_off + o * i * k * k].reshape(o, i, k, k), 'w%d' % dst))
            inits.append(numpy_helper.from_array(flat[b_off:b_off + o], 'b%d' % dst))
            nodes.append(helper.make_node('Conv', [name(src), 'w%d' % dst, 'b%d' % dst], [name(dst)],
                                          kernel_shape=[k, k], strides=[stride, stride], pads=[pad] * 4))
        elif kind in ('relu', 'tanh', 'sigmoid'):
            nodes.append(helper.make_node(kind.capitalize(), [name(op[2])], [name(dst)]))
        elif kind in ('add', 'mul'):
            nodes.append(helper.make_node(kind.capitalize(), [name(op[2]), name(op[3])], [name(dst)]))
        elif kind == 'concat':
            nodes.append(helper.make_node('Concat', [name(t) for t in op[3:]], [name(dst)], axis=1))
        elif kind == 'shuffle':
            nodes.append(helper.make_node('DepthToSpace', [name(op[2])], [name(dst)], blocksize=op[3], mode='CRD'))
    graph = helper.make_graph(nodes, 'ajm', [helper.make_tensor_value_info('t0', TensorProto.FLOAT, [1, 3, h, w])],
                              [helper.make_tensor_value_info(name(out), TensorProto.FLOAT, [1, 3, 2 * h, 2 * w])], inits)
    return helper.make_model(graph, opset_imports=[helper.make_opsetid('', 20)], ir_version=9)


def check_against_onnx(path, ops, weights, out):
    """The operation list must compute what the original model computes."""
    import onnxruntime as ort
    rng = np.random.default_rng(7)
    worst = 0.0
    for h, w in ((64, 96), (128, 64)):
        x = rng.random((1, 3, h, w), dtype=np.float32)
        original = ort.InferenceSession(str(path), providers=['CPUExecutionProvider'])
        ref = original.run(None, {'input': x.astype(np.float16)})[0].astype(np.float32)
        mine = ort.InferenceSession(rebuilt_onnx(ops, weights, out, h, w).SerializeToString(), providers=['CPUExecutionProvider'])
        got = mine.run(None, {'t0': x})[0]
        assert got.shape == ref.shape, (got.shape, ref.shape)
        worst = max(worst, float(np.abs(got - ref).max()))
    # The original runs in half floats, the rebuilt list in single floats: a few 1/1000.
    assert worst < 0.02, 'the operation list differs from the ONNX model by %f' % worst
    return worst


def build_coreml(ops, weights, out, h, w, package):
    """One ML Program for inputs of h x w. Every operation is named, so that two conversions only
    differ by their sizes."""
    import coremltools as ct
    from coremltools.converters.mil import Builder as mb
    flat = np.concatenate([x.reshape(-1) for x in weights]).astype(np.float32)

    @mb.program(input_specs=[mb.TensorSpec(shape=(1, 3, h, w))], opset_version=ct.target.macOS13)
    def program(input):
        t = {0: input}
        for n, op in enumerate(ops):
            kind, dst = op[0], op[1]
            label = 'n%d_%s' % (n, kind)
            if kind == 'unshuffle':
                k = np.zeros((12, 3, 2, 2), np.float32)
                for c in range(3):
                    for dy in range(2):
                        for dx in range(2):
                            k[c * 4 + dy * 2 + dx, c, dy, dx] = 1
                t[dst] = mb.conv(x=t[op[2]], weight=k, strides=[2, 2], pad_type='valid', name=label)
            elif kind == 'conv':
                _, _, src, o, i, k, stride, pad, w_off, b_off = op
                t[dst] = mb.conv(x=t[src], weight=flat[w_off:w_off + o * i * k * k].reshape(o, i, k, k),
                                 bias=flat[b_off:b_off + o], strides=[stride, stride], pad_type='custom',
                                 pad=[pad] * 4, dilations=[1, 1], groups=1, name=label)
            elif kind == 'relu':
                t[dst] = mb.relu(x=t[op[2]], name=label)
            elif kind == 'tanh':
                t[dst] = mb.tanh(x=t[op[2]], name=label)
            elif kind == 'sigmoid':
                t[dst] = mb.sigmoid(x=t[op[2]], name=label)
            elif kind == 'add':
                t[dst] = mb.add(x=t[op[2]], y=t[op[3]], name=label)
            elif kind == 'mul':
                t[dst] = mb.mul(x=t[op[2]], y=t[op[3]], name=label)
            elif kind == 'concat':
                t[dst] = mb.concat(values=[t[s] for s in op[3:]], axis=1, name=label)
            elif kind == 'shuffle':
                t[dst] = mb.pixel_shuffle(x=t[op[2]], upscale_factor=op[3], name=label)
        # 8-bit image out: 0..255, rounded here so that the result does not depend on how Core ML
        # converts floats to bytes.
        y = mb.clip(x=t[out], alpha=0.0, beta=1.0, name='to_unit')
        y = mb.mul(x=y, y=255.0, name='to_bytes')
        return mb.round(x=y, name='output')

    # coremltools only reads `inputs` for a program built in its own language: the image output
    # is declared on the program itself, as its other front ends do.
    program.functions['main'].set_output_types([ct.ImageType(name='output', color_layout=ct.colorlayout.RGB)])
    model = ct.convert(
        program, convert_to='mlprogram', skip_model_load=True,
        inputs=[ct.ImageType(name='input', shape=(1, 3, h, w), scale=1.0 / 255.0, color_layout=ct.colorlayout.RGB)],
        compute_precision=ct.precision.FLOAT16, minimum_deployment_target=ct.target.macOS13)
    described = model.get_spec().description
    assert described.input[0].type.WhichOneof('Type') == 'imageType', 'the model input is not an image'
    assert described.output[0].type.WhichOneof('Type') == 'imageType', 'the model output is not an image'
    if os.path.exists(package):
        shutil.rmtree(package)
    model.save(str(package))
    # Maps are written in a stable order, so that two sizes give comparable files.
    spec_path = Path(package) / 'Data/com.apple.CoreML/model.mlmodel'
    spec = ct.utils.load_spec(str(package))
    spec_path.write_bytes(spec.SerializeToString(deterministic=True))


def varint2(value):
    assert 128 <= value <= 16383, value
    return bytes([(value & 0x7F) | 0x80, value >> 7])


def patch_table(a_bytes, b_bytes):
    """Offsets of the two-byte sizes in the template, by kind."""
    assert len(a_bytes) == len(b_bytes), 'two sizes gave models of different lengths (%d, %d)' % (len(a_bytes), len(b_bytes))
    va, vb = kind_values(TEMPLATE), kind_values(OTHER)
    table = {k: [] for k in KINDS}
    covered = set()
    for p in range(len(a_bytes)):
        if a_bytes[p] == b_bytes[p] or p in covered:
            continue
        for start in (p, p - 1):
            found = [k for k in KINDS if a_bytes[start:start + 2] == varint2(va[k]) and b_bytes[start:start + 2] == varint2(vb[k])]
            if found:
                table[found[0]].append(start)
                covered.update((start, start + 1))
                break
        else:
            raise AssertionError('byte %d differs between two sizes and is not one of the sizes' % p)
    assert all(table[k] for k in ('h', 'w', 'hh', 'ww')), 'input or output sizes not found in the model'
    return table


def apply_patch(template, table, size):
    data = bytearray(template)
    for kind, value in kind_values(size).items():
        for offset in table[kind]:
            data[offset:offset + 2] = varint2(value)
    return bytes(data)


def coreml_for(path, name, folder, work, keep_check=None):
    """Template package and patch table. Each size is converted in its own process: coremltools
    numbers the operations it adds, and the numbering must start the same way every time."""
    packages = {}
    for label, size in (('template', TEMPLATE), ('other', OTHER), ('check', CHECK)):
        packages[label] = work / ('%s-%s.mlpackage' % (name, label))
        subprocess.run([sys.executable, __file__, '--one', str(path), str(size[0]), str(size[1]), str(packages[label])],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    spec = lambda label: (packages[label] / 'Data/com.apple.CoreML/model.mlmodel').read_bytes()
    blob = lambda label: (packages[label] / 'Data/com.apple.CoreML/weights/weight.bin').read_bytes()
    assert blob('template') == blob('other') == blob('check'), 'the weights file depends on the size'
    table = patch_table(spec('template'), spec('other'))
    assert apply_patch(spec('template'), table, CHECK) == spec('check'), 'a patched template differs from a converted model'
    assert apply_patch(spec('template'), table, OTHER) == spec('other')
    if keep_check:
        kept = Path(keep_check) / ('%s-%dx%d.mlpackage' % (name, CHECK[1], CHECK[0]))
        if kept.exists():
            shutil.rmtree(kept)
        shutil.copytree(packages['check'], kept)
    target = folder / (name + '.mlpackage')
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(packages['template'], target)
    lines = ['AJP 1', 'template %d %d' % TEMPLATE, 'model Data/com.apple.CoreML/model.mlmodel %d' % len(spec('template'))]
    lines += ['%s %d %s' % (k, len(table[k]), ' '.join(str(o) for o in table[k])) for k in KINDS]
    (folder / (name + '.mlpatch')).write_text('\n'.join(lines).rstrip() + '\n')
    return {k: len(v) for k, v in table.items()}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--one':
        path, h, w, package = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        ops, weights, out = read_network(path)
        build_coreml(ops, weights, out, h, w, package)
        return
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('onnx_dir', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--no-coreml', action='store_true', help='only the Metal format (no coremltools needed)')
    p.add_argument('--only', default='', help='only the models whose name contains this')
    p.add_argument('--keep-check', type=Path, help='folder that receives the model coremltools makes for %dx%d, for the tests' % (CHECK[1], CHECK[0]))
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    models = sorted(f for f in a.onnx_dir.glob('*SPANF3*.onnx') if not f.name.endswith('.coreml.onnx') and a.only in f.name)
    assert models, 'no SPAN model in ' + str(a.onnx_dir)
    report = {}
    with tempfile.TemporaryDirectory() as work:
        for path in models:
            name = path.name[:-len('.onnx')]
            ops, weights, out = read_network(path)
            write_ajm(ops, weights, out, name, a.output)
            entry = {'operations': len(ops), 'weights': int(sum(w.size for w in weights)),
                     'max_difference_from_onnx': round(check_against_onnx(path, ops, weights, out), 5)}
            if not a.no_coreml:
                if a.keep_check:
                    a.keep_check.mkdir(parents=True, exist_ok=True)
                entry['size_fields'] = coreml_for(path, name, a.output, Path(work), a.keep_check)
            report[name] = entry
            print(name, json.dumps(entry))
    (a.output / 'apple-models.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
