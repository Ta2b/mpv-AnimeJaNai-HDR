#!/usr/bin/env python3
"""Verify both static Windows archives and emit their paired, hashed bundle."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import struct
import subprocess
import sys

release, output = (Path(x).resolve() for x in sys.argv[1:3])
producer = os.environ['GITHUB_SHA']
if not re.fullmatch('[0-9a-f]{40}', producer): raise SystemExit('Invalid producer source')
expected = {
 'schema':'animejanai.windows-mpv-patch.v1',
 'mpv_source':'19c0fcf89595e6ab33908299207c555b67e81558',
 'patch_sha256':'526303a3a596436acc7cc339e400f3f4adc0a40c7680573d8bc7e329e9b03095',
 'filter_sha256':'7ecbb7e76d4f5a05f8933b5bbdf10a075541de23617112730af9ced51e2e8bba',
 'dml_exact_pair':1,'abi':9}
if output.exists(): raise SystemExit('Bundle output must be new')
output.mkdir(parents=True)
provenances=[]
for pattern, names in (('mpv-x86_64-*-git-19c0fcf895.7z',('mpv.exe','mpv.com')),
                       ('mpv-dev-x86_64-*-git-19c0fcf895.7z',('libmpv-2.dll',))):
 archives=list(release.glob(pattern))
 if len(archives)!=1: raise SystemExit(f'Expected one archive for {pattern}, got {len(archives)}')
 # The upstream packager keeps its mpv-*/ directory inside each archive.
 # Resolve a unique exact member before streaming it; a recursive wildcard
 # could silently concatenate duplicate basenames into an invalid bundle.
 listing=subprocess.check_output(['7z','l','-slt','-ba','-sccUTF-8',str(archives[0])],text=True,encoding='utf-8')
 members=[line[len('Path = '):] for line in listing.splitlines() if line.startswith('Path = ')]
 for name in (*names,'aji-dml-pair-provenance.json'):
  matches=[member for member in members if PurePosixPath(member.replace('\\','/')).name==name]
  if len(matches)!=1: raise SystemExit(f'Expected one archive member for {name}, got {len(matches)}')
  data=subprocess.check_output(['7z','e','-so','-spd',str(archives[0]),matches[0]])
  if name=='aji-dml-pair-provenance.json':
   record=json.loads(data)
   if any(record.get(k)!=v for k,v in expected.items()): raise SystemExit('Filter provenance mismatch')
   provenances.append(record)
  else:
   if len(data)<128 or data[:2]!=b'MZ': raise SystemExit(f'{name} is not a PE binary')
   pe=struct.unpack_from('<I',data,0x3c)[0]
   if data[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<H',data,pe+4)[0]!=0x8664:
    raise SystemExit(f'{name} is not x86_64 PE')
   (output/name).write_bytes(data)
if provenances[0]!=provenances[1]: raise SystemExit('Player and libmpv were not prepared identically')
record=provenances[0]
record.update(schema='animejanai.windows-mpv-bundle.v1',player_source=producer,
 winbuild_source='597bab33931cbd2ec29abe9d44a29e6363da7499',
 recipe_source='1f8d2e76255abc48f0456d9be99b4cab9c6566e6',
 libass_source='896614fa263f9f64944f7b8650ff6806d5328c4d',
 libplacebo_source='0d043c7f6f79cd3687c023454bdacbe615e4d96f',
 files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())})
(output/'aji-dml-pair-provenance.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
