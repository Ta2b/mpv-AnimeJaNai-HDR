#!/usr/bin/env python3
"""Keep a pipeline context alive until its first-play TensorRT builds finish.

The ordered pipeline builds missing engines asynchronously through trtexec and
the builder dies with its parent: a short probe never lets a new plan finish.
This tool creates the pipeline from a probe spec, waits for readiness, then
stays alive while any trtexec child runs (and a quiet period passes), so the
next probe run finds every plan. It submits no frame.
"""
import ctypes as C, json, os, subprocess, sys, threading, time
from pathlib import Path
from pipeline_cuda_check import Fixture, Create, Caps, ptr, wakeupfn


def trtexec_running():
    try:
        return subprocess.run(['pgrep', '-x', 'trtexec'], capture_output=True, text=True).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def main():
    s = json.loads(Path(sys.argv[1]).read_text())
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 1200.0
    quiet = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
    f = Fixture(dict(width=s['width'], height=s['height']))
    lib = C.CDLL(s['library'], mode=os.RTLD_LOCAL); ctx = ptr(); wake = threading.Event()

    @wakeupfn
    def notify(_):
        wake.set()
    for name, args in {'aji_pipeline_create_v1': [ptr, ptr, ptr, C.c_size_t], 'aji_pipeline_query_v1': [ptr, ptr, C.c_size_t],
                       'aji_pipeline_last_error_v1': [ptr, ptr, C.c_size_t], 'aji_pipeline_destroy_v1': [ptr]}.items():
        getattr(lib, name).argtypes = args; getattr(lib, name).restype = None if 'destroy' in name else C.c_int
    # Lot B: the stages' configure logs (first-play engine builds included), as the
    # player's stats file sees them. Older modules lack the call.
    status = getattr(lib, 'aji_pipeline_status_text_v1', None)
    if status:
        status.argtypes = [ptr, ptr, C.c_size_t]; status.restype = C.c_int

    def show_status(last):
        if not status or not ctx:
            return last
        buf = C.create_string_buffer(16384)
        if status(ctx, buf, len(buf)) != 0:
            return last
        text = buf.value.decode('utf-8', 'replace')
        if text and text != last:
            print(f'--- status at {time.monotonic() - started:.1f}s ---\n{text.rstrip()}', flush=True)
        return text
    p = Create(struct_size=C.sizeof(Create), version=1, width=s['width'], height=s['height'], slot=1, capacity=1, flags=3, generation=1,
               cuda_context=f.ctx, conf=os.fsencode(s['conf']), model_dir=os.fsencode(s['models']), rife_dir=os.fsencode(s['rife']),
               trtexec=os.fsencode(s.get('trtexec', '/bin/false')), trt_library=os.fsencode(s['trt']), kernel_fatbin=os.fsencode(s['kernel']),
               fps_numerator=24000, fps_denominator=1001, wakeup=notify)
    error = C.create_string_buffer(2048); started = time.monotonic()
    try:
        code = lib.aji_pipeline_create_v1(C.byref(p), C.byref(ctx), error, len(error)); assert code == 0, (code, error.value)
        caps = Caps(); deadline = started + timeout; last_status = ''
        while True:
            last_status = show_status(last_status)
            code = lib.aji_pipeline_query_v1(ctx, C.byref(caps), C.sizeof(caps))
            if code != -4:
                break
            if time.monotonic() > deadline:
                print('timeout waiting for readiness'); return 2
            wake.wait(.5); wake.clear()
        lib.aji_pipeline_last_error_v1(ctx, error, len(error)); assert code == 0, (code, error.value)
        show_status(last_status)
        print(f'ready after {time.monotonic() - started:.1f}s; waiting for builders', flush=True)
        last_busy = time.monotonic(); seen = False
        while time.monotonic() < deadline:
            if trtexec_running():
                last_busy = time.monotonic(); seen = True
            elif time.monotonic() - last_busy > quiet:
                break
            time.sleep(1.0)
        print(f'builders {"seen and " if seen else "not seen; "}quiet for {quiet}s after {time.monotonic() - started:.1f}s', flush=True)
    finally:
        if ctx:
            lib.aji_pipeline_destroy_v1(ctx)
        f.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
