#!/usr/bin/env python3
"""One exact native 1080->720 Area comparison against the previous fatbin.

SPEC.json: library, trt, reference_kernel, candidate_kernel, output (new folder).
All uint16 codes, pitched/cropped planes; no model build or FPS benchmark.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import numpy as np
from pipeline_cuda_check import Fixture, Create, Caps, Request, Done, Stats, ptr, wakeupfn


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = Path(spec["output"]); out.mkdir(parents=True, exist_ok=False)
    pixels = np.random.default_rng(360).integers(0, 65536, (3, 1080, 1920), dtype=np.uint16)
    pixels[:, :6, :6] = 0; pixels[:, -6:, -6:] = 65535
    assert np.unique(pixels).size == 65536
    sy, sx = np.arange(720)*3//2, np.arange(1280)*3//2
    wy, wx = np.where(np.arange(720)%2, 1, 2), np.where(np.arange(1280)%2, 1, 2)
    oracle = np.zeros((3, 720, 1280), dtype=np.uint32)
    for dy in (0, 1):
        for dx in (0, 1):
            oracle += (pixels[:, (sy+dy)[:, None], sx+dx].astype(np.uint32)
                       * (wy if dy==0 else 3-wy)[None, :, None]
                       * (wx if dx==0 else 3-wx)[None, None, :]).astype(np.uint32)
    oracle = ((oracle+4)//9).astype(np.uint16)
    conf = out/"area.conf"
    conf.write_text("[global]\nbackend=TensorRT\nlogging=no\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\n"
                    "chain_1_stage_1_id=down\nchain_1_stage_1_kind=resize\nchain_1_stage_1_method=area\n"
                    "chain_1_stage_1_runtime=cuda\nchain_1_stage_1_target_height=720\n")
    lib = C.CDLL(spec["library"], mode=os.RTLD_LOCAL)
    for name, args in {
        "aji_pipeline_create_v1": [ptr, ptr, ptr, C.c_size_t], "aji_pipeline_query_v1": [ptr, ptr, C.c_size_t],
        "aji_pipeline_last_error_v1": [ptr, ptr, C.c_size_t], "aji_pipeline_submit_v1": [ptr, ptr, ptr],
        "aji_pipeline_drain_v1": [ptr, C.c_uint32], "aji_pipeline_complete_v1": [ptr, C.c_uint64, C.c_uint32, ptr, C.c_size_t],
        "aji_pipeline_stats_v1_get": [ptr, ptr, C.c_size_t], "aji_pipeline_destroy_v1": [ptr],
    }.items():
        getattr(lib, name).argtypes = args
        getattr(lib, name).restype = None if "destroy" in name else C.c_int
    fixture = Fixture(dict(width=1920, height=1080))
    source = fixture.surface(pixels, 7, 1, 0)
    fixture.s = dict(width=1280, height=720)
    sha = lambda value: hashlib.sha256(value).hexdigest()
    result = {"input_sha256": sha(pixels.tobytes()), "input_code16_values": 65536,
              "source_dimensions": [1920, 1080], "output_dimensions": [1280, 720], "variants": {}}
    try:
        for index, variant in enumerate(("reference", "candidate")):
            wake = threading.Event()
            @wakeupfn
            def notify(_):
                wake.set()
            params = Create(struct_size=C.sizeof(Create), version=1, width=1920, height=1080, slot=1, capacity=1,
                            generation=1, cuda_context=fixture.ctx, conf=os.fsencode(conf), model_dir=b"", rife_dir=b"",
                            trtexec=b"/bin/false", trt_library=os.fsencode(spec["trt"]), kernel_fatbin=os.fsencode(spec[variant+"_kernel"]),
                            fps_numerator=24, fps_denominator=1, wakeup=notify)
            ctx = ptr(); error = C.create_string_buffer(2048)
            try:
                assert lib.aji_pipeline_create_v1(C.byref(params), C.byref(ctx), error, len(error)) == 0, error.value
                caps = Caps(); deadline = time.monotonic()+15
                while True:
                    code = lib.aji_pipeline_query_v1(ctx, C.byref(caps), C.sizeof(caps))
                    if code != -4:
                        break
                    assert time.monotonic() < deadline, "model-free configure timeout"
                    wake.wait(.01); wake.clear()
                lib.aji_pipeline_last_error_v1(ctx, error, len(error))
                assert code == 0, (code, error.value)
                assert (caps.width, caps.height, caps.factor) == (1280, 720, 1)
                target = fixture.surface(None, 7, 101+index, 0)
                target[0].duration = source[0].duration
                target[0].timebase_num, target[0].timebase_den = source[0].timebase_num, source[0].timebase_den
                before = [bytes(v[0]) for v in (source, target)]
                request = Request(struct_size=C.sizeof(Request), version=1, flags=2, output_count=1, generation=1,
                                  current=C.addressof(source[0]))
                request.outputs[0] = C.addressof(target[0]); ticket = C.c_uint64()
                assert lib.aji_pipeline_submit_v1(ctx, C.byref(request), C.byref(ticket)) == 0
                assert lib.aji_pipeline_drain_v1(ctx, 0) == 0
                done = Done()
                assert lib.aji_pipeline_complete_v1(ctx, ticket, 1, C.byref(done), C.sizeof(done)) == 0
                assert done.result.state == 2 and done.result.status == 0, done.result.message
                actual = np.asarray(fixture.download(target))
                assert np.array_equal(actual, oracle), (variant, int(np.max(np.abs(actual.astype(np.int32)-oracle.astype(np.int32)))))
                assert before == [bytes(v[0]) for v in (source, target)]
                assert all(n == 0 for n in fixture.held.values())
                stat = Stats()
                assert lib.aji_pipeline_stats_v1_get(ctx, C.byref(stat), C.sizeof(stat)) == 0
                assert stat.rife_predictions == stat.spatial_predictions == stat.failed == stat.cpu_pixel_copies == 0
                result["variants"][variant] = {"kernel_sha256": sha(Path(spec[variant+"_kernel"]).read_bytes()),
                    "output_sha256": sha(actual.tobytes()), "exact_to_integer_oracle": True,
                    "padding_preserved": True, "descriptors_unchanged": True, "owners_balanced": True}
            finally:
                if ctx:
                    lib.aji_pipeline_destroy_v1(ctx)
    finally:
        fixture.close()
    assert result["variants"]["reference"]["output_sha256"] == result["variants"]["candidate"]["output_sha256"]
    result.update(passed=True, compared_code16_values=int(oracle.size), fps_measured=False,
                  library_sha256=sha(Path(spec["library"]).read_bytes()), trt_sha256=sha(Path(spec["trt"]).read_bytes()),
                  scope="Linux CUDA YUV444P16 pitched/cropped active views; no full-chain or FPS remeasurement")
    (out/"receipt.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
