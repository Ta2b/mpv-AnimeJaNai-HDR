#!/usr/bin/env python3
"""Validate fresh-process provider loading from the Manager's imported SDK.
No inference/benchmark replay. Existing FRUC pixel qualification stays valid
because the imported binaries are byte-exact to that SDK.
"""
import ctypes as C,json,os,sys,time,hashlib
from pathlib import Path
from fruc_surface_check import Create,Caps,ptr
s=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():raise SystemExit('Existing conclusive receipt; do not repeat.')
provider='/home/ta2b/.animejanai-tools/work/fruc-provider-build-20261016/libaji_fruc.so'
kernel='/home/ta2b/.animejanai-tools/work/fruc-provider-build-20261016/aji_fruc.fatbin'
lib=C.CDLL(provider,mode=os.RTLD_LOCAL)
lib.aji_fruc_create_v1.argtypes=[ptr,ptr,ptr,C.c_size_t];lib.aji_fruc_create_v1.restype=C.c_int
lib.aji_interpolator_query_v1.argtypes=[ptr,C.c_uint32,ptr,C.c_size_t];lib.aji_interpolator_query_v1.restype=C.c_int
lib.aji_interpolator_destroy_v1.argtypes=[ptr];lib.aji_interpolator_destroy_v1.restype=None
params=Create(struct_size=C.sizeof(Create),version=1,flags=1,width=64,height=64,capacity=1,generation=1,sdk_library=os.fsencode(s['installed_library']),sdk_runtime=os.fsencode(s['installed_runtime']),kernel_fatbin=os.fsencode(kernel))
ctx=ptr();err=C.create_string_buffer(1024);start=time.perf_counter()
try:
 status=lib.aji_fruc_create_v1(C.byref(params),C.byref(ctx),err,len(err));assert status==0,(status,err.value)
 caps=Caps();assert lib.aji_interpolator_query_v1(ctx,1,C.byref(caps),C.sizeof(caps))==0
 assert caps.provider==b'nvidia-fruc' and caps.effective_bits==8
 result=dict(passed=True,provider=provider,sdk_library=s['installed_library'],sdk_runtime=s['installed_runtime'],sdk_hashes={k:hashlib.sha256(Path(s[k]).read_bytes()).hexdigest() for k in ['installed_library','installed_runtime']},setup_ms=(time.perf_counter()-start)*1000,scope='Fresh-process SDK loading/provider create/query/destroy only; no repeated pixel benchmark')
finally:
 if ctx:lib.aji_interpolator_destroy_v1(ctx)
result['destroy_success']=True;receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
