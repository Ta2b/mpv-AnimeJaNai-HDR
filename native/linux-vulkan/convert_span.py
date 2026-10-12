#!/usr/bin/env python3
"""Convert the shipped spatial SPANF3 ONNX models to NCNN without graph tracing.
Only the checked even-size pixel-unshuffle -> SPAN -> pixel-shuffle graph is
accepted. Unsupported models fail; there is no replacement model or CPU fallback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
a=p.parse_args()
m=onnx.load(a.source)
weights={t.name:numpy_helper.to_array(t).astype(np.float32) for t in m.graph.initializer}
nodes=list(m.graph.node)
first=next(i for i,n in enumerate(nodes) if n.op_type=='Conv')
last=next(i for i,n in enumerate(nodes) if n.op_type=='DepthToSpace')
attrs=lambda n:{x.name:onnx.helper.get_attribute_value(x) for x in n.attribute}
unshuffle=next(n for n in nodes[:first] if n.op_type=='Transpose' and attrs(n).get('perm')==[0,1,3,5,2,4])
assert unshuffle and weights[nodes[first].input[1]].shape[1]==12,'Not a supported RGB pixel-unshuffle SPAN model'
assert attrs(nodes[last])=={'blocksize':4,'mode':b'CRD'},'Unsupported output shuffle'
assert all(n.op_type in {'Conv','Relu','Add','Mul','Tanh','Concat'} for n in nodes[first:last]),'Unsupported SPAN operator'
assert all(n.op_type=='Slice' for n in nodes[last+1:]),'Unsupported output transform'
layers=[];data=bytearray()
layers.append(['Input','input',[],['in0'],[]])
layers.append(['Reorg','unshuffle',['in0'],[nodes[first].input[0]],['0=2','1=0']])
for i,n in enumerate(nodes[first:last]):
    x=list(n.input);y=list(n.output);v=attrs(n);params=[];kind=n.op_type
    if kind=='Conv':
        w=weights[x[1]];b=weights[x[2]]
        assert v.get('group',1)==1 and v.get('strides',[1,1])==[1,1] and v.get('dilations',[1,1])==[1,1]
        pad=v.get('pads',[0,0,0,0]);assert pad==[pad[0]]*4
        assert w.shape[2]==w.shape[3] and len(b)==w.shape[0]
        kind='Convolution';params=[f'0={w.shape[0]}',f'1={w.shape[3]}','2=1','3=1',f'4={pad[0]}','5=1',f'6={w.size}']
        data.extend(b'\0\0\0\0');data.extend(w.astype('<f4').tobytes());data.extend(b.astype('<f4').tobytes())
        x=x[:1]
    elif kind in {'Add','Mul'}: params=['0='+('0' if kind=='Add' else '2')];kind='BinaryOp'
    elif kind=='Concat': assert v['axis']==1;params=['0=0']
    elif kind=='Relu':kind='ReLU'
    elif kind=='Tanh':kind='TanH'
    layers.append([kind,'span_'+str(i),x,y,params])
layers.append(['PixelShuffle','shuffle',list(nodes[last].input),['out0'],['0=4','1=0']])
# NCNN's light extractor requires explicit Split layers for reused blobs.
uses={}
for layer in layers:
    for x in layer[2]:uses[x]=uses.get(x,0)+1
counters={};final=[]
for layer in layers:
    inputs=[]
    for x in layer[2]:
        if uses[x]>1:
            index=counters.get(x,0);inputs.append(x+'__'+str(index));counters[x]=index+1
        else:inputs.append(x)
    layer[2]=inputs
    final.append(layer)
    for y in layer[3]:
        if uses.get(y,0)>1:final.append(['Split','split_'+str(len(final)),[y],[y+'__'+str(i) for i in range(uses[y])],[]])
blobs={x for layer in final for x in layer[3]}
lines=['7767517',f'{len(final)} {len(blobs)}']
for kind,name,inputs,outputs,params in final:
    lines.append(' '.join([kind,name,str(len(inputs)),str(len(outputs)),*inputs,*outputs,*params]))
a.destination.parent.mkdir(parents=True,exist_ok=True)
Path(str(a.destination)+'.param').write_text('\n'.join(lines)+'\n')
Path(str(a.destination)+'.bin').write_bytes(data)
Path(str(a.destination)+'.json').write_text(json.dumps({'source':a.source.name,'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
    'converter':'span-direct-v1','input':'in0','output':'out0','scale':2,'source_dimensions':'even','weights':'fp32 from original ONNX values'},indent=2)+'\n')
print(f'Converted {a.source.name}: {len(final)} layers, exact SPAN operators, even-size input')
