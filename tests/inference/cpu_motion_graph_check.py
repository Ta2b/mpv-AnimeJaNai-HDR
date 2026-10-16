#!/usr/bin/env python3
"""Independent dependency proof and actual ORT kernel trace check; no model rerun."""
import collections
import json
from pathlib import Path
import sys
import onnx

folder=Path(sys.argv[1]);receipt=folder/'verified-summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
files=sorted(folder.glob('input-*.onnx'));assert len(files) in [2,4]
rows=[]
for i in range(0,len(files),2):
    a=onnx.load(folder/f'input-{i}.onnx',load_external_data=False)
    b=onnx.load(folder/f'input-{i+1}.onnx',load_external_data=False)
    assert len(a.graph.output)==3 and len(b.graph.output)==2
    assert [v.SerializeToString() for v in a.graph.output[1:]]==[v.SerializeToString() for v in b.graph.output]
    producers={v:n for n in a.graph.node for v in n.output};needed=[v.name for v in a.graph.output[1:]];keep=set()
    while needed:
        name=needed.pop();node=producers.get(name)
        if node is None or node.name in keep:continue
        # The known source graphs use unique, nonempty node names.
        assert node.name;keep.add(node.name);needed.extend(v for v in node.input if v)
    expected=[n.SerializeToString() for n in a.graph.node if n.name in keep]
    assert expected==[n.SerializeToString() for n in b.graph.node]
    removed_nodes=len(a.graph.node)-len(b.graph.node);assert removed_nodes>0
    del b.graph.node[:];b.graph.node.extend(a.graph.node)
    del b.graph.output[:];b.graph.output.extend(a.graph.output)
    assert a.SerializeToString()==b.SerializeToString(), 'Only unreachable nodes and unused output may change'
    observations=[]
    for index in [i,i+1]:
        optimized=onnx.load(folder/f'optimized-{index}.onnx',load_external_data=False)
        profile=next(folder.glob(f'profile-{index}.*.json'));events=json.loads(profile.read_text())
        kernels=collections.Counter(e.get('args',{}).get('op_name') for e in events
            if e.get('cat')=='Node' and e['name'].endswith('_kernel_time'))
        runs=sum(e.get('name')=='model_run' for e in events);assert runs==1
        assert kernels==collections.Counter(n.op_type for n in optimized.graph.node)
        observations.append(dict(outputs=len(optimized.graph.output),nodes=len(optimized.graph.node),kernels=dict(kernels)))
    before,after=observations
    assert before['nodes']-after['nodes']==16 and before['kernels']['GridSample']==5 and after['kernels']['GridSample']==4
    for key in ['Conv','ConvTranspose','ReorderInput','ReorderOutput']:
        assert before['kernels'][key]==after['kernels'][key]
    rows.append(dict(raw_removed_nodes=removed_nodes,weights_and_reachable_nodes_unchanged=True,
        before=before,after=after,actual_removed_kernels=16))
receipt.write_text(json.dumps(dict(passed=True,results=rows),indent=2)+'\n');print(receipt.read_text())
