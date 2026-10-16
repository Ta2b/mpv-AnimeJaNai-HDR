#!/usr/bin/env python3
"""Short compiled/delivered/installed identity checks; no rendering or inference."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
summary=out/'versions-summary.json'
if summary.exists():
    assert json.loads(summary.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
records=[]
def invoke(label,*args):
    path=out/(label+'.json')
    if path.exists():return json.loads(path.read_text())
    t=time.perf_counter();r=subprocess.run([*s['cli'],*map(str,args)],text=True,capture_output=True,timeout=15)
    save(out/(label+'.process.json'),dict(returncode=r.returncode,seconds=time.perf_counter()-t,stderr=r.stderr))
    assert r.returncode==0,r.stderr
    data=json.loads(r.stdout);save(path,data);return data
fixture=out/'package';folder=fixture/'animejanai/inference';folder.mkdir(parents=True,exist_ok=True)
library=folder/'libaji_trt.so'
if not (out/'matched.json').exists():
    shutil.copyfile(s['library'],library);shutil.copyfile(s['metadata'],folder/'GPU-SOURCE.json')
    (fixture/'version.txt').write_text('3.8.0.40\n')
    (fixture/'manifest.json').write_text('{"version":"3.8.0.40"}\n')
matched=invoke('matched','--versions','--root',fixture,'--release-manifest',s['release_manifest'])
assert matched['installed_package']['version']=='3.8.0.40'
assert matched['delivered_manifest']['package_version']=='3.8.0.44'
assert len(matched['installed_libraries'])==1 and matched['installed_libraries'][0]['matches_compiled_metadata'] is True
assert matched['installed_libraries'][0]['compiled_library_metadata']['backend_source']==s['backend_source']
if not (out/'changed.json').exists():
    with library.open('ab') as f:f.write(b'changed fixture')
changed=invoke('changed','--versions','--root',fixture,'--release-manifest',s['release_manifest'])
assert changed['installed_libraries'][0]['matches_compiled_metadata'] is False
assert changed['installed_package']['version']=='3.8.0.40'
actual=invoke('actual-install','--versions','--root',s['actual_install'])
assert actual['installed_libraries'] and all(x['matches_compiled_metadata'] is None for x in actual['installed_libraries'])
cap=invoke('capabilities','--capabilities')
assert 'shared ONNX RIFE' in cap['openvino'] and 'no RIFE yet' not in cap['openvino']
assert 'NCNN' in cap['ncnn_vulkan'] and 'CUDA' in cap['tensorrt'] and 'display API' in cap['vulkan_presentation']
save(summary,dict(passed=True,compiled_delivered_installed_separate=True,changed_library_detected=True,
    missing_compilation_metadata_remains_unknown=True,capabilities_shared=True,
    actual_installed_hashes={Path(x['path']).name:x['actual_sha256'] for x in actual['installed_libraries']},
    native_provider_qualification=False,fps_claimed=False))
print('Version/provenance checks passed')
