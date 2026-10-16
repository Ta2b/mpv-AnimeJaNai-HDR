#!/usr/bin/env python3
"""Inventory ONNX tensor types and operator boundaries, without executing or rewriting it.

Requires onnx. Declared/inferred types do not describe runtime accumulators.
External weight payloads are deliberately not loaded or claimed as hashed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def inspect(path):
    import onnx
    from onnx import TensorProto
    raw = path.read_bytes()
    model = onnx.load_model_from_string(raw)
    inference = 'succeeded'
    try:
        typed = onnx.shape_inference.infer_shapes(model, check_type=True, strict_mode=True)
    except (onnx.shape_inference.InferenceError, onnx.checker.ValidationError) as error:
        # Retain facts available in the source and identify every unknown type.
        typed = model
        inference = 'unavailable: ' + str(error)
    def typename(value):
        return TensorProto.DataType.Name(value) if value else 'UNKNOWN'
    types = {v.name: v.type.tensor_type.elem_type
             for v in [*typed.graph.input, *typed.graph.output, *typed.graph.value_info]
             if v.type.HasField('tensor_type')}
    types.update((t.name, t.data_type) for t in typed.graph.initializer)
    for node in typed.graph.node:
        if node.op_type == 'Constant' and len(node.output) == 1:
            for attr in node.attribute:
                if attr.name == 'value' and attr.HasField('t'):
                    types[node.output[0]] = attr.t.data_type
        if node.op_type == 'Cast':
            for attr in node.attribute:
                if attr.name == 'to':
                    for name in node.output: types[name] = attr.i
    operators = Counter()
    unknown = []
    for index, node in enumerate(typed.graph.node):
        ins = ','.join(typename(types.get(n, 0)) for n in node.input if n)
        outs = ','.join(typename(types.get(n, 0)) for n in node.output if n)
        operators[(node.domain or 'ai.onnx', node.op_type, ins, outs)] += 1
        if 'UNKNOWN' in ins or 'UNKNOWN' in outs:
            unknown.append(dict(index=index, name=node.name, op=node.op_type))
    external = [t.name for t in model.graph.initializer
                if t.data_location == TensorProto.EXTERNAL or t.external_data]
    return dict(model=path.name, graph_file_sha256=hashlib.sha256(raw).hexdigest(),
                hash_covers_external_payloads=False, external_initializers=external,
                node_count=len(model.graph.node), type_inference=inference,
                initializer_types=dict(sorted(Counter(typename(t.data_type) for t in model.graph.initializer).items())),
                inputs=[dict(name=v.name, type=typename(types.get(v.name, 0))) for v in model.graph.input],
                outputs=[dict(name=v.name, type=typename(types.get(v.name, 0))) for v in model.graph.output],
                operators=[dict(domain=d, op=o, inputs=i, outputs=u, count=c)
                           for (d, o, i, u), c in sorted(operators.items())],
                sensitive_nodes=[dict(name=n.name, op=n.op_type, inputs=list(n.input), outputs=list(n.output),
                    attributes={a.name: (a.s.decode('utf-8', errors='backslashreplace') if a.type==onnx.AttributeProto.STRING
                        else a.i if a.type==onnx.AttributeProto.INT else a.f if a.type==onnx.AttributeProto.FLOAT
                        else list(a.ints) if a.type==onnx.AttributeProto.INTS else 'see source protobuf')
                        for a in n.attribute}) for n in model.graph.node
                    if n.op_type in ('Cast', 'GridSample', 'Resize', 'Sigmoid')],
                unknown_type_nodes=unknown,
                runtime_accumulator_precision='unknown; requires provider/kernel evidence',
                runtime_fma_fast_math='unknown; inspect effective build and compiled program')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, help='JSON report; stdout when omitted')
    args = parser.parse_args()
    result = dict(schema=1, interpretation='ONNX tensor types only; no execution, quality or performance claim',
                  models=[inspect(p) for p in args.models])
    report = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end='')


if __name__ == '__main__':
    main()
