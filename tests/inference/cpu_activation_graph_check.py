#!/usr/bin/env python3
"""Graph/weight preservation and content gating; no neural inference."""
import ctypes as C
import json
from pathlib import Path
import sys
import onnx

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
lib=C.CDLL(s['probe']);fn=lib.aji_test_cpu_activation_graph
fn.argtypes=[C.c_char_p,C.c_char_p,C.POINTER(C.c_size_t)];rows=[]
for name,path in s['graphs'].items():
    source=Path(path);dest=out/(name+'.onnx');count=C.c_size_t()
    assert fn(bytes(source),bytes(dest),C.byref(count))==1 and count.value==53
    a=onnx.load(source,load_external_data=False);b=onnx.load(dest,load_external_data=False)
    onnx.checker.check_model(b)
    old=[n for n in a.graph.node if n.op_type=='LeakyRelu']
    custom=[n for n in b.graph.node if n.op_type=='AjiLeakyReluF32']
    assert len(old)==len(custom)==53
    for x,y in zip(old,custom):
        assert x.name==y.name and [v.SerializeToString() for v in x.attribute]==[v.SerializeToString() for v in y.attribute]
        assert y.domain=='aji.cpu'
    original_nodes=[n.SerializeToString() for n in a.graph.node if n.op_type!='LeakyRelu']
    kept_nodes=[n.SerializeToString() for n in b.graph.node if n.op_type!='AjiLeakyReluF32' and not n.name.startswith('__aji_cpu_leaky_')]
    assert original_nodes==kept_nodes
    assert [t.SerializeToString() for t in a.graph.initializer]==[t.SerializeToString() for t in b.graph.initializer]
    # Restoring only the transformed nodes and appended opset restores the whole model.
    del b.graph.node[:];b.graph.node.extend(a.graph.node)
    opsets=[o for o in b.opset_import if o.domain!='aji.cpu'];del b.opset_import[:];b.opset_import.extend(opsets)
    assert a.SerializeToString()==b.SerializeToString()
    unknown=out/(name+'-changed.onnx');data=bytearray(source.read_bytes());data[-1]^=1;unknown.write_bytes(data)
    unexpected=out/(name+'-unexpected.onnx');count=C.c_size_t(99)
    assert fn(bytes(unknown),bytes(unexpected),C.byref(count))==0 and count.value==0 and not unexpected.exists()
    rows.append(dict(graph=name,activations=53,weights_and_unrelated_bytes_preserved=True,unknown_content_untouched=True))
receipt.write_text(json.dumps(dict(passed=True,results=rows),indent=2)+'\n');print(receipt.read_text())
