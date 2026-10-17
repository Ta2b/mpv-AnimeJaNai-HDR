#!/usr/bin/env python3
"""One model-free Spline36 stage against the established ABI9 YUV444P16 resize.
No NV12/P010 migration equivalence or performance gain is implied by this oracle.
Usage: pipeline_spline36_check.py SPEC.json
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
from surface_cuda_check import Frame, Params
from vfi_candidate_probe import rgb_to_yuv444


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    output = Path(spec['output']); output.mkdir(parents=True, exist_ok=True)
    assert not (output / 'summary.json').exists(), 'Conclusive receipt exists; no replay'
    width, height, target = 128, 72, 36
    legacy_conf = output / 'legacy-resize.conf'
    legacy_conf.write_text('[global]\nbackend=TensorRT\nlogging=no\n[slot_1]\nchain_1_rife=no\nchain_1_model_1_name=\nchain_1_model_1_resize_height_before_upscale=36\n')
    ordered_conf = output / 'ordered-resize.conf'
    ordered_conf.write_text('[global]\nbackend=TensorRT\nlogging=no\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=down\nchain_1_stage_1_kind=resize\nchain_1_stage_1_method=spline36\nchain_1_stage_1_runtime=cuda\nchain_1_stage_1_target_height=36\n')
    fixture = Fixture(dict(width=width, height=height))
    native = C.CDLL(spec['trt'], mode=os.RTLD_LOCAL)
    pipeline = C.CDLL(spec['library'], mode=os.RTLD_LOCAL)
    signatures = {
        'aji_create': ([ptr], ptr), 'aji_configure': ([ptr, C.c_int, C.c_int, C.c_double, ptr, ptr], C.c_int),
        'aji_infer': ([ptr, ptr, ptr, ptr], C.c_int), 'aji_last_error': ([ptr], C.c_char_p),
        'aji_destroy': ([ptr], None),
    }
    for name, (args, result) in signatures.items():
        getattr(native, name).argtypes = args; getattr(native, name).restype = result
    signatures = {
        'aji_pipeline_features_v1': ([], C.c_uint64), 'aji_pipeline_create_v1': ([ptr, ptr, ptr, C.c_size_t], C.c_int),
        'aji_pipeline_query_v1': ([ptr, ptr, C.c_size_t], C.c_int), 'aji_pipeline_last_error_v1': ([ptr, ptr, C.c_size_t], C.c_int),
        'aji_pipeline_submit_v1': ([ptr, ptr, ptr], C.c_int), 'aji_pipeline_drain_v1': ([ptr, C.c_uint32], C.c_int),
        'aji_pipeline_complete_v1': ([ptr, C.c_uint64, C.c_uint32, ptr, C.c_size_t], C.c_int),
        'aji_pipeline_stats_v1_get': ([ptr, ptr, C.c_size_t], C.c_int), 'aji_pipeline_destroy_v1': ([ptr], None),
    }
    for name, (args, result) in signatures.items():
        getattr(pipeline, name).argtypes = args; getattr(pipeline, name).restype = result
    assert pipeline.aji_pipeline_features_v1() & 4, 'Spline36 capability absent'
    legacy = ptr(); ordered = ptr(); wake = threading.Event()
    @wakeupfn
    def notify(_): wake.set()
    def frame(surface):
        value = Frame(width=surface.crop.width, height=surface.crop.height, format=3, matrix=surface.color.matrix-1,
                      range=2 if surface.color.range == 1 else 1, siting=surface.color.siting)
        for index in range(3):
            plane = surface.planes[index]
            value.plane[index] = plane.data + plane.offset + surface.crop.y * plane.row_stride + surface.crop.x * 2
            value.stride[index] = plane.row_stride
        return value
    try:
        params = Params(api_version=9, cuda_context=fixture.ctx, conf_path=os.fsencode(legacy_conf), model_dir=b'', trtexec=b'/bin/false', slot=1, rife_model_dir=b'')
        legacy = ptr(native.aji_create(C.byref(params))); assert legacy
        ow, oh = C.c_int(), C.c_int()
        assert native.aji_configure(legacy, width, height, 24, C.byref(ow), C.byref(oh)) == 1, native.aji_last_error(legacy)
        assert (ow.value, oh.value) == (64, target)
        params = Create(struct_size=C.sizeof(Create), version=1, width=width, height=height, slot=1, capacity=1,
                        generation=1, cuda_context=fixture.ctx, conf=os.fsencode(ordered_conf), model_dir=b'', rife_dir=b'',
                        trtexec=b'/bin/false', trt_library=os.fsencode(spec['trt']), kernel_fatbin=os.fsencode(spec['kernel']),
                        fps_numerator=24, fps_denominator=1, wakeup=notify)
        error = C.create_string_buffer(2048)
        assert pipeline.aji_pipeline_create_v1(C.byref(params), C.byref(ordered), error, len(error)) == 0, error.value
        caps = Caps(); deadline = time.monotonic()+15
        while True:
            code = pipeline.aji_pipeline_query_v1(ordered, C.byref(caps), C.sizeof(caps))
            if code != -4: break
            assert time.monotonic() < deadline, 'Model-free initialization timed out'
            wake.wait(.01); wake.clear()
        pipeline.aji_pipeline_last_error_v1(ordered, error, len(error))
        assert code == 0, (code, error.value)
        assert (caps.width, caps.height, caps.factor, caps.stage_count) == (64, target, 1, 1)
        yy, xx = np.indices((height, width))
        rgb = np.stack([xx/(width-1), yy/(height-1), ((xx//3+yy//2)%2)*.8+.1], axis=2).astype(np.float32)
        source = fixture.surface(rgb_to_yuv444(rgb), 7, 1, 0)
        fixture.s = dict(width=64, height=target)
        expected = fixture.surface(None, 7, 101, 0); actual = fixture.surface(None, 7, 102, 0)
        for value, _ in (expected, actual):
            value.duration = source[0].duration; value.timebase_num = source[0].timebase_num; value.timebase_den = source[0].timebase_den
        old_source, old_output = frame(source[0]), frame(expected[0])
        assert native.aji_infer(legacy, C.byref(old_source), C.byref(old_output), None) == 0, native.aji_last_error(legacy)
        fixture.ck(fixture.driver.cuCtxSynchronize())
        request = Request(struct_size=C.sizeof(Request), version=1, flags=2, output_count=1, generation=1, current=C.addressof(source[0]))
        request.outputs[0] = C.addressof(actual[0]); ticket = C.c_uint64()
        descriptors = [bytes(x[0]) for x in (source, expected, actual)]
        assert pipeline.aji_pipeline_submit_v1(ordered, C.byref(request), C.byref(ticket)) == 0
        assert pipeline.aji_pipeline_drain_v1(ordered, 0) == 0
        done = Done(); assert pipeline.aji_pipeline_complete_v1(ordered, ticket, 1, C.byref(done), C.sizeof(done)) == 0
        assert done.result.state == 2 and done.result.status == 0, done.result.message
        assert done.output_count == 1 and done.output_flags[0] == 33
        before = np.asarray(fixture.download(expected)); after = np.asarray(fixture.download(actual))
        assert np.array_equal(before, after), int(np.max(np.abs(before.astype(np.int32)-after.astype(np.int32))))
        assert descriptors == [bytes(x[0]) for x in (source, expected, actual)]
        stats = Stats(); assert pipeline.aji_pipeline_stats_v1_get(ordered, C.byref(stats), C.sizeof(stats)) == 0
        assert stats.rife_predictions == stats.spatial_predictions == stats.cpu_pixel_copies == stats.failed == 0
        assert all(n == 0 for n in fixture.held.values())
        result = dict(passed=True, dimensions=[128,72,64,36], format='YUV444P16 full-range BT709', exact=True,
                      sha256=hashlib.sha256(after.tobytes()).hexdigest(), padding_preserved=True, owners_balanced=True,
                      descriptors_unchanged=True, model_or_plan_builds=0, timeline_unchanged=True,
                      scope='Standalone Spline36 vs established ABI9 resize on canonical 444; no NV12/P010 migration equivalence or FPS claim')
        (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n'); print(json.dumps(result), flush=True)
    finally:
        if ordered: pipeline.aji_pipeline_destroy_v1(ordered)
        if legacy: native.aji_destroy(C.byref(legacy))
        fixture.close()

if __name__ == '__main__': main()
