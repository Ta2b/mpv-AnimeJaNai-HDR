#!/usr/bin/env python3
"""Targeted loaded-engine semantics/initialization checks, no video/FPS replay.

SPEC: library, trt, older_trt, kernel, models, rife, output (new directory).
Requires existing 720p RIFE4.26/SPAN plans; /bin/false forbids hidden builds.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from pipeline_cuda_check import Fixture, Create, Caps, ptr, wakeupfn
from surface_cuda_check import Params


class Semantics(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ("struct_size", "version", "policy", "flags")] + [
        ("module_path", C.c_char*1024), ("source_revision", C.c_char*41)]


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = Path(spec["output"]); out.mkdir(parents=True, exist_ok=False)
    digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    fingerprints = {k: digest(spec[k]) for k in ("library", "trt", "older_trt", "kernel")}
    native = C.CDLL(spec["trt"], mode=os.RTLD_LOCAL)
    native.aji_create.argtypes=[ptr]; native.aji_create.restype=ptr
    native.aji_destroy.argtypes=[ptr]; native.aji_destroy.restype=None
    native.aji_rife_semantics_v1.argtypes=[ptr,C.c_uint32,ptr,C.c_size_t]
    native.aji_rife_semantics_v1.restype=C.c_int
    lib = C.CDLL(spec["library"], mode=os.RTLD_LOCAL)
    for name, args in {
        "aji_pipeline_create_v1": [ptr, ptr, ptr, C.c_size_t], "aji_pipeline_query_v1": [ptr, ptr, C.c_size_t],
        "aji_pipeline_last_error_v1": [ptr, ptr, C.c_size_t], "aji_pipeline_destroy_v1": [ptr],
    }.items():
        getattr(lib,name).argtypes=args;getattr(lib,name).restype=None if "destroy" in name else C.c_int
    lib.aji_pipeline_features_v1.restype=C.c_uint64
    assert lib.aji_pipeline_features_v1() & 16
    fixture = Fixture(dict(width=1280,height=720))
    contexts=[];callbacks=[];direct=ptr()
    result={"binaries":fingerprints,"cases":[],"video_frames_processed":0,"fps_measured":False}
    minimal=out/"unconfigured.conf"
    minimal.write_text("[global]\nbackend=TensorRT\n[slot_1]\nchain_1_model_1_name=\n")
    try:
        params=Params(api_version=9,cuda_context=fixture.ctx,conf_path=os.fsencode(minimal),model_dir=b"",
                      rife_model_dir=b"",trtexec=b"/bin/false",slot=1)
        direct=ptr(native.aji_create(C.byref(params)));assert direct
        sentinel=C.create_string_buffer(C.sizeof(Semantics));C.memset(sentinel,0xa5,C.sizeof(sentinel))
        untouched=bytes(sentinel)
        for ctx,version,size,expected in ((None,1,C.sizeof(Semantics),-1),
                                         (direct,1,C.sizeof(Semantics)-1,-1),
                                         (direct,2,C.sizeof(Semantics),-2),
                                         (direct,1,C.sizeof(Semantics),-2)):
            assert native.aji_rife_semantics_v1(ctx,version,sentinel,size)==expected
            assert bytes(sentinel)==untouched
        result["native_error_outputs_untouched"]=True
        spatial="2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16"
        for label,provider,policy,fused in (("old-quality-alone",spec["older_trt"],"quality",False),
                                         ("current-quality-fused",spec["trt"],"quality",True),
                                         ("current-fast-fused",spec["trt"],"fast",True),
                                         ("old-fast-fused",spec["older_trt"],"fast",True)):
            conf=out/(label+".conf")
            text="[global]\nbackend=TensorRT\nlogging=no\nrife_engine="+policy+"\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count="+str(2 if fused else 1)+"\n"
            text+="chain_1_stage_1_id=rife\nchain_1_stage_1_kind=interpolate\nchain_1_stage_1_method=rife\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_model=426\nchain_1_stage_1_factor_numerator=4\nchain_1_stage_1_factor_denominator=1\nchain_1_stage_1_policy="+policy+"\n"
            if fused:
                text+="chain_1_stage_2_id=span\nchain_1_stage_2_kind=upscale\nchain_1_stage_2_method=onnx\nchain_1_stage_2_runtime=tensorrt\nchain_1_stage_2_model="+spatial+"\nchain_1_stage_2_policy="+policy+"\n"
            conf.write_text(text)
            wake=threading.Event()
            @wakeupfn
            def notify(_):
                wake.set()
            callbacks.append(notify)
            create=Create(struct_size=C.sizeof(Create),version=1,width=1280,height=720,slot=1,capacity=1,flags=1,
                          generation=1,cuda_context=fixture.ctx,conf=os.fsencode(conf),model_dir=os.fsencode(spec["models"]),
                          rife_dir=os.fsencode(spec["rife"]),trtexec=b"/bin/false",trt_library=os.fsencode(provider),
                          kernel_fatbin=os.fsencode(spec["kernel"]),fps_numerator=24,fps_denominator=1,wakeup=notify)
            handle=ptr();error=C.create_string_buffer(4096)
            assert lib.aji_pipeline_create_v1(C.byref(create),C.byref(handle),error,len(error))==0,error.value
            contexts.append(handle)
            caps=Caps();deadline=time.monotonic()+30
            while True:
                code=lib.aji_pipeline_query_v1(handle,C.byref(caps),C.sizeof(caps))
                if code!=-4:
                    break
                assert time.monotonic()<deadline,"initialization timeout; inspect without automatic retry"
                wake.wait(.01);wake.clear()
            lib.aji_pipeline_last_error_v1(handle,error,len(error))
            if label=="old-quality-alone":
                assert code<0 and b"Quality cannot be verified" in error.value,error.value
                result["cases"].append({"name":label,"refused":True,"diagnostic":error.value.decode()})
            else:
                assert code==0,(label,code,error.value)
                assert (caps.width,caps.height,caps.factor,caps.stage_count)==(2560,1440,4,2)
                result["cases"].append({"name":label,"accepted":True,"configured_stages":caps.stage_count})
    finally:
        # Keep the first TensorRT runtime/logger alive until later ones close.
        for handle in reversed(contexts):lib.aji_pipeline_destroy_v1(handle)
        if direct:native.aji_destroy(C.byref(direct))
        fixture.close()
    assert fingerprints=={k:digest(spec[k]) for k in fingerprints},"module changed during observation"
    result.update(passed=True,scope="Linux CUDA configured semantics and old-module refusal/explicit Fast compatibility; no pixels or benchmark")
    (out/"receipt.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
