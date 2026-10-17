#!/usr/bin/env python3
"""Apply AH-344 to the pinned Windows mpv, checking the exact source bytes."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

BASE = '19c0fcf89595e6ab33908299207c555b67e81558'
BEFORE = '0f223b6096847819bca6e6bc306c2b656c4807bed7fef23f9542b1b82c6bcf68'
AFTER = '7ecbb7e76d4f5a05f8933b5bbdf10a075541de23617112730af9ced51e2e8bba'
PATCH_HASH = '526303a3a596436acc7cc339e400f3f4adc0a40c7680573d8bc7e329e9b03095'

source = Path(sys.argv[1]).resolve()
patch = Path(__file__).with_name('vf_animejanai-exact-pair.patch')
if hashlib.sha256(patch.read_bytes()).hexdigest() != PATCH_HASH:
    raise SystemExit('DML pair patch digest differs from the reviewed patch')
ref = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if ref != BASE:
    raise SystemExit(f'Expected Windows mpv {BASE}, found {ref}')
file = source/'video/filter/vf_animejanai.c'
# Windows checkouts may have CRLF; preserve their policy when git apply writes.
sha = lambda: hashlib.sha256(file.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
if sha() == BEFORE:
    subprocess.run(['git','-C',str(source),'apply','--check','--ignore-space-change',str(patch)],check=True)
    subprocess.run(['git','-C',str(source),'apply','--ignore-space-change',str(patch)],check=True)
if sha() != AFTER:
    raise SystemExit('Windows filter does not match the reviewed postimage; do not publish')
provenance = {'schema':'animejanai.windows-mpv-patch.v1','mpv_source':BASE,
    'patch_sha256':PATCH_HASH,'filter_sha256':AFTER,'dml_exact_pair':1,
    'abi':9,'hardware_qualification':'not-run'}
(source/'aji-dml-pair-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps(provenance))
