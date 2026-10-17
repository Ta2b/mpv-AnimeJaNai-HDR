#!/usr/bin/env python3
"""One synthetic Area/Spline36 comparison, no repeated oracle or FPS benchmark.

Usage: downscale_comparison_probe.py SPEC.json (library, trt, kernel, output).
The same 1080p canonical image contains an isolated edge and a Nyquist checker.
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


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    output = Path(spec["output"])
    output.mkdir(parents=True, exist_ok=False)
    width, height, ow, oh = 1920, 1080, 1280, 720
    low, high = 13107, 52428
    yy, xx = np.indices((height, width))
    gray = np.where(xx < width // 2, np.where(xx < width // 4, low, high),
                    np.where(xx - width // 2 > yy * 1.4, high, low)).astype(np.uint16)
    gray[height // 2:, :width // 2] = np.where((xx[height // 2:, :width // 2] + yy[height // 2:, :width // 2]) % 2, high, low)
    gray[height // 2:, width // 2:] = np.rint(low + (high-low) * xx[height // 2:, width // 2:] / (width-1)).astype(np.uint16)
    source_pixels = np.stack((gray, np.full_like(gray, 32768), np.full_like(gray, 32768)))
    lib = C.CDLL(spec["library"], mode=os.RTLD_LOCAL)
    for name, args in {
        "aji_pipeline_create_v1": [ptr, ptr, ptr, C.c_size_t], "aji_pipeline_query_v1": [ptr, ptr, C.c_size_t],
        "aji_pipeline_last_error_v1": [ptr, ptr, C.c_size_t], "aji_pipeline_submit_v1": [ptr, ptr, ptr],
        "aji_pipeline_drain_v1": [ptr, C.c_uint32], "aji_pipeline_complete_v1": [ptr, C.c_uint64, C.c_uint32, ptr, C.c_size_t],
        "aji_pipeline_stats_v1_get": [ptr, ptr, C.c_size_t], "aji_pipeline_destroy_v1": [ptr],
    }.items():
        getattr(lib, name).argtypes = args
        getattr(lib, name).restype = None if "destroy" in name else C.c_int
    fixture = Fixture(dict(width=width, height=height))
    source = fixture.surface(source_pixels, 7, 1, 0)
    fixture.s = dict(width=ow, height=oh)
    result = {"source_dimensions": [width, height], "output_dimensions": [ow, oh],
              "input_sha256": hashlib.sha256(source_pixels.tobytes()).hexdigest(),
              "binaries": {key: digest(spec[key]) for key in ("library", "trt", "kernel")}, "methods": {}}
    try:
        for index, method in enumerate(("area", "spline36")):
            wake = threading.Event()
            @wakeupfn
            def notify(_):
                wake.set()
            conf = output / (method + ".conf")
            conf.write_text("[global]\nbackend=TensorRT\nlogging=no\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\n"
                            "chain_1_stage_1_id=down\nchain_1_stage_1_kind=resize\nchain_1_stage_1_method=" + method +
                            "\nchain_1_stage_1_runtime=cuda\nchain_1_stage_1_target_height=720\n")
            params = Create(struct_size=C.sizeof(Create), version=1, width=width, height=height, slot=1, capacity=1,
                            generation=1, cuda_context=fixture.ctx, conf=os.fsencode(conf), model_dir=b"", rife_dir=b"",
                            trtexec=b"/bin/false", trt_library=os.fsencode(spec["trt"]), kernel_fatbin=os.fsencode(spec["kernel"]),
                            fps_numerator=24, fps_denominator=1, wakeup=notify)
            ctx = ptr(); error = C.create_string_buffer(2048)
            try:
                assert lib.aji_pipeline_create_v1(C.byref(params), C.byref(ctx), error, len(error)) == 0, error.value
                caps = Caps(); deadline = time.monotonic() + 15
                while True:
                    status = lib.aji_pipeline_query_v1(ctx, C.byref(caps), C.sizeof(caps))
                    if status != -4:
                        break
                    assert time.monotonic() < deadline, "model-free configure timed out"
                    wake.wait(.01); wake.clear()
                lib.aji_pipeline_last_error_v1(ctx, error, len(error))
                assert status == 0, (status, error.value)
                assert (caps.width, caps.height, caps.factor) == (ow, oh, 1)
                target = fixture.surface(None, 7, 101 + index, 0)
                target[0].duration = source[0].duration
                target[0].timebase_num, target[0].timebase_den = source[0].timebase_num, source[0].timebase_den
                request = Request(struct_size=C.sizeof(Request), version=1, flags=2, output_count=1, generation=1,
                                  current=C.addressof(source[0]))
                request.outputs[0] = C.addressof(target[0])
                ticket = C.c_uint64()
                assert lib.aji_pipeline_submit_v1(ctx, C.byref(request), C.byref(ticket)) == 0
                assert lib.aji_pipeline_drain_v1(ctx, 0) == 0
                done = Done()
                assert lib.aji_pipeline_complete_v1(ctx, ticket, 1, C.byref(done), C.sizeof(done)) == 0
                assert done.result.state == 2 and done.result.status == 0, done.result.message
                pixels = np.asarray(fixture.download(target))
                np.save(output / (method + ".npy"), pixels)
                # Exclude panel boundaries. Edge halo is measured relative to
                # input levels, checker residual to its exact 50% mean.
                edge = pixels[0, 180, 280:360].astype(np.int32)
                checker = pixels[0, 400:680, 40:600].astype(np.float64)
                stat = Stats()
                assert lib.aji_pipeline_stats_v1_get(ctx, C.byref(stat), C.sizeof(stat)) == 0
                assert stat.rife_predictions == stat.spatial_predictions == stat.failed == 0
                assert all(n == 0 for n in fixture.held.values())
                result["methods"][method] = {"sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
                    "edge_min_code16": int(edge.min()), "edge_max_code16": int(edge.max()),
                    "undershoot_code16": max(0, int(low-edge.min())), "overshoot_code16": max(0, int(edge.max()-high)),
                    "checker_rms_code16": float(np.sqrt(np.mean((checker-(low+high)/2)**2))),
                    "checker_mean_code16": float(checker.mean()), "edge_samples_code16": edge[32:48].tolist(),
                    "model_predictions": 0}
            finally:
                if ctx:
                    lib.aji_pipeline_destroy_v1(ctx)
    finally:
        fixture.close()
    result.update(passed=True, fps_measured=False, scope="one synthetic canonical YUV444P16 BT709 full-range image, Linux CUDA only")
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
