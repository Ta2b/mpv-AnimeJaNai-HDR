#!/usr/bin/env python3
"""Derive the audited RIFE4.26 encoder/head programs without changing weights.
Developer prototype only: no runtime selection or installed model is modified.
Requires ONNX; output directory must not exist.
"""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = 'fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59'
CUT = '/encode/cnn3/ConvTranspose_output_0'
RECIPE = 'rife426-encoder-cut-v1'


def derive(source, output):
    import onnx
    from onnx.utils import Extractor
    source=Path(source);output=Path(output)
    if output.exists():raise ValueError('Output directory already exists; nothing overwritten')
    blob=source.read_bytes()
    digest=hashlib.sha256(blob).hexdigest()
    if digest != SOURCE_SHA256:raise ValueError('Unsupported model SHA256; only the audited non-ensemble RIFE4.26 is supported')
    model=onnx.load_model_from_string(blob)
    onnx.checker.check_model(model)
    if len(model.graph.input)!=1 or len(model.graph.output)!=1:raise ValueError('Unexpected model I/O')
    original_input=model.graph.input[0];original_output=model.graph.output[0]
    if original_input.type.tensor_type.elem_type!=onnx.TensorProto.FLOAT16:raise ValueError('FP16 input required')
    spatial=original_input.type.tensor_type.shape.dim
    if len(spatial)!=4 or spatial[0].dim_value!=1 or spatial[1].dim_value!=11:raise ValueError('Unexpected input shape')
    # The fixed source digest identifies the channel split [RGB6,t1,grid2,mul2].
    # Shapes may depend on H/W; feature values depend on RGB6 alone. Keep the
    # original Split/Reshape operations and the batch of two endpoint images.
    info=onnx.helper.make_tensor_value_info(CUT,onnx.TensorProto.FLOAT16,[2,4,None,None])
    for i in [2,3]:info.type.tensor_type.shape.dim[i].CopyFrom(spatial[i])
    for i in reversed(range(len(model.graph.value_info))):
        if model.graph.value_info[i].name==CUT:del model.graph.value_info[i]
    model.graph.value_info.append(info)
    extractor=Extractor(model)
    encoder=extractor.extract_model([original_input.name],[CUT])
    head=extractor.extract_model([original_input.name,CUT],[original_output.name])
    # The head boundary must really remove the encoder, while retaining every
    # original t-dependent operator (including all five FP32 GridSamples).
    encoder_nodes={n.name for n in encoder.graph.node}
    head_nodes={n.name for n in head.graph.node}
    if not any(n.op_type=='ConvTranspose' and CUT in n.output for n in encoder.graph.node):raise ValueError('Missing audited encoder cut')
    if any(n.name.startswith('/encode/') for n in head.graph.node):raise ValueError('Head still contains encoder')
    if sum(n.op_type=='GridSample' for n in head.graph.node)!=5:raise ValueError('Head lost a refinement warp')
    originals={n.name:n.SerializeToString() for n in model.graph.node}
    for program in [encoder,head]:
        onnx.checker.check_model(program)
        for node in program.graph.node:
            if originals.get(node.name)!=node.SerializeToString():raise ValueError('Changed operator: '+node.name)
    originals={v.name:v.SerializeToString() for v in model.graph.initializer}
    for program in [encoder,head]:
        for weight in program.graph.initializer:
            if originals.get(weight.name)!=weight.SerializeToString():raise ValueError('Changed weight: '+weight.name)
    outputs={'encoder.onnx':encoder.SerializeToString(),'head.onnx':head.SerializeToString()}
    receipt={'schema':'animejanai.rife-encoder-cut.v1','recipe':RECIPE,'source_sha256':digest,
        'input':original_input.name,'output':original_output.name,'features':CUT,
        'feature_shape':[2,4,'same H','same W'],'feature_dtype':'FP16',
        'programs':{name:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in outputs.items()},
        'nodes':{'source':len(model.graph.node),'encoder':len(encoder_nodes),'head':len(head_nodes)},
        'weights_and_operators':'byte-identical retained protobuf records',
        'runtime_enabled':False,'numerical_equivalence':'not yet established; separate TensorRT plans can change tactics/rounding'}
    # Publish only complete, checked programs into a newly created directory.
    # The source is read once and never written; no installed model is replaced.
    output.mkdir(parents=True,exist_ok=False)
    for name,data in outputs.items():
        with (output/name).open('xb') as file:file.write(data)
    with (output/'recipe.json').open('x') as file:json.dump(receipt,file,indent=2);file.write('\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(derive(args.source,args.output)))
