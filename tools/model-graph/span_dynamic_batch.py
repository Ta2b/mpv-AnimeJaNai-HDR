#!/usr/bin/env python3
"""Batch annotations for the audited SPAN graph; no runtime activation.
Only the known model is supported. A new output directory is mandatory.
"""
import argparse,hashlib,json
from pathlib import Path
SOURCE_SHA256='72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4'
RECIPE='span-sharp1-performance-dynamic-batch-v1'
def derive(source,output):
    import onnx
    source,output=Path(source),Path(output)
    if output.exists():raise ValueError('Output already exists; nothing overwritten')
    blob=source.read_bytes();digest=hashlib.sha256(blob).hexdigest()
    if digest!=SOURCE_SHA256:raise ValueError('Unsupported SPAN source SHA256')
    model=onnx.load_model_from_string(blob);onnx.checker.check_model(model)
    nodes=[n.SerializeToString() for n in model.graph.node];weights=[w.SerializeToString() for w in model.graph.initializer]
    assert len(model.graph.input)==len(model.graph.output)==1
    # The audited unshuffle shapes already gather batch from Shape(Pad(input)).
    # Keep every Shape/Gather/Reshape/Pad and numerical operator untouched.
    for tensor in [model.graph.input[0],model.graph.output[0]]:
        assert tensor.type.tensor_type.elem_type==onnx.TensorProto.FLOAT16
        tensor.type.tensor_type.shape.dim[0].ClearField('dim_value')
        tensor.type.tensor_type.shape.dim[0].dim_param='batch'
    del model.graph.value_info[:]
    model=onnx.shape_inference.infer_shapes(model,strict_mode=True)
    onnx.checker.check_model(model)
    assert nodes==[n.SerializeToString() for n in model.graph.node]
    assert weights==[w.SerializeToString() for w in model.graph.initializer]
    derived=model.SerializeToString()
    report={'schema':'animejanai.span-batch-program.v1','recipe':RECIPE,'source_sha256':digest,
        'program_sha256':hashlib.sha256(derived).hexdigest(),'nodes':len(model.graph.node),
        'operators_weights_and_attributes_unchanged':True,'numerical_equivalence':'not established until plan comparison',
        'runtime_enabled':False}
    output.mkdir(parents=True,exist_ok=False)
    with (output/'batch.onnx').open('xb') as f:f.write(derived)
    with (output/'recipe.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('output');args=parser.parse_args()
    print(json.dumps(derive(args.source,args.output)))
